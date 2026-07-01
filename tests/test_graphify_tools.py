from __future__ import annotations

from pathlib import Path

import pytest

from dynamic_agent_runner.tools.graphify import (
    GraphifySemanticExtractionPolicy,
    GraphifySemanticExtractionResult,
    GraphifySemanticWorker,
    create_graphify_semantic_extractor_tool,
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
