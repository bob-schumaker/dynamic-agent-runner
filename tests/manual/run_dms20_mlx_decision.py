#!/usr/bin/env python3
"""Run the separately approved DMS-20 MLX decision-model matrix."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import math
import os
import platform
import resource
import shutil
import subprocess
import sys
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

from run_dms20_transfer import _normalized_text, ordered_inputs


ROOT = Path(__file__).resolve().parents[2]
EVALUATION = ROOT / "specs/decision-model-support/evaluation"
MATRIX_PATH = EVALUATION / "dms20-mlx-decision-matrix.json"
APPROVAL_PATH = EVALUATION / "dms20-mlx-decision-approval.json"
CORPUS_PATH = EVALUATION / "dms14-corpus-manifest.json"
INPUTS_PATH = Path("/private/tmp/dms20-corpus/normalized-inputs.jsonl")
MATERIAL_ROOT = Path("/private/tmp/dms20-mlx-decision-work")
OUTPUT_ROOT = EVALUATION / "dms20-mlx-decision-run-2026-10-24"
_STATUSES = {"ok", "invalid", "missing", "timeout", "oversize", "error", "abstained"}


class MlxDecisionRunError(RuntimeError):
    """Raised when the frozen MLX decision evaluation contract differs."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _choice_question(question: dict[str, Any]) -> Any:
    from mlx_decision import Choice

    return Choice(
        instructions=question["text"],
        criteria={option["id"]: option["label"] for option in question["options"]},
    )


def _map_choice_answer(answer: Any, option_ids: list[str]) -> dict[str, Any]:
    choice = (
        answer.get("choice")
        if isinstance(answer, dict)
        else getattr(answer, "choice", None)
    )
    probabilities = (
        answer.get("probabilities")
        if isinstance(answer, dict)
        else getattr(answer, "probabilities", None)
    )
    if not isinstance(probabilities, dict) or set(probabilities) != set(option_ids):
        raise ValueError("choice probabilities must cover the exact option IDs")
    if (
        any(
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not math.isfinite(value)
            or not 0 <= value <= 1
            for value in probabilities.values()
        )
        or abs(sum(probabilities.values()) - 1.0) > 1e-4
    ):
        raise ValueError("choice probabilities are invalid")
    if choice not in option_ids or probabilities[choice] != max(probabilities.values()):
        raise ValueError("choice differs from the highest probability")
    ordered = [choice, *(key for key in option_ids if key != choice)]
    return {
        "choice": choice,
        "scores": {key: float(probabilities[key]) for key in ordered},
    }


def _map_d1a_answer(answer: dict[str, Any], option_ids: list[str]) -> dict[str, Any]:
    from run_dms20_mlx_extension import _map_choice_answer as map_answer

    return map_answer(answer, option_ids)


def _token_count(tokenizer: Any, text: str) -> int:
    try:
        return len(tokenizer.encode(text, add_special_tokens=False))
    except TypeError:
        return len(tokenizer.encode(text))


