#!/usr/bin/env python3
"""Run the approved Kev-0.6B checkpoint on the frozen DMS-01 inputs only."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import resource
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
INPUTS_SHA256 = "6d0230190f455d3f488881ef0f709881fba783f33bab4d5a6a93db576cf5c73f"
ADAPTER_ID = "jaredpalmer/kev-0.6b"
ADAPTER_REVISION = "dece6dba8d43f0f7ded45e9f5b9df12474d90843"
BASE_ID = "Qwen/Qwen3-0.6B-Base"
BASE_REVISION = "da87bfb608c14b7cf20ba1ce41287e8de496c0cd"
TOKENIZER_ID = BASE_ID
TOKENIZER_REVISION = BASE_REVISION
HARNESS_ID = "jaredpalmer/kev:research-archive-2026-09-24"
HARNESS_REVISION = "41c7b5a384ce93dd88ae0a28c379e947fe716a8d"
EXPECTED_ARTIFACTS = [
    {"id": ADAPTER_ID, "revision": ADAPTER_REVISION},
    {"id": BASE_ID, "revision": BASE_REVISION},
]


class ManualRunError(RuntimeError):
    """Raised when the approved manual-run boundary is not satisfied."""


def verify_preflight(receipt: dict[str, Any]) -> None:
    if receipt.get("run_allowed") is not True:
        raise ManualRunError("preflight did not allow model download and inference")
    if receipt.get("fixture_criteria_approved") is not True:
        raise ManualRunError("preflight lacks fixture and criteria approval")
    if receipt.get("input_sha256") != INPUTS_SHA256:
        raise ManualRunError("preflight input fixture hash differs")
    if receipt.get("harness") != {"id": HARNESS_ID, "revision": HARNESS_REVISION}:
        raise ManualRunError("preflight research harness revision differs")
    if receipt.get("artifacts") != EXPECTED_ARTIFACTS:
        raise ManualRunError("preflight artifact revisions differ from the pinned run")
    expected_harness_files = [
        {
            "id": str(path.relative_to(ROOT)),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        for path in (
            ROOT / "scripts" / "evaluate_decision_models.py",
            Path(__file__).resolve(),
        )
    ]
    if receipt.get("evaluation_harness_files") != expected_harness_files:
        raise ManualRunError("evaluation harness files differ from preflight")


def verify_runtime(receipt: dict[str, Any], kev_repository: Path) -> None:
    runtime = receipt["runtime"]
    if sys.version.split()[0] != runtime.get("python_version"):
        raise ManualRunError("Python version differs from preflight")
    for package, expected_version in runtime.get("packages", {}).items():
        if importlib.metadata.version(package) != expected_version:
            raise ManualRunError(f"{package} version differs from preflight")
    lock_hash = hashlib.sha256((kev_repository / "uv.lock").read_bytes()).hexdigest()
    if lock_hash != runtime.get("lock_sha256"):
        raise ManualRunError("runtime dependency lock differs from preflight")


def build_request(row: dict[str, Any]) -> dict[str, Any]:
    if row.get("kind") == "decision":
        question = row["question"]
        return {
            "state": row["state"],
            "questions": {
                question["id"]: {
                    "type": "choice",
                    "instructions": question["text"],
                    "criteria": {option["id"]: option["label"] for option in question["options"]},
                }
            },
        }
    if row.get("kind") == "retention":
        messages = row["eligible_messages_oldest_first"]
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
            },
        }
    raise ManualRunError("unsupported frozen input row kind")


def _repository_revision(path: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"],
        capture_output=True,
        check=True,
        text=True,
        timeout=5,
    )
    return result.stdout.strip()


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _rss_peak_bytes() -> int:
    peak = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    return peak if sys.platform == "darwin" else peak * 1024


def _measurements(
    *,
    warm_latencies: list[float],
    cold_latency: float,
    oom: bool,
    kev_repository: Path,
) -> dict[str, Any]:
    package_versions = {
        name: importlib.metadata.version(name)
        for name in ("torch", "transformers", "peft")
    }
    lock_path = kev_repository / "uv.lock"
    return {
        "model_id": ADAPTER_ID,
        "artifact_revision": ADAPTER_REVISION,
        "base_model_id": BASE_ID,
        "base_revision": BASE_REVISION,
        "tokenizer_id": TOKENIZER_ID,
        "tokenizer_revision": TOKENIZER_REVISION,
        "harness_id": HARNESS_ID,
        "harness_revision": HARNESS_REVISION,
        "runtime": f"Python {sys.version.split()[0]}; {package_versions}",
        "runtime_lock_sha256": hashlib.sha256(lock_path.read_bytes()).hexdigest(),
        "precision": "fp32",
        "device": "cpu",
        "cold_latency_ms": cold_latency,
        "warm_latency_ms": warm_latencies,
        "peak_rss_bytes": _rss_peak_bytes(),
        "oom": oom,
        "model_server": False,
    }


def _load_pinned_model(arguments: argparse.Namespace) -> tuple[Any, Any, Any, Any, Any]:
    import torch
    from kev.api import Choice, SystemOneRequest, to_record
    from kev.checkpoint import Checkpoint, LoadOptions
    from kev.model import SERVE_MAX_BRANCH, SERVE_MAX_STATE, user_tokens

    checkpoint = Checkpoint(f"{ADAPTER_ID}@{ADAPTER_REVISION}")
    if checkpoint.meta.base != BASE_ID or checkpoint.meta.base_revision != BASE_REVISION:
        raise ManualRunError("adapter metadata does not match the preflighted base revision")
    tokenizer, model = checkpoint.load(
        "cpu",
        LoadOptions(dtype=torch.float32, merge=True, attn="eager", backend="torch"),
    )
    model.eval()
    return torch, Choice, SystemOneRequest, to_record, (tokenizer, model, SERVE_MAX_STATE, SERVE_MAX_BRANCH, user_tokens)


def _infer_row(
    row: dict[str, Any],
    *,
    tokenizer: Any,
    model: Any,
    choice_type: Any,
    request_type: Any,
    to_record: Any,
    max_state: int,
    max_branch: int,
) -> tuple[dict[str, Any], float]:
    request_value = build_request(row)
    questions = {
        question_id: choice_type(**question)
        for question_id, question in request_value["questions"].items()
    }
    request = request_type(state=request_value["state"], model="kev-0.6b", questions=questions)
    record, metadata = to_record(request)
    encoded = model.encode(tokenizer, record, max_state=max_state, max_branch=max_branch)
    started = time.perf_counter()
    probabilities = model.probs(encoded)
    elapsed_ms = (time.perf_counter() - started) * 1000
    scores_by_question = {
        item["id"]: {
            key: float(score)
            for key, score in zip(item["keys"], probabilities[q_index].tolist(), strict=True)
        }
        for q_index, item in enumerate(metadata)
    }
    if row["kind"] == "decision":
        question_id = metadata[0]["id"]
        scores = scores_by_question[question_id]
        result = {
            "id": row["id"],
            "kind": "decision",
            "status": "ok",
            "choice": max(scores, key=scores.get),
            "score_semantics": "probability",
            "scores": scores,
        }
    else:
        result = {
            "id": row["id"],
            "kind": "retention",
            "status": "ok",
            "score_semantics": "probability",
            "scores": {
                message_id: scores["keep"]
                for message_id, scores in scores_by_question.items()
            },
        }
    return result, elapsed_ms


def run(arguments: argparse.Namespace) -> int:
    preflight = json.loads(arguments.preflight.read_text(encoding="utf-8"))
    verify_preflight(preflight)
    verify_runtime(preflight, arguments.kev_repository)
    if _repository_revision(arguments.kev_repository) != HARNESS_REVISION:
        raise ManualRunError("external Kev source checkout is not the preflighted commit")
    if sys.version_info[:3] != (3, 13, 15):
        raise ManualRunError("the pinned evaluation runtime requires Python 3.13.15")
    if hashlib.sha256(arguments.inputs.read_bytes()).hexdigest() != INPUTS_SHA256:
        raise ManualRunError("candidate inputs are not the exact frozen input fixture")
    _torch, choice_type, request_type, to_record, internals = _load_pinned_model(arguments)
    tokenizer, model, max_state, max_branch, user_tokens = internals
    input_rows = _jsonl(arguments.inputs)
    prediction_rows: list[dict[str, Any]] = []
    token_count_rows = [
        {"message_id": message["id"], "token_count": len(user_tokens(tokenizer, message["content"]))}
        for row in input_rows
        if row.get("kind") == "retention"
        for message in row["eligible_messages_oldest_first"]
    ]
    latencies: list[float] = []
    oom = False

    for index, row in enumerate(input_rows):
        try:
            prediction, elapsed = _infer_row(
                row,
                tokenizer=tokenizer,
                model=model,
                choice_type=choice_type,
                request_type=request_type,
                to_record=to_record,
                max_state=max_state,
                max_branch=max_branch,
            )
            prediction_rows.append(prediction)
            latencies.append(elapsed)
        except ValueError as exc:
            status = "oversize" if "exceeds" in str(exc) or "too long" in str(exc) else "invalid"
            prediction_rows.append({"id": row["id"], "kind": row["kind"], "status": status})
        except RuntimeError as exc:
            oom = "out of memory" in str(exc).lower()
            prediction_rows.append({"id": row["id"], "kind": row["kind"], "status": "error"})
            if oom:
                break
        if (index + 1) % 20 == 0:
            print(f"completed {index + 1}/{len(input_rows)} synthetic cases", flush=True)

    arguments.predictions.parent.mkdir(parents=True, exist_ok=True)
    arguments.predictions.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in prediction_rows),
        encoding="utf-8",
    )
    arguments.token_counts.parent.mkdir(parents=True, exist_ok=True)
    arguments.token_counts.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in token_count_rows),
        encoding="utf-8",
    )
    measurements = _measurements(
        warm_latencies=latencies[1:],
        cold_latency=latencies[0] if latencies else 0.0,
        oom=oom,
        kev_repository=arguments.kev_repository,
    )
    arguments.measurements.parent.mkdir(parents=True, exist_ok=True)
    arguments.measurements.write_text(
        json.dumps(measurements, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "cases_completed": len(prediction_rows),
                "cold_latency_ms": measurements["cold_latency_ms"],
                "peak_rss_bytes": measurements["peak_rss_bytes"],
                "oom": oom,
            },
            sort_keys=True,
        )
    )
    return 2 if oom else 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preflight", type=Path, required=True)
    parser.add_argument("--kev-repository", type=Path, required=True)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--token-counts", type=Path, required=True)
    parser.add_argument("--measurements", type=Path, required=True)
    return parser


def main() -> int:
    return run(_parser().parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
