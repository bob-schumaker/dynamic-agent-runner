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
from dynamic_agent_runner.workflow_host.external_adapter_registry import (
    ExternalAdapterRegistry,
)


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
    raw_argv = list(argv) if argv is not None else sys.argv[1:]
    if raw_argv and raw_argv[0] == "adapter":
        return _adapter_main(raw_argv[1:], stdout=stdout, stderr=stderr)
    parser = build_parser()
    args = parser.parse_args(raw_argv)

    try:
        prompt = _resolve_prompt(args, stdin)
        registry = tool_registry or _build_registry(args)
        final_result = run_agent_workflow(
            prompt=prompt,
            package_directory=str(args.package),
            runtime_overrides=args.runtime_overrides,
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
        description="Run a generated dynamic-agent workflow from a package.",
    )
    parser.add_argument(
        "--package",
        required=True,
        type=Path,
        help=(
            "Path to a canonical agent package directory containing "
            "agent-runtime.yaml, agent-design.md, and agent-graph.mmd."
        ),
    )
    parser.add_argument(
        "--runtime-overrides",
        type=Path,
        help="Optional path to runtime prompt and skill overrides YAML.",
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


def _adapter_main(argv: Sequence[str], *, stdout: TextIO, stderr: TextIO) -> int:
    normalized_argv = list(argv)
    state_root: str | None = None
    if "--state-root" in normalized_argv:
        index = normalized_argv.index("--state-root")
        if index + 1 >= len(normalized_argv):
            print(
                "dynamic-agent-runner: error: --state-root requires a value",
                file=stderr,
            )
            return 1
        state_root = normalized_argv[index + 1]
        del normalized_argv[index : index + 2]
    parser = argparse.ArgumentParser(prog="dynamic-agent-runner adapter")
    commands = parser.add_subparsers(dest="adapter_command", required=True)
    install = commands.add_parser("install")
    install.add_argument("approved_local_plugin", type=Path)
    remove = commands.add_parser("remove")
    remove.add_argument("adapter_id")
    commands.add_parser("list")
    try:
        args = parser.parse_args(normalized_argv)
        if state_root is None:
            raise ValueError("--state-root is required")
        registry = ExternalAdapterRegistry(Path(state_root))
        if args.adapter_command == "install":
            receipt = registry.install(args.approved_local_plugin)
            print(json.dumps(receipt.to_mapping(), sort_keys=True), file=stdout)
            return 0
        if args.adapter_command == "remove":
            registry.remove(args.adapter_id)
            print(json.dumps({"removed": args.adapter_id}, sort_keys=True), file=stdout)
            return 0
        print(
            json.dumps(
                {"adapters": [receipt.to_mapping() for receipt in registry.list()]},
                sort_keys=True,
            ),
            file=stdout,
        )
        return 0
    except (DynamicAgentRunnerError, OSError, ValueError) as exc:
        print(f"dynamic-agent-runner: error: {exc}", file=stderr)
        return 1


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
