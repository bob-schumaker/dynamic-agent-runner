#!/usr/bin/env python3
"""Run gated DMS-13 local context evaluation with its pinned Von compactor."""

from __future__ import annotations

import ast
import argparse
import hashlib
import importlib.metadata
import json
import math
import os
import re
import resource
import shutil
import subprocess
import sys
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

MAX_INPUT_TOKENS = 8192
ROOT = Path(__file__).resolve().parents[2]
OFFICIAL_SCORER_SHA256 = "ecce9c4c79dc89d99534ac17b383a5cbb5b9f0c69ee98adaf0684742e3d95251"
ANSWER_MODEL = "mlx-community/Qwen3-4B-Instruct-2507-4bit@50d427756c6b1b2fe0c0a10f67fbda1fc8e82c1b"
ANSWER_MODEL_REPOSITORY = "mlx-community/Qwen3-4B-Instruct-2507-4bit"
ANSWER_MODEL_REVISION = "50d427756c6b1b2fe0c0a10f67fbda1fc8e82c1b"
ANSWER_MODEL_SHA256 = "2a73c6c248601ab904e035548abd8e6abb65ea27dcb5f342fb0a8910eb44173f"
MANIFEST_RELATIVE = Path("specs/decision-model-support/evaluation/dms13-corpus-manifest.json")
PREFLIGHT_RELATIVE = Path("specs/decision-model-support/evaluation/preflight-dms13-run-2026-09-28.json")
RUNTIME_LOCK_RELATIVE = Path("specs/decision-model-support/evaluation/dms13-runtime/poetry.lock")
RUNTIME_LOCK_SHA256 = "24956255add4cb2723714489566b7aa43906316fa19c59c1077eb81f4ec1fade"
RUNTIME_PACKAGES = {
    "accelerate": "1.15.0",
    "huggingface-hub": "1.32.0",
    "mlx": "0.32.2",
    "mlx-lm": "0.31.3",
    "numpy": "2.5.3",
    "tokenizers": "0.23.2",
    "torch": "2.14.0",
    "transformers": "5.17.0",
}
DATASET_SHA256 = "d6f21ea9d60a0d56f34a05b609c79c88a451d2ae03597821ea3d5a9678c3a442"
DATASET_REVISION = "98d7416c24c778c2fee6e6f3006e7a073259d48f"
VON_SOURCE_REVISION = "fb6e7a937e4fc6b6e72b2ce5035edd56bc370e54"
VON_MODEL_REVISION = "5df8185a4f2327ad0a7cd117cc4f701ac557b9ae"
LONGMEMEVAL_SOURCE_REVISION = "9e0b455f4ef0e2ab8f2e582289761153549043fc"
SCORER_MODEL_REPOSITORY = "mlx-community/Llama-3.1-8B-Instruct-4bit"
SCORER_MODEL_REVISION = "90215b22ec18e72f623dde2ea7af4097025160e2"
SCORER_MODEL = f"{SCORER_MODEL_REPOSITORY}@{SCORER_MODEL_REVISION}"
SCORER_MODEL_LICENSE = "Llama 3.1 Community License"
SCORER_MODEL_SIZE_BYTES = 4517489037
SCORER_MODEL_FILES = {
    ".gitattributes": "34448b82c17d60fec9b65b1f093c115ddbaadc04beb1b0140b6bfed2e012a930",
    "README.md": "df2b6fd835306d188b6193fa3dd075c72f4d52140f11e480fffb0f2e19c38cfd",
    "config.json": "88804b1a541a86ce1b5b21dd0b38d95ee99006ef656a0b59ab267ecb0bce8b22",
    "model.safetensors": "192065799d1621df78b68274137974d3258c5dadce9ca71305ed014d997d67c4",
    "model.safetensors.index.json": "9a76e05055778bb04cacb7aff616b378da0e57c87a181c932037a943efba5997",
    "special_tokens_map.json": "6f38c73729248f6c127296386e3cdde96e254636cc58b4169d3fd32328d9a8ec",
    "tokenizer.json": "6b9e4e7fb171f92fd137b777cc2714bf87d11576700a1dcd7a399e7bbe39537b",
    "tokenizer_config.json": "f0f2d5fa9caf736f4184e3fe3316378290696f9ebd9f11ac431d48fbda92a11c",
}
EVALUATION_BUDGETS = [8192, 16384, 32768, 65536]
EXPECTED_VON_TURN_SCORES = 122462
_DIGITS = re.compile(r"\d+")


