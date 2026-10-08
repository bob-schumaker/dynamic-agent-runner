#!/usr/bin/env python3
"""Run the pinned Von checkpoint in-process on approved DMS-01 inputs only."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import re
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
MODEL_ID = "von-1.2.0"
MODEL_REPOSITORY = "wfzyx/von"
MODEL_REVISION = "5df8185a4f2327ad0a7cd117cc4f701ac557b9ae"
SOURCE_ID = "wfzyx/von-source"
SOURCE_REVISION = "fb6e7a937e4fc6b6e72b2ce5035edd56bc370e54"
RUNTIME_LOCK_SHA256 = "acaaa8abfcd3bc18eff1557fe2c73be73c00899eed5b1145de1b30518acf1f41"
RUNTIME_PACKAGES = {
    "accelerate": "1.15.0",
    "huggingface-hub": "1.32.0",
    "torch": "2.14.0",
    "transformers": "5.17.0",
}
EXPECTED_ARTIFACTS = [{"id": MODEL_REPOSITORY, "revision": MODEL_REVISION}]
EXPECTED_SOURCE = {"id": SOURCE_ID, "revision": SOURCE_REVISION}
EXPECTED_MODEL_FILES = {
    "model.safetensors": "af57d5d2ab15715a753a1eb4add4271d1aecce7e76f3365f629c082df329297a",
    "option_marker.pt": "3faf27f88d30aaf9aa37860d4cdef99f1d05450cf40364f6236ac892d4d139ed",
}
_DIGITS = re.compile(r"\d+")


class ManualRunError(RuntimeError):
    """Raised when the approved manual-run boundary is not satisfied."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_preflight(receipt: dict[str, Any], *, source_checkout: Path) -> None:
    if receipt.get("run_allowed") is not True:
        raise ManualRunError("preflight did not allow model download and inference")
    if receipt.get("candidate_run_approved") is not True:
        raise ManualRunError("candidate-specific approval is absent")
    if receipt.get("fixture_criteria_approved") is not True:
        raise ManualRunError("preflight lacks fixture and criteria approval")
    if receipt.get("input_sha256") != INPUTS_SHA256:
        raise ManualRunError("preflight input fixture hash differs")
    if receipt.get("source") != EXPECTED_SOURCE:
        raise ManualRunError("Von source revision differs from the preflight")
    if receipt.get("artifacts") != EXPECTED_ARTIFACTS:
        raise ManualRunError("artifact revisions differ from the preflight")
    runtime = receipt.get("runtime")
    if (
        not isinstance(runtime, dict)
        or runtime.get("python_version") != sys.version.split()[0]
        or runtime.get("lock_sha256") != RUNTIME_LOCK_SHA256
        or runtime.get("packages") != RUNTIME_PACKAGES
    ):
        raise ManualRunError("exact runtime versions are missing from preflight")
    if _repository_revision(source_checkout) != SOURCE_REVISION:
        raise ManualRunError("Von source checkout is not the preflighted commit")
    expected_harness_files = [
        {
            "id": str(path.relative_to(ROOT)),
            "sha256": _sha256(path),
        }
        for path in (
            ROOT / "scripts" / "evaluate_decision_models.py",
            Path(__file__).resolve(),
        )
    ]
    if receipt.get("evaluation_harness_files") != expected_harness_files:
        raise ManualRunError("evaluation harness files differ from preflight")


def verify_runtime(receipt: dict[str, Any], source_checkout: Path) -> None:
    runtime = receipt["runtime"]
    if sys.version.split()[0] != runtime.get("python_version"):
        raise ManualRunError("Python version differs from preflight")
    if runtime.get("available") is not True or Path(runtime.get("executable", "")).resolve() != Path(sys.executable).resolve():
        raise ManualRunError("preflighted Von runtime executable is unavailable")
    if _sha256(source_checkout / "uv.lock") != RUNTIME_LOCK_SHA256:
        raise ManualRunError("Von runtime lock differs from the pinned source")
    for package, expected_version in RUNTIME_PACKAGES.items():
        try:
            actual_version = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError as exc:
            raise ManualRunError("a preflighted runtime package is missing") from exc
        if actual_version != expected_version:
            raise ManualRunError("a runtime package version differs from preflight")
    if runtime.get("lock_sha256") != RUNTIME_LOCK_SHA256:
        raise ManualRunError("runtime lock hash differs from preflight")


def _repository_revision(path: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"],
        capture_output=True,
        check=True,
        text=True,
        timeout=5,
    )
    return result.stdout.strip()


def _runtime_package_versions() -> tuple[dict[str, str | None], bool]:
    versions: dict[str, str | None] = {}
    available = True
    for package, expected_version in RUNTIME_PACKAGES.items():
        try:
            actual = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            actual = None
        versions[package] = actual
        available = available and actual == expected_version
    return versions, available


