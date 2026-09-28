#!/usr/bin/env python3
"""Evaluate the pinned Jev-Style MLX checkpoint on frozen DMS-01 inputs."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
import math
import os
import platform
import resource
import shutil
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
INPUTS_SHA256 = "6d0230190f455d3f488881ef0f709881fba783f33bab4d5a6a93db576cf5c73f"
MODEL_ID = "chaoliangUNSW/Jev-Style-0.8B-Decision-v3-MLX"
MODEL_REVISION = "1235ccd1c95d5228a07616cd7e323c9e0532c1dc"
BASE_MODEL_ID = "Qwen/Qwen3.5-0.8B-Base"
BASE_MODEL_REVISION = "dc7cdfe2ee4154fa7e30f5b51ca41bfa40174e68"
RUNTIME_FILE_SHA256 = "e3ba700043d764f0fe50931cc3524d8329552bf4f4187f411671fd323e363acf"
EXPECTED_MODEL_FILES = {
    "8bit/model.safetensors": "36890afff7a9da5b7228d81cd79434088267bd250c9eafab14539e6a5161a5fe",
    "8bit/config.json": "5cfb0922af6406668fc828adc5630b9a5606d46bb31b7a6b2262c3d0674ae419",
    "8bit/tokenizer.json": "06b9509352d2af50381ab2247e083b80d32d5c0aba91c272ca9ff729b6a0e523",
    "8bit/tokenizer_config.json": "95c557768e6b88a7128befc7bfd3c7de50e5d51af9b8b33a9f4dee0e04f99679",
    "jev_style_decision_mlx.py": RUNTIME_FILE_SHA256,
    "readout_config.json": "01de9bcce7effbfd1ae0a3fa13e52d7fa9aa4dd1cd1e47977d6bbdcd5e63054a",
    "release_config.json": "3921e2bde22223eb677961ea3b75d8cff48ceb4112c3fff0f94a0c190e1408b9",
}
RUNTIME_PACKAGES = {
    "huggingface-hub": "1.33.0",
    "mlx": "0.32.2",
    "mlx-lm": "0.31.3",
    "numpy": "2.5.3",
    "tokenizers": "0.23.2",
}
EXPECTED_ARTIFACTS = [{"id": MODEL_ID, "revision": MODEL_REVISION}]


class ManualRunError(RuntimeError):
    """Raised when the candidate-specific evaluation gate is not satisfied."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _runtime_versions() -> tuple[dict[str, str | None], bool]:
    versions: dict[str, str | None] = {}
    for package in RUNTIME_PACKAGES:
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = None
    return versions, versions == RUNTIME_PACKAGES


def _active_virtualenv() -> str | None:
    value = os.environ.get("VIRTUAL_ENV")
    if not value:
        return None
    environment = Path(value).absolute()
    executable = Path(sys.executable).absolute()
    try:
        executable.relative_to(environment)
    except ValueError:
        return None
    return str(environment) if environment.is_dir() else None


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
        raise ManualRunError("candidate-specific Jev-Style run approval is absent")
    if receipt.get("run_allowed") is not True:
        raise ManualRunError("preflight did not allow model download and inference")
    if receipt.get("fixture_criteria_approved") is not True or receipt.get("input_sha256") != INPUTS_SHA256:
        raise ManualRunError("preflight fixture approval or input hash differs")
    if receipt.get("source") != {"id": MODEL_ID, "revision": MODEL_REVISION}:
        raise ManualRunError("Jev-Style source revision differs from preflight")
    if receipt.get("artifacts") != EXPECTED_ARTIFACTS:
        raise ManualRunError("Jev-Style model revision differs from preflight")
    if receipt.get("provenance_base") != {"id": BASE_MODEL_ID, "revision": BASE_MODEL_REVISION}:
        raise ManualRunError("Jev-Style provenance base differs from preflight")
    if receipt.get("expected_model_files") != EXPECTED_MODEL_FILES:
        raise ManualRunError("Jev-Style model digests differ from preflight")


