#!/usr/bin/env python3
"""Run the separately approved DMS-20 MLX decision-model cohort."""

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
from pathlib import Path
from typing import Any, Callable

from run_dms20_transfer import _normalized_text, ordered_inputs

ROOT = Path(__file__).resolve().parents[2]
EVALUATION = ROOT / "specs/decision-model-support/evaluation"
MATRIX_PATH = EVALUATION / "dms20-mlx-matrix.json"
APPROVAL_PATH = EVALUATION / "dms20-mlx-approval.json"
CORPUS_PATH = EVALUATION / "dms14-corpus-manifest.json"
INPUTS_PATH = Path("/private/tmp/dms20-corpus/normalized-inputs.jsonl")
LABELS_PATH = Path("/private/tmp/dms20-corpus/gold-labels.jsonl")
MATERIAL_ROOT = Path("/private/tmp/dms20-mlx-model-cache")
OUTPUT_ROOT = EVALUATION / "dms20-mlx-run-2026-10-23"
_CANDIDATES = {"qwen35-08b-decision", "d1a-e2b-8bit"}


class MlxRunError(RuntimeError):
    """Raised when the MLX approval or execution contract differs."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _choice_request(state: str, question: dict[str, Any]) -> dict[str, Any]:
    return {
        "state": state,
        "questions": {
            "decision": {
                "type": "choice",
                "instructions": question["text"],
                "criteria": {
                    option["id"]: option["label"] for option in question["options"]
                },
            }
        },
    }


def _map_choice_answer(answer: dict[str, Any], option_ids: list[str]) -> dict[str, Any]:
    scores = answer.get("probabilities", answer)
    if not isinstance(scores, dict) or set(scores) != set(option_ids):
        raise ValueError("choice probabilities must cover the exact option IDs")
    if any(
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(value)
        or not 0 <= value <= 1
        for value in scores.values()
    ) or not math.isclose(sum(scores.values()), 1.0, abs_tol=1e-4):
        raise ValueError("choice probabilities are invalid")
    choice = answer.get("choice", max(scores, key=scores.get))
    if choice not in option_ids or scores[choice] != max(scores.values()):
        raise ValueError("choice differs from the highest probability")
    ordered_ids = [choice, *(key for key in option_ids if key != choice)]
    return {
        "choice": choice,
        "scores": {key: float(scores[key]) for key in ordered_ids},
    }


def _prediction_jsonl(predictions: list[dict[str, Any]]) -> str:
    return "".join(json.dumps(prediction) + "\n" for prediction in predictions)


def _verify_approval(  # noqa: C901 - validates one frozen evaluation contract.
    matrix_path: Path, corpus_path: Path, approval_path: Path
) -> dict[str, Any]:
    matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
    corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    if matrix.get("corpus_manifest_sha256") != _sha256(corpus_path):
        raise MlxRunError("corpus manifest digest differs")
    if matrix.get("normalized_input_sha256") != corpus.get("normalized_input_sha256"):
        raise MlxRunError("normalized input digest differs")
    if matrix.get("gold_label_sha256") != corpus.get("gold_label_sha256"):
        raise MlxRunError("gold label digest differs")
    for item in matrix.get("input_files", {}).values():
        path = Path(item["path"])
        if not path.is_file() or _sha256(path) != item["sha256"]:
            raise MlxRunError("approved normalized input or gold-label file differs")
    dispositions = {row["id"]: row["disposition"] for row in matrix.get("rows", [])}
    runnable = [row["id"] for row in matrix["rows"] if row["disposition"] == "selected"]
    if set(dispositions) != _CANDIDATES or any(
        value != "selected" for value in dispositions.values()
    ):
        raise MlxRunError("matrix must select the exact two approved MLX candidates")
    for item in matrix.get("harness_files", []):
        path = ROOT / item["path"]
        if not path.is_file() or _sha256(path) != item["sha256"]:
            raise MlxRunError("evaluation harness digest differs")
    if not approval_path.is_file():
        raise MlxRunError("matrix approval receipt is absent")
    approval = json.loads(approval_path.read_text(encoding="utf-8"))
    if (
        approval.get("approved") is not True
        or approval.get("matrix_sha256") != _sha256(matrix_path)
        or approval.get("corpus_manifest_sha256") != _sha256(corpus_path)
        or approval.get("approval_scope") != matrix.get("approval_scope")
        or approval.get("dispositions") != dispositions
        or approval.get("runnable_cohort") != runnable
    ):
        raise MlxRunError("approval receipt does not bind the complete MLX matrix")
    return matrix


def _row(matrix: dict[str, Any], candidate_id: str) -> dict[str, Any]:
    row = next((item for item in matrix["rows"] if item["id"] == candidate_id), None)
    if row is None or row["disposition"] != "selected":
        raise MlxRunError("candidate is not selected in the approved matrix")
    return row


def _snapshot(material_root: Path, repository: str, revision: str) -> Path:
    return (
        material_root
        / f"models--{repository.replace('/', '--')}"
        / "snapshots"
        / revision
    )


def _verify_artifacts(row: dict[str, Any], material_root: Path) -> Path:
    snapshots: dict[tuple[str, str], Path] = {}
    for artifact in row["artifact_files"]:
        key = artifact["repository"], artifact["revision"]
        snapshot = snapshots.setdefault(key, _snapshot(material_root, *key))
        path = snapshot / artifact["path"]
        if (
            not path.is_file()
            or path.stat().st_size != artifact["size_bytes"]
            or _sha256(path) != artifact["sha256"]
        ):
            raise MlxRunError(f"pinned artifact differs: {artifact['path']}")
    model = row["model"]
    return _snapshot(material_root, model["id"], model["revision"])


def _stage(
    row: dict[str, Any], matrix: dict[str, Any], matrix_path: Path, material_root: Path
) -> dict[str, Any]:
    from huggingface_hub import snapshot_download

    preflight = _check_resources(row, material_root, before_stage=True)
    material_root.mkdir(parents=True, exist_ok=True)
    for repository, revision in sorted(
        {(item["repository"], item["revision"]) for item in row["artifact_files"]}
    ):
        snapshot_download(
            repository,
            revision=revision,
            cache_dir=str(material_root),
            allow_patterns=matrix["artifact_download_allow_patterns"],
            ignore_patterns=matrix["artifact_download_ignore_patterns"],
        )
    snapshot = _verify_artifacts(row, material_root)
    postflight = _check_resources(row, material_root, before_stage=False)
    receipt = {
        "candidate_id": row["id"],
        "verified": True,
        "matrix_sha256": _sha256(matrix_path),
        "resource_preflight": {"before_stage": preflight, "after_stage": postflight},
    }
    output = OUTPUT_ROOT / row["id"]
    output.mkdir(parents=True, exist_ok=True)
    (output / "stage-receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    )
    return {**receipt, "snapshot": str(snapshot)}


def _load_model(
    row: dict[str, Any], model_dir: Path
) -> tuple[Callable[[dict[str, Any]], dict[str, Any]], Any]:
    if row["id"] == "qwen35-08b-decision":
        from optiq.decision import DecisionModel
        from transformers import AutoTokenizer

        model = DecisionModel.load(str(model_dir))
        tokenizer = AutoTokenizer.from_pretrained(str(model_dir), local_files_only=True)

        def infer(item: dict[str, Any]) -> dict[str, Any]:
            answer = model.predict(
                _choice_request(_normalized_text(item), item["question"])
            )["decision"]
            return _map_choice_answer(
                answer, [option["id"] for option in item["question"]["options"]]
            )

        return infer, tokenizer

    from d1a import D1A

    model = D1A.load(str(model_dir))

    def infer(item: dict[str, Any]) -> dict[str, Any]:
        answer = model.decide(
            _normalized_text(item), _choice_request("", item["question"])["questions"]
        )["decision"]
        return _map_choice_answer(
            answer, [option["id"] for option in item["question"]["options"]]
        )

    return infer, model.tok


def _runtime(row: dict[str, Any]) -> None:
    lock = ROOT / row["runtime"]["lock_path"]
    if (
        _sha256(lock) != row["runtime"]["lock_sha256"]
        or sys.version.split()[0] != row["runtime"]["python_version"]
    ):
        raise MlxRunError("runtime lock or Python version differs from the matrix")
    for package, version in row["runtime"]["packages"].items():
        if importlib.metadata.version(package) != version:
            raise MlxRunError(f"runtime package differs: {package}")
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        raise MlxRunError("MLX evaluation requires Apple silicon macOS")
    import mlx.core as mx

    if mx.default_device().type != mx.DeviceType.gpu:
        raise MlxRunError("MLX GPU device is unavailable")


def _check_resources(
    row: dict[str, Any], material_root: Path, *, before_stage: bool
) -> dict[str, int]:
    floors = row["resource_floor"]
    if sys.platform != "darwin":
        raise MlxRunError("MLX evaluation requires macOS")
    output = subprocess.run(
        ["memory_pressure"], capture_output=True, check=True, text=True, timeout=5
    ).stdout
    marker = "System-wide memory free percentage:"
    line = next((item for item in output.splitlines() if item.startswith(marker)), None)
    if line is None:
        raise MlxRunError("could not read current macOS memory pressure")
    free_percent = int(line.removeprefix(marker).strip().rstrip("%"))
    total_memory = int(os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE"))
    free_memory = total_memory * free_percent // 100
    if free_memory < floors["minimum_free_memory_bytes"]:
        raise MlxRunError("current free memory is below the approved candidate floor")
    free_disk = shutil.disk_usage(
        material_root if material_root.exists() else material_root.parent
    ).free
    floor_name = (
        "minimum_free_disk_before_stage_bytes"
        if before_stage
        else "minimum_free_disk_after_stage_bytes"
    )
    if free_disk < floors[floor_name]:
        raise MlxRunError("current free disk is below the approved candidate floor")
    return {"free_memory_bytes_estimate": free_memory, "free_disk_bytes": free_disk}


def run_candidate(
    candidate_id: str,
    matrix_path: Path = MATRIX_PATH,
    corpus_path: Path = CORPUS_PATH,
    approval_path: Path = APPROVAL_PATH,
    material_root: Path = MATERIAL_ROOT,
) -> dict[str, Any]:
    matrix = _verify_approval(matrix_path, corpus_path, approval_path)
    row = _row(matrix, candidate_id)
    _runtime(row)
    resources = _check_resources(row, material_root, before_stage=False)
    model_dir = _verify_artifacts(row, material_root)
    if (
        _sha256(INPUTS_PATH) != matrix["normalized_input_sha256"]
        or _sha256(LABELS_PATH) != matrix["gold_label_sha256"]
    ):
        raise MlxRunError("normalized inputs or labels differ from the approved corpus")
    os.environ.update(
        HF_HOME=str(material_root),
        HF_HUB_CACHE=str(material_root),
        HF_HUB_OFFLINE="1",
        TRANSFORMERS_OFFLINE="1",
    )
    started = time.perf_counter()
    infer, tokenizer = _load_model(row, model_dir)
    cold_load_ms = (time.perf_counter() - started) * 1000
    input_rows = [
        json.loads(line)
        for line in INPUTS_PATH.read_text(encoding="utf-8").splitlines()
    ]
    max_tokens = max(
        len(tokenizer.encode(_normalized_text(item))) for item in input_rows
    )
    if max_tokens > matrix["protocol"]["normalized_content_token_limit"]:
        raise MlxRunError("common normalized-content token budget exceeded")
    predictions, latencies = [], []
    total = len(input_rows) * 2
    for order in ("canonical", "reversed"):
        for item in ordered_inputs(input_rows, order):
            started = time.perf_counter()
            try:
                options = item["question"]["options"]
                raw = infer(item)
                mapped = _map_choice_answer(
                    {"choice": raw["choice"], "probabilities": raw["scores"]},
                    [o["id"] for o in options],
                )
                prediction = {
                    "id": item["id"],
                    "option_order": order,
                    "status": "ok",
                    **mapped,
                    "score_semantics": "probability",
                }
            except Exception as exc:  # output is redacted to avoid writing input-bearing exception strings
                prediction = {
                    "id": item["id"],
                    "option_order": order,
                    "status": "invalid" if isinstance(exc, ValueError) else "error",
                }
            latencies.append((time.perf_counter() - started) * 1000)
            predictions.append(prediction)
            print(f"progress {len(predictions)}/{total}", file=sys.stderr, flush=True)
    output = OUTPUT_ROOT / candidate_id
    output.mkdir(parents=True, exist_ok=True)
    (output / "predictions.jsonl").write_text(_prediction_jsonl(predictions))
    import mlx.core as mx

    receipt = {
        "candidate_id": candidate_id,
        "model": row["model"],
        "runtime": row["runtime"],
        "item_count": len(input_rows),
        "prediction_count": len(predictions),
        "failures": sum(p["status"] != "ok" for p in predictions),
        "cold_load_ms": cold_load_ms,
        "inference_latency_ms": latencies,
        "resource_preflight": resources,
        "peak_rss_bytes": int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss),
        "mlx_active_memory_bytes": int(mx.get_active_memory()),
        "mlx_peak_memory_bytes": int(mx.get_peak_memory()),
        "matrix_sha256": _sha256(matrix_path),
        "corpus_manifest_sha256": _sha256(corpus_path),
        "host_platform": platform.platform(),
        "common_max_token_count": max_tokens,
    }
    (output / "measurements.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    )
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", choices=sorted(_CANDIDATES), required=True)
    parser.add_argument("--stage-only", action="store_true")
    parser.add_argument("--matrix", type=Path, default=MATRIX_PATH)
    parser.add_argument("--corpus-manifest", type=Path, default=CORPUS_PATH)
    parser.add_argument("--approval", type=Path, default=APPROVAL_PATH)
    parser.add_argument("--material-root", type=Path, default=MATERIAL_ROOT)
    args = parser.parse_args()
    try:
        matrix = _verify_approval(args.matrix, args.corpus_manifest, args.approval)
        row = _row(matrix, args.candidate)
        result = (
            _stage(row, matrix, args.matrix, args.material_root)
            if args.stage_only
            else run_candidate(
                args.candidate,
                args.matrix,
                args.corpus_manifest,
                args.approval,
                args.material_root,
            )
        )
    except (MlxRunError, OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
