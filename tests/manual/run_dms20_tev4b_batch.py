#!/usr/bin/env python3
"""Helpers for approved DMS-20 microbatch execution variants."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import resource
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
EVALUATION = ROOT / "specs/decision-model-support/evaluation"
MATRIX_PATH = EVALUATION / "dms20-tev1-4b-batch4-matrix.json"
APPROVAL_PATH = EVALUATION / "dms20-tev1-4b-batch4-approval.json"
CORPUS_PATH = EVALUATION / "dms14-corpus-manifest.json"
INPUTS_PATH = Path("/private/tmp/dms20-corpus/normalized-inputs.jsonl")
LABELS_PATH = Path("/private/tmp/dms20-corpus/gold-labels.jsonl")
MATERIAL_ROOT = Path("/private/tmp/dms20-tev1-4b-batch4-models")
OUTPUT_ROOT = EVALUATION / "dms20-tev1-4b-batch4-run-2026-10-24"
BASELINE_PATH = EVALUATION / "dms20-extension-run-2026-10-22/tev1-4b/predictions.jsonl"


class BatchRunError(RuntimeError):
    """Raised when the microbatch run contract is not satisfied."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _verify(
    matrix_path: Path, approval_path: Path
) -> tuple[dict[str, Any], dict[str, Any]]:
    matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
    corpus = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    if _sha256(CORPUS_PATH) != matrix.get("corpus_manifest_sha256"):
        raise BatchRunError("corpus manifest differs from the frozen matrix")
    if not corpus.get("license_review_status") == "cleared":
        raise BatchRunError("corpus license review has not cleared")
    for name, digest in (
        ("normalized_inputs", matrix["normalized_input_sha256"]),
        ("gold_labels", matrix["gold_label_sha256"]),
    ):
        path = INPUTS_PATH if name == "normalized_inputs" else LABELS_PATH
        if not path.is_file() or _sha256(path) != digest:
            raise BatchRunError(f"approved {name} are absent or changed")
    row = matrix["rows"][0]
    if (
        len(matrix["rows"]) != 1
        or row.get("id") != "tev1-4b"
        or row.get("batch_size") != 4
    ):
        raise BatchRunError("matrix must select only the Tev1-4B batch-4 variant")
    for item in matrix["harness_files"]:
        path = ROOT / item["path"]
        if not path.is_file() or _sha256(path) != item["sha256"]:
            raise BatchRunError("pinned batch harness differs")
    approval = json.loads(approval_path.read_text(encoding="utf-8"))
    if approval.get("approved") is not True or approval.get("matrix_sha256") != _sha256(
        matrix_path
    ):
        raise BatchRunError("approval does not bind the frozen batch matrix")
    if approval.get("approval_scope") != matrix.get("approval_scope"):
        raise BatchRunError("approval scope differs from the matrix")
    return matrix, row


def _resource_preflight(row: dict[str, Any], *, before_stage: bool) -> dict[str, int]:
    import shutil
    import subprocess

    total_memory = os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE")
    output = subprocess.run(
        ["memory_pressure"], capture_output=True, check=True, text=True, timeout=5
    ).stdout
    marker = "System-wide memory free percentage:"
    line = next(
        (value for value in output.splitlines() if value.startswith(marker)), None
    )
    if line is None:
        raise BatchRunError("could not read system-wide free memory")
    free_percent = int(line.removeprefix(marker).strip().rstrip("%"))
    free_memory = total_memory * free_percent // 100
    if free_memory < row["resource_floor"]["minimum_free_memory_bytes"]:
        raise BatchRunError("free memory is below the approved row floor")
    free_disk = shutil.disk_usage(MATERIAL_ROOT.parent).free
    floor_key = (
        "minimum_free_disk_before_stage_bytes"
        if before_stage
        else "minimum_free_disk_after_stage_bytes"
    )
    if free_disk < row["resource_floor"][floor_key]:
        raise BatchRunError("free disk is below the approved row floor")
    return {
        "system_memory_free_percent": free_percent,
        "free_memory_bytes_estimate": free_memory,
        "free_disk_bytes": free_disk,
    }


