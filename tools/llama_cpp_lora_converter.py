#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = [
#   "safetensors>=0.5.3,<0.7",
#   "torch==2.11.0",
#   "transformers==4.57.6",
# ]
# ///
"""Run the reviewed llama.cpp LoRA converter in an isolated uv environment."""

from __future__ import annotations

import argparse
import runpy
import shutil
import sys
from pathlib import Path


def main() -> None:
    """Stage declared inputs and execute llama.cpp's pinned converter."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--converter-root", type=Path, required=True)
    parser.add_argument("--lora-model", type=Path, required=True)
    parser.add_argument("--lora-config", type=Path, required=True)
    parser.add_argument("--base-config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    converter = args.converter_root / "convert_lora_to_gguf.py"
    if not converter.is_file() or not (args.converter_root / "gguf-py").is_dir():
        raise SystemExit("reviewed converter is unavailable")
    workspace = args.output.parent / ".converter-input"
    shutil.rmtree(workspace, ignore_errors=True)
    lora_root = workspace / "lora"
    base_root = workspace / "base"
    lora_root.mkdir(parents=True)
    base_root.mkdir()
    shutil.copyfile(args.lora_model, lora_root / "adapter_model.safetensors")
    shutil.copyfile(args.lora_config, lora_root / "adapter_config.json")
    shutil.copyfile(args.base_config, base_root / "config.json")
    sys.path.insert(0, str(args.converter_root))
    sys.path.insert(0, str(args.converter_root / "gguf-py"))
    sys.argv = [
        str(converter),
        "--outfile",
        str(args.output),
        "--outtype",
        "f16",
        "--base",
        str(base_root),
        str(lora_root),
    ]
    try:
        runpy.run_path(str(converter), run_name="__main__")
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


if __name__ == "__main__":
    main()
