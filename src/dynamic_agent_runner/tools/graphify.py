"""DAR-owned Graphify semantic extraction tool primitives."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
import fnmatch
import hashlib
from pathlib import Path
from typing import Any, Protocol, TypeAlias

from dynamic_agent_runner.models import ToolDefinition, ToolExposure, ToolOriginKind
from dynamic_agent_runner.registry import RegisteredTool
from dynamic_agent_runner.models import ToolSource, ToolSourceKind


@dataclass(frozen=True)
class GraphifySemanticExtractionPolicy:
    """Policy values shared by the API and console wrapper."""

    output_dir: Path
    repo_root: Path | None = None
    concurrency: int = 3
    required_globs: tuple[str, ...] = ()
    model: str | None = None
    max_retries: int = 1
    chunk_size: int = 8

    def __post_init__(self) -> None:
        if self.concurrency < 1:
            raise ValueError("concurrency must be at least 1")
        if self.max_retries < 0:
            raise ValueError("max_retries cannot be negative")
        if self.chunk_size < 1:
            raise ValueError("chunk_size must be at least 1")


class GraphifyManifestError(ValueError):
    """Raised when a Graphify corpus manifest is unsafe or incomplete."""


@dataclass(frozen=True)
class GraphifyCorpusFile:
    """One relative corpus file admitted for semantic extraction."""

    path: str
    sha256: str | None = None


@dataclass(frozen=True)
class GraphifyCorpusManifest:
    """Caller-supplied corpus evidence derived from Graphify detection."""

    repo_root: Path
    files: tuple[GraphifyCorpusFile, ...]

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "GraphifyCorpusManifest":
        raw_files = value.get("files")
        if not isinstance(raw_files, Sequence) or isinstance(raw_files, (str, bytes)):
            raise GraphifyManifestError("corpus manifest requires a files sequence")
        files: list[GraphifyCorpusFile] = []
        for raw_file in raw_files:
            if isinstance(raw_file, str):
                files.append(GraphifyCorpusFile(path=raw_file))
            elif isinstance(raw_file, Mapping) and raw_file.get("path") is not None:
                files.append(
                    GraphifyCorpusFile(
                        path=str(raw_file["path"]),
                        sha256=(
                            str(raw_file["sha256"])
                            if raw_file.get("sha256") is not None
                            else None
                        ),
                    )
                )
            else:
                raise GraphifyManifestError("corpus manifest file entries need path")
        try:
            repo_root = Path(value["repo_root"]).resolve()
        except (KeyError, TypeError, ValueError) as exc:
            raise GraphifyManifestError("corpus manifest requires repo_root") from exc
        return cls(repo_root=repo_root, files=tuple(files))


@dataclass(frozen=True)
class GraphifyChunk:
    """Deterministic unit of work passed to one semantic worker."""

    chunk_id: str
    files: tuple[GraphifyCorpusFile, ...]


@dataclass(frozen=True)
class GraphifySemanticExtractionResult:
    """Normalized result returned after a candidate extraction run."""

    output_dir: Path
    chunks: tuple[Mapping[str, Any], ...] = ()
    audit: Mapping[str, Any] = field(default_factory=dict)


class GraphifySemanticWorker(Protocol):
    """Injected worker boundary for one semantic extraction chunk."""

    def __call__(
        self, chunk: Mapping[str, Any]
    ) -> Mapping[str, Any] | Awaitable[Mapping[str, Any]]: ...


WorkerLike: TypeAlias = GraphifySemanticWorker | Callable[..., Any]


_DOCUMENT_SUFFIXES = {".md", ".markdown", ".rst", ".txt", ".yaml", ".yml", ".json"}
_REJECTED_SUFFIXES = {
    ".c",
    ".cc",
    ".cpp",
    ".go",
    ".java",
    ".js",
    ".jsx",
    ".py",
    ".rb",
    ".rs",
    ".sh",
    ".sql",
    ".swift",
    ".ts",
    ".tsx",
}


def validate_graphify_corpus_manifest(
    manifest: GraphifyCorpusManifest,
    policy: GraphifySemanticExtractionPolicy,
) -> GraphifyCorpusManifest:
    """Validate paths, source hashes, corpus scope, and output safety."""

    if (
        policy.repo_root is not None
        and manifest.repo_root != policy.repo_root.resolve()
    ):
        raise GraphifyManifestError(
            "manifest repo_root does not match policy repo_root"
        )
    output_dir = policy.output_dir.resolve()
    accepted_output = manifest.repo_root / "graphify-out"
    if output_dir == accepted_output or _is_relative_to(output_dir, accepted_output):
        raise GraphifyManifestError("output_dir cannot be accepted graphify-out")
    validated: list[GraphifyCorpusFile] = []
    seen: set[str] = set()
    for entry in manifest.files:
        item = _validate_manifest_entry(manifest.repo_root, entry)
        if item.path in seen:
            raise GraphifyManifestError(f"duplicate source path: {item.path!r}")
        seen.add(item.path)
        validated.append(item)
    if not validated:
        raise GraphifyManifestError("corpus manifest contains no files")
    for pattern in policy.required_globs:
        if not any(fnmatch.fnmatch(item.path, pattern) for item in validated):
            raise GraphifyManifestError(
                f"required corpus glob has no coverage: {pattern!r}"
            )
    return GraphifyCorpusManifest(
        repo_root=manifest.repo_root,
        files=tuple(sorted(validated, key=lambda item: item.path)),
    )


def _validate_manifest_entry(
    repo_root: Path,
    entry: GraphifyCorpusFile,
) -> GraphifyCorpusFile:
    relative = Path(entry.path)
    if relative.is_absolute() or ".." in relative.parts:
        raise GraphifyManifestError(f"source path is not relative: {entry.path!r}")
    normalized = relative.as_posix()
    if normalized == "graphify-out" or normalized.startswith("graphify-out/"):
        raise GraphifyManifestError("generated graph output is not admissible")
    path = (repo_root / relative).resolve()
    if not _is_relative_to(path, repo_root):
        raise GraphifyManifestError(f"source escapes repo_root: {entry.path!r}")
    if not path.is_file():
        raise GraphifyManifestError(f"source file does not exist: {entry.path!r}")
    suffix = path.suffix.lower()
    if suffix in _REJECTED_SUFFIXES or suffix not in _DOCUMENT_SUFFIXES:
        raise GraphifyManifestError(f"source file is not a document: {entry.path!r}")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if entry.sha256 is not None and entry.sha256 != digest:
        raise GraphifyManifestError(f"source hash mismatch: {entry.path!r}")
    return GraphifyCorpusFile(path=normalized, sha256=digest)


def plan_graphify_chunks(
    manifest: GraphifyCorpusManifest,
    *,
    chunk_size: int = 8,
) -> tuple[GraphifyChunk, ...]:
    """Split an admitted manifest into stable, deterministic chunks."""

    if chunk_size < 1:
        raise ValueError("chunk_size must be at least 1")
    ordered = tuple(sorted(manifest.files, key=lambda item: item.path))
    return tuple(
        GraphifyChunk(
            chunk_id=f"chunk-{offset // chunk_size + 1:04d}",
            files=ordered[offset : offset + chunk_size],
        )
        for offset in range(0, len(ordered), chunk_size)
    )


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def create_graphify_semantic_extractor_tool(*, worker: WorkerLike) -> RegisteredTool:
    """Create the explicitly registered Graphify extraction tool."""

    async def _handler(args: Mapping[str, Any]) -> Mapping[str, Any]:
        result = worker(args)
        if hasattr(result, "__await__"):
            result = await result
        return dict(result)

    definition = ToolDefinition.from_mapping(
        {
            "id": "graphify_semantic_extract",
            "label": "Graphify semantic extract",
            "tool_type": "graphify_semantic_extract",
            "exposure": ToolExposure.DIRECT.value,
            "source": {
                "kind": ToolSourceKind.BUILT_IN.value,
                "origin": ToolOriginKind.BUILT_IN.value,
                "source_id": "graphify-semantic-extractor-tool",
            },
            "parameters": {
                "type": "object",
                "properties": {},
            },
        }
    )
    # ``ToolDefinition.from_mapping`` intentionally preserves only the
    # repository's typed metadata fields; attach explicit provenance for this
    # package-owned tool.
    if definition.source is None:
        from dataclasses import replace

        definition = replace(
            definition,
            source=ToolSource(
                kind=ToolSourceKind.BUILT_IN,
                origin=ToolOriginKind.BUILT_IN,
                source_id="graphify-semantic-extractor-tool",
            ),
        )
    return RegisteredTool(definition, _handler)
