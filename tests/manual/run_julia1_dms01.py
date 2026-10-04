#!/usr/bin/env python3
"""Run the pinned Julia 1 model on the frozen DMS-01 inputs."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import resource
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
INPUTS_SHA256 = "6d0230190f455d3f488881ef0f709881fba783f33bab4d5a6a93db576cf5c73f"
MODEL_ID = "SupersonicLabs/Julia-1"
MODEL_REVISION = "a85b127321d580d65176c89ced8273f305745d85"
SOURCE_REVISION = MODEL_REVISION
TOKENIZER_ID = MODEL_ID
TOKENIZER_REVISION = MODEL_REVISION
EXPECTED_ARTIFACTS = [{"id": MODEL_ID, "revision": MODEL_REVISION}]


class ManualRunError(RuntimeError):
    """Raised when the manual DMS-01 evaluation boundary is not satisfied."""


def verify_preflight(receipt: dict[str, Any]) -> None:
    if receipt.get("run_allowed") is not True:
        raise ManualRunError("preflight did not allow model inference")
    if receipt.get("fixture_criteria_approved") is not True:
        raise ManualRunError("preflight lacks fixture and criteria approval")
    if receipt.get("input_sha256") != INPUTS_SHA256:
        raise ManualRunError("preflight input fixture hash differs")
    if receipt.get("artifacts") != EXPECTED_ARTIFACTS:
        raise ManualRunError("preflight model revision differs")
    expected_files = [
        {"id": str(path.relative_to(ROOT)), "sha256": _sha256(path)}
        for path in (ROOT / "scripts/evaluate_decision_models.py", Path(__file__).resolve())
    ]
    if receipt.get("evaluation_harness_files") != expected_files:
        raise ManualRunError("evaluation harness files differ from preflight")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_request(row: dict[str, Any]) -> tuple[str, dict[str, dict[str, Any]]]:
    if row.get("kind") == "decision":
        question = row["question"]
        return json.dumps(row["state"], sort_keys=True, separators=(",", ":")), {
            question["id"]: {
                "type": "choice",
                "instructions": question["text"],
                "criteria": {option["id"]: option["label"] for option in question["options"]},
            }
        }
    if row.get("kind") == "retention":
        messages = row["eligible_messages_oldest_first"]
        state = {
            "task_context": row["task_context"],
            "candidate_messages": [
                {"id": message["id"], "content": message["content"]}
                for message in messages
            ],
        }
        questions = {
            message["id"]: {
                "type": "choice",
                "instructions": (
                    "Should this candidate message be retained in the active context "
                    "to complete the task?"
                ),
                "criteria": {
                    "keep": "Retain this message in the active context.",
                    "drop": "The active context can omit this message.",
                },
            }
            for message in messages
        }
        return json.dumps(state, ensure_ascii=False, sort_keys=True, separators=(",", ":")), questions
    raise ManualRunError("unsupported frozen input row kind")


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _rss_peak_bytes() -> int:
    peak = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    return peak if sys.platform == "darwin" else peak * 1024


def _predict(engine: Any, row: dict[str, Any]) -> tuple[dict[str, Any], float]:
    state, questions = build_request(row)
    started = time.perf_counter()
    raw = engine.predict(state=state, questions=questions)
    elapsed_ms = (time.perf_counter() - started) * 1000
    answers = raw.get("answers") if isinstance(raw, dict) else None
    if not isinstance(answers, dict) or set(answers) != set(questions):
        raise ValueError("Julia 1 answer IDs do not match the request")
    if row["kind"] == "decision":
        answer = answers[next(iter(questions))]
        scores = answer.get("probabilities")
        choice = answer.get("choice")
        return {
            "id": row["id"],
            "kind": "decision",
            "status": "ok",
            "choice": choice,
            "score_semantics": "probability",
            "scores": scores,
        }, elapsed_ms
    scores = {
        message_id: answer["probabilities"]["keep"]
        for message_id, answer in answers.items()
    }
    return {
        "id": row["id"],
        "kind": "retention",
        "status": "ok",
        "score_semantics": "probability",
        "scores": scores,
    }, elapsed_ms


def run(arguments: argparse.Namespace) -> int:
    preflight = json.loads(arguments.preflight.read_text(encoding="utf-8"))
    verify_preflight(preflight)
    runtime = preflight["runtime"]
    if sys.version.split()[0] != runtime.get("python_version"):
        raise ManualRunError("Python version differs from preflight")
    for package, version in runtime.get("packages", {}).items():
        if importlib.metadata.version(package) != version:
            raise ManualRunError(f"{package} version differs from preflight")
    if _sha256(arguments.inputs) != INPUTS_SHA256:
        raise ManualRunError("candidate inputs are not the exact frozen input fixture")

    sys.path.insert(0, str(arguments.model_materials))
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    import julia

    started = time.perf_counter()
    engine = julia.load_model(str(arguments.model_materials), device="cpu", backend="torch")
    cold_ms = (time.perf_counter() - started) * 1000
    input_rows = _jsonl(arguments.inputs)
    predictions: list[dict[str, Any]] = []
    latencies: list[float] = []
    token_counts = {
        message["id"]: len(engine.tokenizer.encode(message["content"], add_special_tokens=False))
        for row in input_rows
        if row.get("kind") == "retention"
        for message in row["eligible_messages_oldest_first"]
    }
    for index, row in enumerate(input_rows):
        try:
            prediction, elapsed = _predict(engine, row)
            predictions.append(prediction)
            latencies.append(elapsed)
        except Exception:
            predictions.append({"id": row["id"], "kind": row["kind"], "status": "error"})
        if (index + 1) % 20 == 0:
            print(f"completed {index + 1}/{len(input_rows)} cases", flush=True)

    arguments.predictions.parent.mkdir(parents=True, exist_ok=True)
    arguments.predictions.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in predictions),
        encoding="utf-8",
    )
    arguments.token_counts.parent.mkdir(parents=True, exist_ok=True)
    arguments.token_counts.write_text(
        "".join(
            json.dumps({"message_id": key, "token_count": value}, sort_keys=True) + "\n"
            for key, value in sorted(token_counts.items())
        ),
        encoding="utf-8",
    )
    measurements = {
        "model_id": MODEL_ID,
        "artifact_revision": MODEL_REVISION,
        "harness_id": "dynamic-agent-runner DMS-01 Julia 1",
        "harness_revision": preflight["harness"]["revision"],
        "runtime": runtime["id"],
        "runtime_lock_sha256": runtime["lock_sha256"],
        "device": "cpu",
        "precision": "fp32",
        "tokenizer_id": TOKENIZER_ID,
        "tokenizer_revision": TOKENIZER_REVISION,
        "model_server": False,
        "cold_latency_ms": cold_ms,
        "warm_latency_ms": latencies[1:] if len(latencies) > 1 else latencies,
        "peak_rss_bytes": _rss_peak_bytes(),
        "oom": False,
    }
    arguments.measurements.parent.mkdir(parents=True, exist_ok=True)
    arguments.measurements.write_text(json.dumps(measurements, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"cases_completed": len(predictions), "cold_latency_ms": cold_ms}))
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preflight", type=Path, required=True)
    parser.add_argument("--model-materials", type=Path, required=True)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--token-counts", type=Path, required=True)
    parser.add_argument("--measurements", type=Path, required=True)
    return parser


if __name__ == "__main__":
    raise SystemExit(run(_parser().parse_args()))