def _verify_runtime(receipt: dict[str, Any], runtime_checkout: Path) -> None:
    runtime = receipt.get("runtime")
    if (
        not isinstance(runtime, dict)
        or runtime.get("available") is not True
        or Path(runtime.get("executable", "")) != Path(sys.executable)
        or runtime.get("virtualenv") != _active_virtualenv()
        or _active_virtualenv() is None
        or runtime.get("python_version") != sys.version.split()[0]
        or runtime.get("packages") != RUNTIME_PACKAGES
        or not runtime.get("lock_sha256")
    ):
        raise ManualRunError("exact pinned Jev-Style runtime is unavailable")
    lock_path = runtime_checkout / "poetry.lock"
    if not lock_path.is_file() or _sha256(lock_path) != runtime["lock_sha256"]:
        raise ManualRunError("isolated Poetry runtime lock differs from preflight")
    versions, available = _runtime_versions()
    if not available or versions != RUNTIME_PACKAGES:
        raise ManualRunError("installed Jev-Style runtime differs from preflight")
    if receipt.get("evaluation_harness_files") != _expected_harness_files():
        raise ManualRunError("evaluation harness files differ from preflight")


def verify_preflight(receipt: dict[str, Any], *, runtime_checkout: Path) -> None:
    _verify_receipt_pins(receipt)
    _verify_runtime(receipt, runtime_checkout)