def run_rows(
    input_rows: list[dict[str, Any]],
    model: Any,
    *,
    family: str = "mlx-decision",
    tokenizer: Any = None,
    content_token_limit: int = 3584,
) -> list[dict[str, Any]]:
    predictions: list[dict[str, Any]] = []
    total = len(input_rows) * 2
    for order in ("canonical", "reversed"):
        for item in ordered_inputs(input_rows, order):
            option_ids = [option["id"] for option in item["question"]["options"]]
            started = time.perf_counter()
            state = _normalized_text(item)
            if (
                tokenizer is not None
                and _token_count(tokenizer, state) > content_token_limit
            ):
                predictions.append(
                    {
                        "id": item["id"],
                        "option_order": order,
                        "status": "oversize",
                        "latency_ms": 0.0,
                    }
                )
                print(
                    f"progress {len(predictions)}/{total}", file=sys.stderr, flush=True
                )
                continue
            try:
                if family == "d1a":
                    questions = {
                        "decision": {
                            "type": "choice",
                            "instructions": item["question"]["text"],
                            "criteria": {
                                option["id"]: option["label"]
                                for option in item["question"]["options"]
                            },
                        }
                    }
                    raw = model.decide(state, questions)["decision"]
                    mapped = _map_d1a_answer(raw, option_ids)
                    truncated = False
                else:
                    questions = {"decision": _choice_question(item["question"])}
                    result = model.decide(state, questions)
                    truncated = bool(result.truncated)
                    mapped = _map_choice_answer(result.answers["decision"], option_ids)
                if truncated:
                    prediction = {
                        "id": item["id"],
                        "option_order": order,
                        "status": "oversize",
                    }
                else:
                    prediction = {
                        "id": item["id"],
                        "option_order": order,
                        "status": "ok",
                        **mapped,
                        "score_semantics": "probability",
                    }
            except (
                Exception
            ) as exc:  # input text in exception details is never written.
                name = type(exc).__name__
                message = str(getattr(exc, "message", exc)).lower()
                too_long = (
                    "limit" in message
                    or "longer than" in message
                    or (
                        "token" in message
                        and ("more than" in message or "needs" in message)
                    )
                )
                status = (
                    "oversize"
                    if too_long
                    else ("invalid" if isinstance(exc, ValueError) else "error")
                )
                prediction = {"id": item["id"], "option_order": order, "status": status}
                prediction["error_type"] = name
            prediction["latency_ms"] = (time.perf_counter() - started) * 1000
            predictions.append(prediction)
            print(f"progress {len(predictions)}/{total}", file=sys.stderr, flush=True)
    return predictions


def verify_matrix(  # noqa: C901 - validates one frozen evaluation contract.
    matrix_path: Path, approval_path: Path, corpus_path: Path
) -> dict[str, Any]:
    matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
    approval = json.loads(approval_path.read_text(encoding="utf-8"))
    corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    if _sha256(corpus_path) != matrix["corpus_manifest_sha256"]:
        raise MlxDecisionRunError("corpus manifest digest differs")
    if matrix["normalized_input_sha256"] != corpus["normalized_input_sha256"]:
        raise MlxDecisionRunError("normalized input digest differs")
    if matrix["gold_label_sha256"] != corpus["gold_label_sha256"]:
        raise MlxDecisionRunError("gold-label digest differs")
    if _sha256(INPUTS_PATH) != matrix["normalized_input_sha256"]:
        raise MlxDecisionRunError("normalized input file digest differs")
    rows = matrix["rows"]
    dispositions = {row["id"]: row["disposition"] for row in rows}
    if len(dispositions) != len(rows) or any(
        v not in {"selected", "unsupported"} for v in dispositions.values()
    ):
        raise MlxDecisionRunError("matrix dispositions are malformed")
    runnable = [row["id"] for row in rows if row["disposition"] == "selected"]
    if (
        approval.get("approved") is not True
        or approval.get("matrix_sha256") != _sha256(matrix_path)
        or approval.get("corpus_manifest_sha256") != _sha256(corpus_path)
        or approval.get("approval_scope") != matrix.get("approval_scope")
        or approval.get("dispositions") != dispositions
        or approval.get("runnable_cohort") != runnable
    ):
        raise MlxDecisionRunError("approval receipt does not bind the complete matrix")
    for item in matrix["harness_files"]:
        path = ROOT / item["path"]
        if not path.is_file() or _sha256(path) != item["sha256"]:
            raise MlxDecisionRunError("evaluation harness digest differs")
    for item in matrix["input_files"].values():
        path = Path(item["path"])
        if not path.is_file() or _sha256(path) != item["sha256"]:
            raise MlxDecisionRunError("approved corpus input file differs")
    return matrix


