#!/usr/bin/env python3
"""Run pinned LitJev with a small pinned Qwen checkpoint on frozen DMS inputs."""

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
SOURCE_ID = "zhengxuyu/litjev"
SOURCE_REVISION = "e7fb109a7466da9709028eb9c4e9f16eaeb4e2a3"
MODEL_ID = "Qwen/Qwen3-0.6B-Base"
MODEL_REVISION = "da87bfb608c14b7cf20ba1ce41287e8de496c0cd"
RUNTIME_LOCK_SHA256 = "bf0e1ff4aeda5ffe276e58f64edd7324bbaa8cec941fa174312b23e6bab0f1d8"
RUNTIME_PACKAGES = {
    "accelerate": "1.15.0",
    "huggingface-hub": "1.32.0",
    "numpy": "2.5.3",
    "safetensors": "0.8.0",
    "torch": "2.11.0",
    "torchvision": "0.26.0",
    "transformers": "5.17.0",
}
EXPECTED_SOURCE = {"id": SOURCE_ID, "revision": SOURCE_REVISION}
EXPECTED_ARTIFACTS = [{"id": MODEL_ID, "revision": MODEL_REVISION}]
EXPECTED_MODEL_FILES = {
    "model.safetensors": "cd2a512003e2f9f3cd3c32a9c3573f820bb28c940f73c57b1ddaa983d9223eba",
}


