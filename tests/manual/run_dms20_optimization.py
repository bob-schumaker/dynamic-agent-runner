#!/usr/bin/env python3
"""Run the separately approved Kev-4B PyTorch MPS optimization pilot."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import resource
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable

from run_dms20_transfer import (
    MatrixRunError,
    _check_resources,
    _normalized_text,
    _verify_artifacts,
    run_rows,
)


ROOT = Path(__file__).resolve().parents[2]
EVALUATION = ROOT / "specs/decision-model-support/evaluation"
MATRIX_PATH = EVALUATION / "dms20-kev-mps-pilot-matrix.json"
APPROVAL_PATH = EVALUATION / "dms20-kev-mps-pilot-approval.json"
CORPUS_PATH = EVALUATION / "dms14-corpus-manifest.json"
INPUTS_PATH = Path("/private/tmp/dms20-optimization-data/normalized-inputs.jsonl")
LABELS_PATH = Path("/private/tmp/dms20-optimization-data/gold-labels.jsonl")
MATERIAL_ROOT = Path("/private/tmp/dms20-kev-mps-materials")
OUTPUT_ROOT = EVALUATION / "dms20-kev-mps-pilot-run-2026-10-24"
CANDIDATE_ID = "kev-4b-mps-bf16"
KEV_SOURCE_REVISION = "1f04cfa28e6a708485b28a9585010b9e436b776e"
KEV_SOURCE_LOCK_SHA256 = (
    "a9922dbb89acdef78299fd2b4a8c3f7f0fa1b2bc08b55595b6926fa785a9c466"
)


class OptimizationRunError(RuntimeError):
    """Raised when a pinned Kev MPS pilot gate fails."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _verify_matrix_and_approval(
    matrix_path: Path = MATRIX_PATH,
    corpus_path: Path = CORPUS_PATH,
    approval_path: Path = APPROVAL_PATH,
) -> tuple[dict[str, Any], dict[str, Any]]:
    matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
    corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    if matrix.get("corpus_manifest_sha256") != _sha256(corpus_path):
        raise OptimizationRunError("corpus manifest digest differs")
    if matrix.get("normalized_input_sha256") != corpus.get("normalized_input_sha256"):
        raise OptimizationRunError("normalized input digest differs")
    if matrix.get("gold_label_sha256") != corpus.get("gold_label_sha256"):
        raise OptimizationRunError("gold-label digest differs")
    if corpus.get("license_review_status") != "cleared":
        raise OptimizationRunError("corpus license review has not cleared")
    for entry in matrix.get("harness_files", []):
        path = ROOT / entry["path"]
        if not path.is_file() or _sha256(path) != entry.get("sha256"):
            raise OptimizationRunError("approved pilot harness digest differs")
    rows = matrix.get("rows")
    if not isinstance(rows, list) or len(rows) != 1:
        raise OptimizationRunError("Kev MPS pilot matrix must contain exactly one row")
    row = rows[0]
    if row.get("id") != CANDIDATE_ID or row.get("disposition") != "selected":
        raise OptimizationRunError("Kev MPS pilot row is not selected")
    if matrix.get("runnable_cohort") != [CANDIDATE_ID]:
        raise OptimizationRunError("Kev MPS pilot runnable cohort differs")
    _verify_approval(matrix, row, matrix_path, corpus_path, approval_path)
    _verify_input_files(matrix)
    return matrix, row


def _verify_approval(
    matrix: dict[str, Any],
    row: dict[str, Any],
    matrix_path: Path,
    corpus_path: Path,
    approval_path: Path,
) -> None:
    approval = json.loads(approval_path.read_text(encoding="utf-8"))
    dispositions = {row["id"]: row["disposition"]}
    if (
        approval.get("approved") is not True
        or approval.get("matrix_sha256") != _sha256(matrix_path)
        or approval.get("corpus_manifest_sha256") != _sha256(corpus_path)
        or approval.get("approval_scope") != matrix.get("approval_scope")
        or approval.get("dispositions") != dispositions
        or approval.get("runnable_cohort") != [CANDIDATE_ID]
    ):
        raise OptimizationRunError("pilot approval does not bind the frozen matrix")