def create_preflight_receipt(
    *, runtime_checkout: Path, storage_path: Path, candidate_run_approved: bool,
    required_free_storage_bytes: int = 8 * 1024**3,
) -> dict[str, Any]:
    storage_path.mkdir(parents=True, exist_ok=True)
    inputs = ROOT / "specs" / "decision-model-support" / "evaluation" / "dms01-inputs.jsonl"
    fixture_hash = _sha256(inputs) if inputs.is_file() else ""
    versions, packages_available = _runtime_versions()
    virtualenv = _active_virtualenv()
    accelerator_status = _detect_accelerator()
    lock_path = runtime_checkout / "poetry.lock"
    lock_hash = _sha256(lock_path) if lock_path.is_file() else ""
    free_storage = shutil.disk_usage(storage_path).free
    memory = None
    try:
        memory = int(os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE"))
    except (AttributeError, OSError, ValueError):
        pass
    blockers = []
    if not candidate_run_approved:
        blockers.append("candidate-specific Jev-Style run approval is absent")
    if fixture_hash != INPUTS_SHA256:
        blockers.append("frozen input fixture hash does not match")
    if not lock_hash or not packages_available or virtualenv is None:
        blockers.append("exact isolated Jev-Style Poetry runtime is unavailable")
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
        "source": {"id": MODEL_ID, "revision": MODEL_REVISION},
        "artifacts": EXPECTED_ARTIFACTS,
        "provenance_base": {"id": BASE_MODEL_ID, "revision": BASE_MODEL_REVISION},
        "expected_model_files": EXPECTED_MODEL_FILES,
        "runtime_file_sha256": RUNTIME_FILE_SHA256,
        "evaluation_harness_files": _expected_harness_files(),
        "runtime": {
            "available": packages_available and bool(lock_hash) and virtualenv is not None,
            "executable": str(Path(sys.executable)),
            "virtualenv": virtualenv,
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
        "transformers_remote_code_allowed": False,
        "runtime_source": "pinned checkpoint script; digest verified before local import",
        "blockers": blockers,
        "run_allowed": not blockers,
    }


def build_request(row: dict[str, Any]) -> tuple[Any, list[dict[str, Any]]]:
    if row.get("kind") == "decision":
        question = row["question"]
        options = question["options"]
        if len(options) < 2 or len({item["id"] for item in options}) != len(options):
            raise ManualRunError("decision fixture options are invalid")
        questions = [{
            "t": "choice", "ins": question["text"],
            "crit": {item["id"]: item["label"] for item in options},
        }]
        return row["state"], questions
    if row.get("kind") == "retention":
        messages = row["eligible_messages_oldest_first"]
        if len({item["id"] for item in messages}) != len(messages):
            raise ManualRunError("retention fixture message IDs are invalid")
        return row["task_context"], [
            {
                "t": "choice",
                "ins": (
                    "Should this candidate message be retained in active context to complete "
                    "the task?\nCandidate message:\n" + item["content"]
                ),
                "crit": {
                    "keep": "Retain this message in active context.",
                    "drop": "The active context can omit this message.",
                },
            }
            for item in messages
        ]
    raise ManualRunError("unsupported frozen input row kind")


def _validate_answer(answer: dict[str, Any], option_ids: set[str]) -> dict[str, float]:
    if not isinstance(answer, dict) or answer.get("answer") not in option_ids:
        raise ManualRunError("Jev-Style returned an invalid choice answer")
    raw = answer.get("probabilities")
    if not isinstance(raw, dict) or set(raw) != option_ids:
        raise ManualRunError("Jev-Style returned an incomplete probability distribution")
    try:
        values = {key: float(value) for key, value in raw.items()}
    except (TypeError, ValueError) as exc:
        raise ManualRunError("Jev-Style returned invalid probabilities") from exc
    if any(not math.isfinite(value) or not 0 <= value <= 1 for value in values.values()):
        raise ManualRunError("Jev-Style returned invalid probabilities")
    total = sum(values.values())
    if not math.isclose(total, 1.0, abs_tol=1e-7):
        raise ManualRunError("Jev-Style probabilities do not sum to one")
    if values[answer["answer"]] + 1e-7 < max(values.values()):
        raise ManualRunError("Jev-Style answer does not match its probability distribution")
    return values


def score_input_rows(
    rows: list[dict[str, Any]], *, agent: Any,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[float], int, bool]:
    predictions, token_counts, latencies = [], [], []
    oom = False
    for row in rows:
        state, questions = build_request(row)
        if row["kind"] == "retention":
            token_counts.extend(
                {"message_id": item["id"], "token_count": len(agent.encode(item["content"]))}
                for item in row["eligible_messages_oldest_first"]
            )
        status = "ok"
        try:
            started = time.perf_counter()
            try:
                answers = agent.decide_many(state, questions)
            finally:
                latencies.append((time.perf_counter() - started) * 1000)
            if not isinstance(answers, list) or len(answers) != len(questions):
                raise ManualRunError("Jev-Style returned missing or unexpected answers")
            scores = [
                _validate_answer(answer, set(question["crit"]))
                for answer, question in zip(answers, questions, strict=True)
            ]
        except ManualRunError as exc:
            status = "oversize" if "budget" in str(exc).lower() else "invalid"
        except TimeoutError:
            status = "timeout"
        except Exception as exc:  # noqa: BLE001 - do not expose model/input errors in receipts.
            status = "oversize" if type(exc).__name__ == "InputBudgetError" else "error"
            oom = oom or "out of memory" in str(exc).lower() or "outofmemory" in type(exc).__name__.lower()
        if status != "ok":
            predictions.append({"id": row["id"], "kind": row["kind"], "status": status})
        elif row["kind"] == "decision":
            values = scores[0]
            predictions.append({
                "id": row["id"], "kind": "decision", "status": "ok",
                "choice": max(values, key=values.get), "score_semantics": "probability",
                "scores": values,
            })
        else:
            predictions.append({
                "id": row["id"], "kind": "retention", "status": "ok",
                "score_semantics": "probability",
                "scores": {item["id"]: values["keep"] for item, values in zip(
                    row["eligible_messages_oldest_first"], scores, strict=True
                )},
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


def _load_agent(model_directory: Path) -> Any:
    from huggingface_hub import snapshot_download

    model_path = Path(snapshot_download(
        repo_id=MODEL_ID, revision=MODEL_REVISION, local_dir=str(model_directory),
        allow_patterns=["manifest.json", "jev_style_decision_mlx.py", "readout_config.json",
                        "release_config.json", "requirements.txt", "LICENSE", "8bit/*"],
    ))
    for filename, expected in EXPECTED_MODEL_FILES.items():
        path = model_path / filename
        if not path.is_file() or _sha256(path) != expected:
            raise ManualRunError("downloaded Jev-Style artifact digest differs from the pin")
    os.environ["HF_HUB_OFFLINE"] = "1"
    runtime_path = model_path / "jev_style_decision_mlx.py"
    spec = importlib.util.spec_from_file_location("dms_jev_style_runtime", runtime_path)
    if spec is None or spec.loader is None:
        raise ManualRunError("pinned Jev-Style runtime cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.JevStyleDecisionMLX(
        model_path, precision="8bit", verify=True, cache_limit_gib=2.0
    )


def run(arguments: argparse.Namespace) -> int:
    receipt = json.loads(arguments.preflight.read_text(encoding="utf-8"))
    verify_preflight(receipt, runtime_checkout=arguments.runtime_checkout)
    if _sha256(arguments.inputs) != INPUTS_SHA256:
        raise ManualRunError("candidate inputs are not the frozen DMS-01 fixture")
    rows = _jsonl(arguments.inputs)
    load_started = time.perf_counter()
    agent = _load_agent(arguments.model_directory)
    load_ms = (time.perf_counter() - load_started) * 1000
    predictions, token_counts, latencies, peak_memory, oom = score_input_rows(rows, agent=agent)
    _write_jsonl(arguments.predictions, predictions)
    _write_jsonl(arguments.token_counts, token_counts)
    measurements = {
        "model_id": MODEL_ID, "artifact_revision": MODEL_REVISION,
        "base_model_id": BASE_MODEL_ID, "base_revision": BASE_MODEL_REVISION,
        "runtime_file_sha256": RUNTIME_FILE_SHA256,
        "runtime": f"Python {sys.version.split()[0]}; Jev-Style in-process MLX 8-bit",
        "runtime_lock_sha256": receipt["runtime"]["lock_sha256"],
        "device": "metal", "precision": "8bit",
        "score_calibration": "checkpoint global temperature applied; DMS calibration unverified",
        "tokenizer_id": MODEL_ID, "tokenizer_revision": MODEL_REVISION,
        "input_limit_tokens": 25600,
        "completed_cases": sum(item["status"] == "ok" for item in predictions),
        "failed_cases": sum(item["status"] != "ok" for item in predictions),
        "model_load_ms": load_ms,
        "median_inference_ms": sorted(latencies)[len(latencies) // 2] if latencies else None,
        "peak_memory_bytes": peak_memory,
        "cold_latency_ms": load_ms, "warm_latency_ms": latencies,
        "peak_rss_bytes": peak_memory, "oom": oom,
    }
    arguments.measurements.parent.mkdir(parents=True, exist_ok=True)
    arguments.measurements.write_text(json.dumps(measurements, indent=2, sort_keys=True) + "\n")
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    preflight = subparsers.add_parser("preflight")
    preflight.add_argument("--runtime-checkout", type=Path, required=True)
    preflight.add_argument("--storage-path", type=Path, required=True)
    preflight.add_argument("--output", type=Path, required=True)
    preflight.add_argument("--candidate-run-approved", action="store_true")
    run_parser = subparsers.add_parser("run")
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
                runtime_checkout=args.runtime_checkout, storage_path=args.storage_path,
                candidate_run_approved=args.candidate_run_approved,
            )
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
            print(json.dumps({"receipt": str(args.output), "run_allowed": receipt["run_allowed"]}))
            return 0 if receipt["run_allowed"] else 2
        return run(args)
    except (ManualRunError, OSError, ValueError) as exc:
        print(f"Jev-Style evaluation failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
