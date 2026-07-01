"""Console parser for the DAR Graphify extraction workflow."""

from __future__ import annotations

import argparse
from pathlib import Path


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


def console_main() -> None:
    """Console entry point for the Graphify extraction workflow."""

    build_graphify_parser().parse_args()


if __name__ == "__main__":  # pragma: no cover - exercised through the script.
    console_main()