def create_preflight_receipt(
    *,
    source_checkout: Path,
    storage_path: Path,
    candidate_run_approved: bool,
    required_free_storage_bytes: int = 8 * 1024**3,
) -> dict[str, Any]:
    storage_path.mkdir(parents=True, exist_ok=True)
    inputs_path = ROOT / "specs" / "decision-model-support" / "evaluation" / "dms01-inputs.jsonl"
    fixture_hash = _sha256(inputs_path) if inputs_path.is_file() else ""
    runtime_packages, runtime_available = _runtime_package_versions()
    lock_path = source_checkout / "uv.lock"
    lock_hash = _sha256(lock_path) if lock_path.is_file() else ""
    source_revision = _repository_revision(source_checkout)
    free_storage = shutil.disk_usage(storage_path).free
    total_memory = None
    try:
        total_memory = int(os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE"))
    except (AttributeError, OSError, ValueError):
        pass
    runner_files = [
        ROOT / "scripts" / "evaluate_decision_models.py",
        Path(__file__).resolve(),
    ]
    harness_files = [
        {"id": str(path.relative_to(ROOT)), "sha256": _sha256(path)}
        for path in runner_files
        if path.is_file()
    ]
    blockers = []
    if not candidate_run_approved:
        blockers.append("candidate-specific Von run approval is absent")
    if fixture_hash != INPUTS_SHA256:
        blockers.append("frozen input fixture hash does not match")
    if source_revision != SOURCE_REVISION or lock_hash != RUNTIME_LOCK_SHA256:
        blockers.append("pinned Von source or runtime lock differs")
    if not runtime_available:
        blockers.append("exact pinned Von runtime packages are unavailable")
    if len(harness_files) != len(runner_files):
        blockers.append("evaluation harness files are incomplete")
    if free_storage < required_free_storage_bytes:
        blockers.append("available storage is below the declared requirement")
    if total_memory is None or total_memory < 24 * 1024**3:
        blockers.append("host does not meet the 24 GiB evaluation memory ceiling")
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
            "state": row["state"],
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
            "state": {
                "task_context": row["task_context"],
                "candidate_messages": [
                    {"id": message["id"], "content": message["content"]}
                    for message in messages
                ],
            },
            "questions": {
                message["id"]: {
                    "text": "Should this candidate message be retained in active context to complete the task?",
                    "options": {
                        "keep": "Retain this message in active context.",
                        "drop": "The active context can omit this message.",
                    },
                }
                for message in messages
            },
        }
    raise ManualRunError("unsupported frozen input row kind")


