#!/usr/bin/env python3
"""Evaluate the frozen DMS-01 additions on one exact local runtime row."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import resource
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
INPUTS_SHA256 = "6d0230190f455d3f488881ef0f709881fba783f33bab4d5a6a93db576cf5c73f"
MATRIX_PATH = ROOT / "specs/decision-model-support/evaluation/dms01-additions-matrix.json"
RUNNERS = {"macjev-torch-cpu", "lev-torch-cpu", "jevstyle-torch-cpu", "jevstyle-gguf-f16-cpu"}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_questions(row: dict[str, Any]) -> tuple[Any, dict[str, dict[str, Any]]]:
    if row.get("kind") == "decision":
        question = row["question"]
        options = question["options"]
        if len(options) < 2 or len({option["id"] for option in options}) != len(options):
            raise ValueError("decision fixture options are invalid")
        return row["state"], {
            question["id"]: {
                "text": question["text"],
                "options": {option["id"]: option["label"] for option in options},
            }
        }
    if row.get("kind") == "retention":
        messages = row["eligible_messages_oldest_first"]
        if len({message["id"] for message in messages}) != len(messages):
            raise ValueError("retention fixture message IDs are invalid")
        return row["task_context"], {
            message["id"]: {
                "text": (
                    "Should this candidate message be retained in active context to complete "
                    "the task?\nCandidate message:\n" + message["content"]
                ),
                "options": {
                    "keep": "Retain this message in active context.",
                    "drop": "The active context can omit this message.",
                },
            }
            for message in messages
        }
    raise ValueError("unsupported frozen input row kind")


def prediction_from_answers(row: dict[str, Any], answers: dict[str, Any]) -> dict[str, Any]:
    _, questions = build_questions(row)
    if set(answers) != set(questions):
        raise ValueError("answer IDs do not match the requested questions")
    probabilities: dict[str, dict[str, float]] = {}
    for question_id, question in questions.items():
        answer = answers[question_id]
        raw = answer.get("probabilities") if isinstance(answer, dict) else None
        if not isinstance(raw, dict) or set(raw) != set(question["options"]):
            raise ValueError("model returned an incomplete probability distribution")
        try:
            values = {key: float(value) for key, value in raw.items()}
        except (TypeError, ValueError) as exc:
            raise ValueError("model returned invalid probabilities") from exc
        if any(not 0 <= value <= 1 for value in values.values()) or abs(sum(values.values()) - 1) > 0.002:
            raise ValueError("model returned invalid probabilities")
        selected = answer.get("choice", answer.get("answer"))
        if selected not in values or values[selected] + 1e-7 < max(values.values()):
            raise ValueError("model returned an invalid or inconsistent choice")
        probabilities[question_id] = values
    if row["kind"] == "decision":
        question_id = next(iter(questions))
        scores = probabilities[question_id]
        choice = answers[question_id].get("choice", answers[question_id].get("answer"))
        return {
            "id": row["id"], "kind": "decision", "status": "ok", "choice": choice,
            "score_semantics": "probability", "scores": scores,
        }
    return {
        "id": row["id"], "kind": "retention", "status": "ok",
        "score_semantics": "probability",
        "scores": {message_id: values["keep"] for message_id, values in probabilities.items()},
    }


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _rss_peak_bytes(include_child: bool = False) -> int:
    peak = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    if include_child:
        peak += int(resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss)
    return peak if sys.platform == "darwin" else peak * 1024


class Candidate:
    def __init__(self, candidate_id: str, materials: Path, source: Path | None, scorer: Path | None):
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
        self.candidate_id = candidate_id
        self.close_engine = None
        self.kind = "torch"
        if candidate_id == "macjev-torch-cpu":
            sys.path.insert(0, str(materials))
            from macjev import MacJev

            self.engine = MacJev(materials, device="cpu")
            self.count_tokens = lambda text: len(self.engine.tokenizer.encode(text, add_special_tokens=False))
            self.infer_one = self._infer_macjev
        elif candidate_id == "jevstyle-torch-cpu":
            sys.path.insert(0, str(materials))
            from jev_style_decision import JevStyleDecision

            self.engine = JevStyleDecision(materials, device="cpu", dtype="bfloat16", verify=True)
            self.count_tokens = lambda text: len(self.engine.encode(text))
            self.infer_one = self._infer_jevstyle
        elif candidate_id == "jevstyle-gguf-f16-cpu":
            sys.path.insert(0, str(materials))
            from jev_style_decision_gguf import JevStyleDecisionGGUF

            self.engine = JevStyleDecisionGGUF(
                materials, quant="F16", gguf=materials / "Jev-Style-0.8B-Decision-v3-F16.gguf",
                binary=scorer, n_gpu_layers=0, many_mode="exact", verify=True,
            )
            self.close_engine = self.engine.close
            self.kind = "gguf"
            self.count_tokens = lambda text: len(self.engine.encode(text))
            self.infer_one = self._infer_jevstyle
        elif candidate_id == "lev-torch-cpu":
            if source is None:
                raise ValueError("Lev source checkout is required")
            sys.path.insert(0, str(source))
            import torch
            from lev.api import Choice, SystemOneRequest, to_answers, to_record
            from lev.evaluate import load
            from lev.model import user_tokens

            self.torch = torch
            self.Choice = Choice
            self.SystemOneRequest = SystemOneRequest
            self.to_answers = to_answers
            self.to_record = to_record
            self.engine = load(str(materials), "cpu")
            self.temperature = float(json.loads((materials / "calibration.json").read_text())["temperature"])
            self.count_tokens = lambda text: len(user_tokens(self.engine[0], text))
            self.infer_one = self._infer_lev
        else:
            raise ValueError("unknown DMS-01 addition candidate")

    def _infer_macjev(self, state: Any, question: dict[str, Any]) -> dict[str, Any]:
        result = self.engine.decide(state, {"t": "choice", "ins": question["text"], "crit": question["options"]})
        return {"answer": result["answer"], "probabilities": result["probabilities"]}

    def _infer_jevstyle(self, state: Any, question: dict[str, Any]) -> dict[str, Any]:
        request = {"t": "choice", "ins": question["text"], "crit": question["options"]}
        result = self.engine.decide(state, request)
        return {"choice": result["answer"], "probabilities": result["probabilities"]}

    def _infer_lev(self, state: Any, question: dict[str, Any]) -> dict[str, Any]:
        tokenizer, model = self.engine
        request = self.SystemOneRequest(
            state=state,
            questions={"candidate": self.Choice(type="choice", instructions=question["text"], criteria=question["options"])},
        )
        record, metadata = self.to_record(request)
        encoded = model.encode(tokenizer, record, max_state=8192, max_branch=8192)
        with self.torch.inference_mode():
            raw = [self.torch.softmax(scores / self.temperature, -1).cpu() for scores in model.forward(encoded)]
        answers = self.to_answers(raw, metadata)
        answer = answers["candidate"]
        return {"choice": answer["choice"], "probabilities": answer["probabilities"]}

    def predict(self, row: dict[str, Any]) -> tuple[dict[str, Any], float]:
        state, questions = build_questions(row)
        answers: dict[str, Any] = {}
        elapsed_ms = 0.0
        for question_id, question in questions.items():
            started = time.perf_counter()
            answers[question_id] = self.infer_one(state, question)
            elapsed_ms += (time.perf_counter() - started) * 1000
        return prediction_from_answers(row, answers), elapsed_ms


def _expected_artifacts(candidate_id: str, candidate_spec: dict[str, Any]) -> list[dict[str, str]]:
    artifacts = [{"id": candidate_spec["model_id"], "revision": candidate_spec["model_revision"]}]
    if candidate_id == "lev-torch-cpu":
        artifacts.extend([
            {"id": candidate_spec["source_id"], "revision": candidate_spec["source_revision"]},
            {"id": candidate_spec["base_model_id"], "revision": candidate_spec["base_revision"]},
        ])
    return artifacts


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _verify_digests(directory: Path, checks: dict[str, str]) -> None:
    for filename, expected in checks.items():
        _require(_sha256(directory / filename) == expected, f"pinned model material digest differs: {filename}")


def _verify_lev_materials(
    candidate_spec: dict[str, Any], source: Path | None, base_materials: Path | None, materials: Path,
) -> None:
    _require(source is not None and base_materials is not None, "Lev source and pinned base-model materials are required")
    revision = subprocess.run(
        ["git", "-C", str(source), "rev-parse", "HEAD"],
        capture_output=True, check=True, text=True, timeout=5,
    ).stdout.strip()
    _require(revision == candidate_spec["source_revision"], "Lev source checkout differs from the frozen matrix")
    _require(_sha256(source / "uv.lock") == candidate_spec["source_lock_sha256"], "Lev uv.lock differs from the frozen matrix")
    _require(_sha256(base_materials / "model.safetensors") == candidate_spec["base_weight_sha256"],
             "LFM2.5 base weights differ from the frozen matrix")
    _verify_digests(materials, {
        "adapter_model.safetensors": candidate_spec["adapter_sha256"],
        "head.pt": candidate_spec["head_sha256"],
    })


def _verify_gguf_build(candidate_spec: dict[str, Any], preflight: dict[str, Any], scorer: Path | None) -> None:
    _require(scorer is not None and _sha256(scorer) == preflight.get("scorer_sha256"),
             "compiled GGUF scorer differs from its preflight digest")
    _require(preflight.get("llama_cpp_revision") == candidate_spec["llama_cpp_revision"],
             "llama.cpp revision differs from the pinned GGUF build")


def _verify_materials(
    candidate_id: str,
    candidate_spec: dict[str, Any],
    preflight: dict[str, Any],
    materials: Path,
    source: Path | None,
    base_materials: Path | None,
    scorer: Path | None,
) -> None:
    checks = {
        "macjev-torch-cpu": {
            "manifest.json": candidate_spec.get("runtime_manifest_sha256", ""),
            "model.safetensors": candidate_spec.get("model_file_sha256", ""),
        },
        "jevstyle-torch-cpu": {
            "manifest.json": candidate_spec.get("runtime_manifest_sha256", ""),
            "model.safetensors": candidate_spec.get("model_file_sha256", ""),
            "jev_style_decision.py": candidate_spec.get("runtime_file_sha256", ""),
        },
        "jevstyle-gguf-f16-cpu": {
            "manifest.json": candidate_spec.get("runtime_manifest_sha256", ""),
            "Jev-Style-0.8B-Decision-v3-F16.gguf": candidate_spec.get("model_file_sha256", ""),
            "jev_style_decision_gguf.py": candidate_spec.get("runtime_file_sha256", ""),
            "jev_score.cpp": candidate_spec.get("scorer_source_sha256", ""),
            "build_jev_score.sh": candidate_spec.get("build_script_sha256", ""),
        },
    }
    if candidate_id == "lev-torch-cpu":
        _verify_lev_materials(candidate_spec, source, base_materials, materials)
        return
    _verify_digests(materials, checks[candidate_id])
    if candidate_id == "jevstyle-gguf-f16-cpu":
        _verify_gguf_build(candidate_spec, preflight, scorer)


def _verify_preflight(arguments: argparse.Namespace) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    preflight = json.loads(arguments.preflight.read_text(encoding="utf-8"))
    matrix = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
    _require(preflight.get("run_allowed") is True and preflight.get("candidate_run_approved") is True,
             "DMS-01 addition run is not approved and preflighted")
    _require(preflight.get("candidate_id") == arguments.candidate, "candidate differs from its preflight receipt")
    _require(preflight.get("matrix_sha256") == _sha256(MATRIX_PATH), "candidate matrix differs from its approved preflight")
    _require(preflight.get("input_sha256") == INPUTS_SHA256 and _sha256(arguments.inputs) == INPUTS_SHA256,
             "input fixture does not match the frozen DMS-01 fixture")
    _require(arguments.candidate in RUNNERS and arguments.candidate in matrix["candidates"],
             "candidate is not in the frozen DMS-01 additions matrix")
    _require(preflight.get("runner_sha256") == _sha256(Path(__file__).resolve()),
             "runner differs from the preflighted harness")
    candidate_spec = matrix["candidates"][arguments.candidate]
    _require(preflight.get("artifacts") == _expected_artifacts(arguments.candidate, candidate_spec),
             "artifact IDs or revisions differ from the approved candidate row")
    runtime = preflight["runtime"]
    for package, version in runtime["packages"].items():
        _require(importlib.metadata.version(package) == version, f"{package} runtime differs from preflight")
    lock_path = Path(preflight["runtime_lock_path"])
    _require(_sha256(lock_path) == runtime["lock_sha256"], "runtime lock differs from the approved preflight")
    _verify_materials(
        arguments.candidate, candidate_spec, preflight, arguments.materials,
        arguments.source, arguments.base_materials, arguments.scorer,
    )
    return matrix, candidate_spec, runtime


def _evaluate_rows(engine: Candidate, rows: list[dict[str, Any]], candidate_id: str) -> tuple[list[dict[str, Any]], list[float], list[str], bool]:
    predictions: list[dict[str, Any]] = []
    latencies: list[float] = []
    errors: list[str] = []
    oom = False
    for index, row in enumerate(rows):
        try:
            prediction, elapsed_ms = engine.predict(row)
            predictions.append(prediction)
            latencies.append(elapsed_ms)
        except ValueError as exc:
            status = "oversize" if any(term in str(exc).lower() for term in ("exceed", "budget", "too long")) else "invalid"
            predictions.append({"id": row["id"], "kind": row["kind"], "status": status})
            errors.append(type(exc).__name__)
        except RuntimeError as exc:
            oom = "out of memory" in str(exc).lower()
            predictions.append({"id": row["id"], "kind": row["kind"], "status": "error"})
            errors.append(type(exc).__name__)
            if oom:
                break
        except Exception as exc:  # Record class only; fixture content stays local.
            predictions.append({"id": row["id"], "kind": row["kind"], "status": "error"})
            errors.append(type(exc).__name__)
        if (index + 1) % 20 == 0:
            print(f"{candidate_id}: completed {index + 1}/{len(rows)} cases", flush=True)
    return predictions, latencies, errors, oom


def _write_results(
    arguments: argparse.Namespace,
    candidate_spec: dict[str, Any],
    runtime: dict[str, Any],
    cold_ms: float,
    predictions: list[dict[str, Any]],
    token_rows: list[dict[str, Any]],
    latencies: list[float],
    errors: list[str],
    oom: bool,
) -> None:
    arguments.predictions.parent.mkdir(parents=True, exist_ok=True)
    arguments.predictions.write_text("".join(json.dumps(item, sort_keys=True) + "\n" for item in predictions))
    arguments.token_counts.parent.mkdir(parents=True, exist_ok=True)
    arguments.token_counts.write_text("".join(json.dumps(item, sort_keys=True) + "\n" for item in token_rows))
    measurements = {
        "model_id": candidate_spec["model_id"], "artifact_revision": candidate_spec["model_revision"],
        "base_model_id": candidate_spec.get("base_model_id"), "base_revision": candidate_spec.get("base_revision"),
        "harness_id": "dynamic-agent-runner DMS-01 additions", "harness_revision": _sha256(Path(__file__).resolve()),
        "runtime": runtime["id"], "runtime_lock_sha256": runtime["lock_sha256"],
        "device": "cpu", "precision": candidate_spec["precision"], "tokenizer_id": candidate_spec["tokenizer_id"],
        "tokenizer_revision": candidate_spec["tokenizer_revision"], "model_server": False,
        "cold_latency_ms": cold_ms, "warm_latency_ms": latencies[1:],
        "peak_rss_bytes": _rss_peak_bytes(arguments.candidate == "jevstyle-gguf-f16-cpu"),
        "peak_rss_scope": (
            "parent plus scorer-child high-water RSS; conservative upper bound"
            if arguments.candidate == "jevstyle-gguf-f16-cpu" else "runner process"
        ),
        "oom": oom, "error_types": sorted(set(errors)),
        "candidate_id": arguments.candidate,
    }
    arguments.measurements.parent.mkdir(parents=True, exist_ok=True)
    arguments.measurements.write_text(json.dumps(measurements, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"candidate": arguments.candidate, "cases_completed": len(predictions),
                      "cold_latency_ms": cold_ms, "peak_rss_bytes": measurements["peak_rss_bytes"],
                      "oom": oom}, sort_keys=True))


def run(arguments: argparse.Namespace) -> int:
    _matrix, candidate_spec, runtime = _verify_preflight(arguments)
    started = time.perf_counter()
    engine = Candidate(arguments.candidate, arguments.materials, arguments.source, arguments.scorer)
    cold_ms = (time.perf_counter() - started) * 1000
    rows = _read_jsonl(arguments.inputs)
    token_rows = [
        {"message_id": message["id"], "token_count": engine.count_tokens(message["content"])}
        for row in rows if row["kind"] == "retention"
        for message in row["eligible_messages_oldest_first"]
    ]
    predictions, latencies, errors, oom = _evaluate_rows(engine, rows, arguments.candidate)
    if engine.close_engine:
        engine.close_engine()
    _write_results(arguments, candidate_spec, runtime, cold_ms, predictions, token_rows, latencies, errors, oom)
    return 2 if oom else 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", choices=sorted(RUNNERS), required=True)
    parser.add_argument("--preflight", type=Path, required=True)
    parser.add_argument("--materials", type=Path, required=True)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--base-materials", type=Path)
    parser.add_argument("--scorer", type=Path)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--token-counts", type=Path, required=True)
    parser.add_argument("--measurements", type=Path, required=True)
    return parser


if __name__ == "__main__":
    raise SystemExit(run(_parser().parse_args()))