class ManualRunError(RuntimeError):
    """Raised when the approved manual-run boundary is not satisfied."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _repository_revision(path: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"],
        capture_output=True,
        check=True,
        text=True,
        timeout=5,
    )
    return result.stdout.strip()


def _repository_clean(path: Path) -> bool:
    result = subprocess.run(
        ["git", "-C", str(path), "status", "--porcelain", "--untracked-files=all"],
        capture_output=True,
        check=True,
        text=True,
        timeout=5,
    )
    return not result.stdout.strip()


def _runtime_versions() -> tuple[dict[str, str | None], bool]:
    versions: dict[str, str | None] = {}
    available = True
    for package, expected in RUNTIME_PACKAGES.items():
        try:
            version = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            version = None
        versions[package] = version
        available = available and version == expected
    return versions, available


def _expected_harness_files() -> list[dict[str, str]]:
    return [
        {"id": str(path.relative_to(ROOT)), "sha256": _sha256(path)}
        for path in (ROOT / "scripts" / "evaluate_decision_models.py", Path(__file__).resolve())
    ]


def _verify_receipt_identity(receipt: dict[str, Any]) -> None:
    if receipt.get("candidate_run_approved") is not True:
        raise ManualRunError("candidate-specific approval is absent")
    if receipt.get("run_allowed") is not True:
        raise ManualRunError("preflight did not allow model download and inference")
    if receipt.get("fixture_criteria_approved") is not True or receipt.get("input_sha256") != INPUTS_SHA256:
        raise ManualRunError("preflight fixture approval or input hash differs")
    if receipt.get("source") != EXPECTED_SOURCE:
        raise ManualRunError("LitJev source revision differs from preflight")
    if receipt.get("artifacts") != EXPECTED_ARTIFACTS:
        raise ManualRunError("base model revision differs from preflight")
    if receipt.get("expected_model_file_sha256") != EXPECTED_MODEL_FILES:
        raise ManualRunError("base model file digest differs from preflight")


def _verify_runtime(receipt: dict[str, Any], runtime_checkout: Path) -> None:
    runtime = receipt.get("runtime")
    if (
        not isinstance(runtime, dict)
        or runtime.get("available") is not True
        or Path(runtime.get("executable", "")).resolve() != Path(sys.executable).resolve()
        or runtime.get("python_version") != sys.version.split()[0]
        or runtime.get("packages") != RUNTIME_PACKAGES
        or runtime.get("lock_sha256") != RUNTIME_LOCK_SHA256
    ):
        raise ManualRunError("LitJev's exact pinned runtime is unavailable")
    if _sha256(runtime_checkout / "uv.lock") != RUNTIME_LOCK_SHA256:
        raise ManualRunError("LitJev runtime lock differs from preflight")
    actual, available = _runtime_versions()
    if not available or actual != RUNTIME_PACKAGES:
        raise ManualRunError("installed LitJev runtime differs from preflight")


def verify_preflight(
    receipt: dict[str, Any], *, source_checkout: Path, runtime_checkout: Path
) -> None:
    _verify_receipt_identity(receipt)
    _verify_runtime(receipt, runtime_checkout)
    if receipt.get("source") != EXPECTED_SOURCE or _repository_revision(source_checkout) != SOURCE_REVISION:
        raise ManualRunError("LitJev source revision differs from preflight")
    if not _repository_clean(source_checkout):
        raise ManualRunError("LitJev source checkout contains uncommitted files")
    if receipt.get("evaluation_harness_files") != _expected_harness_files():
        raise ManualRunError("evaluation harness files differ from preflight")


def create_preflight_receipt(
    *, source_checkout: Path, storage_path: Path, candidate_run_approved: bool,
    required_free_storage_bytes: int = 8 * 1024**3
) -> dict[str, Any]:
    storage_path.mkdir(parents=True, exist_ok=True)
    inputs_path = ROOT / "specs" / "decision-model-support" / "evaluation" / "dms01-inputs.jsonl"
    input_hash = _sha256(inputs_path) if inputs_path.is_file() else ""
    versions, runtime_available = _runtime_versions()
    lock_path = source_checkout / "uv.lock"
    lock_hash = _sha256(lock_path) if lock_path.is_file() else ""
    source_revision = _repository_revision(source_checkout)
    source_clean = _repository_clean(source_checkout)
    free_storage = shutil.disk_usage(storage_path).free
    total_memory = None
    try:
        total_memory = int(os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE"))
    except (AttributeError, OSError, ValueError):
        pass
    blockers = []
    if not candidate_run_approved:
        blockers.append("candidate-specific LitJev run approval is absent")
    if input_hash != INPUTS_SHA256:
        blockers.append("frozen input fixture hash does not match")
    if source_revision != SOURCE_REVISION or lock_hash != RUNTIME_LOCK_SHA256 or not source_clean:
        blockers.append("pinned LitJev source, runtime lock, or clean checkout check failed")
    if not runtime_available:
        blockers.append("exact LitJev runtime packages are unavailable")
    if free_storage < required_free_storage_bytes:
        blockers.append("available storage is below the declared requirement")
    if total_memory is None or total_memory < 8 * 1024**3:
        blockers.append("host does not meet the 8 GiB evaluation memory floor")
    return {
        "created_at_utc": datetime.now(UTC).isoformat(),
        "candidate_run_approved": candidate_run_approved,
        "fixture_criteria_approved": True,
        "input_sha256": INPUTS_SHA256,
        "source": EXPECTED_SOURCE,
        "artifacts": EXPECTED_ARTIFACTS,
        "expected_model_file_sha256": EXPECTED_MODEL_FILES,
        "evaluation_harness_files": _expected_harness_files(),
        "runtime": {
            "available": runtime_available,
            "executable": str(Path(sys.executable).resolve()),
            "python_version": sys.version.split()[0],
            "packages": versions,
            "lock_sha256": lock_hash,
        },
        "host": {
            "platform": platform.platform(),
            "architecture": platform.machine(),
            "total_memory_bytes": total_memory,
            "storage_path": str(storage_path),
            "free_storage_bytes": free_storage,
            "required_free_storage_bytes": required_free_storage_bytes,
        },
        "execution_mode": "external_in_process_cpu",
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
        return {
            "state": row["state"],
            "questions": {
                question["id"]: {
                    "text": question["text"],
                    "options": {item["id"]: item["label"] for item in options},
                }
            },
        }
    if row.get("kind") == "retention":
        messages = row["eligible_messages_oldest_first"]
        if len({item["id"] for item in messages}) != len(messages):
            raise ManualRunError("retention fixture message IDs are invalid")
        return {
            "state": row["task_context"],
            "questions": {
                item["id"]: {
                    "text": "Should this candidate message be retained in active context to complete the task?",
                    "options": {
                        "keep": "Retain this message in active context.",
                        "drop": "The active context can omit this message.",
                    },
                    "content": item["content"],
                }
                for item in messages
            },
        }
    raise ManualRunError("unsupported frozen input row kind")


def _validate_answer(answer: Any, option_ids: set[str]) -> dict[str, float]:
    raw = getattr(answer, "probabilities", None)
    if not isinstance(raw, dict) or set(raw) != option_ids:
        raise ManualRunError("LitJev returned an incomplete probability distribution")
    values = {key: float(value) for key, value in raw.items()}
    if any(not math.isfinite(value) or not 0 <= value <= 1 for value in values.values()):
        raise ManualRunError("LitJev returned invalid probabilities")
    if not math.isclose(sum(values.values()), 1.0, abs_tol=1e-6):
        raise ManualRunError("LitJev probability distribution does not sum to one")
    if getattr(answer, "choice", None) not in values or max(values, key=values.get) != answer.choice:
        raise ManualRunError("LitJev choice does not match its distribution")
    return values


def score_input_rows(
    rows: list[dict[str, Any]], *, engine: Any, choice_factory: Any,
    schema_factory: Any, tokenizer: Any
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[float], bool]:
    predictions, token_counts, latencies = [], [], []
    oom = False
    for row in rows:
        request = build_request(row)
        values_by_id: dict[str, dict[str, float]] = {}
        if row["kind"] == "retention":
            token_counts.extend(
                {"message_id": item["id"], "token_count": len(tokenizer.encode(
                    item["content"], add_special_tokens=False
                ))}
                for item in row["eligible_messages_oldest_first"]
            )
        status = "ok"
        try:
            for question_id, item in request["questions"].items():
                state = request["state"]
                if row["kind"] == "retention":
                    state = f"{state}\nCandidate message: {item['content']}"
                question = choice_factory(
                    instructions=item["text"], criteria=item["options"]
                )
                schema = schema_factory({question_id: question})
                started = time.perf_counter()
                try:
                    result = engine.evaluate(state, schema).result
                finally:
                    latencies.append((time.perf_counter() - started) * 1000)
                values_by_id[question_id] = _validate_answer(
                    result.answers[question_id], set(item["options"])
                )
        except TimeoutError:
            status = "timeout"
        except ManualRunError:
            status = "invalid"
        except Exception as exc:  # noqa: BLE001 - message may contain input text.
            status = "error"
            oom = oom or "out of memory" in str(exc).lower() or "outofmemory" in type(exc).__name__.lower()
        if status != "ok":
            predictions.append({"id": row["id"], "kind": row["kind"], "status": status})
        elif row["kind"] == "decision":
            question_id = next(iter(request["questions"]))
            values = values_by_id[question_id]
            predictions.append({
                "id": row["id"],
                "kind": "decision",
                "status": "ok",
                "choice": max(values, key=values.get),
                "score_semantics": "probability",
                "scores": values,
            })
        else:
            predictions.append({
                "id": row["id"],
                "kind": "retention",
                "status": "ok",
                "score_semantics": "probability",
                "scores": {key: values["keep"] for key, values in values_by_id.items()},
            })
    return predictions, token_counts, latencies, oom


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def _load_engine(source_checkout: Path, model_directory: Path) -> tuple[Any, Any, Any, Any]:
    from huggingface_hub import snapshot_download

    model_path = Path(snapshot_download(
        repo_id=MODEL_ID,
        revision=MODEL_REVISION,
        local_dir=str(model_directory),
        allow_patterns=["*.json", "*.model", "*.safetensors", "*.tiktoken", "*.txt"],
    ))
    for filename, expected in EXPECTED_MODEL_FILES.items():
        if not (model_path / filename).is_file() or _sha256(model_path / filename) != expected:
            raise ManualRunError("downloaded Qwen file does not match its pinned digest")
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    sys.path.insert(0, str(source_checkout / "src"))
    from litjev.backend import ModelSettings, TransformersScorer
    from litjev.decision import SchemaDecisionEngine
    from litjev.schema import Choice, DecisionSchema

    settings = ModelSettings(
        model_id=str(model_path), revision="main", device_map="cpu", dtype="float32",
        max_input_tokens=16384,
    )
    scorer = TransformersScorer.load(settings)
    engine = SchemaDecisionEngine(
        scorer, temperature=1.0, model_id=MODEL_ID, calibration_fitted=False
    )
    return engine, Choice, DecisionSchema.from_mapping, scorer.tokenizer


def run(arguments: argparse.Namespace) -> int:
    receipt = json.loads(arguments.preflight.read_text(encoding="utf-8"))
    verify_preflight(
        receipt, source_checkout=arguments.source_checkout,
        runtime_checkout=arguments.source_checkout,
    )
    if _sha256(arguments.inputs) != INPUTS_SHA256:
        raise ManualRunError("candidate inputs are not the frozen DMS-01 fixture")
    rows = _jsonl(arguments.inputs)
    started = time.perf_counter()
    engine, choice_factory, schema_factory, tokenizer = _load_engine(
        arguments.source_checkout, arguments.model_directory
    )
    cold_latency_ms = (time.perf_counter() - started) * 1000
    predictions, token_counts, warm_latencies, oom = score_input_rows(
        rows, engine=engine, choice_factory=choice_factory,
        schema_factory=schema_factory, tokenizer=tokenizer,
    )
    _write_jsonl(arguments.predictions, predictions)
    _write_jsonl(arguments.token_counts, token_counts)
    measurements = {
        "model_id": MODEL_ID,
        "artifact_revision": MODEL_REVISION,
        "base_model_id": MODEL_ID,
        "base_revision": MODEL_REVISION,
        "harness_id": SOURCE_ID,
        "harness_revision": SOURCE_REVISION,
        "runtime": f"Python {sys.version.split()[0]}; LitJev in-process CPU fp32",
        "runtime_lock_sha256": RUNTIME_LOCK_SHA256,
        "device": "cpu",
        "precision": "fp32",
        "score_calibration": "unfitted temperature=1.0",
        "tokenizer_id": MODEL_ID,
        "tokenizer_revision": MODEL_REVISION,
        "model_server": False,
        "cold_latency_ms": cold_latency_ms,
        "warm_latency_ms": warm_latencies,
        "peak_rss_bytes": int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss),
        "oom": oom,
    }
    arguments.measurements.parent.mkdir(parents=True, exist_ok=True)
    arguments.measurements.write_text(json.dumps(measurements, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"predictions": len(predictions), "measurements": arguments.measurements.name}))
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    preflight = commands.add_parser("preflight")
    preflight.add_argument("--source-checkout", type=Path, required=True)
    preflight.add_argument("--storage-path", type=Path, required=True)
    preflight.add_argument("--output", type=Path, required=True)
    preflight.add_argument("--candidate-run-approved", action="store_true")
    preflight.add_argument("--required-free-storage-bytes", type=int, default=8 * 1024**3)
    run_parser = commands.add_parser("run")
    run_parser.add_argument("--preflight", type=Path, required=True)
    run_parser.add_argument("--source-checkout", type=Path, required=True)
    run_parser.add_argument("--model-directory", type=Path, required=True)
    run_parser.add_argument("--inputs", type=Path, required=True)
    run_parser.add_argument("--predictions", type=Path, required=True)
    run_parser.add_argument("--token-counts", type=Path, required=True)
    run_parser.add_argument("--measurements", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        if arguments.command == "preflight":
            receipt = create_preflight_receipt(
                source_checkout=arguments.source_checkout,
                storage_path=arguments.storage_path,
                candidate_run_approved=arguments.candidate_run_approved,
                required_free_storage_bytes=arguments.required_free_storage_bytes,
            )
            arguments.output.parent.mkdir(parents=True, exist_ok=True)
            arguments.output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
            print(json.dumps({"receipt": str(arguments.output), "run_allowed": receipt["run_allowed"]}))
            return 0 if receipt["run_allowed"] else 2
        return run(arguments)
    except Exception as exc:  # noqa: BLE001 - external errors may contain fixture text.
        if isinstance(exc, ManualRunError):
            print(f"LitJev DMS-06 run blocked: {exc}", file=sys.stderr)
        else:
            print("LitJev DMS-06 run failed; details omitted to protect synthetic inputs.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
