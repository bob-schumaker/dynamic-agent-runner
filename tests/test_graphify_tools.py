from __future__ import annotations

from pathlib import Path

import pytest

from dynamic_agent_runner.tools.graphify import (
    GraphifyCorpusManifest,
    GraphifyManifestError,
    GraphifySemanticExtractionPolicy,
    GraphifySemanticExtractionResult,
    GraphifySemanticWorker,
    create_graphify_semantic_extractor_tool,
    plan_graphify_chunks,
    validate_graphify_corpus_manifest,
)
from dynamic_agent_runner.tools.graphify_cli import build_graphify_parser


def test_graphify_public_contract_is_constructible(tmp_path: Path) -> None:
    policy = GraphifySemanticExtractionPolicy(output_dir=tmp_path)

    assert policy.concurrency == 3
    assert policy.output_dir == tmp_path
    assert GraphifySemanticExtractionResult is not None
    assert GraphifySemanticWorker is not None


def test_graphify_factory_returns_explicit_registered_tool() -> None:
    tool = create_graphify_semantic_extractor_tool(worker=lambda _chunk: {})

    assert tool.id == "graphify_semantic_extract"
    assert tool.definition.exposure.value == "direct"


def test_graphify_factory_requires_worker() -> None:
    with pytest.raises(TypeError):
        create_graphify_semantic_extractor_tool()


def test_graphify_console_parser_accepts_cross_repository_arguments() -> None:
    args = build_graphify_parser().parse_args(
        [
            "--repo-root",
            "/repo",
            "--corpus-manifest",
            "/repo/manifest.json",
            "--output-dir",
            "/tmp/candidate",
            "--concurrency",
            "4",
            "--required-glob",
            "specs/**/*.md",
            "--model",
            "foundation",
        ]
    )

    assert args.repo_root == Path("/repo")
    assert args.corpus_manifest == Path("/repo/manifest.json")
    assert args.output_dir == Path("/tmp/candidate")
    assert args.concurrency == 4
    assert args.required_glob == ["specs/**/*.md"]
    assert args.model == "foundation"


def make_corpus_file(root: Path, relative: str, content: str = "# note") -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def test_manifest_validation_accepts_relative_allowlisted_documents(
    tmp_path: Path,
) -> None:
    make_corpus_file(tmp_path, "specs/one.md")
    manifest = GraphifyCorpusManifest.from_mapping(
        {"repo_root": str(tmp_path), "files": [{"path": "specs/one.md"}]}
    )

    validated = validate_graphify_corpus_manifest(
        manifest,
        GraphifySemanticExtractionPolicy(output_dir=tmp_path / "candidate"),
    )

    assert validated.files[0].path == "specs/one.md"
    assert len(validated.files[0].sha256) == 64


@pytest.mark.parametrize(
    "relative",
    ["/etc/passwd", "../outside.md", "src/main.py", "graphify-out/graph.json"],
)
def test_manifest_validation_rejects_unsafe_sources(
    tmp_path: Path, relative: str
) -> None:
    if not relative.startswith(("/", "../")):
        make_corpus_file(tmp_path, relative)
    manifest = GraphifyCorpusManifest.from_mapping(
        {"repo_root": str(tmp_path), "files": [{"path": relative}]}
    )

    with pytest.raises(GraphifyManifestError):
        validate_graphify_corpus_manifest(
            manifest,
            GraphifySemanticExtractionPolicy(output_dir=tmp_path / "candidate"),
        )


def test_manifest_validation_rejects_symlink_escape(tmp_path: Path) -> None:
    outside = tmp_path.parent / "graphify-outside.md"
    outside.write_text("outside", encoding="utf-8")
    link = tmp_path / "specs" / "link.md"
    link.parent.mkdir()
    link.symlink_to(outside)
    manifest = GraphifyCorpusManifest.from_mapping(
        {"repo_root": str(tmp_path), "files": [{"path": "specs/link.md"}]}
    )

    with pytest.raises(GraphifyManifestError):
        validate_graphify_corpus_manifest(
            manifest,
            GraphifySemanticExtractionPolicy(output_dir=tmp_path / "candidate"),
        )


def test_manifest_validation_rejects_accepted_graphify_output(tmp_path: Path) -> None:
    make_corpus_file(tmp_path, "specs/one.md")

    with pytest.raises(GraphifyManifestError):
        validate_graphify_corpus_manifest(
            GraphifyCorpusManifest.from_mapping(
                {"repo_root": str(tmp_path), "files": [{"path": "specs/one.md"}]}
            ),
            GraphifySemanticExtractionPolicy(output_dir=tmp_path / "graphify-out"),
        )


def test_manifest_required_glob_and_chunk_plan_are_deterministic(
    tmp_path: Path,
) -> None:
    for name in ("specs/b.md", "specs/a.md", "docs/c.md"):
        make_corpus_file(tmp_path, name)
    manifest = GraphifyCorpusManifest.from_mapping(
        {
            "repo_root": str(tmp_path),
            "files": [{"path": "specs/b.md"}, {"path": "specs/a.md"}],
        }
    )
    policy = GraphifySemanticExtractionPolicy(
        output_dir=tmp_path / "candidate", required_globs=("specs/*.md",)
    )
    validated = validate_graphify_corpus_manifest(manifest, policy)

    chunks = plan_graphify_chunks(validated, chunk_size=1)

    assert [chunk.files[0].path for chunk in chunks] == ["specs/a.md", "specs/b.md"]
    assert [chunk.chunk_id for chunk in chunks] == ["chunk-0001", "chunk-0002"]
