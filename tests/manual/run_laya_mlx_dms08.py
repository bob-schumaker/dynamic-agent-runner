#!/usr/bin/env python3
"""Evaluate the pinned Laya-MLX checkpoint on frozen DMS-01 inputs."""

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
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
INPUTS_SHA256 = "6d0230190f455d3f488881ef0f709881fba783f33bab4d5a6a93db576cf5c73f"
SOURCE_ID = "mizorewww/laya-mlx"
SOURCE_REVISION = "0a859518634112655cb97c745dbf04f5191aaf13"
MODEL_ID = "aac6fef/laya-typed-decisions-mlx"
MODEL_REVISION = "28416e78cb26a239a4eabaa2e084904ec5e6cacb"
BASE_MODEL_ID = "convaiinnovations/laya-typed-decisions"
BASE_MODEL_REVISION = "f9ab0b228f0fc0f14d873dbc99038f135c2da1b2"
MODEL_SHA256 = "804ef8802b4cac7a67913b0cfb8448659e934a50284aaa867b98d7d9a6e7d1e0"
MAX_INPUT_TOKENS = 1024
RUNTIME_PACKAGES = {
    "huggingface-hub": "1.33.0",
    "mlx": "0.32.2",
    "numpy": "2.5.3",
    "tokenizers": "0.23.2",
}
EXPECTED_SOURCE = {"id": SOURCE_ID, "revision": SOURCE_REVISION}
EXPECTED_ARTIFACTS = [{"id": MODEL_ID, "revision": MODEL_REVISION}]
EXPECTED_BASE = {"id": BASE_MODEL_ID, "revision": BASE_MODEL_REVISION}
EXPECTED_MODEL_FILES = {"model.safetensors": MODEL_SHA256}