def _verify_input_files(matrix: dict[str, Any]) -> None:
    for entry in matrix.get("input_files", {}).values():
        path = Path(entry["path"])
        if not path.is_file() or _sha256(path) != entry.get("sha256"):
            raise OptimizationRunError("approved pilot input or label file differs")


def _verify_runtime(row: dict[str, Any], source: Path) -> None:
    runtime = row["runtime"]
    lock = ROOT / runtime["lock_path"]
    if _sha256(lock) != runtime["lock_sha256"]:
        raise OptimizationRunError("Kev MPS runtime lock differs")
    if sys.version.split()[0] != runtime["python_version"]:
        raise OptimizationRunError("Kev MPS Python version differs")
    for package, expected in runtime["packages"].items():
        if importlib.metadata.version(package) != expected:
            raise OptimizationRunError(f"runtime package differs: {package}")
    commit = subprocess.run(
        ["git", "-C", str(source), "rev-parse", "HEAD"],
        capture_output=True,
        check=True,
        text=True,
        timeout=5,
    ).stdout.strip()
    if (
        commit != KEV_SOURCE_REVISION
        or _sha256(source / "uv.lock") != KEV_SOURCE_LOCK_SHA256
    ):
        raise OptimizationRunError("pinned Kev source checkout differs")


def _load_kev_mps(
    row: dict[str, Any], source: Path
) -> tuple[
    Callable[[dict[str, Any]], dict[str, Any]], Callable[[dict[str, Any]], int], Any
]:
    sys.path.insert(0, str(source))
    import torch
    from kev.api import Choice, SystemOneRequest, to_record
    from kev.checkpoint import Checkpoint, LoadOptions
    from kev.model import SERVE_MAX_BRANCH, SERVE_MAX_STATE

    if not torch.backends.mps.is_available():
        raise OptimizationRunError("PyTorch MPS is unavailable")
    checkpoint = Checkpoint(f"{row['model']['id']}@{row['model']['revision']}")
    if (
        checkpoint.meta.base != row["base_model"]["id"]
        or checkpoint.meta.base_revision != row["base_model"]["revision"]
    ):
        raise OptimizationRunError("Kev adapter base identity differs from the matrix")
    tokenizer, model = checkpoint.load(
        "mps",
        LoadOptions(
            dtype=torch.bfloat16,
            merge=True,
            attn="sdpa",
            backend="torch",
        ),
    )
    model.eval()

    def infer(item: dict[str, Any]) -> dict[str, Any]:
        question = item["question"]
        qid = question["id"]
        request = SystemOneRequest(
            state=item["state"],
            model="kev-4b",
            questions={
                qid: Choice(
                    type="choice",
                    instructions=question["text"],
                    criteria={
                        option["id"]: option["label"] for option in question["options"]
                    },
                )
            },
        )
        record, metadata = to_record(request)
        encoded = model.encode(
            tokenizer, record, max_state=SERVE_MAX_STATE, max_branch=SERVE_MAX_BRANCH
        )
        with torch.inference_mode():
            probs = model.probs(encoded)[0].tolist()
        torch.mps.synchronize()
        scores = {
            key: float(value)
            for key, value in zip(metadata[0]["keys"], probs, strict=True)
        }
        return {
            "status": "ok",
            "choice": max(scores, key=scores.get),
            "score_semantics": "probability",
            "scores": scores,
        }

    return infer, lambda item: len(tokenizer.encode(_normalized_text(item))), model