class ManualRunError(RuntimeError):
    """Raised when the pinned compactor returns unusable scores."""


def verify_run_approval(approval: Mapping[str, Any], *, expected: Mapping[str, Any]) -> None:
    if approval.get("approved") is not True or any(
        approval.get(key) != value for key, value in expected.items()
    ):
        raise ManualRunError("DMS-13 run approval is absent or does not match the pinned run")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as model_file:
        for chunk in iter(lambda: model_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _combined_harness_sha256(*paths: Path) -> str:
    content = b"".join(
        path.relative_to(ROOT).as_posix().encode("utf-8") + b"\0" + path.read_bytes()
        for path in paths
    )
    return hashlib.sha256(content).hexdigest()


def build_run_approval_expectation(root: Path, *, preflight_path: Path) -> dict[str, Any]:
    manifest_path = root / MANIFEST_RELATIVE
    evaluator_path = root / "scripts/evaluate_context_compression.py"
    runner_path = Path(__file__).resolve()
    lock_path = root / RUNTIME_LOCK_RELATIVE
    return {
        "manifest_sha256": _sha256(manifest_path),
        "preflight_sha256": _sha256(preflight_path),
        "harness_sha256": _combined_harness_sha256(evaluator_path, runner_path),
        "runtime_lock_sha256": _sha256(lock_path),
        "dataset_revision": DATASET_REVISION,
        "dataset_sha256": DATASET_SHA256,
        "answer_model": ANSWER_MODEL,
        "compactor": f"wfzyx/von@{VON_MODEL_REVISION}",
        "von_source_revision": VON_SOURCE_REVISION,
        "scorer_model": SCORER_MODEL,
        "scorer_model_files": SCORER_MODEL_FILES,
        "scorer_runtime": "MLX-LM in-process",
        "scorer_model_license": SCORER_MODEL_LICENSE,
        "scorer_model_size_bytes": SCORER_MODEL_SIZE_BYTES,
        "budgets_history_tokens": EVALUATION_BUDGETS,
        "primary_budget_history_tokens": 32768,
        "answer_generation": {"temperature": 0, "max_new_tokens": 512, "thinking": False},
        "answer_context_tokens": 262144,
        "reserved_generation_tokens": 512,
        "acceptance_thresholds": {
            "accuracy_ci_lower_bound_gt": -0.03,
            "evidence_recall_delta_gte": -0.05,
            "accuracy_or_evidence_recall_delta_gte": 0.05,
        },
        "expected_remote_judge_calls": 0,
        "expected_local_judge_calls": 4500,
        "expected_von_turn_scores": EXPECTED_VON_TURN_SCORES,
        "external_data_fields": [],
        "approval_scope": (
            "download exact pinned public artifacts from Hugging Face and run "
            "all inference in process; send no benchmark data to model endpoints"
        ),
    }


def verify_preflight(
    preflight: Mapping[str, Any],
    *,
    runtime_lock_path: Path,
    root: Path = ROOT,
) -> None:
    if preflight.get("preflight_passed") is not True:
        raise ManualRunError("DMS-13 host/runtime preflight did not pass")
    _verify_preflight_runtime(preflight, runtime_lock_path)
    _verify_preflight_artifacts(preflight, root)
    _verify_preflight_approval_state(preflight)


def _verify_preflight_runtime(preflight: Mapping[str, Any], runtime_lock_path: Path) -> None:
    if (
        _sha256(runtime_lock_path) != RUNTIME_LOCK_SHA256
        or preflight.get("runtime_lock_sha256") != RUNTIME_LOCK_SHA256
        or preflight.get("python") != "3.14.7"
        or preflight.get("packages") != RUNTIME_PACKAGES
        or preflight.get("package_versions_match_lock") is not True
    ):
        raise ManualRunError("DMS-13 preflight runtime versions differ from the pinned lock")
    if preflight.get("metal_available") is not True:
        raise ManualRunError("DMS-13 preflight did not verify Metal availability")


def _verify_preflight_artifacts(preflight: Mapping[str, Any], root: Path) -> None:
    if preflight.get("manifest_sha256") != _sha256(root / MANIFEST_RELATIVE):
        raise ManualRunError("DMS-13 preflight manifest digest differs")
    expected_harness_files = [
        {"path": str(path.relative_to(root)), "sha256": _sha256(path)}
        for path in (
            root / "scripts/evaluate_context_compression.py",
            root / "tests/manual/run_context_compression_dms13.py",
        )
    ]
    if preflight.get("harness_files") != expected_harness_files:
        raise ManualRunError("DMS-13 preflight harness digests differ")
    if (
        preflight.get("dataset_revision") != DATASET_REVISION
        or preflight.get("dataset_sha256") != DATASET_SHA256
        or preflight.get("conversation_turns") != EXPECTED_VON_TURN_SCORES
        or preflight.get("von_source_revision") != VON_SOURCE_REVISION
        or preflight.get("longmemeval_source_revision") != LONGMEMEVAL_SOURCE_REVISION
        or preflight.get("official_scorer_sha256") != OFFICIAL_SCORER_SHA256
        or preflight.get("scorer_model") != SCORER_MODEL
        or preflight.get("scorer_model_revision") != SCORER_MODEL_REVISION
        or preflight.get("scorer_model_files") != SCORER_MODEL_FILES
        or preflight.get("scorer_runtime") != "MLX-LM in-process"
        or preflight.get("scorer_model_license") != SCORER_MODEL_LICENSE
        or preflight.get("scorer_model_size_bytes") != SCORER_MODEL_SIZE_BYTES
        or preflight.get("expected_local_judge_calls") != 4500
        or preflight.get("expected_remote_judge_calls") != 0
        or preflight.get("external_data_fields") != []
        or preflight.get("compactor_model_revision") != VON_MODEL_REVISION
        or preflight.get("answer_model")
        != {
            "repository": ANSWER_MODEL_REPOSITORY,
            "revision": ANSWER_MODEL_REVISION,
            "weights_sha256": ANSWER_MODEL_SHA256,
        }
    ):
        raise ManualRunError("DMS-13 preflight artifact pins differ")
    judge_snapshot = Path(str(preflight.get("scorer_model_snapshot_path", "")))
    _verify_judge_snapshot(judge_snapshot)


def _verify_preflight_approval_state(preflight: Mapping[str, Any]) -> None:
    if preflight.get("run_allowed") is not True:
        blockers = preflight.get("blockers")
        if not isinstance(blockers, list) or not blockers or any(
            "approval" not in str(blocker).lower() for blocker in blockers
        ):
            raise ManualRunError("DMS-13 preflight has a non-approval blocker")


def verify_runtime(runtime_executable: Path) -> None:
    if Path(sys.executable).resolve() != runtime_executable.resolve():
        raise ManualRunError("Python executable differs from the preflighted runtime")
    if sys.version.split()[0] != "3.14.7":
        raise ManualRunError("Python version differs from the pinned runtime")
    for package, expected_version in RUNTIME_PACKAGES.items():
        try:
            actual = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError as exc:
            raise ManualRunError("a preflighted runtime package is missing") from exc
        if actual != expected_version:
            raise ManualRunError("a preflighted runtime package version differs")


def _check_current_host(storage_path: Path) -> None:
    try:
        memory_bytes = int(os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE"))
    except (AttributeError, OSError, ValueError) as exc:
        raise ManualRunError("host memory cannot be verified") from exc
    if memory_bytes < 24 * 1024**3 or shutil.disk_usage(storage_path).free < 8 * 1024**3:
        raise ManualRunError("current host capacity is below the DMS-13 run minimum")


def _verify_answer_snapshot(model_path: Path) -> None:
    expected_files = {
        "model.safetensors": ANSWER_MODEL_SHA256,
        "tokenizer.json": "aeb13307a71acd8fe81861d94ad54ab689df773318809eed3cbe794b4492dae4",
        "tokenizer_config.json": "4397cc477eb6d79715ccd2000accd6b3531928f30029665832fa1b255f24d2b9",
        "chat_template.jinja": "40c21f34cf67d8c760ef72f8ad3ae5afad514299d4b06e91dd9a8d705af7b541",
    }
    for filename, expected_hash in expected_files.items():
        path = model_path / filename
        if not path.is_file() or _sha256(path) != expected_hash:
            raise ManualRunError("answer model snapshot differs from its pinned file digest")


def _verify_judge_snapshot(model_path: Path) -> None:
    for filename, expected_hash in SCORER_MODEL_FILES.items():
        path = model_path / filename
        if not path.is_file() or _sha256(path) != expected_hash:
            raise ManualRunError("DMS-13 local judge snapshot differs from its pinned file digest")


def _percentile(values: Sequence[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int((len(ordered) - 1) * fraction))]


def _score_with_local_model(
    generate: Any,
    judge_model: Any,
    judge_tokenizer: Any,
    prompt: str,
) -> str:
    formatted_prompt = judge_tokenizer.apply_chat_template(
        [{"role": "user", "content": prompt}],
        tokenize=False,
        add_generation_prompt=True,
    )
    return generate(
        judge_model,
        judge_tokenizer,
        formatted_prompt,
        temp=0,
        max_tokens=10,
        verbose=False,
    )


def _verify_run_boundary(
    arguments: argparse.Namespace,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    root = ROOT
    runtime_lock_path = root / RUNTIME_LOCK_RELATIVE
    preflight_path = arguments.preflight
    approval_path = arguments.approval
    try:
        preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
        approval = json.loads(approval_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ManualRunError("DMS-13 preflight or user approval receipt is unavailable") from exc
    verify_preflight(preflight, runtime_lock_path=runtime_lock_path, root=root)
    expected_approval = build_run_approval_expectation(root, preflight_path=preflight_path)
    verify_run_approval(approval, expected=expected_approval)

    runtime_executable = Path(preflight.get("runtime_executable", ""))
    verify_runtime(runtime_executable)
    arguments.model_cache.mkdir(parents=True, exist_ok=True)
    _check_current_host(arguments.model_cache)
    if _repository_revision(arguments.source_checkout) != VON_SOURCE_REVISION:
        raise ManualRunError("Von source checkout differs from the pinned revision")
    if _repository_revision(arguments.longmemeval_source) != LONGMEMEVAL_SOURCE_REVISION:
        raise ManualRunError("LongMemEval source checkout differs from the pinned revision")
    scripts_directory = str(root / "scripts")
    if scripts_directory not in sys.path:
        sys.path.insert(0, scripts_directory)
    return expected_approval, approval, preflight


def _load_pinned_models(
    arguments: argparse.Namespace,
    *,
    judge_model_path: Path,
) -> tuple[Any, Any, "VonTurnScorer", float, float, float, Any, Any]:
    from huggingface_hub import snapshot_download

    answer_model_path = Path(
        snapshot_download(
            repo_id=ANSWER_MODEL_REPOSITORY,
            revision=ANSWER_MODEL_REVISION,
            local_dir=str(arguments.model_cache / "answer"),
        )
    )
    _verify_answer_snapshot(answer_model_path)
    _verify_judge_snapshot(judge_model_path)
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    import mlx.core as mx
    from mlx_lm import generate, load

    answer_load_started = time.perf_counter()
    answer_model, answer_tokenizer = load(str(answer_model_path))
    answer_model_load_ms = (time.perf_counter() - answer_load_started) * 1000
    judge_load_started = time.perf_counter()
    judge_model, judge_tokenizer = load(str(judge_model_path))
    judge_model_load_ms = (time.perf_counter() - judge_load_started) * 1000

    manual_directory = str(Path(__file__).resolve().parent)
    if manual_directory not in sys.path:
        sys.path.insert(0, manual_directory)
    from run_von_dms06 import _load_local_backend

    von_started = time.perf_counter()
    von_backend, choice_factory, digit_split = _load_local_backend(
        arguments.source_checkout, arguments.model_cache / "von"
    )
    von_model_load_ms = (time.perf_counter() - von_started) * 1000
    von_scorer = VonTurnScorer(
        backend=von_backend,
        choice_factory=choice_factory,
        tokenizer=von_backend._model.tokenizer,
        digit_split=digit_split,
        pack_sequence=von_backend._model.pack_sequence,
    )
    return (
        answer_model,
        answer_tokenizer,
        von_scorer,
        answer_model_load_ms,
        judge_model_load_ms,
        von_model_load_ms,
        (generate, mx),
        (judge_model, judge_tokenizer),
    )


def run(arguments: argparse.Namespace) -> int:
    expected_approval, approval, preflight = _verify_run_boundary(arguments)
    approval_path = arguments.approval
    preflight_path = arguments.preflight

    from evaluate_context_compression import (
        aggregate_results,
        RankedTurnCompactor,
        build_answer_prompt_messages,
        build_redacted_receipt,
        count_answer_prompt_tokens,
        count_history_tokens,
        _conversation_turns,
        build_history_messages,
        load_dataset,
        paired_accuracy_bootstrap_interval,
        run_evaluation,
        write_redacted_predictions,
    )

    items = load_dataset(arguments.dataset, expected_sha256=DATASET_SHA256)
    actual_turn_count = sum(
        len(_conversation_turns(build_history_messages(item))) for item in items
    )
    if actual_turn_count != expected_approval["expected_von_turn_scores"]:
        raise ManualRunError("dataset turn count differs from the approved run")
    (
        answer_model,
        answer_tokenizer,
        von_scorer,
        answer_model_load_ms,
        judge_model_load_ms,
        von_model_load_ms,
        model_functions,
        judge_model_parts,
    ) = _load_pinned_models(
        arguments,
        judge_model_path=Path(preflight["scorer_model_snapshot_path"]),
    )
    generate, mlx_core = model_functions
    judge_model, judge_tokenizer = judge_model_parts
    def history_token_counter(history):
        return count_history_tokens(history, answer_tokenizer)
    compactor = RankedTurnCompactor(
        score_turn=von_scorer,
        token_counter=history_token_counter,
    )
    prompt_builder = load_official_prompt_builder(
        arguments.longmemeval_source / "src/evaluation/evaluate_qa.py",
        expected_sha256=OFFICIAL_SCORER_SHA256,
    )
    def answer(history, question):
        prompt = answer_tokenizer.apply_chat_template(
            build_answer_prompt_messages(history, question),
            tokenize=False,
            add_generation_prompt=True,
            enable_thinking=False,
        )
        return generate(
            answer_model,
            answer_tokenizer,
            prompt,
            temp=0,
            max_tokens=512,
            verbose=False,
        )

    judge_call_count = 0

    def judge(question_id, question, gold_answer, hypothesis, question_type):
        nonlocal judge_call_count
        prompt = get_official_judge_prompt(
            prompt_builder,
            question_type,
            question,
            gold_answer,
            hypothesis,
            question_id.endswith("_abs"),
        )
        judge_call_count += 1
        content = _score_with_local_model(
            generate, judge_model, judge_tokenizer, prompt
        )
        if not isinstance(content, str):
            raise ManualRunError("official judge returned an invalid label")
        return "yes" in content.lower()

    predictions = run_evaluation(
        items,
        budgets=EVALUATION_BUDGETS,
        max_context_tokens=262144,
        reserved_generation_tokens=512,
        token_counter=history_token_counter,
        prompt_token_counter=lambda history, question: count_answer_prompt_tokens(
            history, question, answer_tokenizer
        ),
        answer=answer,
        judge=judge,
        compact=compactor,
    )
    metrics = aggregate_results(items, predictions)
    primary_budget = 32768
    model_primary = [
        row for row in predictions
        if row["condition"] == "model_guided" and row["budget"] == primary_budget
    ]
    recent_primary = [
        row for row in predictions
        if row["condition"] == "recency" and row["budget"] == primary_budget
    ]
    if all(isinstance(row["correct"], bool) for row in (*model_primary, *recent_primary)):
        accuracy_interval = paired_accuracy_bootstrap_interval(model_primary, recent_primary)
    else:
        accuracy_interval = None
    if judge_call_count != expected_approval["expected_local_judge_calls"]:
        raise ManualRunError("actual local judge call count differs from the approved run")
    if von_scorer.scoring_calls != expected_approval["expected_von_turn_scores"]:
        raise ManualRunError("actual Von turn score count differs from the approved run")
    model_metrics = metrics["model_guided"][primary_budget]
    recency_metrics = metrics["recency"][primary_budget]
    accuracy_delta = (
        model_metrics["answer_accuracy"] - recency_metrics["answer_accuracy"]
        if model_metrics["answer_accuracy"] is not None
        and recency_metrics["answer_accuracy"] is not None
        else None
    )
    evidence_delta = (
        model_metrics["evidence_turn_recall"] - recency_metrics["evidence_turn_recall"]
        if model_metrics["evidence_turn_recall"] is not None
        and recency_metrics["evidence_turn_recall"] is not None
        else None
    )
    accuracy_pass = accuracy_interval is not None and accuracy_interval[0] > -0.03
    evidence_pass = evidence_delta is not None and evidence_delta >= -0.05
    improvement_pass = (accuracy_delta is not None and accuracy_delta >= 0.05) or (
        evidence_delta is not None and evidence_delta >= 0.05
    )
    acceptance = {
        "primary_budget_tokens": primary_budget,
        "accuracy_delta_model_guided_minus_recency": accuracy_delta,
        "accuracy_noninferiority_ci_95": accuracy_interval,
        "accuracy_noninferiority_pass": accuracy_pass,
        "evidence_recall_delta_model_guided_minus_recency": evidence_delta,
        "evidence_noninferiority_pass": evidence_pass,
        "minimum_improvement_pass": improvement_pass,
        "all_thresholds_pass": accuracy_pass and evidence_pass and improvement_pass,
    }
    receipt = build_redacted_receipt(
        corpus_revision=DATASET_REVISION,
        corpus_sha256=DATASET_SHA256,
        answer_model=ANSWER_MODEL,
        scorer=SCORER_MODEL,
        metrics=metrics,
        item_count=len(items),
    )
    latencies = {
        field: [float(row[field]) for row in predictions]
        for field in ("compaction_latency_ms", "answer_latency_ms", "scorer_latency_ms")
    }
    receipt["run"] = {
        "approval_sha256": _sha256(approval_path),
        "preflight_sha256": _sha256(preflight_path),
        "harness_sha256": expected_approval["harness_sha256"],
        "compactor": f"wfzyx/von@{VON_MODEL_REVISION}",
        "runtime_lock_sha256": RUNTIME_LOCK_SHA256,
        "model_load_ms": answer_model_load_ms,
        "judge_model_load_ms": judge_model_load_ms,
        "von_model_load_ms": von_model_load_ms,
        "host_peak_rss_bytes": int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        * (1 if sys.platform == "darwin" else 1024),
        "primary_accuracy_difference_ci_95": accuracy_interval,
        "acceptance": acceptance,
        "local_judge_calls": judge_call_count,
        "von_turn_scores": von_scorer.scoring_calls,
        "mlx_peak_memory_bytes": mlx_core.get_peak_memory(),
        "latency_p50_p95_ms": {
            name: [_percentile(values, 0.50), _percentile(values, 0.95)]
            for name, values in latencies.items()
        },
    }
    arguments.output_dir.mkdir(parents=True, exist_ok=True)
    write_redacted_predictions(arguments.output_dir / "predictions.jsonl", predictions)
    (arguments.output_dir / "receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({"items": len(items), "prediction_rows": len(predictions), "output": str(arguments.output_dir)}))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--source-checkout", type=Path, required=True)
    parser.add_argument("--longmemeval-source", type=Path, required=True)
    parser.add_argument("--model-cache", type=Path, required=True)
    parser.add_argument("--preflight", type=Path, default=ROOT / PREFLIGHT_RELATIVE)
    parser.add_argument("--approval", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    arguments = parser.parse_args(argv)
    try:
        return run(arguments)
    except (ManualRunError, OSError, ValueError, KeyError) as exc:
        print(f"DMS-13 run stopped: {type(exc).__name__}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001 - provider errors may contain benchmark content.
        print(f"DMS-13 run stopped: {type(exc).__name__}", file=sys.stderr)
        return 2


def _repository_revision(path: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"],
        capture_output=True,
        check=True,
        text=True,
        timeout=5,
    )
    return result.stdout.strip()


def load_official_prompt_builder(scorer_source: Path, *, expected_sha256: str):
    """Load only the official prompt function from its hash-pinned source file."""

    try:
        source = scorer_source.read_bytes()
    except OSError as exc:
        raise ManualRunError("official scorer source is unavailable") from exc
    if hashlib.sha256(source).hexdigest() != expected_sha256:
        raise ManualRunError("official scorer source digest differs")
    try:
        module = ast.parse(source, filename=str(scorer_source))
        prompt_function = next(
            node
            for node in module.body
            if isinstance(node, ast.FunctionDef) and node.name == "get_anscheck_prompt"
        )
        namespace: dict[str, Any] = {}
        exec(compile(ast.Module(body=[prompt_function], type_ignores=[]), str(scorer_source), "exec"), namespace)
        return namespace["get_anscheck_prompt"]
    except (StopIteration, SyntaxError, TypeError) as exc:
        raise ManualRunError("official scorer prompt function is invalid") from exc


def get_official_judge_prompt(
    prompt_builder: Any,
    question_type: str,
    question: str,
    gold_answer: Any,
    hypothesis: str,
    is_abstention: bool,
) -> str:
    """Build the exact pinned LongMemEval scorer prompt for one answer."""

    prompt = prompt_builder(
        question_type,
        question,
        gold_answer,
        hypothesis,
        abstention=is_abstention,
    )
    if not isinstance(prompt, str) or not prompt:
        raise ManualRunError("official scorer prompt is invalid")
    return prompt


def _keep_drop_margin(answer: Any) -> float:
    raw = getattr(answer, "probabilities", None)
    if not isinstance(raw, Mapping) or set(raw) != {"keep", "drop"}:
        raise ManualRunError("Von returned an incomplete keep/drop distribution")
    try:
        probabilities = {key: float(value) for key, value in raw.items()}
    except (TypeError, ValueError) as exc:
        raise ManualRunError("Von returned invalid keep/drop probabilities") from exc
    if any(
        not math.isfinite(value) or not 0.0 <= value <= 1.0
        for value in probabilities.values()
    ):
        raise ManualRunError("Von returned invalid keep/drop probabilities")
    total = sum(probabilities.values())
    if total <= 0.0:
        raise ManualRunError("Von returned an empty keep/drop distribution")
    probabilities = {key: value / total for key, value in probabilities.items()}
    if getattr(answer, "choice", None) != max(probabilities, key=probabilities.get):
        raise ManualRunError("Von choice does not match its keep/drop distribution")
    return probabilities["keep"] - probabilities["drop"]


class VonTurnScorer:
    """Score one complete history turn with Von's keep/drop decision head."""

    def __init__(
        self,
        *,
        backend: Any,
        choice_factory: Any,
        tokenizer: Any,
        digit_split: bool = False,
        pack_sequence: Any = None,
    ) -> None:
        self._backend = backend
        self._choice_factory = choice_factory
        self._tokenizer = tokenizer
        self._digit_split = digit_split
        self._pack_sequence = pack_sequence
        self.scoring_calls = 0

    def __call__(self, turn: Sequence[Mapping[str, Any]]) -> float:
        if not turn or any(
            not isinstance(message.get("id"), str)
            or message.get("role") not in {"user", "assistant"}
            or not isinstance(message.get("content"), str)
            for message in turn
        ):
            raise ManualRunError("conversation turn is invalid")
        state = "\n".join(
            f"[{message.get('session_date', '')}] session "
            f"{message.get('session_id', '')} {message['role']}: {message['content']}"
            for message in turn
        )
        instructions = "Should this conversation turn be retained in active context to help answer future requests?"
        criteria = {
            "keep": "Retain this turn in active context.",
            "drop": "The active context can omit this turn.",
        }
        token_text = (
            self._pack_sequence(state, instructions, list(criteria.values()))
            if self._pack_sequence is not None
            else state
        )
        if self._pack_sequence is None and self._digit_split:
            token_text = _DIGITS.sub(lambda match: " ".join(match.group()), token_text)
        try:
            token_count = len(self._tokenizer.encode(token_text, add_special_tokens=False))
        except Exception as exc:  # noqa: BLE001 - tokenizer details may contain history text.
            raise ManualRunError("Von input tokenization failed") from exc
        if token_count > MAX_INPUT_TOKENS:
            raise ManualRunError("Von turn exceeds the pinned input limit")

        turn_key = hashlib.sha256(
            "\0".join(str(message["id"]) for message in turn).encode("utf-8")
        ).hexdigest()[:16]
        choice = self._choice_factory(
            instructions=instructions,
            criteria=criteria,
        )
        try:
            self.scoring_calls += 1
            answer = self._backend.evaluate_choice(turn_key, state, choice)
        except Exception as exc:  # noqa: BLE001 - model errors may contain history text.
            raise ManualRunError("Von turn scoring failed") from exc
        return _keep_drop_margin(answer)


if __name__ == "__main__":
    raise SystemExit(main())
