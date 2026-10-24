#!/usr/bin/env python3
"""Evaluate separately approved DMS-20 MLX 4-bit artifacts."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import resource
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
EVALUATION = ROOT / "specs/decision-model-support/evaluation"
CORPUS_PATH = EVALUATION / "dms14-corpus-manifest.json"
INPUTS_PATH = Path("/private/tmp/dms20-corpus/normalized-inputs.jsonl")
LABELS_PATH = Path("/private/tmp/dms20-corpus/gold-labels.jsonl")
ROWS = {
    "qwen35-08b-decision-mlx-4bit": {
        "matrix": EVALUATION
        / "dms20-qwen35-08b-decision-mlx-4bit-evaluation-matrix.json",
        "approval": EVALUATION
        / "dms20-qwen35-08b-decision-mlx-4bit-evaluation-approval.json",
        "model": Path("/private/tmp/dms20-qwen35-08b-4bit-model"),
        "output": EVALUATION / "dms20-qwen35-08b-4bit-run-2026-10-24",
        "baseline": EVALUATION
        / "dms20-mlx-run-2026-10-23/qwen35-08b-decision/predictions.jsonl",
    },
    "d1a-e2b-mlx-4bit": {
        "matrix": EVALUATION / "dms20-d1a-e2b-mlx-4bit-evaluation-matrix.json",
        "approval": EVALUATION / "dms20-d1a-e2b-mlx-4bit-evaluation-approval.json",
        "model": Path("/private/tmp/dms20-d1a-e2b-4bit-model"),
        "output": EVALUATION / "dms20-d1a-e2b-4bit-run-2026-10-24",
        "baseline": EVALUATION
        / "dms20-mlx-run-2026-10-23/d1a-e2b-8bit/predictions.jsonl",
    },
}


class Mlx4BitRunError(RuntimeError):
    """Raised when a pinned MLX 4-bit evaluation contract differs."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _verify(  # noqa: C901 - one frozen artifact binding boundary.
    row_id: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    config = ROWS[row_id]
    matrix = json.loads(config["matrix"].read_text(encoding="utf-8"))
    approval = json.loads(config["approval"].read_text(encoding="utf-8"))
    row = matrix["rows"][0]
    if len(matrix["rows"]) != 1 or row.get("optimization_id") != row_id:
        raise Mlx4BitRunError("evaluation matrix does not select this 4-bit variant")
    if _sha256(CORPUS_PATH) != matrix["corpus_manifest_sha256"]:
        raise Mlx4BitRunError(
            "DMS-20 corpus manifest differs from the evaluation matrix"
        )
    if (
        _sha256(INPUTS_PATH) != matrix["normalized_input_sha256"]
        or _sha256(LABELS_PATH) != matrix["gold_label_sha256"]
    ):
        raise Mlx4BitRunError("DMS-20 normalized inputs or labels differ")
    if approval.get("approved") is not True or approval.get("matrix_sha256") != _sha256(
        config["matrix"]
    ):
        raise Mlx4BitRunError("approval does not bind the 4-bit evaluation matrix")
    for item in matrix["harness_files"]:
        path = ROOT / item["path"]
        if not path.is_file() or _sha256(path) != item["sha256"]:
            raise Mlx4BitRunError("pinned MLX evaluation harness differs")
    if (
        not config["baseline"].is_file()
        or _sha256(config["baseline"]) != row["baseline_predictions_sha256"]
    ):
        raise Mlx4BitRunError("pinned baseline predictions are absent or changed")
    conversion_matrix = EVALUATION / row["conversion_matrix_path"]
    conversion_approval = EVALUATION / row["conversion_approval_path"]
    conversion_receipt = EVALUATION / row["conversion_receipt_path"]
    source_matrix = EVALUATION / matrix["source_optimization_matrix_path"]
    if _sha256(source_matrix) != row["source_matrix_sha256"]:
        raise Mlx4BitRunError("source MLX matrix differs")
    if (
        _sha256(conversion_matrix) != row["conversion_matrix_sha256"]
        or _sha256(conversion_approval) != row["conversion_approval_sha256"]
    ):
        raise Mlx4BitRunError("source conversion matrix or approval differs")
    if _sha256(conversion_receipt) != row["conversion_receipt_sha256"]:
        raise Mlx4BitRunError("conversion receipt differs")
    if row["conversion_output_path"] != str(config["model"]):
        raise Mlx4BitRunError("conversion output path differs")
    for item in row["artifact_files"]:
        path = config["model"] / item["path"]
        if (
            not path.is_file()
            or path.stat().st_size != item["size_bytes"]
            or _sha256(path) != item["sha256"]
        ):
            raise Mlx4BitRunError(f"generated 4-bit artifact differs: {item['path']}")
    return matrix, row, config


