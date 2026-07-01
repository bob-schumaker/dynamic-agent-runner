"""Console parser for the DAR Graphify extraction workflow."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Mapping, Sequence
from io import TextIOBase
from pathlib import Path
from typing import Any

from dynamic_agent_runner.errors import DynamicAgentRunnerError
from dynamic_agent_runner.openai_client import (
    AsyncOpenAIClientAdapter,
    OpenAIMessage,
    OpenAIModelRequest,
    create_default_async_openai_provider,
)
from dynamic_agent_runner.tools.graphify import (
    GraphifySemanticWorker,
    extract_graphify_semantic_artifacts,
)


def build_graphify_parser() -> argparse.ArgumentParser:
    """Build the cross-repository Graphify extraction parser."""

    parser = argparse.ArgumentParser(
        prog="dynamic-agent-runner-graphify-extract",
        description="Run DAR-backed bounded Graphify semantic extraction.",
    )
    parser.add_argument("--repo-root", required=True, type=Path)
    parser.add_argument("--corpus-manifest", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--concurrency", type=int, default=3)
    parser.add_argument("--required-glob", action="append", default=[])
    parser.add_argument("--model")
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    worker: GraphifySemanticWorker | Callable[..., Any] | None = None,
    adapter: AsyncOpenAIClientAdapter | None = None,
    stdout: TextIOBase | None = None,
    stderr: TextIOBase | None = None,
) -> int:
    """Run the cross-repository Graphify extraction command."""

    stdout = stdout or sys.stdout
    stderr = stderr or sys.stderr
    args = build_graphify_parser().parse_args(argv)
    try:
        manifest = json.loads(args.corpus_manifest.read_text(encoding="utf-8"))
        selected_worker = worker or _adapter_worker(adapter, args.model)
        result = extract_graphify_semantic_artifacts(
            manifest,
            repo_root=args.repo_root,
            output_dir=args.output_dir,
            worker=selected_worker,
            concurrency=args.concurrency,
            required_globs=args.required_glob,
            model=args.model,
        )
    except (OSError, ValueError, DynamicAgentRunnerError) as exc:
        print(f"dynamic-agent-runner-graphify-extract: error: {exc}", file=stderr)
        return 1
    print(
        json.dumps(
            {
                "output_dir": str(result.output_dir),
                "chunks": result.audit.get("chunks", []),
            },
            sort_keys=True,
        ),
        file=stdout,
    )
    return 0


def _adapter_worker(
    adapter: AsyncOpenAIClientAdapter | None,
    model: str | None,
) -> GraphifySemanticWorker:
    resolved_adapter = adapter or AsyncOpenAIClientAdapter(
        provider=create_default_async_openai_provider()
    )

    async def worker(request: Mapping[str, Any]) -> str:
        selected_model = model or await resolved_adapter.default_model()
        response = await resolved_adapter.create_response(
            OpenAIModelRequest(
                model=selected_model,
                messages=(
                    OpenAIMessage(
                        role="system", content=str(request["instructions"])
                    ).to_mapping(),
                    OpenAIMessage(
                        role="user",
                        content=json.dumps(
                            {
                                "chunk_id": request["chunk_id"],
                                "documents": request["documents"],
                            },
                            ensure_ascii=False,
                        ),
                    ).to_mapping(),
                ),
            )
        )
        if response.content is None:
            raise DynamicAgentRunnerError("Graphify model returned no semantic JSON")
        return response.content

    return worker


def console_main() -> None:
    """Console entry point for the Graphify extraction workflow."""

    raise SystemExit(main())


if __name__ == "__main__":  # pragma: no cover - exercised through the script.
    console_main()