def _format_state(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return "\n".join(f"{key}: {item}" for key, item in value.items())
    return str(value)


def _probabilities(answer: Any, option_ids: set[str]) -> dict[str, float]:
    raw = getattr(answer, "probabilities", None)
    if not isinstance(raw, dict) or set(raw) != option_ids:
        raise ManualRunError("Von returned an incomplete probability distribution")
    values = {option_id: float(score) for option_id, score in raw.items()}
    if any(not 0.0 <= score <= 1.0 for score in values.values()):
        raise ManualRunError("Von returned a probability outside [0, 1]")
    total = sum(values.values())
    if total <= 0.0:
        raise ManualRunError("Von returned an empty probability distribution")
    # Von's API rounds probabilities to four decimal places; restore a unit sum
    # required by the shared evaluation contract.
    return {option_id: score / total for option_id, score in values.items()}


def _token_count(tokenizer: Any, content: str, *, digit_split: bool) -> int:
    normalized = _DIGITS.sub(lambda match: " ".join(match.group()), content) if digit_split else content
    return len(tokenizer.encode(normalized, add_special_tokens=False))


def score_input_rows(
    rows: list[dict[str, Any]],
    *,
    backend: Any,
    choice_factory: Any,
    tokenizer: Any,
    digit_split: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[float], bool]:
    predictions: list[dict[str, Any]] = []
    token_counts: list[dict[str, Any]] = []
    latencies_ms: list[float] = []
    oom = False
    for row in rows:
        request = build_request(row)
        state_text = _format_state(request["state"])
        scores: dict[str, dict[str, float]] = {}
        if row["kind"] == "retention":
            token_counts.extend(
                {
                    "message_id": message["id"],
                    "token_count": _token_count(
                        tokenizer, message["content"], digit_split=digit_split
                    ),
                }
                for message in row["eligible_messages_oldest_first"]
            )
        status = "ok"
        try:
            for question_id, question in request["questions"].items():
                choice = choice_factory(
                    instructions=question["text"],
                    criteria=question["options"],
                )
                started = time.perf_counter()
                try:
                    answer = backend.evaluate_choice(question_id, state_text, choice)
                finally:
                    latencies_ms.append((time.perf_counter() - started) * 1000)
                probabilities = _probabilities(answer, set(question["options"]))
                if answer.choice not in probabilities or max(probabilities, key=probabilities.get) != answer.choice:
                    raise ManualRunError("Von choice does not match its probability distribution")
                scores[question_id] = probabilities
        except TimeoutError:
            status = "timeout"
        except ManualRunError:
            status = "invalid"
        except Exception as exc:  # noqa: BLE001 - error details may contain input text.
            status = "error"
            oom = oom or "out of memory" in str(exc).lower() or "outofmemory" in type(exc).__name__.lower()
        if status != "ok":
            predictions.append({"id": row["id"], "kind": row["kind"], "status": status})
            continue
        if row["kind"] == "decision":
            question_id = next(iter(request["questions"]))
            predictions.append(
                {
                    "id": row["id"],
                    "kind": "decision",
                    "status": "ok",
                    "choice": max(scores[question_id], key=scores[question_id].get),
                    "score_semantics": "probability",
                    "scores": scores[question_id],
                }
            )
        else:
            predictions.append(
                {
                    "id": row["id"],
                    "kind": "retention",
                    "status": "ok",
                    "score_semantics": "probability",
                    "scores": {message_id: values["keep"] for message_id, values in scores.items()},
                }
            )
    return predictions, token_counts, latencies_ms, oom


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def _peak_rss_bytes() -> int:
    peak = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    return peak if sys.platform == "darwin" else peak * 1024


def _load_local_backend(source_checkout: Path, model_directory: Path) -> tuple[Any, Any, bool]:
    from huggingface_hub import snapshot_download

    model_path = Path(
        snapshot_download(
            repo_id=MODEL_REPOSITORY,
            revision=MODEL_REVISION,
            local_dir=str(model_directory),
        )
    )
    for filename, expected_hash in EXPECTED_MODEL_FILES.items():
        path = model_path / filename
        if not path.is_file() or _sha256(path) != expected_hash:
            raise ManualRunError("downloaded model file does not match its pinned digest")
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    sys.path.insert(0, str(source_checkout / "src"))
    from von.backends.option_marker_backend import OptionMarkerBackend
    from von.types import Choice

    backend = OptionMarkerBackend(checkpoint_dir=str(model_path), device="cpu")
    model = backend._get_model()
    return backend, Choice, bool(model.digit_split)


def run(arguments: argparse.Namespace) -> int:
    preflight = json.loads(arguments.preflight.read_text(encoding="utf-8"))
    verify_preflight(preflight, source_checkout=arguments.source_checkout)
    verify_runtime(preflight, arguments.source_checkout)
    if _sha256(arguments.inputs) != INPUTS_SHA256:
        raise ManualRunError("candidate inputs are not the frozen DMS-01 fixture")
    rows = _read_jsonl(arguments.inputs)
    started = time.perf_counter()
    backend, choice_factory, digit_split = _load_local_backend(
        arguments.source_checkout, arguments.model_directory
    )
    cold_latency_ms = (time.perf_counter() - started) * 1000
    predictions, token_counts, warm_latencies_ms, oom = score_input_rows(
        rows,
        backend=backend,
        choice_factory=choice_factory,
        tokenizer=backend._model.tokenizer,
        digit_split=digit_split,
    )
    _write_jsonl(arguments.predictions, predictions)
    _write_jsonl(arguments.token_counts, token_counts)
    measurements = {
        "model_id": MODEL_ID,
        "artifact_revision": MODEL_REVISION,
        "base_model_id": MODEL_REPOSITORY,
        "base_revision": MODEL_REVISION,
        "harness_id": SOURCE_ID,
        "harness_revision": SOURCE_REVISION,
        "runtime": f"Python {sys.version.split()[0]}; Von in-process CPU fp32",
        "runtime_lock_sha256": RUNTIME_LOCK_SHA256,
        "device": "cpu",
        "precision": "fp32",
        "tokenizer_id": MODEL_REPOSITORY,
        "tokenizer_revision": MODEL_REVISION,
        "model_server": False,
        "cold_latency_ms": cold_latency_ms,
        "warm_latency_ms": warm_latencies_ms,
        "peak_rss_bytes": _peak_rss_bytes(),
        "oom": oom,
    }
    arguments.measurements.parent.mkdir(parents=True, exist_ok=True)
    arguments.measurements.write_text(
        json.dumps(measurements, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
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
            arguments.output.write_text(
                json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            print(json.dumps({"receipt": str(arguments.output), "run_allowed": receipt["run_allowed"]}))
            return 0 if receipt["run_allowed"] else 2
        return run(arguments)
    except Exception as exc:  # noqa: BLE001 - external runtime errors may include input text.
        if isinstance(exc, ManualRunError):
            print(f"Von DMS-06 run blocked: {exc}", file=sys.stderr)
        else:
            print("Von DMS-06 run failed; details omitted to protect synthetic inputs.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