def _resource_preflight(row: dict[str, Any], *, before_run: bool) -> dict[str, int]:
    total = os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE")
    output = subprocess.run(
        ["memory_pressure"], capture_output=True, check=True, text=True, timeout=5
    ).stdout
    marker = "System-wide memory free percentage:"
    line = next(
        (value for value in output.splitlines() if value.startswith(marker)), None
    )
    if line is None:
        raise Mlx4BitRunError("could not read macOS memory pressure")
    percent = int(line.removeprefix(marker).strip().rstrip("%"))
    free_memory = total * percent // 100
    if free_memory < row["resource_floor"]["minimum_free_memory_bytes"]:
        raise Mlx4BitRunError("free memory is below the evaluation row floor")
    free_disk = shutil.disk_usage(Path("/private/tmp")).free
    floor = (
        "minimum_free_disk_before_run_bytes"
        if before_run
        else "minimum_free_disk_after_run_bytes"
    )
    if free_disk < row["resource_floor"][floor]:
        raise Mlx4BitRunError("free disk is below the evaluation row floor")
    return {
        "system_memory_free_percent": percent,
        "free_memory_bytes_estimate": free_memory,
        "free_disk_bytes": free_disk,
    }


def run(row_id: str) -> dict[str, Any]:  # noqa: C901 - one gated evaluation lifecycle.
    import mlx.core as mx

    matrix, row, config = _verify(row_id)
    runtime = row["runtime"]
    if (
        sys.version.split()[0] != runtime["python_version"]
        or _sha256(ROOT / runtime["lock_path"]) != runtime["lock_sha256"]
    ):
        raise Mlx4BitRunError("runtime Python version or lock differs")
    for package, version in runtime["packages"].items():
        if importlib.metadata.version(package) != version:
            raise Mlx4BitRunError(f"runtime package differs: {package}")
    if (
        platform.system() != "Darwin"
        or platform.machine() != "arm64"
        or mx.default_device().type != mx.DeviceType.gpu
    ):
        raise Mlx4BitRunError("Apple Silicon MLX GPU is required")
    resources = _resource_preflight(row, before_run=True)
    if row_id == "d1a-e2b-mlx-4bit":
        import d1a  # noqa: F401
    sys.path.insert(0, str(ROOT / "tests/manual"))
    from run_dms20_mlx_extension import _load_model
    from run_dms20_transfer import _normalized_text, ordered_inputs

    started = time.perf_counter()
    infer, tokenizer = _load_model(row, config["model"])
    cold_load_ms = (time.perf_counter() - started) * 1000
    inputs = [
        json.loads(line)
        for line in INPUTS_PATH.read_text(encoding="utf-8").splitlines()
    ]
    max_tokens = max(len(tokenizer.encode(_normalized_text(item))) for item in inputs)
    if max_tokens > matrix["protocol"]["normalized_content_token_limit"]:
        raise Mlx4BitRunError("shared normalized-content token budget exceeded")
    predictions: list[dict[str, Any]] = []
    latencies: list[float] = []
    total = len(inputs) * 2
    for order in ("canonical", "reversed"):
        for item in ordered_inputs(inputs, order):
            started_item = time.perf_counter()
            try:
                raw = infer(item)
                prediction = {
                    "id": item["id"],
                    "option_order": order,
                    "status": "ok",
                    **raw,
                    "score_semantics": "probability",
                }
            except (
                Exception
            ) as exc:  # Do not persist model exception details or input text.
                prediction = {
                    "id": item["id"],
                    "option_order": order,
                    "status": "invalid" if isinstance(exc, ValueError) else "error",
                }
            latencies.append((time.perf_counter() - started_item) * 1000)
            predictions.append(prediction)
            if len(predictions) % 40 == 0 or len(predictions) == total:
                print(
                    f"progress {len(predictions)}/{total}", file=sys.stderr, flush=True
                )
    config["output"].mkdir(parents=True, exist_ok=True)
    pred_path = config["output"] / "predictions.jsonl"
    pred_path.write_text(
        "".join(json.dumps(item, sort_keys=True) + "\n" for item in predictions)
    )
    measurement = {
        "optimization_id": row_id,
        "candidate_id": row["candidate_id"],
        "model": row["model"],
        "device": "mlx",
        "precision": "affine 4-bit weights, group size 64",
        "item_count": len(inputs),
        "prediction_count": len(predictions),
        "failures": sum(item["status"] != "ok" for item in predictions),
        "cold_load_ms": cold_load_ms,
        "mean_per_decision_latency_ms": sum(latencies) / len(latencies),
        "median_per_decision_latency_ms": sorted(latencies)[len(latencies) // 2],
        "inference_latency_ms": latencies,
        "peak_rss_bytes": int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss),
        "mlx_active_memory_bytes": int(mx.get_active_memory()),
        "mlx_peak_memory_bytes": int(mx.get_peak_memory()),
        "common_max_token_count": max_tokens,
        "resource_preflight": resources,
        "matrix_sha256": _sha256(config["matrix"]),
        "corpus_manifest_sha256": _sha256(CORPUS_PATH),
        "host_platform": platform.platform(),
    }
    (config["output"] / "measurements.json").write_text(
        json.dumps(measurement, indent=2, sort_keys=True) + "\n"
    )
    return {
        "optimization_id": row_id,
        "prediction_count": len(predictions),
        "failures": measurement["failures"],
        "mean_per_decision_latency_ms": measurement["mean_per_decision_latency_ms"],
        "predictions_path": str(pred_path),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--row", choices=sorted(ROWS), required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.row), sort_keys=True))


if __name__ == "__main__":
    main()