class ManualRunError(RuntimeError):
    """Raised when the candidate-specific evaluation gate is not satisfied."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _repository_revision(path: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"],
        capture_output=True, check=True, text=True, timeout=5,
    )
    return result.stdout.strip()


def _repository_clean(path: Path) -> bool:
    result = subprocess.run(
        ["git", "-C", str(path), "status", "--porcelain", "--untracked-files=all"],
        capture_output=True, check=True, text=True, timeout=5,
    )
    return not result.stdout.strip()


def _runtime_versions() -> tuple[dict[str, str | None], bool]:
    versions: dict[str, str | None] = {}
    for package in RUNTIME_PACKAGES:
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = None
    return versions, versions == RUNTIME_PACKAGES


def _expected_harness_files() -> list[dict[str, str]]:
    paths = (ROOT / "scripts" / "evaluate_decision_models.py", Path(__file__).resolve())
    return [{"id": str(path.relative_to(ROOT)), "sha256": _sha256(path)} for path in paths]


def _detect_accelerator() -> str:
    try:
        import mlx.core as mx

        if mx.default_device() == mx.gpu:
            return "Metal available"
        return f"MLX default device is {mx.default_device()}"
    except Exception as exc:  # noqa: BLE001 - preflight must record unavailable backends.
        return f"Metal unavailable: {type(exc).__name__}: {exc}"


def _verify_receipt_pins(receipt: dict[str, Any]) -> None:
    if receipt.get("candidate_run_approved") is not True:
        raise ManualRunError("candidate-specific Laya-MLX run approval is absent")
    if receipt.get("run_allowed") is not True:
        raise ManualRunError("preflight did not allow model download and inference")
    if receipt.get("fixture_criteria_approved") is not True or receipt.get("input_sha256") != INPUTS_SHA256:
        raise ManualRunError("preflight fixture approval or input hash differs")
    if receipt.get("source") != EXPECTED_SOURCE:
        raise ManualRunError("Laya-MLX source revision differs from preflight")
    if receipt.get("artifacts") != EXPECTED_ARTIFACTS:
        raise ManualRunError("Laya-MLX model revision differs from preflight")
    if receipt.get("provenance_base") != EXPECTED_BASE:
        raise ManualRunError("Laya provenance base differs from preflight")
    if receipt.get("expected_model_file_sha256") != EXPECTED_MODEL_FILES:
        raise ManualRunError("Laya-MLX model digest differs from preflight")


def _verify_runtime_and_source(
    receipt: dict[str, Any], *, source_checkout: Path, runtime_checkout: Path
) -> None:
    runtime = receipt.get("runtime")
    if (
        not isinstance(runtime, dict)
        or runtime.get("available") is not True
        or Path(runtime.get("executable", "")).resolve() != Path(sys.executable).resolve()
        or runtime.get("python_version") != sys.version.split()[0]
        or runtime.get("packages") != RUNTIME_PACKAGES
        or not runtime.get("lock_sha256")
    ):
        raise ManualRunError("exact pinned Laya-MLX runtime is unavailable")
    lock_path = runtime_checkout / "poetry.lock"
    if not lock_path.is_file() or _sha256(lock_path) != runtime["lock_sha256"]:
        raise ManualRunError("isolated Poetry runtime lock differs from preflight")
    versions, available = _runtime_versions()
    if not available or versions != RUNTIME_PACKAGES:
        raise ManualRunError("installed Laya-MLX runtime differs from preflight")
    if _repository_revision(source_checkout) != SOURCE_REVISION or not _repository_clean(source_checkout):
        raise ManualRunError("Laya-MLX source checkout is not the pinned clean revision")
    if receipt.get("evaluation_harness_files") != _expected_harness_files():
        raise ManualRunError("evaluation harness files differ from preflight")


def verify_preflight(
    receipt: dict[str, Any], *, source_checkout: Path, runtime_checkout: Path
) -> None:
    _verify_receipt_pins(receipt)
    _verify_runtime_and_source(
        receipt, source_checkout=source_checkout, runtime_checkout=runtime_checkout
    )


def create_preflight_receipt(
    *, source_checkout: Path, runtime_checkout: Path, storage_path: Path,
    candidate_run_approved: bool,
    required_free_storage_bytes: int = 8 * 1024**3,
) -> dict[str, Any]:
    storage_path.mkdir(parents=True, exist_ok=True)
    inputs = ROOT / "specs" / "decision-model-support" / "evaluation" / "dms01-inputs.jsonl"
    fixture_hash = _sha256(inputs) if inputs.is_file() else ""
    versions, packages_available = _runtime_versions()
    accelerator_status = _detect_accelerator()
    lock_path = runtime_checkout / "poetry.lock"
    lock_hash = _sha256(lock_path) if lock_path.is_file() else ""
    source_revision = _repository_revision(source_checkout) if source_checkout.is_dir() else ""
    source_clean = _repository_clean(source_checkout) if source_checkout.is_dir() else False
    free_storage = shutil.disk_usage(storage_path).free
    memory = None
    try:
        memory = int(os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE"))
    except (AttributeError, OSError, ValueError):
        pass
    blockers = []
    if not candidate_run_approved:
        blockers.append("candidate-specific Laya-MLX run approval is absent")
    if fixture_hash != INPUTS_SHA256:
        blockers.append("frozen input fixture hash does not match")
    if source_revision != SOURCE_REVISION or not source_clean:
        blockers.append("pinned Laya-MLX source revision or clean checkout check failed")
    if not lock_hash or not packages_available:
        blockers.append("exact isolated Laya-MLX Poetry runtime is unavailable")
    if free_storage < required_free_storage_bytes:
        blockers.append("available storage is below the 8 GiB requirement")
    if memory is None or memory < 24 * 1024**3:
        blockers.append("host does not meet the 24 GiB evaluation memory ceiling")
    if accelerator_status != "Metal available":
        blockers.append("MLX Metal device is unavailable")
    return {
        "created_at_utc": datetime.now(UTC).isoformat(),
        "candidate_run_approved": candidate_run_approved,
        "fixture_criteria_approved": True,
        "input_sha256": INPUTS_SHA256,
        "source": EXPECTED_SOURCE,
        "artifacts": EXPECTED_ARTIFACTS,
        "provenance_base": EXPECTED_BASE,
        "expected_model_file_sha256": EXPECTED_MODEL_FILES,
        "evaluation_harness_files": _expected_harness_files(),
        "runtime": {
            "available": packages_available and bool(lock_hash),
            "executable": str(Path(sys.executable).resolve()),
            "python_version": sys.version.split()[0],
            "packages": versions,
            "lock_sha256": lock_hash,
        },
        "host": {
            "platform": platform.platform(), "architecture": platform.machine(),
            "total_memory_bytes": memory, "storage_path": str(storage_path),
            "free_storage_bytes": free_storage,
            "required_free_storage_bytes": required_free_storage_bytes,
            "accelerator_status": accelerator_status,
        },
        "execution_mode": "external_in_process_mlx",
        "remote_code_allowed": False,
        "blockers": blockers,
        "run_allowed": not blockers,
    }


def build_request(row: dict[str, Any]) -> dict[str, Any]:
    if row.get("kind") == "decision":
        question = row["question"]
        options = question["options"]
        if len(options) < 2 or len({item["id"] for item in options}) != len(options):
            raise ManualRunError("decision fixture options are invalid")
        questions = {
            question["id"]: {
                "type": "choice",
                "instructions": question["text"],
                "criteria": {item["id"]: item["label"] for item in options},
            }
        }
        state = row["state"]
    elif row.get("kind") == "retention":
        messages = row["eligible_messages_oldest_first"]
        if len({item["id"] for item in messages}) != len(messages):
            raise ManualRunError("retention fixture message IDs are invalid")
        questions = {
            item["id"]: {
                "type": "choice",
                "instructions": (
                    "Should this candidate message be retained in active context to complete "
                    "the task?\nCandidate message:\n" + item["content"]
                ),
                "criteria": {
                    "keep": "Retain this message in active context.",
                    "drop": "The active context can omit this message.",
                },
            }
            for item in messages
        }
        state = row["task_context"]
    else:
        raise ManualRunError("unsupported frozen input row kind")
    return {"state": state, "questions": questions}


def _validate_answer(answer: dict[str, Any], option_ids: set[str]) -> dict[str, float]:
    if answer.get("type") != "choice" or answer.get("choice") not in option_ids:
        raise ManualRunError("Laya returned an invalid choice answer")
    raw = answer.get("probabilities")
    if not isinstance(raw, dict) or set(raw) != option_ids:
        raise ManualRunError("Laya returned an incomplete probability distribution")
    try:
        values = {key: float(value) for key, value in raw.items()}
    except (TypeError, ValueError) as exc:
        raise ManualRunError("Laya returned invalid probabilities") from exc
    if any(not math.isfinite(value) or not 0 <= value <= 1 for value in values.values()):
        raise ManualRunError("Laya returned invalid probabilities")
    total = sum(values.values())
    rounding_tolerance = 0.00005 * len(values) + 1e-6
    if not math.isclose(total, 1, abs_tol=rounding_tolerance):
        raise ManualRunError("Laya probabilities do not sum to one")
    values = {key: value / total for key, value in values.items()}
    if values[answer["choice"]] + 0.00011 < max(values.values()):
        raise ManualRunError("Laya choice does not match its probability distribution")
    return values


def _ensure_context_fits(agent: Any, request: dict[str, Any]) -> None:
    from laya_mlx.common import build_prefix, serialize_state

    max_len = int(agent.cfg.get("max_len", MAX_INPUT_TOKENS))
    for question in request["questions"].values():
        internal = agent._to_internal(question)
        prefix, _markers = build_prefix(agent.tok, internal, agent.cfg.get("head_max_len", 192))
        state = serialize_state(request["state"]).replace(agent.tok.mask_token, " ")
        state_tokens = len(agent.tok(state, add_special_tokens=False)["input_ids"])
        if len(prefix) + state_tokens + 1 > max_len:
            raise ManualRunError("input exceeds Laya-MLX context limit")


def score_input_rows(
    rows: list[dict[str, Any]], *, agent: Any, tokenizer: Any,
    context_check: Any | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[float], int, bool]:
    predictions, token_counts, latencies = [], [], []
    oom = False
    for row in rows:
        request = build_request(row)
        if row["kind"] == "retention":
            token_counts.extend(
                {"message_id": item["id"], "token_count": len(tokenizer(item["content"])["input_ids"])}
                for item in row["eligible_messages_oldest_first"]
            )
        status = "ok"
        try:
            (context_check or _ensure_context_fits)(agent, request)
            started = time.perf_counter()
            try:
                result = agent.predict(request["state"], request["questions"])
            finally:
                latencies.append((time.perf_counter() - started) * 1000)
            answers = result.get("answers")
            if not isinstance(answers, dict) or set(answers) != set(request["questions"]):
                raise ManualRunError("Laya returned missing or unexpected answers")
            scores = {
                question_id: _validate_answer(
                    answers[question_id],
                    set(request["questions"][question_id]["criteria"]),
                )
                for question_id in request["questions"]
            }
        except ManualRunError as exc:
            status = "oversize" if "context limit" in str(exc) else "invalid"
        except TimeoutError:
            status = "timeout"
        except Exception as exc:  # noqa: BLE001 - do not expose model/input errors in receipts.
            status = "error"
            oom = oom or "out of memory" in str(exc).lower() or "outofmemory" in type(exc).__name__.lower()
        if status != "ok":
            predictions.append({"id": row["id"], "kind": row["kind"], "status": status})
        elif row["kind"] == "decision":
            qid = next(iter(scores))
            values = scores[qid]
            predictions.append({
                "id": row["id"], "kind": "decision", "status": "ok",
                "choice": max(values, key=values.get), "score_semantics": "probability",
                "scores": values,
            })
        else:
            predictions.append({
                "id": row["id"], "kind": "retention", "status": "ok",
                "score_semantics": "probability",
                "scores": {qid: values["keep"] for qid, values in scores.items()},
            })
    peak_memory = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    if sys.platform != "darwin":
        peak_memory *= 1024
    return predictions, token_counts, latencies, peak_memory, oom


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def _load_agent(source_checkout: Path, model_directory: Path) -> Any:
    from huggingface_hub import snapshot_download

    model_path = Path(snapshot_download(
        repo_id=MODEL_ID, revision=MODEL_REVISION, local_dir=str(model_directory)
    ))
    for filename, expected in EXPECTED_MODEL_FILES.items():
        path = model_path / filename
        if not path.is_file() or _sha256(path) != expected:
            raise ManualRunError("downloaded Laya-MLX weight digest differs from the pin")
    os.environ["HF_HUB_OFFLINE"] = "1"
    sys.path.insert(0, str(source_checkout))
    import laya_mlx

    if laya_mlx.__version__ != "0.2.0":
        raise ManualRunError("Laya-MLX package version differs from reviewed source")
    return laya_mlx.load(str(model_path), revision=MODEL_REVISION, dtype="float16")


def run(arguments: argparse.Namespace) -> int:
    receipt = json.loads(arguments.preflight.read_text(encoding="utf-8"))
    verify_preflight(receipt, source_checkout=arguments.source_checkout,
                     runtime_checkout=arguments.runtime_checkout)
    if _sha256(arguments.inputs) != INPUTS_SHA256:
        raise ManualRunError("candidate inputs are not the frozen DMS-01 fixture")
    rows = _jsonl(arguments.inputs)
    load_started = time.perf_counter()
    agent = _load_agent(arguments.source_checkout, arguments.model_directory)
    load_ms = (time.perf_counter() - load_started) * 1000
    predictions, token_counts, latencies, peak_memory, oom = score_input_rows(
        rows, agent=agent, tokenizer=agent.tok
    )
    _write_jsonl(arguments.predictions, predictions)
    _write_jsonl(arguments.token_counts, token_counts)
    measurements = {
        "model_id": MODEL_ID, "artifact_revision": MODEL_REVISION,
        "base_model_id": BASE_MODEL_ID, "base_revision": BASE_MODEL_REVISION,
        "harness_id": SOURCE_ID, "harness_revision": SOURCE_REVISION,
        "runtime": f"Python {sys.version.split()[0]}; Laya-MLX in-process MLX fp16",
        "runtime_lock_sha256": receipt["runtime"]["lock_sha256"],
        "device": "metal", "precision": "fp16",
        "score_calibration": "checkpoint temperatures applied; DMS calibration unverified",
        "tokenizer_id": MODEL_ID, "tokenizer_revision": MODEL_REVISION,
        "input_limit_tokens": int(agent.cfg.get("max_len", MAX_INPUT_TOKENS)),
        "completed_cases": sum(item["status"] == "ok" for item in predictions),
        "failed_cases": sum(item["status"] != "ok" for item in predictions),
        "model_load_ms": load_ms,
        "median_inference_ms": sorted(latencies)[len(latencies) // 2] if latencies else None,
        "peak_memory_bytes": peak_memory,
        "cold_latency_ms": load_ms,
        "warm_latency_ms": latencies,
        "peak_rss_bytes": peak_memory,
        "oom": oom,
    }
    arguments.measurements.parent.mkdir(parents=True, exist_ok=True)
    arguments.measurements.write_text(json.dumps(measurements, indent=2, sort_keys=True) + "\n")
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    preflight = subparsers.add_parser("preflight")
    preflight.add_argument("--source-checkout", type=Path, required=True)
    preflight.add_argument("--runtime-checkout", type=Path, required=True)
    preflight.add_argument("--storage-path", type=Path, required=True)
    preflight.add_argument("--output", type=Path, required=True)
    preflight.add_argument("--candidate-run-approved", action="store_true")
    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--source-checkout", type=Path, required=True)
    run_parser.add_argument("--runtime-checkout", type=Path, required=True)
    run_parser.add_argument("--model-directory", type=Path, required=True)
    run_parser.add_argument("--preflight", type=Path, required=True)
    run_parser.add_argument("--inputs", type=Path, required=True)
    run_parser.add_argument("--predictions", type=Path, required=True)
    run_parser.add_argument("--token-counts", type=Path, required=True)
    run_parser.add_argument("--measurements", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "preflight":
            receipt = create_preflight_receipt(
                source_checkout=args.source_checkout, runtime_checkout=args.runtime_checkout,
                storage_path=args.storage_path,
                candidate_run_approved=args.candidate_run_approved,
            )
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
            print(json.dumps({"receipt": str(args.output), "run_allowed": receipt["run_allowed"]}))
            return 0 if receipt["run_allowed"] else 2
        return run(args)
    except (ManualRunError, OSError, ValueError) as exc:
        print(f"Laya-MLX evaluation failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
