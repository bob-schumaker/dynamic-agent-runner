#!/usr/bin/env python3
"""Run one approved DMS-14 candidate in process on both option orders."""

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
import subprocess
import sys
import time
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[2]
MATRIX_PATH = ROOT / "specs/decision-model-support/evaluation/dms14-matrix.json"
CORPUS_MANIFEST_PATH = ROOT / "specs/decision-model-support/evaluation/dms14-corpus-manifest.json"
_STATUSES = {"ok", "invalid", "missing", "timeout", "oversize", "abstained", "error"}


class MatrixRunError(RuntimeError):
    """Raised when the frozen corpus, matrix approval, or row identity is invalid."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_matrix_approval(
    matrix_path: Path = MATRIX_PATH,
    corpus_manifest_path: Path = CORPUS_MANIFEST_PATH,
    approval_path: Path | None = None,
) -> dict[str, Any]:
    matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
    corpus = json.loads(corpus_manifest_path.read_text(encoding="utf-8"))
    _verify_corpus_binding(matrix, corpus, corpus_manifest_path)
    _verify_harness_files(matrix)
    if corpus.get("license_review_status") != "cleared":
        raise MatrixRunError("corpus license review has not cleared all source terms")
    if not matrix.get("rows") or matrix.get("approval_scope") != "one approval for the complete matrix":
        raise MatrixRunError("matrix manifest does not define a complete approval scope")
    if approval_path is None or not approval_path.is_file():
        raise MatrixRunError("matrix-level approval receipt is absent")
    approval = json.loads(approval_path.read_text(encoding="utf-8"))
    if approval.get("approved") is not True:
        raise MatrixRunError("matrix-level approval is absent")
    if approval.get("matrix_sha256") != _sha256(matrix_path):
        raise MatrixRunError("matrix hash differs from the approved matrix")
    if approval.get("corpus_manifest_sha256") != _sha256(corpus_manifest_path):
        raise MatrixRunError("corpus manifest hash differs from the approved corpus")
    if approval.get("approval_scope") != matrix["approval_scope"]:
        raise MatrixRunError("approval does not cover the complete matrix")
    return matrix


def _verify_corpus_binding(
    matrix: dict[str, Any], corpus: dict[str, Any], corpus_manifest_path: Path
) -> None:
    if matrix.get("corpus_manifest_sha256") != _sha256(corpus_manifest_path):
        raise MatrixRunError("matrix corpus-manifest hash differs")
    if matrix.get("normalized_input_sha256") != corpus.get("normalized_input_sha256"):
        raise MatrixRunError("matrix normalized input hash differs")
    if matrix.get("gold_label_sha256") != corpus.get("gold_label_sha256"):
        raise MatrixRunError("matrix gold-label hash differs")


def _verify_harness_files(matrix: dict[str, Any]) -> None:
    files = matrix.get("harness_files")
    if not isinstance(files, list) or not files:
        raise MatrixRunError("matrix does not pin the evaluation harness files")
    for item in files:
        path = ROOT / item["path"]
        if not path.is_file() or _sha256(path) != item.get("sha256"):
            raise MatrixRunError("evaluation harness differs from the approved matrix")


def ordered_inputs(
    input_rows: list[dict[str, Any]], option_order: str
) -> list[dict[str, Any]]:
    if option_order not in {"canonical", "reversed"}:
        raise MatrixRunError("option order is unsupported")
    ordered = deepcopy(input_rows)
    for row in ordered:
        if any(key in row for key in ("expected_choice", "gold", "label", "_meta")):
            raise MatrixRunError("gold labels or source metadata reached the model input")
        if row.get("kind") != "decision" or not isinstance(row.get("question"), dict):
            raise MatrixRunError("input row is not a normalized choice request")
        options = row["question"].get("options")
        if not isinstance(options, list) or len(options) < 2:
            raise MatrixRunError("choice request has fewer than two options")
        if option_order == "reversed":
            options.reverse()
    return ordered


def _probability_scores(
    scores: Any, choice: str, option_ids: set[str]
) -> dict[str, float] | None:
    if not isinstance(scores, dict) or set(scores) != option_ids:
        return None
    values = list(scores.values())
    if any(
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(value)
        or not 0 <= value <= 1
        for value in values
    ) or not math.isclose(sum(values), 1.0, abs_tol=1e-4):
        return None
    if choice not in scores or max(scores, key=scores.get) != choice:
        return None
    return {key: float(value) for key, value in scores.items()}


def _ranking_scores(scores: Any, option_ids: set[str]) -> dict[str, float] | None:
    if not isinstance(scores, dict) or set(scores) != option_ids:
        return None
    if any(
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(value)
        for value in scores.values()
    ):
        return None
    return {key: float(value) for key, value in scores.items()}


def _safe_result(
    item_id: str, option_order: str, raw: dict[str, Any], option_ids: set[str]
) -> dict[str, Any]:
    status = raw.get("status", "invalid")
    if status not in _STATUSES:
        status = "invalid"
    result: dict[str, Any] = {"id": item_id, "option_order": option_order, "status": status}
    if status != "ok":
        return result
    choice = raw.get("choice")
    if not isinstance(choice, str) or choice not in option_ids:
        return {"id": item_id, "option_order": option_order, "status": "invalid"}
    semantics = raw.get("score_semantics")
    result["choice"] = choice
    clean_scores = None
    if semantics in {"probability", "calibrated_probability"}:
        clean_scores = _probability_scores(raw.get("scores"), choice, option_ids)
    elif semantics == "ranking_score":
        clean_scores = _ranking_scores(raw.get("scores"), option_ids)
    if semantics in {"probability", "calibrated_probability", "ranking_score"}:
        if clean_scores is None:
            return {"id": item_id, "option_order": option_order, "status": "invalid"}
        result.update(score_semantics=semantics, scores=clean_scores)
    return result


def run_rows(
    input_rows: list[dict[str, Any]],
    infer: Callable[[dict[str, Any]], dict[str, Any]],
) -> list[dict[str, Any]]:
    """Run fake or real in-process inference on canonical and reversed inputs."""

    predictions = []
    for order in ("canonical", "reversed"):
        for row in ordered_inputs(input_rows, order):
            try:
                raw = infer(row)
                option_ids = {option["id"] for option in row["question"]["options"]}
                prediction = _safe_result(row["id"], order, raw, option_ids)
            except TimeoutError:
                prediction = {"id": row["id"], "option_order": order, "status": "timeout"}
            except Exception as exc:  # noqa: BLE001 - model errors can reveal input text.
                status = "error"
                if isinstance(exc, (ValueError, MatrixRunError)):
                    status = "invalid"
                prediction = {"id": row["id"], "option_order": order, "status": status}
            predictions.append(prediction)
    return predictions


def _load_module(filename: str) -> Any:
    path = ROOT / "tests" / "manual" / filename
    name = f"_dms14_{path.stem}"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise MatrixRunError("candidate runner module is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_kev(candidate: dict[str, Any], source_checkout: Path) -> tuple[Callable[..., Any], Any]:
    runner = _load_module(candidate["runner_module"])
    loaded_at = time.perf_counter()
    arguments = SimpleNamespace(kev_repository=source_checkout)
    _torch, choice_type, request_type, to_record, internals = runner._load_pinned_model(arguments)
    tokenizer, model, max_state, max_branch, _user_tokens = internals
    load_ms = (time.perf_counter() - loaded_at) * 1000
    latencies: list[float] = []

    def infer(item: dict[str, Any]) -> dict[str, Any]:
        result, elapsed = runner._infer_row(
            item,
            tokenizer=tokenizer,
            model=model,
            choice_type=choice_type,
            request_type=request_type,
            to_record=to_record,
            max_state=max_state,
            max_branch=max_branch,
        )
        latencies.append(elapsed)
        return result

    return infer, lambda: latencies, load_ms


def _load_von(
    candidate: dict[str, Any], source_checkout: Path, model_directory: Path
) -> tuple[Callable[..., Any], Any]:
    runner = _load_module(candidate["runner_module"])
    loaded_at = time.perf_counter()
    backend, choice_type, digit_split = runner._load_local_backend(source_checkout, model_directory)
    load_ms = (time.perf_counter() - loaded_at) * 1000
    latencies: list[float] = []

    def infer(item: dict[str, Any]) -> dict[str, Any]:
        output, _counts, timings, _oom = runner.score_input_rows(
            [item], backend=backend, choice_factory=choice_type,
            tokenizer=backend._model.tokenizer, digit_split=digit_split,
        )
        latencies.extend(timings)
        return output[0]

    return infer, lambda: latencies, load_ms


def _load_poorjev(
    candidate: dict[str, Any], source_checkout: Path, model_directory: Path
) -> tuple[Callable[..., Any], Any]:
    runner = _load_module(candidate["runner_module"])
    loaded_at = time.perf_counter()
    client, internals = runner._load_backend(source_checkout, model_directory)
    choice_type, tokenizer = internals
    load_ms = (time.perf_counter() - loaded_at) * 1000
    latencies: list[float] = []

    def infer(item: dict[str, Any]) -> dict[str, Any]:
        output, _counts, timings, _oom = runner.score_input_rows(
            [item], client=client,
            choice_factory=lambda options: choice_type(options=options), tokenizer=tokenizer,
        )
        latencies.extend(timings)
        return output[0]

    return infer, lambda: latencies, load_ms


def _load_litjev(
    candidate: dict[str, Any], source_checkout: Path, model_directory: Path
) -> tuple[Callable[..., Any], Any]:
    runner = _load_module(candidate["runner_module"])
    loaded_at = time.perf_counter()
    engine, choice_type, schema_factory, tokenizer = runner._load_engine(
        source_checkout, model_directory
    )
    load_ms = (time.perf_counter() - loaded_at) * 1000
    latencies: list[float] = []

    def infer(item: dict[str, Any]) -> dict[str, Any]:
        output, _counts, timings, _oom = runner.score_input_rows(
            [item], engine=engine, choice_factory=choice_type,
            schema_factory=schema_factory, tokenizer=tokenizer,
        )
        latencies.extend(timings)
        return output[0]

    return infer, lambda: latencies, load_ms


def _load_laya(
    candidate: dict[str, Any], source_checkout: Path, model_directory: Path
) -> tuple[Callable[..., Any], Any]:
    runner = _load_module(candidate["runner_module"])
    loaded_at = time.perf_counter()
    agent = runner._load_agent(source_checkout, model_directory)
    load_ms = (time.perf_counter() - loaded_at) * 1000
    latencies: list[float] = []

    def infer(item: dict[str, Any]) -> dict[str, Any]:
        output, _counts, timings, _rss, _oom = runner.score_input_rows(
            [item], agent=agent, tokenizer=agent.tok
        )
        latencies.extend(timings)
        return output[0]

    return infer, lambda: latencies, load_ms


def _candidate_inference(
    candidate: dict[str, Any],
    *,
    source_checkout: Path,
    model_directory: Path,
) -> tuple[Callable[[dict[str, Any]], dict[str, Any]], Callable[[], list[float]], float]:
    sys.path.insert(0, str(source_checkout))
    loaders = {
        "kev-0.6b-cpu": lambda: _load_kev(candidate, source_checkout),
        "kev-0.8b-cpu": lambda: _load_kev(candidate, source_checkout),
        "von-cpu": lambda: _load_von(candidate, source_checkout, model_directory),
        "poorjev-cpu": lambda: _load_poorjev(candidate, source_checkout, model_directory),
        "litjev-cpu": lambda: _load_litjev(candidate, source_checkout, model_directory),
        "laya-mlx-metal": lambda: _load_laya(candidate, source_checkout, model_directory),
    }
    try:
        return loaders[candidate["id"]]()
    except KeyError as exc:
        raise MatrixRunError("candidate has no approved in-process adapter") from exc


def _verify_row_runtime(
    candidate: dict[str, Any], source_checkout: Path, runtime_lock: Path
) -> None:
    expected_revision = candidate["source"]["revision"]
    actual = subprocess.run(
        ["git", "-C", str(source_checkout), "rev-parse", "HEAD"],
        capture_output=True,
        check=True,
        text=True,
        timeout=5,
    ).stdout.strip()
    if actual != expected_revision:
        raise MatrixRunError("candidate source revision differs from the frozen matrix")
    if not runtime_lock.is_file() or _sha256(runtime_lock) != candidate["runtime"]["lock_sha256"]:
        raise MatrixRunError("candidate runtime lock differs from the frozen matrix")
    if sys.version.split()[0] != candidate["runtime"]["python_version"]:
        raise MatrixRunError("Python version differs from the frozen matrix")
    for package, version in candidate["runtime"]["packages"].items():
        if importlib.metadata.version(package) != version:
            raise MatrixRunError(f"{package} version differs from the frozen matrix")


def _verify_candidate_artifacts(
    candidate: dict[str, Any], model_directory: Path
) -> None:
    for artifact in candidate.get("artifact_files", []):
        if candidate["id"].startswith("kev-"):
            repository_cache = "models--" + artifact["repository"].replace("/", "--")
            artifact_path = (
                model_directory
                / "hub"
                / repository_cache
                / "snapshots"
                / artifact["revision"]
                / artifact["path"]
            )
        else:
            artifact_path = model_directory / artifact["path"]
        if (
            not artifact_path.is_file()
            or artifact_path.stat().st_size != artifact["size_bytes"]
            or _sha256(artifact_path) != artifact["sha256"]
        ):
            raise MatrixRunError("candidate artifact digest differs from the frozen matrix")


def _configure_offline_model_access(candidate: dict[str, Any], model_directory: Path) -> None:
    os.environ["HF_HOME"] = str(
        model_directory if candidate["id"].startswith("kev-") else model_directory / "hf-home"
    )
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"


def run_candidate(arguments: argparse.Namespace) -> int:
    matrix = verify_matrix_approval(arguments.matrix, arguments.corpus_manifest, arguments.approval)
    candidate = next((item for item in matrix["rows"] if item["id"] == arguments.candidate), None)
    if candidate is None:
        raise MatrixRunError("candidate row is not in the approved matrix")
    _verify_row_runtime(candidate, arguments.source_checkout, arguments.runtime_lock)
    _verify_candidate_artifacts(candidate, arguments.model_directory)
    input_rows = _read_jsonl(arguments.inputs)
    if _sha256(arguments.inputs) != matrix["normalized_input_sha256"]:
        raise MatrixRunError("normalized corpus inputs differ from the approved matrix")
    _configure_offline_model_access(candidate, arguments.model_directory)
    infer, latencies, load_ms = _candidate_inference(
        candidate,
        source_checkout=arguments.source_checkout,
        model_directory=arguments.model_directory,
    )
    predictions = run_rows(input_rows, infer)
    arguments.predictions.parent.mkdir(parents=True, exist_ok=True)
    arguments.predictions.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in predictions),
        encoding="utf-8",
    )
    elapsed = latencies()
    peak_rss = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    if sys.platform != "darwin":
        peak_rss *= 1024
    measurements = {
        "candidate_id": candidate["id"],
        "model": candidate["model"],
        "source": candidate["source"],
        "runtime": candidate["runtime"],
        "device": candidate["device"],
        "precision": candidate["precision"],
        "execution_mode": "in_process",
        "model_server": False,
        "row_count": len(input_rows),
        "prediction_count": len(predictions),
        "failures": sum(item["status"] != "ok" for item in predictions),
        "model_load_ms": load_ms,
        "cold_latency_ms": load_ms,
        "warm_latency_ms": elapsed,
        "peak_rss_bytes": peak_rss,
        "host_platform": platform.platform(),
    }
    arguments.measurements.parent.mkdir(parents=True, exist_ok=True)
    arguments.measurements.write_text(
        json.dumps(measurements, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return 0


def execute_matrix(
    matrix: dict[str, Any],
    preflight: dict[str, Any],
    run_row: Callable[[dict[str, Any], dict[str, Any]], bool],
) -> dict[str, Any]:
    """Execute every preflighted row under the same matrix-level approval."""

    if preflight.get("matrix_sha256") != matrix.get("_matrix_sha256"):
        raise MatrixRunError("preflight matrix hash differs")
    if preflight.get("run_allowed") is not True:
        raise MatrixRunError("matrix preflight has blockers")
    row_preflights = preflight.get("rows")
    if not isinstance(row_preflights, dict) or set(row_preflights) != {
        row["id"] for row in matrix["rows"]
    }:
        raise MatrixRunError("preflight does not cover every matrix row")
    if any(row.get("run_allowed") is not True for row in row_preflights.values()):
        raise MatrixRunError("at least one frozen matrix row failed preflight")
    required = ("runtime_executable", "source_checkout", "runtime_lock", "model_directory")
    if any(
        any(
            not isinstance(row_preflights[row["id"]].get(key), str)
            or not row_preflights[row["id"]][key]
            for key in required
        )
        for row in matrix["rows"]
    ):
        raise MatrixRunError("preflight is missing command inputs for a matrix row")
    results = []
    for row in matrix["rows"]:
        status = "completed" if run_row(row, row_preflights[row["id"]]) else "failed"
        results.append({"candidate_id": row["id"], "status": status})
    return {
        "matrix_sha256": preflight["matrix_sha256"],
        "corpus_manifest_sha256": preflight["corpus_manifest_sha256"],
        "approval_scope": "one approval for the complete matrix",
        "rows": results,
        "completed_rows": sum(row["status"] == "completed" for row in results),
        "failed_rows": sum(row["status"] == "failed" for row in results),
    }


def run_full_matrix(arguments: argparse.Namespace) -> int:
    matrix = verify_matrix_approval(arguments.matrix, arguments.corpus_manifest, arguments.approval)
    matrix_hash = _sha256(arguments.matrix)
    matrix["_matrix_sha256"] = matrix_hash
    preflight = json.loads(arguments.preflight.read_text(encoding="utf-8"))
    if preflight.get("corpus_manifest_sha256") != _sha256(arguments.corpus_manifest):
        raise MatrixRunError("preflight corpus manifest hash differs")
    if _sha256(arguments.inputs) != matrix["normalized_input_sha256"]:
        raise MatrixRunError("normalized corpus inputs differ from the approved matrix")
    for row in matrix["rows"]:
        row_preflight = preflight.get("rows", {}).get(row["id"], {})
        runtime = Path(row_preflight.get("runtime_executable", ""))
        source = Path(row_preflight.get("source_checkout", ""))
        lock = Path(row_preflight.get("runtime_lock", ""))
        model = Path(row_preflight.get("model_directory", ""))
        if not runtime.is_file() or not os.access(runtime, os.X_OK):
            raise MatrixRunError("preflighted runtime executable is unavailable")
        if not source.is_dir() or not lock.is_file() or not model.is_dir():
            raise MatrixRunError("preflighted source, lock, or model directory is unavailable")

    def run_row(candidate: dict[str, Any], row_preflight: dict[str, Any]) -> bool:
        row_output = arguments.output_dir / candidate["id"]
        command = [
            row_preflight["runtime_executable"],
            str(Path(__file__).resolve()),
            "--candidate",
            candidate["id"],
            "--matrix",
            str(arguments.matrix),
            "--corpus-manifest",
            str(arguments.corpus_manifest),
            "--approval",
            str(arguments.approval),
            "--source-checkout",
            row_preflight["source_checkout"],
            "--runtime-lock",
            row_preflight["runtime_lock"],
            "--model-directory",
            row_preflight["model_directory"],
            "--inputs",
            str(arguments.inputs),
            "--predictions",
            str(row_output / "predictions.jsonl"),
            "--measurements",
            str(row_output / "measurements.json"),
        ]
        result = subprocess.run(command, capture_output=True, check=False, timeout=None)
        return result.returncode == 0

    report = execute_matrix(matrix, preflight, run_row)
    arguments.output_dir.mkdir(parents=True, exist_ok=True)
    (arguments.output_dir / "matrix-receipt.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return 0 if report["failed_rows"] == 0 else 2


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate")
    parser.add_argument("--run-matrix", action="store_true")
    parser.add_argument("--matrix", type=Path, default=MATRIX_PATH)
    parser.add_argument("--corpus-manifest", type=Path, default=CORPUS_MANIFEST_PATH)
    parser.add_argument("--approval", type=Path)
    parser.add_argument("--preflight", type=Path)
    parser.add_argument("--source-checkout", type=Path)
    parser.add_argument("--runtime-lock", type=Path)
    parser.add_argument("--model-directory", type=Path)
    parser.add_argument("--inputs", type=Path)
    parser.add_argument("--predictions", type=Path)
    parser.add_argument("--measurements", type=Path)
    parser.add_argument("--output-dir", type=Path)
    arguments = parser.parse_args()
    try:
        if arguments.run_matrix:
            if not all((arguments.approval, arguments.preflight, arguments.inputs, arguments.output_dir)):
                parser.error("--run-matrix requires --approval, --preflight, --inputs, and --output-dir")
            return run_full_matrix(arguments)
        if not arguments.candidate or not all((
            arguments.approval,
            arguments.source_checkout,
            arguments.runtime_lock,
            arguments.model_directory,
            arguments.inputs,
            arguments.predictions,
            arguments.measurements,
        )):
            parser.error("a candidate row requires approval, source/runtime paths, inputs, and output paths")
        return run_candidate(arguments)
    except (MatrixRunError, OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f"DMS-14 candidate run blocked: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
