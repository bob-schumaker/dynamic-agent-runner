"""Command-line interface for running dynamic-agent workflow artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence, TextIO

from dynamic_agent_runner.api import run_agent_workflow
from dynamic_agent_runner.errors import DynamicAgentRunnerError
from dynamic_agent_runner.registry import ToolRegistry, create_local_workspace_registry


def main(
    argv: Sequence[str] | None = None,
    *,
    model_adapter: Any | None = None,
    tool_registry: ToolRegistry | None = None,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    """Run the CLI and return a process-style exit code."""

    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    stderr = stderr or sys.stderr
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        prompt = _resolve_prompt(args, stdin)
        registry = tool_registry or _build_registry(args)
        final_result = run_agent_workflow(
            prompt=prompt,
            runtime_manifest=args.runtime_manifest,
            agent_design=args.agent_design,
            mermaid_graph=args.mermaid_graph,
            tool_index=args.tool_index,
            tool_registry=registry,
            model_adapter=model_adapter,
            max_steps=args.max_steps,
        )
    except DynamicAgentRunnerError as exc:
        print(f"dynamic-agent-runner: error: {exc}", file=stderr)
        return 1
    except OSError as exc:
        print(f"dynamic-agent-runner: error: {exc}", file=stderr)
        return 1

    print(_format_result(final_result), file=stdout)
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""

    parser = argparse.ArgumentParser(
        prog="dynamic-agent-runner",
        description="Run a generated dynamic-agent workflow from artifacts.",
    )
    parser.add_argument(
        "--runtime-manifest",
        required=True,
        type=Path,
        help="Path to agent-runtime.yaml.",
    )
    parser.add_argument(
        "--agent-design",
        type=Path,
        help="Path to agent-design.md.",
    )
    parser.add_argument(
        "--mermaid-graph",
        "--mermaid-diagram",
        dest="mermaid_graph",
        type=Path,
        help="Path to agent-graph.mmd; defaults to the manifest reference.",
    )
    parser.add_argument(
        "--tool-index",
        type=Path,
        help="Optional path to reusable tool-index.yaml metadata.",
    )
    prompt_group = parser.add_mutually_exclusive_group()
    prompt_group.add_argument("--prompt", help="Prompt text for the workflow run.")
    prompt_group.add_argument(
        "--prompt-file",
        type=Path,
        help="Path to a UTF-8 text file containing the workflow prompt.",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        help="Maximum workflow node executions before failing.",
    )
    parser.add_argument(
        "--workspace-root",
        action="append",
        type=Path,
        default=[],
        help=(
            "Enable the read-only local_workspace registry pack for this root. "
            "May be supplied multiple times."
        ),
    )
    return parser


def _resolve_prompt(args: argparse.Namespace, stdin: TextIO) -> str:
    if args.prompt is not None:
        prompt = args.prompt
    elif args.prompt_file is not None:
        prompt = args.prompt_file.read_text(encoding="utf-8")
    else:
        prompt = stdin.read()
    if not prompt.strip():
        raise DynamicAgentRunnerError(
            "workflow prompt is required; pass --prompt, --prompt-file, or stdin"
        )
    return prompt


def _build_registry(args: argparse.Namespace) -> ToolRegistry | None:
    if not args.workspace_root:
        return None
    return create_local_workspace_registry(args.workspace_root)


def _format_result(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, default=str, sort_keys=True)


def console_main() -> None:
    """Console-script entry point."""

    raise SystemExit(main())


if __name__ == "__main__":  # pragma: no cover - exercised through console script.
    console_main()