def _smoke_inputs(
    inputs: list[dict[str, Any]], baseline: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    by_key = {(row["id"], row["option_order"]): row for row in baseline}
    chosen: dict[str, dict[str, Any]] = {}
    for item in inputs:
        chosen.setdefault(item["category"], item)
    if len(chosen) != 7:
        raise OptimizationRunError("pilot smoke set does not cover seven categories")
    smoke_baseline: list[dict[str, Any]] = []
    for order in ("canonical", "reversed"):
        for item in chosen.values():
            expected = by_key.get((item["id"], order))
            if expected is None or expected.get("status") != "ok":
                raise OptimizationRunError("baseline lacks a valid smoke prediction")
            smoke_baseline.append(expected)
    return list(chosen.values()), smoke_baseline


def _compare_smoke(
    candidate: list[dict[str, Any]], baseline: list[dict[str, Any]]
) -> dict[str, Any]:
    if len(candidate) != len(baseline) or not candidate:
        raise OptimizationRunError("pilot smoke outputs are incomplete")
    max_probability_delta = 0.0
    for actual, expected in zip(candidate, baseline, strict=True):
        if (
            actual.get("id") != expected.get("id")
            or actual.get("option_order") != expected.get("option_order")
            or actual.get("status") != "ok"
            or actual.get("choice") != expected.get("choice")
        ):
            raise OptimizationRunError("Kev MPS pilot failed smoke choice parity")
        actual_scores, expected_scores = actual.get("scores"), expected.get("scores")
        if not isinstance(actual_scores, dict) or not isinstance(expected_scores, dict):
            raise OptimizationRunError("pilot smoke probability scores are absent")
        if set(actual_scores) != set(expected_scores):
            raise OptimizationRunError("pilot smoke option IDs differ from baseline")
        max_probability_delta = max(
            max_probability_delta,
            *(abs(actual_scores[key] - expected_scores[key]) for key in actual_scores),
        )
    return {
        "item_count": len(candidate),
        "choice_matches": len(candidate),
        "choice_parity": True,
        "max_probability_delta": max_probability_delta,
    }


def stage_candidate(
    matrix_path: Path,
    corpus_path: Path,
    approval_path: Path,
    material_root: Path,
) -> dict[str, Any]:
    from huggingface_hub import snapshot_download

    matrix, row = _verify_matrix_and_approval(matrix_path, corpus_path, approval_path)
    material_root.mkdir(parents=True, exist_ok=True)
    before = _check_resources(row, material_root, before_stage=True)
    repos = sorted(
        {(item["repository"], item["revision"]) for item in row["artifact_files"]}
    )
    for repo, revision in repos:
        snapshot_download(
            repo,
            revision=revision,
            cache_dir=str(material_root),
            allow_patterns=matrix["artifact_download_allow_patterns"],
            ignore_patterns=matrix["artifact_download_ignore_patterns"],
        )
    after = _check_resources(row, material_root, before_stage=False)
    _verify_artifacts(row, material_root)
    receipt = {
        "candidate_id": CANDIDATE_ID,
        "matrix_sha256": _sha256(matrix_path),
        "repositories": repos,
        "verified": True,
        "resource_preflight": {"before_stage": before, "after_stage": after},
    }
    destination = OUTPUT_ROOT / CANDIDATE_ID
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "stage-receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return receipt


def run_candidate(
    matrix_path: Path,
    corpus_path: Path,
    approval_path: Path,
    material_root: Path,
    source: Path,
    inputs_path: Path,
    labels_path: Path,
    *,
    smoke_only: bool = False,
) -> dict[str, Any]:
    matrix, row = _verify_matrix_and_approval(matrix_path, corpus_path, approval_path)
    _verify_runtime(row, source)
    resources = _check_resources(row, material_root, before_stage=False)
    _verify_artifacts(row, material_root)
    baseline = matrix["baseline"]
    baseline_path = ROOT / baseline["predictions_path"]
    if _sha256(baseline_path) != baseline["predictions_sha256"]:
        raise OptimizationRunError(
            "baseline predictions differ from the approved matrix"
        )
    if (
        _sha256(inputs_path) != matrix["normalized_input_sha256"]
        or _sha256(labels_path) != matrix["gold_label_sha256"]
    ):
        raise OptimizationRunError("normalized input or gold labels differ")

    os.environ.update(
        HF_HOME=str(material_root),
        HF_HUB_CACHE=str(material_root),
        HF_HUB_OFFLINE="1",
        TRANSFORMERS_OFFLINE="1",
    )
    started = time.perf_counter()
    infer, count_tokens, model = _load_kev_mps(row, source)
    cold_load_ms = (time.perf_counter() - started) * 1000
    input_rows = [
        json.loads(line)
        for line in inputs_path.read_text(encoding="utf-8").splitlines()
    ]
    max_tokens = max(count_tokens(item) for item in input_rows)
    if max_tokens > matrix["protocol"]["normalized_content_token_limit"]:
        raise OptimizationRunError("shared normalized-content token limit exceeded")
    baseline_rows = [
        json.loads(line)
        for line in baseline_path.read_text(encoding="utf-8").splitlines()
    ]
    smoke_inputs, smoke_baseline = _smoke_inputs(input_rows, baseline_rows)
    smoke_predictions = run_rows(smoke_inputs, infer)
    output_dir = OUTPUT_ROOT / CANDIDATE_ID
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "smoke-predictions.jsonl").write_text(
        "".join(json.dumps(item, sort_keys=True) + "\n" for item in smoke_predictions),
        encoding="utf-8",
    )
    smoke = _compare_smoke(smoke_predictions, smoke_baseline)
    if smoke_only:
        return {
            "candidate_id": CANDIDATE_ID,
            "smoke": smoke,
            "cold_load_ms": cold_load_ms,
        }

    inference_latency_ms: list[float] = []

    def timed_infer(item: dict[str, Any]) -> dict[str, Any]:
        started_item = time.perf_counter()
        try:
            return infer(item)
        finally:
            inference_latency_ms.append((time.perf_counter() - started_item) * 1000)

    predictions = run_rows(input_rows, timed_infer)
    predictions_path = output_dir / "predictions.jsonl"
    predictions_path.write_text(
        "".join(json.dumps(item, sort_keys=True) + "\n" for item in predictions),
        encoding="utf-8",
    )
    import torch

    status_counts: dict[str, int] = {}
    for item in predictions:
        status_counts[item["status"]] = status_counts.get(item["status"], 0) + 1
    measurements = {
        "candidate_id": CANDIDATE_ID,
        "device": "mps",
        "backend": "torch",
        "precision": "bfloat16",
        "attention": "sdpa",
        "prediction_count": len(predictions),
        "status_counts": status_counts,
        "failures": len(predictions) - status_counts.get("ok", 0),
        "smoke_comparison": smoke,
        "cold_load_ms": cold_load_ms,
        "mean_inference_latency_ms": sum(inference_latency_ms)
        / len(inference_latency_ms),
        "inference_latency_ms": inference_latency_ms,
        "peak_rss_bytes": int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss),
        "mps_current_allocated_bytes": int(torch.mps.current_allocated_memory()),
        "mps_driver_allocated_bytes": int(torch.mps.driver_allocated_memory()),
        "common_max_token_count": max_tokens,
        "resource_preflight": resources,
        "matrix_sha256": _sha256(matrix_path),
        "corpus_manifest_sha256": _sha256(corpus_path),
        "host_platform": platform.platform(),
    }
    measurements_path = output_dir / "measurements.json"
    measurements_path.write_text(
        json.dumps(measurements, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    del model
    return {
        "candidate_id": CANDIDATE_ID,
        "prediction_count": len(predictions),
        "status_counts": status_counts,
        "mean_inference_latency_ms": measurements["mean_inference_latency_ms"],
        "smoke_comparison": smoke,
        "predictions_path": str(predictions_path),
        "measurements_path": str(measurements_path),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage-only", action="store_true")
    parser.add_argument("--smoke-only", action="store_true")
    parser.add_argument("--matrix", type=Path, default=MATRIX_PATH)
    parser.add_argument("--approval", type=Path, default=APPROVAL_PATH)
    parser.add_argument("--corpus-manifest", type=Path, default=CORPUS_PATH)
    parser.add_argument("--inputs", type=Path, default=INPUTS_PATH)
    parser.add_argument("--labels", type=Path, default=LABELS_PATH)
    parser.add_argument("--material-root", type=Path, default=MATERIAL_ROOT)
    parser.add_argument("--source", type=Path, required=True)
    arguments = parser.parse_args()
    try:
        if arguments.stage_only:
            result = stage_candidate(
                arguments.matrix,
                arguments.corpus_manifest,
                arguments.approval,
                arguments.material_root,
            )
        else:
            result = run_candidate(
                arguments.matrix,
                arguments.corpus_manifest,
                arguments.approval,
                arguments.material_root,
                arguments.source,
                arguments.inputs,
                arguments.labels,
                smoke_only=arguments.smoke_only,
            )
    except (
        MatrixRunError,
        OptimizationRunError,
        OSError,
        ValueError,
        subprocess.SubprocessError,
    ) as exc:
        parser.error(str(exc))
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