def _snapshot(repository: str, revision: str) -> Path:
    return (
        MATERIAL_ROOT
        / f"models--{repository.replace('/', '--')}"
        / "snapshots"
        / revision
    )


def _verify_artifacts(row: dict[str, Any]) -> Path:
    for artifact in row["artifact_files"]:
        path = (
            _snapshot(artifact["repository"], artifact["revision"]) / artifact["path"]
        )
        if not path.is_file() or _sha256(path) != artifact["sha256"]:
            raise BatchRunError(f"pinned artifact differs: {artifact['path']}")
    return _snapshot(row["model"]["id"], row["model"]["revision"])


def stage_candidate(
    matrix_path: Path = MATRIX_PATH, approval_path: Path = APPROVAL_PATH
) -> dict[str, Any]:
    from huggingface_hub import snapshot_download

    matrix, row = _verify(matrix_path, approval_path)
    before = _resource_preflight(row, before_stage=True)
    MATERIAL_ROOT.mkdir(parents=True, exist_ok=True)
    for repository, revision in sorted(
        {(item["repository"], item["revision"]) for item in row["artifact_files"]}
    ):
        snapshot_download(
            repository,
            revision=revision,
            cache_dir=str(MATERIAL_ROOT),
            allow_patterns=matrix["artifact_download_allow_patterns"],
            ignore_patterns=matrix["artifact_download_ignore_patterns"],
        )
    model_dir = _verify_artifacts(row)
    after = _resource_preflight(row, before_stage=False)
    receipt = {
        "candidate_id": row["id"],
        "verified": True,
        "matrix_sha256": _sha256(matrix_path),
        "resource_preflight": {"before_stage": before, "after_stage": after},
    }
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    (OUTPUT_ROOT / "stage-receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    )
    return {**receipt, "model_dir": str(model_dir)}


def _load_tev_batch(model_dir: Path) -> tuple[Any, Any]:
    import torch
    from transformers import AutoTokenizer, Qwen3_5ForConditionalGeneration

    tokenizer = AutoTokenizer.from_pretrained(str(model_dir), local_files_only=True)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    model = (
        Qwen3_5ForConditionalGeneration.from_pretrained(
            str(model_dir), dtype=torch.bfloat16, local_files_only=True
        )
        .to("mps")
        .eval()
    )
    return model, tokenizer


def _infer_batch(
    model: Any, tokenizer: Any, rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    import torch

    from run_dms20_extension import _MODEL_PROMPT_TOKEN_LIMIT, _tev_messages

    prompts: list[str] = []
    prompt_ids: list[list[int]] = []
    candidate_ids: list[list[int]] = []
    option_ids: list[list[str]] = []
    for row in rows:
        messages = _tev_messages(row)
        prompt = tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True, enable_thinking=False
        )
        ids = tokenizer.encode(prompt, add_special_tokens=False)
        if len(ids) > _MODEL_PROMPT_TOKEN_LIMIT:
            raise ValueError("Tev1 formatted prompt exceeds the approved token budget")
        options = row["question"]["options"]
        letters = [chr(ord("A") + index) for index in range(len(options))]
        answer_tokens = []
        for letter in letters:
            complete = tokenizer.encode(prompt + letter, add_special_tokens=False)
            if complete[: len(ids)] != ids or len(complete) != len(ids) + 1:
                raise ValueError(
                    "answer letter is not one token at the prompt boundary"
                )
            answer_tokens.append(complete[-1])
        prompts.append(prompt)
        prompt_ids.append(ids)
        candidate_ids.append(answer_tokens)
        option_ids.append([option["id"] for option in options])

    padded, mask = pad_token_ids(prompt_ids, tokenizer.pad_token_id)
    input_ids = torch.tensor(padded, dtype=torch.long, device="mps")
    attention_mask = torch.tensor(mask, dtype=torch.long, device="mps")
    with torch.inference_mode():
        output = model.model(
            input_ids=input_ids,
            attention_mask=attention_mask,
            use_cache=False,
        )
        hidden_states = output.last_hidden_state
    last_token_indexes = torch.tensor(
        [len(ids) - 1 for ids in prompt_ids],
        device=hidden_states.device,
        dtype=torch.long,
    )
    final_hidden = hidden_states[
        torch.arange(len(prompt_ids), device=hidden_states.device), last_token_indexes
    ]
    logits = model.lm_head(final_hidden)
    return batch_scores(logits, candidate_ids, option_ids)


def run_candidate(  # noqa: C901 - this is one gated benchmark lifecycle.
    matrix_path: Path = MATRIX_PATH, approval_path: Path = APPROVAL_PATH
) -> dict[str, Any]:
    matrix, row = _verify(matrix_path, approval_path)
    runtime = row["runtime"]
    lock = ROOT / runtime["lock_path"]
    if (
        _sha256(lock) != runtime["lock_sha256"]
        or sys.version.split()[0] != runtime["python_version"]
    ):
        raise BatchRunError("approved runtime lock or Python version differs")
    for package, version in runtime["packages"].items():
        if importlib.metadata.version(package) != version:
            raise BatchRunError(f"runtime package differs: {package}")
    resources = _resource_preflight(row, before_stage=False)
    model_dir = _verify_artifacts(row)
    started = time.perf_counter()
    model, tokenizer = _load_tev_batch(model_dir)
    cold_load_ms = (time.perf_counter() - started) * 1000
    inputs = [
        json.loads(line)
        for line in INPUTS_PATH.read_text(encoding="utf-8").splitlines()
    ]
    if (
        max(len(tokenizer.encode(_normalized(item))) for item in inputs)
        > matrix["protocol"]["normalized_content_token_limit"]
    ):
        raise BatchRunError("normalized-content token limit exceeded")

    from run_dms20_extension import ordered_inputs

    def predict(
        rows: list[dict[str, Any]], model: Any = model, tokenizer: Any = tokenizer
    ) -> tuple[list[dict[str, Any]], list[float]]:
        predictions: list[dict[str, Any]] = []
        latencies: list[float] = []
        for offset in range(0, len(rows), row["batch_size"]):
            batch = rows[offset : offset + row["batch_size"]]
            started_batch = time.perf_counter()
            scores = _infer_batch(model, tokenizer, batch)
            import torch

            torch.mps.synchronize()
            elapsed = (time.perf_counter() - started_batch) * 1000
            for item, score in zip(batch, scores, strict=True):
                predictions.append({"id": item["id"], "status": "ok", **score})
                latencies.append(elapsed / len(batch))
        return predictions, latencies

    baseline = [
        json.loads(line)
        for line in BASELINE_PATH.read_text(encoding="utf-8").splitlines()
    ]
    by_key = {(item["id"], item["option_order"]): item for item in baseline}
    smoke_items: dict[str, dict[str, Any]] = {}
    for item in inputs:
        smoke_items.setdefault(item["category"], item)
    smoke_rows: list[dict[str, Any]] = []
    smoke_baseline: list[dict[str, Any]] = []
    for order in ("canonical", "reversed"):
        for item in ordered_inputs(list(smoke_items.values()), order):
            smoke_rows.append(item)
            smoke_baseline.append(by_key[(item["id"], order)])
    smoke_predictions, _ = predict(smoke_rows)
    for actual, expected in zip(smoke_predictions, smoke_baseline, strict=True):
        if actual["choice"] != expected["choice"]:
            raise BatchRunError(
                "batch-4 smoke choice differs from the pinned unbatched baseline"
            )

    predictions: list[dict[str, Any]] = []
    latencies: list[float] = []
    for order in ("canonical", "reversed"):
        ordered = ordered_inputs(inputs, order)
        current, current_latencies = predict(ordered)
        for _item, prediction in zip(ordered, current, strict=True):
            prediction["option_order"] = order
            predictions.append(prediction)
        latencies.extend(current_latencies)
        print(
            f"progress {len(predictions)}/{len(inputs) * 2}",
            file=sys.stderr,
            flush=True,
        )

    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    predictions_path = OUTPUT_ROOT / "predictions.jsonl"
    predictions_path.write_text(
        "".join(json.dumps(item, sort_keys=True) + "\n" for item in predictions)
    )
    measurements = {
        "candidate_id": "tev1-4b-mps-batch4",
        "batch_size": row["batch_size"],
        "item_count": len(inputs),
        "prediction_count": len(predictions),
        "failures": sum(item["status"] != "ok" for item in predictions),
        "cold_load_ms": cold_load_ms,
        "mean_per_decision_latency_ms": sum(latencies) / len(latencies),
        "per_decision_latency_ms": latencies,
        "peak_rss_bytes": int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss),
        "mps_current_allocated_bytes": int(
            __import__("torch").mps.current_allocated_memory()
        ),
        "mps_driver_allocated_bytes": int(
            __import__("torch").mps.driver_allocated_memory()
        ),
        "resource_preflight": resources,
        "matrix_sha256": _sha256(matrix_path),
        "corpus_manifest_sha256": _sha256(CORPUS_PATH),
        "host_platform": platform.platform(),
    }
    (OUTPUT_ROOT / "measurements.json").write_text(
        json.dumps(measurements, indent=2, sort_keys=True) + "\n"
    )
    del model
    return {
        "candidate_id": measurements["candidate_id"],
        "prediction_count": len(predictions),
        "failures": measurements["failures"],
        "mean_per_decision_latency_ms": measurements["mean_per_decision_latency_ms"],
        "predictions_path": str(predictions_path),
    }