def _check_resources(row: dict[str, Any], *, before_stage: bool) -> dict[str, int]:
    floors = row["resource_floor"]
    output = subprocess.run(
        ["memory_pressure"], capture_output=True, check=True, text=True, timeout=5
    ).stdout
    marker = "System-wide memory free percentage:"
    line = next(
        (value for value in output.splitlines() if value.startswith(marker)), None
    )
    if line is None:
        raise MlxDecisionRunError("could not read current macOS memory pressure")
    percent = int(line.removeprefix(marker).strip().rstrip("%"))
    total = int(os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE"))
    free_memory = total * percent // 100
    free_disk = shutil.disk_usage(MATERIAL_ROOT.parent).free
    disk_floor = floors[
        "minimum_free_disk_before_stage_bytes"
        if before_stage
        else "minimum_free_disk_after_stage_bytes"
    ]
    if free_memory < floors["minimum_free_memory_bytes"] or free_disk < disk_floor:
        raise MlxDecisionRunError(
            "current free memory or disk is below the frozen row floor"
        )
    return {"free_memory_bytes_estimate": free_memory, "free_disk_bytes": free_disk}


def _artifact_hashes(root: Path) -> list[dict[str, Any]]:
    return [
        {
            "path": path.relative_to(root).as_posix(),
            "size_bytes": path.stat().st_size,
            "sha256": _sha256(path),
        }
        for path in sorted(root.rglob("*"))
        if path.is_file()
    ]


def _stage(row: dict[str, Any], runtime_root: Path) -> tuple[Path, dict[str, Any]]:
    from huggingface_hub import snapshot_download

    model_dir = runtime_root / "model"
    repo, revision = row["model"]["id"], row["model"]["revision"]
    preflight = _check_resources(row, before_stage=True)
    if row["runtime"]["kind"] == "mlx-decision" and row.get("bits"):
        from mlx_decision.download import check_repo, download_quantized, record_source

        check = check_repo(repo)
        if check.revision != revision:
            raise MlxDecisionRunError(
                "Hub source revision differs from the pinned model revision"
            )
        download_quantized(check, row["bits"], model_dir, draw=True)
        source_revision = check.revision
        record_source(model_dir, repo, revision)
        source_marker = json.loads((model_dir / ".download.json").read_text())
        if source_marker != {"repo": repo, "revision": revision}:
            raise MlxDecisionRunError(
                "quantized model source marker differs from pinned model"
            )
    else:
        snapshot_download(
            repo,
            revision=revision,
            local_dir=str(model_dir),
            allow_patterns=row.get("artifact_patterns"),
        )
        source_revision = revision
        for artifact in row["artifact_files"]:
            path = model_dir / artifact["path"]
            if (
                not path.is_file()
                or path.stat().st_size != artifact["size_bytes"]
                or _sha256(path) != artifact["sha256"]
            ):
                raise MlxDecisionRunError(
                    f"pinned model artifact differs: {artifact['path']}"
                )
    hashes = _artifact_hashes(model_dir)
    postflight = _check_resources(row, before_stage=False)
    stage = {
        "source_revision": source_revision,
        "artifacts": hashes,
        "resource_preflight": {"before_stage": preflight, "after_stage": postflight},
    }
    return model_dir, stage


def _load_model(row: dict[str, Any], model_dir: Path) -> tuple[Any, Any]:
    if row["runtime"]["kind"] == "mlx-decision":
        import mlx_decision

        options: dict[str, Any] = {}
        if row["id"] in {
            "clef-flash-mlx-8bit",
            "h2o-lightning-4b-mlx-8bit",
            "liquidai-d1-3b",
        }:
            options["prefix_cache_gb"] = 0
        model = mlx_decision.load(model_dir, **options)
        if model.info()["family"] == "laya":
            model.backend.settings.strict = True
            model.backend.capabilities = replace(
                model.backend.capabilities, truncates_input=False
            )
        return model, model.backend.tokenizer

    from d1a import D1A
    from transformers import AutoTokenizer

    model = D1A.load(str(model_dir))
    tokenizer = AutoTokenizer.from_pretrained(str(model_dir), local_files_only=True)
    return model, tokenizer


def _check_runtime(row: dict[str, Any]) -> None:
    runtime = row["runtime"]
    lock = ROOT / runtime["lock_path"]
    if (
        _sha256(lock) != runtime["lock_sha256"]
        or sys.version.split()[0] != runtime["python_version"]
    ):
        raise MlxDecisionRunError("runtime lock or Python version differs")
    for package, version in runtime["packages"].items():
        if importlib.metadata.version(package) != version:
            raise MlxDecisionRunError(f"runtime package differs: {package}")
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        raise MlxDecisionRunError("MLX evaluation requires Apple silicon macOS")
    import mlx.core as mx

    if mx.default_device().type != mx.DeviceType.gpu:
        raise MlxDecisionRunError("MLX GPU device is unavailable")


def run_candidate(
    candidate_id: str, matrix_path: Path, approval_path: Path, corpus_path: Path
) -> dict[str, Any]:
    matrix = verify_matrix(matrix_path, approval_path, corpus_path)
    row = next((item for item in matrix["rows"] if item["id"] == candidate_id), None)
    if row is None or row["disposition"] != "selected":
        raise MlxDecisionRunError("candidate is not selected in the approved matrix")
    _check_runtime(row)
    inputs = [
        json.loads(line)
        for line in INPUTS_PATH.read_text(encoding="utf-8").splitlines()
    ]
    MATERIAL_ROOT.mkdir(parents=True, exist_ok=True)
    work = MATERIAL_ROOT / candidate_id
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    try:
        model_dir, stage = _stage(row, work)
        load_started = time.perf_counter()
        model, tokenizer = _load_model(row, model_dir)
        cold_load_ms = (time.perf_counter() - load_started) * 1000
        token_counts = {}
        for order in ("canonical", "reversed"):
            for item in ordered_inputs(inputs, order):
                token_counts[(item["id"], order)] = _token_count(
                    tokenizer, _normalized_text(item)
                )
        max_tokens = max(token_counts.values(), default=0)
        oversized_tokens = sum(
            count > matrix["protocol"]["normalized_content_token_limit"]
            for count in token_counts.values()
        )
        started = time.perf_counter()
        predictions = run_rows(
            inputs,
            model,
            family=row["runtime"]["kind"],
            tokenizer=tokenizer,
            content_token_limit=matrix["protocol"]["normalized_content_token_limit"],
        )
        elapsed_ms = (time.perf_counter() - started) * 1000
        OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
        output = OUTPUT_ROOT / candidate_id
        output.mkdir(parents=True, exist_ok=True)
        (output / "predictions.jsonl").write_text(
            "".join(json.dumps(item, sort_keys=True) + "\n" for item in predictions),
            encoding="utf-8",
        )
        import mlx.core as mx

        measurements = {
            "candidate_id": candidate_id,
            "model": row["model"],
            "runtime": row["runtime"],
            "item_count": len(inputs),
            "prediction_count": len(predictions),
            "failed_outputs": sum(item["status"] != "ok" for item in predictions),
            "oversize_outputs": sum(
                item["status"] == "oversize" for item in predictions
            ),
            "elapsed_inference_ms": elapsed_ms,
            "mean_prediction_latency_ms": sum(
                item["latency_ms"] for item in predictions
            )
            / len(predictions),
            "cold_load_ms": cold_load_ms,
            "peak_rss_bytes": int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss),
            "mlx_active_memory_bytes": int(mx.get_active_memory()),
            "mlx_peak_memory_bytes": int(mx.get_peak_memory()),
            "max_normalized_input_tokens": max_tokens,
            "normalized_inputs_over_content_limit": oversized_tokens,
            "stage": stage,
            "matrix_sha256": _sha256(matrix_path),
            "corpus_manifest_sha256": _sha256(corpus_path),
            "host_platform": platform.platform(),
        }
        (output / "measurements.json").write_text(
            json.dumps(measurements, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return measurements
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--matrix", type=Path, default=MATRIX_PATH)
    parser.add_argument("--approval", type=Path, default=APPROVAL_PATH)
    parser.add_argument("--corpus-manifest", type=Path, default=CORPUS_PATH)
    args = parser.parse_args()
    try:
        result = run_candidate(
            args.candidate, args.matrix, args.approval, args.corpus_manifest
        )
    except (MlxDecisionRunError, OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
