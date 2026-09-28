#!/usr/bin/env python3
"""Run pinned PoorJev in-process on the approved frozen DMS-01 inputs."""

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
MODEL_REPOSITORY = "MoritzLaurer/deberta-v3-base-zeroshot-v2.0"
MODEL_REVISION = "8e7e5af5983a0ddb1a5b45a38b129ab69e2258e8"
SOURCE_ID = "rupeshpoojary9/poorjev"
SOURCE_REVISION = "7e684e95db13b90238c63e6ab39e1a016263a168"
RUNTIME_LOCK_SHA256 = "acaaa8abfcd3bc18eff1557fe2c73be73c00899eed5b1145de1b30518acf1f41"
RUNTIME_PACKAGES = {
    "accelerate": "1.15.0",
    "huggingface-hub": "1.32.0",
    "torch": "2.14.0",
    "transformers": "5.17.0",
}
EXPECTED_SOURCE = {"id": SOURCE_ID, "revision": SOURCE_REVISION}
EXPECTED_ARTIFACTS = [{"id": MODEL_REPOSITORY, "revision": MODEL_REVISION}]
EXPECTED_MODEL_FILES = {
    "model.safetensors": "6e8f2af78c828dcbd5243aac40fb87430376f0b8a9c288f4993df3ea3558d557",
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


def _verify_harness_files(receipt: dict[str, Any]) -> None:
    expected = [
        {"id": str(path.relative_to(ROOT)), "sha256": _sha256(path)}
        for path in (ROOT / "scripts" / "evaluate_decision_models.py", Path(__file__).resolve())
    ]
    if receipt.get("evaluation_harness_files") != expected:
        raise ManualRunError("evaluation harness files differ from preflight")


def _verify_receipt_pins(receipt: dict[str, Any]) -> None:
    if receipt.get("run_allowed") is not True:
        raise ManualRunError("preflight did not allow model download and inference")
    if receipt.get("candidate_run_approved") is not True:
        raise ManualRunError("candidate-specific approval is absent")
    if receipt.get("fixture_criteria_approved") is not True:
        raise ManualRunError("preflight lacks fixture and criteria approval")
    if receipt.get("input_sha256") != INPUTS_SHA256:
        raise ManualRunError("preflight input fixture hash differs")
    if receipt.get("source") != EXPECTED_SOURCE:
        raise ManualRunError("PoorJev source revision differs from preflight")
    if receipt.get("artifacts") != EXPECTED_ARTIFACTS:
        raise ManualRunError("artifact revisions differ from preflight")
    if receipt.get("expected_model_file_sha256") != EXPECTED_MODEL_FILES:
        raise ManualRunError("model file digest differs from preflight")


def _verify_runtime(receipt: dict[str, Any], runtime_checkout: Path) -> None:
    runtime = receipt.get("runtime")
    if (
        not isinstance(runtime, dict)
        or runtime.get("available") is not True
        or Path(runtime.get("executable", "")).resolve() != Path(sys.executable).resolve()
        or runtime.get("python_version") != sys.version.split()[0]
        or runtime.get("lock_sha256") != RUNTIME_LOCK_SHA256
        or runtime.get("packages") != RUNTIME_PACKAGES
    ):
        raise ManualRunError("exact runtime versions are missing from preflight")
    if _sha256(runtime_checkout / "uv.lock") != RUNTIME_LOCK_SHA256:
        raise ManualRunError("shared evaluation runtime lock differs from preflight")
    actual_packages, packages_available = _runtime_versions()
    if not packages_available or actual_packages != RUNTIME_PACKAGES:
        raise ManualRunError("installed runtime packages differ from preflight")


def verify_preflight(
    receipt: dict[str, Any], *, source_checkout: Path, runtime_checkout: Path
) -> None:
    _verify_receipt_pins(receipt)
    _verify_runtime(receipt, runtime_checkout)
    if _repository_revision(source_checkout) != SOURCE_REVISION:
        raise ManualRunError("PoorJev source checkout is not the preflighted commit")
    if not _repository_clean(source_checkout):
        raise ManualRunError("PoorJev source checkout contains uncommitted files")
    _verify_harness_files(receipt)


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


def create_preflight_receipt(
    *,
    source_checkout: Path,
    runtime_checkout: Path,
    storage_path: Path,
    candidate_run_approved: bool,
    required_free_storage_bytes: int = 2 * 1024**3,
) -> dict[str, Any]:
    storage_path.mkdir(parents=True, exist_ok=True)
    inputs_path = ROOT / "specs" / "decision-model-support" / "evaluation" / "dms01-inputs.jsonl"
    input_hash = _sha256(inputs_path) if inputs_path.is_file() else ""
    runtime_packages, runtime_available = _runtime_versions()
    lock_path = runtime_checkout / "uv.lock"
    lock_hash = _sha256(lock_path) if lock_path.is_file() else ""
    source_revision = _repository_revision(source_checkout)
    free_storage = shutil.disk_usage(storage_path).free
    total_memory = None
    try:
        total_memory = int(os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE"))
    except (AttributeError, OSError, ValueError):
        pass
    runner_files = [ROOT / "scripts" / "evaluate_decision_models.py", Path(__file__).resolve()]
    harness_files = [
        {"id": str(path.relative_to(ROOT)), "sha256": _sha256(path)}
        for path in runner_files
        if path.is_file()
    ]
    blockers = []
    if not candidate_run_approved:
        blockers.append("candidate-specific PoorJev run approval is absent")
    if input_hash != INPUTS_SHA256:
        blockers.append("frozen input fixture hash does not match")
    if source_revision != SOURCE_REVISION or lock_hash != RUNTIME_LOCK_SHA256:
        blockers.append("pinned PoorJev source or evaluation runtime lock differs")
    if source_checkout.is_dir() and not _repository_clean(source_checkout):
        blockers.append("PoorJev source checkout contains uncommitted files")
    if not runtime_available:
        blockers.append("exact pinned PoorJev runtime packages are unavailable")
    if len(harness_files) != len(runner_files):
        blockers.append("evaluation harness files are incomplete")
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
        "evaluation_harness_files": harness_files,
        "runtime": {
            "available": runtime_available,
            "executable": str(Path(sys.executable).resolve()),
            "python_version": sys.version.split()[0],
            "packages": runtime_packages,
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
        if len(options) < 2 or len({option["id"] for option in options}) != len(options):
            raise ManualRunError("decision fixture options are invalid")
        return {
            "state": json.dumps(row["state"], ensure_ascii=False, sort_keys=True),
            "questions": {
                question["id"]: {
                    "text": question["text"],
                    "options": {option["id"]: option["label"] for option in options},
                }
            },
        }
    if row.get("kind") == "retention":
        messages = row["eligible_messages_oldest_first"]
        if len({message["id"] for message in messages}) != len(messages):
            raise ManualRunError("retention fixture message IDs are invalid")
        return {
            "state": row["task_context"],
            "questions": {
                message["id"]: {
                    "text": "Should this candidate message be retained in active context to complete the task?",
                    "options": {
                        "keep": "Retain this message in active context.",
                        "drop": "The active context can omit this message.",
                    },
                    "content": message["content"],
                }
                for message in messages
            },
        }
    raise ManualRunError("unsupported frozen input row kind")


def _option_hypotheses(question: dict[str, Any]) -> tuple[list[str], dict[str, str]]:
    hypotheses = {
        option_id: f"Option {option_id}: {label}. The question is: {question['text']}"
        for option_id, label in question["options"].items()
    }
    return list(hypotheses.values()), {value: key for key, value in hypotheses.items()}


def _score_question(
    *, client: Any, choice_factory: Any, state: str, question_id: str,
    question: dict[str, Any]
) -> tuple[dict[str, float], float]:
    hypotheses, reverse = _option_hypotheses(question)
    started = time.perf_counter()
    answer = client.ask(state, {question_id: choice_factory(hypotheses)})[question_id]
    elapsed_ms = (time.perf_counter() - started) * 1000
    if getattr(answer, "abstained", False):
        raise ManualRunError("PoorJev abstained")
    raw = getattr(answer, "probs", None)
    if not isinstance(raw, dict) or set(raw) != set(hypotheses):
        raise ManualRunError("PoorJev returned an incomplete distribution")
    values = {reverse[key]: float(value) for key, value in raw.items()}
    if (
        any(not 0.0 <= value <= 1.0 for value in values.values())
        or not math.isclose(sum(values.values()), 1.0, abs_tol=1e-6)
    ):
        raise ManualRunError("PoorJev returned invalid probabilities")
    if getattr(answer, "value", None) not in reverse or reverse[answer.value] != max(
        values, key=values.get
    ):
        raise ManualRunError("PoorJev choice does not match its distribution")
    return values, elapsed_ms


def score_input_rows(
    rows: list[dict[str, Any]], *, client: Any, choice_factory: Any, tokenizer: Any
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[float], bool]:
    predictions: list[dict[str, Any]] = []
    token_counts: list[dict[str, Any]] = []
    latencies: list[float] = []
    oom = False
    for row in rows:
        request = build_request(row)
        scores: dict[str, dict[str, float]] = {}
        if row["kind"] == "retention":
            token_counts.extend(
                {"message_id": message["id"], "token_count": len(tokenizer.encode(
                    message["content"], add_special_tokens=False
                ))}
                for message in row["eligible_messages_oldest_first"]
            )
        status = "ok"
        try:
            for question_id, question in request["questions"].items():
                state = request["state"]
                if row["kind"] == "retention":
                    state = f"{state}\nCandidate message: {question['content']}"
                values, elapsed_ms = _score_question(
                    client=client,
                    choice_factory=choice_factory,
                    state=state,
                    question_id=question_id,
                    question=question,
                )
                latencies.append(elapsed_ms)
                scores[question_id] = values
        except TimeoutError:
            status = "timeout"
        except ManualRunError:
            status = "invalid"
        except Exception as exc:  # noqa: BLE001 - details may contain input text.
            status = "error"
            oom = oom or "out of memory" in str(exc).lower() or "outofmemory" in type(exc).__name__.lower()
        if status != "ok":
            predictions.append({"id": row["id"], "kind": row["kind"], "status": status})
        elif row["kind"] == "decision":
            question_id = next(iter(request["questions"]))
            values = scores[question_id]
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
                "scores": {question_id: values["keep"] for question_id, values in scores.items()},
            })
    return predictions, token_counts, latencies, oom


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def _load_backend(source_checkout: Path, model_directory: Path) -> tuple[Any, Any]:
    from huggingface_hub import snapshot_download

    model_path = Path(snapshot_download(
        repo_id=MODEL_REPOSITORY,
        revision=MODEL_REVISION,
        local_dir=str(model_directory),
        allow_patterns=[
            "added_tokens.json",
            "config.json",
            "model.safetensors",
            "special_tokens_map.json",
            "spm.model",
            "tokenizer.json",
            "tokenizer_config.json",
        ],
    ))
    for filename, expected in EXPECTED_MODEL_FILES.items():
        if not (model_path / filename).is_file() or _sha256(model_path / filename) != expected:
            raise ManualRunError("downloaded model file does not match pinned digest")
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    sys.path.insert(0, str(source_checkout / "src"))
    from poorjev.backends.local_nli import LocalNLIBackend
    from poorjev.client import Client
    from poorjev.primitives import Choice

    backend = LocalNLIBackend(model_name=str(model_path), device="cpu")
    backend._ensure_loaded()
    client = Client(backend=backend, hypothesis_template="{}", temperature=1.0)
    return client, (Choice, backend._tokenizer)


def run(arguments: argparse.Namespace) -> int:
    receipt = json.loads(arguments.preflight.read_text(encoding="utf-8"))
    verify_preflight(receipt, source_checkout=arguments.source_checkout,
                     runtime_checkout=arguments.runtime_checkout)
    if _sha256(arguments.inputs) != INPUTS_SHA256:
        raise ManualRunError("candidate inputs are not the frozen DMS-01 fixture")
    rows = _jsonl(arguments.inputs)
    started = time.perf_counter()
    client, internals = _load_backend(arguments.source_checkout, arguments.model_directory)
    cold_latency = (time.perf_counter() - started) * 1000
    choice_type, tokenizer = internals
    predictions, token_counts, warm_latencies, oom = score_input_rows(
        rows, client=client, choice_factory=lambda options: choice_type(options=options),
        tokenizer=tokenizer,
    )
    _write_jsonl(arguments.predictions, predictions)
    _write_jsonl(arguments.token_counts, token_counts)
    measurements = {
        "model_id": MODEL_REPOSITORY,
        "artifact_revision": MODEL_REVISION,
        "harness_id": SOURCE_ID,
        "harness_revision": SOURCE_REVISION,
        "runtime": f"Python {sys.version.split()[0]}; shared locked research runtime",
        "runtime_lock_sha256": RUNTIME_LOCK_SHA256,
        "device": "cpu",
        "precision": "fp32",
        "score_calibration": "unfitted default temperature=1.0",
        "tokenizer_id": MODEL_REPOSITORY,
        "tokenizer_revision": MODEL_REVISION,
        "model_server": False,
        "cold_latency_ms": cold_latency,
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
    preflight.add_argument("--runtime-checkout", type=Path, required=True)
    preflight.add_argument("--storage-path", type=Path, required=True)
    preflight.add_argument("--output", type=Path, required=True)
    preflight.add_argument("--candidate-run-approved", action="store_true")
    preflight.add_argument("--required-free-storage-bytes", type=int, default=2 * 1024**3)
    run_parser = commands.add_parser("run")
    run_parser.add_argument("--preflight", type=Path, required=True)
    run_parser.add_argument("--source-checkout", type=Path, required=True)
    run_parser.add_argument("--runtime-checkout", type=Path, required=True)
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
                runtime_checkout=arguments.runtime_checkout,
                storage_path=arguments.storage_path,
                candidate_run_approved=arguments.candidate_run_approved,
                required_free_storage_bytes=arguments.required_free_storage_bytes,
            )
            arguments.output.parent.mkdir(parents=True, exist_ok=True)
            arguments.output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
            print(json.dumps({"receipt": str(arguments.output), "run_allowed": receipt["run_allowed"]}))
            return 0 if receipt["run_allowed"] else 2
        return run(arguments)
    except Exception as exc:  # noqa: BLE001 - external errors may include input text.
        if isinstance(exc, ManualRunError):
            print(f"PoorJev DMS-06 run blocked: {exc}", file=sys.stderr)
        else:
            print("PoorJev DMS-06 run failed; details omitted to protect synthetic inputs.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