def _normalized(item: dict[str, Any]) -> str:
    from run_dms20_transfer import _normalized_text

    return _normalized_text(item)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage-only", action="store_true")
    parser.add_argument("--matrix", type=Path, default=MATRIX_PATH)
    parser.add_argument("--approval", type=Path, default=APPROVAL_PATH)
    args = parser.parse_args()
    result = (
        stage_candidate(args.matrix, args.approval)
        if args.stage_only
        else run_candidate(args.matrix, args.approval)
    )
    print(json.dumps(result, sort_keys=True))


def pad_token_ids(
    rows: list[list[int]], pad_token_id: int
) -> tuple[list[list[int]], list[list[int]]]:
    """Right-pad distinct prompts and return matching attention masks."""
    if not rows or any(not row for row in rows):
        raise ValueError("a batch must contain non-empty token rows")
    width = max(map(len, rows))
    input_ids = [row + [pad_token_id] * (width - len(row)) for row in rows]
    attention_mask = [[1] * len(row) + [0] * (width - len(row)) for row in rows]
    return input_ids, attention_mask


def batch_scores(
    logits: Any,
    candidate_ids: list[list[int]],
    option_ids: list[list[str]],
) -> list[dict[str, Any]]:
    """Map each batch row's selected logits to normalized option probabilities."""
    import math

    import torch

    if len(candidate_ids) != len(option_ids) or len(candidate_ids) != logits.shape[0]:
        raise ValueError("batch output and candidate rows differ")
    results = []
    for index, (token_ids, ids) in enumerate(
        zip(candidate_ids, option_ids, strict=True)
    ):
        if not token_ids or len(token_ids) != len(ids) or len(set(ids)) != len(ids):
            raise ValueError("candidate tokens and option IDs must match")
        selected = (
            logits[index]
            .index_select(
                0, torch.tensor(token_ids, device=logits.device, dtype=torch.long)
            )
            .float()
        )
        if not bool(torch.isfinite(selected).all()):
            raise ValueError("candidate logits are non-finite")
        probabilities = selected.softmax(dim=0).cpu().tolist()
        if any(not math.isfinite(value) for value in probabilities):
            raise ValueError("candidate probabilities are non-finite")
        scores = dict(zip(ids, map(float, probabilities), strict=True))
        results.append({"choice": max(scores, key=scores.get), "scores": scores})
    return results


if __name__ == "__main__":
    main()
