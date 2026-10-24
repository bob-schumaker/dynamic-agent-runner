#!/usr/bin/env python3
"""Run the separately approved Nimble-9B MPS linear-attention variant."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import math
import os
import platform
import resource
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable

from run_dms20_extension import (
    ExtensionRunError,
    _check_resources,
    _nimble_schema,
    _verify_artifacts,
    run_predictions,
)
from run_dms20_transfer import _normalized_text, _sha256, ordered_inputs


ROOT = Path(__file__).resolve().parents[2]
EVALUATION = ROOT / "specs/decision-model-support/evaluation"
MATRIX_PATH = EVALUATION / "dms20-nimble-mps-matrix.json"
APPROVAL_PATH = EVALUATION / "dms20-nimble-mps-approval.json"
CORPUS_PATH = EVALUATION / "dms14-corpus-manifest.json"
INPUTS_PATH = Path("/private/tmp/dms20-nimble-mps-data/normalized-inputs.jsonl")
LABELS_PATH = Path("/private/tmp/dms20-nimble-mps-data/gold-labels.jsonl")
MATERIAL_ROOT = Path("/private/tmp/dms20-nimble-mps-model-cache")
OUTPUT_ROOT = EVALUATION / "dms20-nimble-mps-debug-run-2026-10-24"
CANDIDATE_ID = "nimble-9b-mps-linear-attn"
OPTIMIZER_REPOSITORY = "https://github.com/mpsops/mps-linear-attention"
OPTIMIZER_REVISION = "f0889940cf168dcc9e2541b061875835e63a095e"


def _json_number(value: float) -> float | str:
    number = float(value)
    return number if math.isfinite(number) else str(number)


def _verify_matrix_and_approval(
    matrix_path: Path = MATRIX_PATH,
    corpus_path: Path = CORPUS_PATH,
    approval_path: Path = APPROVAL_PATH,
) -> dict[str, Any]:
    matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
    corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    _verify_corpus_bindings(matrix, corpus, corpus_path)
    _verify_harness_files(matrix)
    row = _verify_candidate_row(matrix)
    _verify_approval(matrix, row, matrix_path, corpus_path, approval_path)
    return matrix


def _verify_corpus_bindings(
    matrix: dict[str, Any], corpus: dict[str, Any], corpus_path: Path
) -> None:
    if matrix.get("corpus_manifest_sha256") != _sha256(corpus_path):
        raise ExtensionRunError("corpus manifest digest differs")
    if matrix.get("normalized_input_sha256") != corpus.get("normalized_input_sha256"):
        raise ExtensionRunError("normalized input digest differs")
    if matrix.get("gold_label_sha256") != corpus.get("gold_label_sha256"):
        raise ExtensionRunError("gold label digest differs")
    if corpus.get("license_review_status") != "cleared":
        raise ExtensionRunError("shared corpus license review has not cleared")
    for item in matrix.get("input_files", {}).values():
        path = Path(item["path"])
        if not path.is_file() or _sha256(path) != item.get("sha256"):
            raise ExtensionRunError("approved normalized input or label file differs")


def _verify_harness_files(matrix: dict[str, Any]) -> None:
    files = matrix.get("harness_files")
    if not isinstance(files, list) or not files:
        raise ExtensionRunError("optimized Nimble matrix does not pin its harness")
    for item in files:
        path = ROOT / item["path"]
        if not path.is_file() or _sha256(path) != item.get("sha256"):
            raise ExtensionRunError("optimized Nimble harness digest differs")


def _verify_candidate_row(matrix: dict[str, Any]) -> dict[str, Any]:
    rows = matrix.get("rows")
    if not isinstance(rows, list) or len(rows) != 1:
        raise ExtensionRunError("optimized Nimble matrix must contain exactly one row")
    row = rows[0]
    if row.get("id") != CANDIDATE_ID or row.get("disposition") != "selected":
        raise ExtensionRunError("optimized Nimble row is not the selected candidate")
    if matrix.get("runnable_cohort") != [CANDIDATE_ID]:
        raise ExtensionRunError("optimized Nimble runnable cohort differs")
    optimizer = row.get("optimizer", {})
    if optimizer.get("revision") != OPTIMIZER_REVISION:
        raise ExtensionRunError(
            "optimized kernel revision differs from the approved pin"
        )
    return row


def _verify_approval(
    matrix: dict[str, Any],
    row: dict[str, Any],
    matrix_path: Path,
    corpus_path: Path,
    approval_path: Path,
) -> None:
    if not approval_path.is_file():
        raise ExtensionRunError("optimized Nimble approval receipt is absent")
    approval = json.loads(approval_path.read_text(encoding="utf-8"))
    dispositions = {row["id"]: row["disposition"]}
    if (
        approval.get("approved") is not True
        or approval.get("matrix_sha256") != _sha256(matrix_path)
        or approval.get("corpus_manifest_sha256") != _sha256(corpus_path)
        or approval.get("approval_scope") != matrix.get("approval_scope")
        or approval.get("dispositions") != dispositions
        or approval.get("runnable_cohort") != [CANDIDATE_ID]
        or approval.get("optimizer_revision") != OPTIMIZER_REVISION
    ):
        raise ExtensionRunError(
            "optimized Nimble approval does not bind the frozen matrix"
        )


def _verify_runtime(row: dict[str, Any]) -> None:
    runtime = row["runtime"]
    lock_path = ROOT / runtime["lock_path"]
    if _sha256(lock_path) != runtime["lock_sha256"]:
        raise ExtensionRunError("optimized Nimble runtime lock differs")
    if sys.version.split()[0] != runtime["python_version"]:
        raise ExtensionRunError("optimized Nimble Python version differs")
    for name, expected in runtime["packages"].items():
        if importlib.metadata.version(name) != expected:
            raise ExtensionRunError(
                f"{name} version differs from the optimized Nimble matrix"
            )
    distribution = importlib.metadata.distribution("mps-linear-attn")
    direct_url = distribution.read_text("direct_url.json")
    if not direct_url:
        raise ExtensionRunError("optimized kernel VCS installation metadata is absent")
    source = json.loads(direct_url)
    if (
        source.get("vcs_info", {}).get("commit_id") != OPTIMIZER_REVISION
        or source.get("url", "").rstrip("/").removesuffix(".git")
        != OPTIMIZER_REPOSITORY
    ):
        raise ExtensionRunError(
            "installed optimized kernel source differs from its pin"
        )


def _configure_optimized_kernels() -> dict[str, int]:
    import mps_linear_attn  # noqa: F401 - patches FLA before Transformers import.
    from mps_linear_attn import causal_conv1d, delta_rule

    if not getattr(delta_rule, "_HAS_METAL", False) or not getattr(
        causal_conv1d, "_HAS_METAL", False
    ):
        raise ExtensionRunError(
            "mps-linear-attn was installed without compiled Metal kernels"
        )
    required = (
        (delta_rule._C, "delta_rule_fused"),
        (causal_conv1d._C, "causal_conv1d"),
    )
    if any(not callable(getattr(module, name, None)) for module, name in required):
        raise ExtensionRunError("compiled optimized Metal entry points are unavailable")

    counters = {"delta_rule_fused": 0, "causal_conv1d": 0}
    for module, name in required:
        original = getattr(module, name)

        def counted(
            *args: Any,
            _name: str = name,
            _original: Callable[..., Any] = original,
            **kwargs: Any,
        ) -> Any:
            counters[_name] += 1
            return _original(*args, **kwargs)

        setattr(module, name, counted)

    gated_delta_rule = sys.modules.get("fla.ops.gated_delta_rule")
    fused_recurrent = getattr(delta_rule, "fused_recurrent_gated_delta_rule", None)
    if gated_delta_rule is None or not callable(fused_recurrent):
        raise ExtensionRunError(
            "mps-linear-attn did not install its FLA implementations"
        )
    # Qwen3.5's full-prompt path calls chunk_gated_delta_rule. The upstream
    # package's chunk function is a PyTorch reference path, so select its fused
    # recurrent prefill implementation to exercise the Metal delta-rule kernel.
    gated_delta_rule.chunk_gated_delta_rule = fused_recurrent
    return counters


def _load_nimble(
    row: dict[str, Any], model_dir: Path, base_dir: Path
) -> tuple[Callable[..., Any], Any, dict[str, int]]:
    import torch

    if not torch.backends.mps.is_available():
        raise ExtensionRunError("MPS is unavailable for the optimized Nimble row")
    counters = _configure_optimized_kernels()
    from peft import PeftModel
    from transformers import AutoTokenizer, Qwen3_5ForConditionalGeneration

    sys.path.insert(0, str(model_dir))
    from inference import validate_serving_config
    from serving_schema import prepare_prompts

    contract = json.loads(
        (model_dir / "schema_config.json").read_text(encoding="utf-8")
    )
    if _sha256(model_dir / "parallel_schema.py") != contract["prompt_code_sha256"]:
        raise ExtensionRunError("Nimble prompt source differs from its pinned contract")
    for name, expected in contract.get("prompt_source_sha256", {}).items():
        if Path(name).name != name or _sha256(model_dir / name) != expected:
            raise ExtensionRunError(
                "Nimble prompt dependency differs from its pinned contract"
            )
    tokenizer = AutoTokenizer.from_pretrained(str(model_dir), local_files_only=True)
    validate_serving_config(model_dir, tokenizer)
    base = Qwen3_5ForConditionalGeneration.from_pretrained(
        str(base_dir),
        revision=row["base_model"]["revision"],
        dtype=torch.bfloat16,
        local_files_only=True,
        attn_implementation="sdpa",
    ).to("mps")
    base.config.use_cache = False
    model = PeftModel.from_pretrained(
        base, str(model_dir), local_files_only=True
    ).eval()
    candidate_limit = min(int(contract["max_length"]), 4096)

    def infer(item: dict[str, Any]) -> dict[str, Any]:
        context = json.dumps(item["state"], ensure_ascii=False, sort_keys=True)
        prepared = prepare_prompts(
            tokenizer, context, _nimble_schema(item), candidate_limit
        )
        candidate_ids = prepared.candidate_ids[0]
        if len(candidate_ids) != len(item["question"]["options"]):
            raise ValueError("Nimble codebook does not match requested options")
        ids = torch.tensor([prepared.full_ids[0]], dtype=torch.long, device="mps")
        mask = torch.ones_like(ids)
        with torch.inference_mode():
            logits = model(
                input_ids=ids,
                attention_mask=mask,
                use_cache=False,
                logits_to_keep=1,
            ).logits[0, -1]
        candidate_logits = logits.index_select(
            0, torch.tensor(candidate_ids, device=logits.device, dtype=torch.long)
        )
        finite_mask = torch.isfinite(logits)
        finite_logits = logits[finite_mask].float()
        probs_tensor = candidate_logits.float().softmax(dim=0)
        probs = probs_tensor.cpu().tolist()
        options = item["question"]["options"]
        scores = {
            option["id"]: float(prob)
            for option, prob in zip(options, probs, strict=True)
        }
        debug = {
            "logits_shape": list(logits.shape),
            "logits_dtype": str(logits.dtype),
            "logits_device": str(logits.device),
            "logits_finite_count": int(finite_mask.sum().item()),
            "logits_total_count": logits.numel(),
            "logits_non_finite_count": int((~finite_mask).sum().item()),
            "finite_logits_min": float(finite_logits.min().item())
            if finite_logits.numel()
            else None,
            "finite_logits_max": float(finite_logits.max().item())
            if finite_logits.numel()
            else None,
            "candidate_token_ids": [int(token_id) for token_id in candidate_ids],
            "candidate_logits": [
                _json_number(value) for value in candidate_logits.float().cpu().tolist()
            ],
            "candidate_logits_finite": bool(
                torch.isfinite(candidate_logits).all().item()
            ),
            "candidate_probabilities": [_json_number(value) for value in probs],
            "candidate_probabilities_finite": bool(
                torch.isfinite(probs_tensor).all().item()
            ),
        }
        return {
            "choice": max(scores, key=scores.get),
            "scores": scores,
            "debug": debug,
        }

    return infer, tokenizer, counters


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _run_smoke_check(
    infer: Callable[[dict[str, Any]], dict[str, Any]],
    input_rows: list[dict[str, Any]],
    baseline_path: Path,
    kernel_calls: dict[str, int],
    output_dir: Path,
) -> dict[str, Any]:
    smoke_item = ordered_inputs(input_rows[:1], "canonical")[0]
    baseline_rows = _read_jsonl(baseline_path)
    baseline_smoke = next(
        item
        for item in baseline_rows
        if item["id"] == smoke_item["id"] and item["option_order"] == "canonical"
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    smoke_receipt: dict[str, Any] = {
        "item_id": smoke_item["id"],
        "baseline_choice": baseline_smoke["choice"],
        "kernel_calls": dict(kernel_calls),
    }
    try:
        smoke_output = infer(smoke_item)
        scores = smoke_output["scores"]
        smoke_diff = max(
            abs(scores[option] - baseline_smoke["scores"][option]) for option in scores
        )
        smoke_receipt.update(
            {
                "optimized_choice": smoke_output["choice"],
                "choice_match": smoke_output["choice"] == baseline_smoke["choice"],
                "optimized_scores": {
                    key: _json_number(value) for key, value in scores.items()
                },
                "baseline_scores": baseline_smoke["scores"],
                "max_probability_delta": _json_number(smoke_diff),
                "max_probability_delta_finite": math.isfinite(smoke_diff),
                "debug": smoke_output.get("debug"),
            }
        )
    except Exception as exc:  # noqa: BLE001 - persist failure context for local debugging.
        smoke_receipt["inference_error"] = {
            "type": type(exc).__name__,
            "message": str(exc),
        }
    smoke_receipt["kernel_calls"] = dict(kernel_calls)
    smoke_path = output_dir / "smoke-debug.json"
    smoke_path.write_text(
        json.dumps(smoke_receipt, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    if not all(kernel_calls.values()):
        raise ExtensionRunError(
            f"optimized Metal path was not proven by the smoke item; see {smoke_path}"
        )
    if "inference_error" in smoke_receipt:
        raise ExtensionRunError(
            f"Nimble optimized smoke inference failed; see {smoke_path}"
        )
    debug = smoke_receipt.get("debug") or {}
    if (
        debug.get("logits_non_finite_count")
        or not debug.get("candidate_probabilities_finite", False)
        or not smoke_receipt["max_probability_delta_finite"]
        or not smoke_receipt["choice_match"]
    ):
        raise ExtensionRunError(
            f"Nimble optimized smoke failed numerical checks; see {smoke_path}"
        )
    kernel_calls.update(dict.fromkeys(kernel_calls, 0))
    return smoke_receipt


def stage_candidate(
    matrix_path: Path = MATRIX_PATH,
    corpus_path: Path = CORPUS_PATH,
    approval_path: Path = APPROVAL_PATH,
    material_root: Path = MATERIAL_ROOT,
) -> dict[str, Any]:
    from huggingface_hub import snapshot_download

    matrix = _verify_matrix_and_approval(matrix_path, corpus_path, approval_path)
    row = matrix["rows"][0]
    _verify_runtime(row)
    before = _check_resources(row, material_root, before_stage=True)
    repositories = sorted(
        {(item["repository"], item["revision"]) for item in row["artifact_files"]}
    )
    for repository, revision in repositories:
        snapshot_download(
            repository,
            revision=revision,
            cache_dir=str(material_root),
            allow_patterns=matrix["artifact_download_allow_patterns"],
            ignore_patterns=matrix["artifact_download_ignore_patterns"],
        )
    after = _check_resources(row, material_root, before_stage=False)
    _verify_artifacts(row, material_root)
    result = {
        "candidate_id": CANDIDATE_ID,
        "matrix_sha256": _sha256(matrix_path),
        "repositories": repositories,
        "verified": True,
        "resource_preflight": {"before_stage": before, "after_stage": after},
    }
    out = OUTPUT_ROOT / CANDIDATE_ID
    out.mkdir(parents=True, exist_ok=True)
    (out / "stage-receipt.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return result


def run_candidate(
    matrix_path: Path = MATRIX_PATH,
    corpus_path: Path = CORPUS_PATH,
    approval_path: Path = APPROVAL_PATH,
    material_root: Path = MATERIAL_ROOT,
) -> dict[str, Any]:
    matrix = _verify_matrix_and_approval(matrix_path, corpus_path, approval_path)
    row = matrix["rows"][0]
    _verify_runtime(row)
    resources = _check_resources(row, material_root, before_stage=False)
    snapshots = _verify_artifacts(row, material_root)
    if snapshots["base"] is None:
        raise ExtensionRunError("pinned Nimble base snapshot is absent")
    if (
        _sha256(INPUTS_PATH) != matrix["normalized_input_sha256"]
        or _sha256(LABELS_PATH) != matrix["gold_label_sha256"]
    ):
        raise ExtensionRunError("normalized input or label digest differs")
    baseline = matrix["baseline_comparison"]
    baseline_path = ROOT / baseline["predictions_path"]
    if _sha256(baseline_path) != baseline["predictions_sha256"]:
        raise ExtensionRunError("baseline Nimble predictions differ from the matrix")

    os.environ["HF_HOME"] = str(material_root)
    os.environ["HF_HUB_CACHE"] = str(material_root)
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    started = time.perf_counter()
    infer, tokenizer, kernel_calls = _load_nimble(
        row, snapshots["model"], snapshots["base"]
    )
    cold_load_ms = (time.perf_counter() - started) * 1000
    input_rows = _read_jsonl(INPUTS_PATH)
    if len(input_rows) != matrix["item_count"]:
        raise ExtensionRunError("normalized input row count differs from matrix")
    token_counts = [
        len(tokenizer.encode(_normalized_text(item))) for item in input_rows
    ]
    max_tokens = max(token_counts)
    if max_tokens > matrix["protocol"]["normalized_content_token_limit"]:
        raise ExtensionRunError("normalized-content token budget exceeded")

    output_dir = OUTPUT_ROOT / CANDIDATE_ID
    smoke_receipt = _run_smoke_check(
        infer, input_rows, baseline_path, kernel_calls, output_dir
    )

    predictions, inference_latency_ms = run_predictions(input_rows, infer)
    predictions_path = output_dir / "predictions.jsonl"
    predictions_path.write_text(
        "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in predictions),
        encoding="utf-8",
    )
    import torch

    counts: dict[str, int] = {}
    for item in predictions:
        counts[item["status"]] = counts.get(item["status"], 0) + 1
    required_kernels_used = all(value > 0 for value in kernel_calls.values())
    result = {
        "candidate_id": CANDIDATE_ID,
        "model": row["model"],
        "base_model": row["base_model"],
        "optimizer": row["optimizer"],
        "runtime": row["runtime"],
        "device": "mps",
        "precision": row["precision"],
        "execution_mode": "in_process",
        "prediction_count": len(predictions),
        "status_counts": counts,
        "failures": len(predictions) - counts.get("ok", 0),
        "cold_load_ms": cold_load_ms,
        "mean_inference_latency_ms": sum(inference_latency_ms)
        / max(len(inference_latency_ms), 1),
        "inference_latency_ms": inference_latency_ms,
        "peak_rss_bytes": int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss),
        "mps_current_allocated_bytes": int(torch.mps.current_allocated_memory()),
        "mps_driver_allocated_bytes": int(torch.mps.driver_allocated_memory()),
        "resource_preflight": resources,
        "common_max_token_count": max_tokens,
        "corpus_manifest_sha256": _sha256(corpus_path),
        "matrix_sha256": _sha256(matrix_path),
        "kernel_calls": kernel_calls,
        "required_metal_kernels_used": required_kernels_used,
        "smoke_comparison": smoke_receipt,
        "host_platform": platform.platform(),
    }
    measurements_path = output_dir / "measurements.json"
    measurements_path.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    if not required_kernels_used:
        raise ExtensionRunError(
            "one or more required optimized Metal kernels were not invoked"
        )
    return {
        "candidate_id": CANDIDATE_ID,
        "prediction_count": len(predictions),
        "status_counts": counts,
        "mean_inference_latency_ms": result["mean_inference_latency_ms"],
        "cold_load_ms": cold_load_ms,
        "peak_rss_bytes": result["peak_rss_bytes"],
        "mps_driver_allocated_bytes": result["mps_driver_allocated_bytes"],
        "kernel_calls": kernel_calls,
        "smoke_comparison": smoke_receipt,
        "predictions_path": str(predictions_path),
        "measurements_path": str(measurements_path),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage-only", action="store_true")
    arguments = parser.parse_args()
    try:
        result = stage_candidate() if arguments.stage_only else run_candidate()
    except (ExtensionRunError, OSError, ValueError, subprocess.SubprocessError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
