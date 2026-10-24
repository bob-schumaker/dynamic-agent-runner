#!/usr/bin/env python3
"""Run separately approved Lev and Strands BF16 MPS DMS-20 variants."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import platform
import resource
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from run_dms20_transfer import _normalized_text, _sha256, run_rows

ROOT = Path(__file__).resolve().parents[2]
EVALUATION = ROOT / "specs/decision-model-support/evaluation"
CORPUS_PATH = EVALUATION / "dms14-corpus-manifest.json"
INPUTS_PATH = Path("/private/tmp/dms20-corpus/normalized-inputs.jsonl")
LABELS_PATH = Path("/private/tmp/dms20-corpus/gold-labels.jsonl")
RUNTIME_LOCK = EVALUATION / "dms20-runtimes/qwen-mps.lock"
RESOURCE_ROOT = Path("/private/tmp")
ROWS = {
    "lev-mps-bf16": {
        "candidate": "lev",
        "matrix": EVALUATION / "dms20-lev-mps-bf16-matrix.json",
        "approval": EVALUATION / "dms20-lev-mps-bf16-approval.json",
        "cache": Path("/private/tmp/dms20-lev-mps-bf16-models"),
        "source": Path("/private/tmp/dms20-lev-source"),
        "output": EVALUATION / "dms20-lev-mps-bf16-run-2026-10-24",
    },
    "strands-decider-2b-mps-bf16": {
        "candidate": "strands-decider-2b",
        "matrix": EVALUATION / "dms20-strands-decider-2b-mps-bf16-matrix.json",
        "approval": EVALUATION / "dms20-strands-decider-2b-mps-bf16-approval.json",
        "cache": Path("/private/tmp/dms20-strands-mps-bf16-models"),
        "source": Path("/private/tmp/dms20-strands-source"),
        "output": EVALUATION / "dms20-strands-mps-bf16-run-2026-10-24",
    },
}


class MpsOptimizationError(RuntimeError):
    """Raised when an MPS optimization row fails its frozen contract."""


def _verify(row_id: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    config = ROWS[row_id]
    matrix = json.loads(config["matrix"].read_text(encoding="utf-8"))
    row = matrix["rows"][0]
    if len(matrix["rows"]) != 1 or row.get("optimization_id") != row_id:
        raise MpsOptimizationError(
            "matrix does not select the requested MPS optimization row"
        )
    corpus = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    if matrix.get("corpus_manifest_sha256") != _sha256(CORPUS_PATH):
        raise MpsOptimizationError("corpus manifest differs from the frozen matrix")
    if corpus.get("license_review_status") != "cleared":
        raise MpsOptimizationError("corpus license review has not cleared")
    if (
        _sha256(INPUTS_PATH) != matrix["normalized_input_sha256"]
        or _sha256(LABELS_PATH) != matrix["gold_label_sha256"]
    ):
        raise MpsOptimizationError(
            "normalized inputs or labels differ from the approved corpus"
        )
    for item in matrix["harness_files"]:
        path = ROOT / item["path"]
        if not path.is_file() or _sha256(path) != item["sha256"]:
            raise MpsOptimizationError("pinned MPS harness differs")
    approval = json.loads(config["approval"].read_text(encoding="utf-8"))
    if approval.get("approved") is not True or approval.get("matrix_sha256") != _sha256(
        config["matrix"]
    ):
        raise MpsOptimizationError("approval does not bind the frozen MPS matrix")
    if approval.get("corpus_manifest_sha256") != _sha256(CORPUS_PATH):
        raise MpsOptimizationError("approval corpus digest differs")
    return matrix, row, config


def _resources(
    row: dict[str, Any], cache: Path, *, before_stage: bool
) -> dict[str, int]:
    import shutil

    total = os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE")
    result = subprocess.run(
        ["memory_pressure"], capture_output=True, check=True, text=True, timeout=5
    ).stdout
    marker = "System-wide memory free percentage:"
    line = next((item for item in result.splitlines() if item.startswith(marker)), None)
    if line is None:
        raise MpsOptimizationError("could not read macOS free-memory percentage")
    percent = int(line.removeprefix(marker).strip().rstrip("%"))
    free_memory = total * percent // 100
    floors = row["resource_floor"]
    if free_memory < floors["minimum_free_memory_bytes"]:
        raise MpsOptimizationError("free memory is below the approved row floor")
    free_disk = shutil.disk_usage(cache.parent).free
    floor_key = (
        "minimum_free_disk_before_stage_bytes"
        if before_stage
        else "minimum_free_disk_after_stage_bytes"
    )
    if free_disk < floors[floor_key]:
        raise MpsOptimizationError("free disk is below the approved row floor")
    return {
        "system_memory_free_percent": percent,
        "free_memory_bytes_estimate": free_memory,
        "free_disk_bytes": free_disk,
    }


def _snapshot(cache: Path, repository: str, revision: str) -> Path:
    return cache / f"models--{repository.replace('/', '--')}" / "snapshots" / revision


def _verify_artifacts(row: dict[str, Any], cache: Path) -> tuple[Path, Path]:
    for item in row["artifact_files"]:
        path = _snapshot(cache, item["repository"], item["revision"]) / item["path"]
        if not path.is_file() or _sha256(path) != item["sha256"]:
            raise MpsOptimizationError(f"pinned artifact differs: {item['path']}")
    return (
        _snapshot(cache, row["model"]["id"], row["model"]["revision"]),
        _snapshot(cache, row["base_model"]["id"], row["base_model"]["revision"]),
    )


def stage_candidate(row_id: str) -> dict[str, Any]:
    from huggingface_hub import snapshot_download

    matrix, row, config = _verify(row_id)
    before = _resources(row, config["cache"], before_stage=True)
    config["cache"].mkdir(parents=True, exist_ok=True)
    for repository, revision in sorted(
        {(item["repository"], item["revision"]) for item in row["artifact_files"]}
    ):
        snapshot_download(
            repository,
            revision=revision,
            cache_dir=str(config["cache"]),
            allow_patterns=matrix["artifact_download_allow_patterns"],
            ignore_patterns=matrix["artifact_download_ignore_patterns"],
        )
    model_dir, base_dir = _verify_artifacts(row, config["cache"])
    after = _resources(row, config["cache"], before_stage=False)
    receipt = {
        "optimization_id": row_id,
        "verified": True,
        "matrix_sha256": _sha256(config["matrix"]),
        "resource_preflight": {"before_stage": before, "after_stage": after},
    }
    config["output"].mkdir(parents=True, exist_ok=True)
    (config["output"] / "stage-receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    )
    return {**receipt, "model_dir": str(model_dir), "base_dir": str(base_dir)}


def _load_lev(row: dict[str, Any], model_dir: Path, base_dir: Path, source: Path):
    import torch

    sys.path.insert(0, str(source / "packages/lev/src"))
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from lev.calibrate import CalibrationProfile
    from lev.model import DecisionEngine, EngineConfig, _load_head, _set_adapter_scale

    manifest = json.loads((model_dir / "lev_release.json").read_text(encoding="utf-8"))
    tokenizer = AutoTokenizer.from_pretrained(str(model_dir), local_files_only=True)
    model = AutoModelForCausalLM.from_pretrained(
        str(base_dir),
        dtype=torch.bfloat16,
        local_files_only=True,
        attn_implementation="sdpa",
    ).to("mps")
    model = PeftModel.from_pretrained(model, str(model_dir), local_files_only=True)
    scale = float(manifest.get("adapter_scale", 1.0))
    if scale != 1.0:
        _set_adapter_scale(model, scale)
    model = model.merge_and_unload().eval()
    head = _load_head(model_dir / "mode_b_head.pt", model)
    calibration = (
        CalibrationProfile.load(model_dir / "calibration.json")
        if (model_dir / "calibration.json").is_file()
        else CalibrationProfile()
    )
    engine = DecisionEngine(
        model,
        tokenizer,
        EngineConfig(
            model_id=row["base_model"]["id"],
            prompt_style=manifest.get("prompt_style", "plain"),
        ),
        calibration,
        mode_b_head=head,
    )

    def infer(item: dict[str, Any]) -> dict[str, Any]:
        from run_dms20_transfer import _lev_choice_question

        question = item["question"]
        answer = engine.system_one(
            item["state"], {question["id"]: _lev_choice_question(question)}
        ).answers[question["id"]]
        return {
            "status": "ok",
            "choice": answer.choice,
            "score_semantics": "calibrated_probability",
            "scores": answer.probabilities,
        }

    return (
        infer,
        lambda item: len(tokenizer.encode(_normalized_text(item))),
        (engine, model),
    )


def _load_strands(row: dict[str, Any], model_dir: Path, source: Path):
    sys.path.insert(0, str(source / "src"))
    from strands_decider.infer import load_engine
    from strands_decider.schema import ChoiceQuestion

    engine = load_engine(str(model_dir), device="mps", attn_implementation="sdpa")

    def infer(item: dict[str, Any]) -> dict[str, Any]:
        question = item["question"]
        answer = engine.ask(
            item["state"],
            {
                question["id"]: ChoiceQuestion(
                    instructions=question["text"],
                    criteria={
                        option["id"]: option["label"] for option in question["options"]
                    },
                )
            },
        ).answers[question["id"]]
        return {
            "status": "ok",
            "choice": answer.choice,
            "score_semantics": "calibrated_probability",
            "scores": answer.probabilities,
        }

    return infer, lambda item: len(engine.tok.encode(_normalized_text(item))), engine


def run_candidate(row_id: str) -> dict[str, Any]:  # noqa: C901 - one gated benchmark lifecycle.
    import torch

    matrix, row, config = _verify(row_id)
    runtime = row["runtime"]
    if (
        _sha256(ROOT / runtime["lock_path"]) != runtime["lock_sha256"]
        or sys.version.split()[0] != runtime["python_version"]
    ):
        raise MpsOptimizationError("runtime lock or Python version differs")
    for package, version in runtime["packages"].items():
        if importlib.metadata.version(package) != version:
            raise MpsOptimizationError(f"runtime package differs: {package}")
    if not torch.backends.mps.is_available():
        raise MpsOptimizationError("PyTorch MPS is unavailable")
    resources = _resources(row, config["cache"], before_stage=False)
    model_dir, base_dir = _verify_artifacts(row, config["cache"])
    source = config["source"]
    commit = subprocess.run(
        ["git", "-C", str(source), "rev-parse", "HEAD"],
        capture_output=True,
        check=True,
        text=True,
        timeout=5,
    ).stdout.strip()
    if commit != row["source"]["revision"]:
        raise MpsOptimizationError("pinned source checkout differs")
    os.environ.update(
        HF_HOME=str(config["cache"]),
        HF_HUB_CACHE=str(config["cache"]),
        HF_HUB_OFFLINE="1",
        TRANSFORMERS_OFFLINE="1",
    )
    started = time.perf_counter()
    if row_id == "lev-mps-bf16":
        infer, count_tokens, engine = _load_lev(row, model_dir, base_dir, source)
    else:
        infer, count_tokens, engine = _load_strands(row, model_dir, source)
    cold_load_ms = (time.perf_counter() - started) * 1000
    inputs = [
        json.loads(line)
        for line in INPUTS_PATH.read_text(encoding="utf-8").splitlines()
    ]
    max_tokens = max(count_tokens(item) for item in inputs)
    if max_tokens > matrix["protocol"]["normalized_content_token_limit"]:
        raise MpsOptimizationError("normalized-content token limit exceeded")
    candidate_id = config["candidate"]
    baseline_path = (
        EVALUATION / "dms20-run-2026-10-22" / candidate_id / "predictions.jsonl"
    )
    baseline = [
        json.loads(line)
        for line in baseline_path.read_text(encoding="utf-8").splitlines()
    ]
    by_key = {(item["id"], item["option_order"]): item for item in baseline}
    selected: dict[str, dict[str, Any]] = {}
    for item in inputs:
        selected.setdefault(item["category"], item)
    smoke_inputs = list(selected.values())
    smoke_predictions = run_rows(smoke_inputs, infer)
    for actual in smoke_predictions:
        expected = by_key[(actual["id"], actual["option_order"])]
        if actual["status"] != "ok" or actual["choice"] != expected["choice"]:
            raise MpsOptimizationError(
                "MPS BF16 smoke choice differs from the pinned CPU baseline"
            )
    print("smoke passed: 14/14 choices", file=sys.stderr, flush=True)
    latencies: list[float] = []
    completed = 0

    def timed(item: dict[str, Any]) -> dict[str, Any]:
        nonlocal completed
        started_item = time.perf_counter()
        try:
            return infer(item)
        finally:
            if torch.backends.mps.is_available():
                torch.mps.synchronize()
            latencies.append((time.perf_counter() - started_item) * 1000)
            completed += 1
            if completed % 40 == 0 or completed == len(inputs) * 2:
                print(
                    f"progress {completed}/{len(inputs) * 2}",
                    file=sys.stderr,
                    flush=True,
                )

    predictions = run_rows(inputs, timed)
    output = config["output"]
    output.mkdir(parents=True, exist_ok=True)
    pred_path = output / "predictions.jsonl"
    pred_path.write_text(
        "".join(json.dumps(item, sort_keys=True) + "\n" for item in predictions)
    )
    failures = sum(item["status"] != "ok" for item in predictions)
    peak = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    if sys.platform != "darwin":
        peak *= 1024
    measurement = {
        "optimization_id": row_id,
        "candidate_id": candidate_id,
        "model": row["model"],
        "base_model": row["base_model"],
        "device": "mps",
        "precision": "bfloat16",
        "attention": "sdpa",
        "item_count": len(inputs),
        "prediction_count": len(predictions),
        "failures": failures,
        "smoke_choice_parity": True,
        "cold_load_ms": cold_load_ms,
        "mean_per_decision_latency_ms": sum(latencies) / len(latencies),
        "per_decision_latency_ms": latencies,
        "peak_rss_bytes": peak,
        "mps_current_allocated_bytes": int(torch.mps.current_allocated_memory()),
        "mps_driver_allocated_bytes": int(torch.mps.driver_allocated_memory()),
        "common_max_token_count": max_tokens,
        "resource_preflight": resources,
        "matrix_sha256": _sha256(config["matrix"]),
        "corpus_manifest_sha256": _sha256(CORPUS_PATH),
        "host_platform": platform.platform(),
    }
    (output / "measurements.json").write_text(
        json.dumps(measurement, indent=2, sort_keys=True) + "\n"
    )
    del engine
    return {
        "optimization_id": row_id,
        "prediction_count": len(predictions),
        "failures": failures,
        "mean_per_decision_latency_ms": measurement["mean_per_decision_latency_ms"],
        "predictions_path": str(pred_path),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--row", choices=sorted(ROWS), required=True)
    parser.add_argument("--stage-only", action="store_true")
    args = parser.parse_args()
    print(
        json.dumps(
            stage_candidate(args.row) if args.stage_only else run_candidate(args.row),
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
