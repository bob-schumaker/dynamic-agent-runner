"""DAR-owned Graphify semantic extraction tool primitives."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
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

    def __post_init__(self) -> None:
        if self.concurrency < 1:
            raise ValueError("concurrency must be at least 1")
        if self.max_retries < 0:
            raise ValueError("max_retries cannot be negative")


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
