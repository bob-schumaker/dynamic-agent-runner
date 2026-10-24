#!/usr/bin/env python3
"""Run the approved DMS-20 transfer cohort in process."""

from __future__ import annotations

import argparse
import copy
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
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[2]
MATRIX_PATH = ROOT / "specs/decision-model-support/evaluation/dms20-matrix.json"
CORPUS_PATH = (
    ROOT / "specs/decision-model-support/evaluation/dms14-corpus-manifest.json"
)
_STATUSES = {"ok", "invalid", "missing", "timeout", "oversize", "abstained", "error"}
_LEAD_IDS = {"julia-1", "kev-4b", "lev", "strands-decider-2b"}
_CONTENT_TOKEN_LIMIT = 3584


class MatrixRunError(RuntimeError):
    """Raised when the frozen DMS-20 approval or preflight does not match."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _normalized_text(row: dict[str, Any]) -> str:
    question = row["question"]
    labels = "\n".join(option["label"] for option in question["options"])
    state = json.dumps(row["state"], ensure_ascii=False, sort_keys=True)
    return f"{state}\n{question['text']}\n{labels}"


def verify_matrix_approval(
    matrix_path: Path = MATRIX_PATH,
    corpus_path: Path = CORPUS_PATH,
    approval_path: Path | None = None,
) -> dict[str, Any]:
    matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
    corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    _verify_corpus(matrix, corpus, corpus_path)
    _verify_harness(matrix)
    _verify_approval(matrix, matrix_path, corpus_path, approval_path)
    return matrix


def _verify_corpus(
    matrix: dict[str, Any], corpus: dict[str, Any], corpus_path: Path
) -> None:
    if matrix.get("corpus_manifest_sha256") != _sha256(corpus_path):
        raise MatrixRunError("corpus manifest digest differs")
    if matrix.get("normalized_input_sha256") != corpus.get("normalized_input_sha256"):
        raise MatrixRunError("normalized input digest differs")
    if matrix.get("gold_label_sha256") != corpus.get("gold_label_sha256"):
        raise MatrixRunError("gold label digest differs")
    if corpus.get("license_review_status") != "cleared":
        raise MatrixRunError("corpus license review has not cleared")


def _verify_harness(matrix: dict[str, Any]) -> None:
    files = matrix.get("harness_files")
    if not isinstance(files, list) or not files:
        raise MatrixRunError("matrix does not pin its harness files")
    for item in files:
        path = ROOT / item["path"]
        if not path.is_file() or _sha256(path) != item.get("sha256"):
            raise MatrixRunError("evaluation harness digest differs")


def _verify_approval(
    matrix: dict[str, Any],
    matrix_path: Path,
    corpus_path: Path,
    approval_path: Path | None,
) -> None:
    rows = matrix.get("rows")
    if not isinstance(rows, list) or not rows:
        raise MatrixRunError("matrix has no candidate rows")
    dispositions = {row["id"]: row["disposition"] for row in rows}
    runnable = [row["id"] for row in rows if row["disposition"] == "selected"]
    if len(dispositions) != len(rows) or set(dispositions.values()) - {
        "selected",
        "deferred",
        "unsupported",
    }:
        raise MatrixRunError("matrix candidate dispositions are malformed")
    _verify_lead_set(dispositions)
    if approval_path is None or not approval_path.is_file():
        raise MatrixRunError("matrix-level approval receipt is absent")
    approval = json.loads(approval_path.read_text(encoding="utf-8"))
    if approval.get("approved") is not True:
        raise MatrixRunError("matrix-level approval is absent")
    if approval.get("matrix_sha256") != _sha256(matrix_path):
        raise MatrixRunError("matrix hash differs from approved matrix")
    if approval.get("corpus_manifest_sha256") != _sha256(corpus_path):
        raise MatrixRunError("corpus manifest hash differs from approved corpus")
    if approval.get("approval_scope") != matrix.get("approval_scope"):
        raise MatrixRunError("approval does not cover the complete matrix")
    if approval.get("dispositions") != dispositions:
        raise MatrixRunError("approval does not bind every matrix disposition")
    if approval.get("runnable_cohort") != runnable:
        raise MatrixRunError("approval runnable cohort differs from matrix")


def _verify_lead_set(dispositions: dict[str, str]) -> None:
    if set(dispositions) != _LEAD_IDS:
        raise MatrixRunError("matrix must contain the exact four DMS-20 leads")
    if any(disposition != "selected" for disposition in dispositions.values()):
        raise MatrixRunError("all four DMS-20 leads must be selected")


def ordered_inputs(
    input_rows: list[dict[str, Any]], option_order: str
) -> list[dict[str, Any]]:
    if option_order not in {"canonical", "reversed"}:
        raise MatrixRunError("option order is unsupported")
    rows = copy.deepcopy(input_rows)
    for row in rows:
        if any(key in row for key in ("expected_choice", "gold", "label", "_meta")):
            raise MatrixRunError("gold labels or source metadata reached model input")
        if row.get("kind") != "decision" or not isinstance(row.get("question"), dict):
            raise MatrixRunError("row is not a normalized decision input")
        options = row["question"].get("options")
        if not isinstance(options, list) or len(options) < 2:
            raise MatrixRunError("decision input has fewer than two options")
        if option_order == "reversed":
            options.reverse()
    return rows


def _clean_result(
    item_id: str, order: str, raw: dict[str, Any], option_ids: set[str]
) -> dict[str, Any]:
    status = raw.get("status", "invalid")
    if status not in _STATUSES:
        status = "invalid"
    result: dict[str, Any] = {"id": item_id, "option_order": order, "status": status}
    if status != "ok":
        return result
    choice = raw.get("choice")
    if not isinstance(choice, str) or choice not in option_ids:
        result["status"] = "invalid"
        return result
    result["choice"] = choice
    semantics, scores = raw.get("score_semantics"), raw.get("scores")
    if semantics in {"probability", "calibrated_probability"}:
        if (
            not isinstance(scores, dict)
            or set(scores) != option_ids
            or any(
                not isinstance(v, (int, float))
                or isinstance(v, bool)
                or not math.isfinite(v)
                or not 0 <= v <= 1
                for v in scores.values()
            )
            or not math.isclose(sum(scores.values()), 1.0, abs_tol=1e-4)
            or max(scores, key=scores.get) != choice
        ):
            result["status"] = "invalid"
            result.pop("choice")
            return result
        result.update(
            score_semantics=semantics, scores={k: float(v) for k, v in scores.items()}
        )
    elif semantics == "ranking_score":
        if (
            not isinstance(scores, dict)
            or set(scores) != option_ids
            or any(
                not isinstance(v, (int, float))
                or isinstance(v, bool)
                or not math.isfinite(v)
                for v in scores.values()
            )
        ):
            result["status"] = "invalid"
            result.pop("choice")
            return result
        result.update(
            score_semantics=semantics, scores={k: float(v) for k, v in scores.items()}
        )
    return result


def run_rows(
    input_rows: list[dict[str, Any]], infer: Callable[[dict[str, Any]], dict[str, Any]]
) -> list[dict[str, Any]]:
    predictions = []
    for order in ("canonical", "reversed"):
        for row in ordered_inputs(input_rows, order):
            try:
                options = row["question"]["options"]
                prediction = _clean_result(
                    row["id"], order, infer(row), {item["id"] for item in options}
                )
            except TimeoutError:
                prediction = {
                    "id": row["id"],
                    "option_order": order,
                    "status": "timeout",
                }
            except Exception as exc:  # noqa: BLE001 - exception text may contain input data.
                status = (
                    "invalid"
                    if isinstance(exc, (ValueError, MatrixRunError))
                    else "error"
                )
                prediction = {"id": row["id"], "option_order": order, "status": status}
            predictions.append(prediction)
    return predictions


def execute_matrix(
    matrix: dict[str, Any],
    preflight: dict[str, Any],
    execute_row: Callable[[dict[str, Any], dict[str, Any]], bool],
) -> dict[str, Any]:
    runnable = [row for row in matrix["rows"] if row["disposition"] == "selected"]
    if preflight.get("run_allowed") is not True:
        raise MatrixRunError("matrix preflight does not allow execution")
    if preflight.get("matrix_sha256") != matrix.get("_matrix_sha256"):
        raise MatrixRunError("preflight matrix digest differs")
    if preflight.get("corpus_manifest_sha256") != matrix.get("corpus_manifest_sha256"):
        raise MatrixRunError("preflight corpus digest differs")
    checks = preflight.get("rows")
    if not isinstance(checks, dict) or any(row["id"] not in checks for row in runnable):
        raise MatrixRunError("preflight must cover every selected row")
    completed = []
    for row in runnable:
        check = checks[row["id"]]
        if check.get("run_allowed") is not True:
            raise MatrixRunError(f"selected row {row['id']} failed preflight")
        if not execute_row(row, check):
            raise MatrixRunError(f"selected row {row['id']} did not complete")
        completed.append(row["id"])
    return {"completed_rows": len(completed), "row_ids": completed}


def _material_snapshot(material_root: Path, repository: str, revision: str) -> Path:
    repository_cache = f"models--{repository.replace('/', '--')}"
    snapshot = material_root / repository_cache / "snapshots" / revision
    if not snapshot.is_dir():
        raise MatrixRunError(
            "pinned artifact snapshot is absent from the material cache"
        )
    return snapshot


def _verify_artifacts(row: dict[str, Any], material_root: Path) -> dict[str, Path]:
    snapshots: dict[tuple[str, str], Path] = {}
    for item in row["artifact_files"]:
        key = (item["repository"], item["revision"])
        if key not in snapshots:
            snapshots[key] = _material_snapshot(material_root, *key)
        snapshot = snapshots[key]
        artifact = snapshot / item["path"]
        if (
            not artifact.is_file()
            or artifact.stat().st_size != item["size_bytes"]
            or _sha256(artifact) != item["sha256"]
        ):
            raise MatrixRunError(f"pinned artifact differs: {item['path']}")
    return {
        "model": snapshots[(row["model"]["id"], row["model"]["revision"])],
        "base": snapshots.get(
            (
                row["base_model"]["id"],
                row["base_model"]["revision"],
            )
            if row.get("base_model")
            else ("", "")
        ),
    }


def stage_candidate(
    matrix_path: Path,
    corpus_path: Path,
    approval_path: Path,
    candidate_id: str,
    material_root: Path,
) -> dict[str, Any]:
    from huggingface_hub import snapshot_download

    matrix = verify_matrix_approval(matrix_path, corpus_path, approval_path)
    row = next((item for item in matrix["rows"] if item["id"] == candidate_id), None)
    if row is None or row["disposition"] != "selected":
        raise MatrixRunError("candidate is not selected in the approved matrix")
    material_root.mkdir(parents=True, exist_ok=True)
    _check_resources(row, material_root, before_stage=True)
    repositories = sorted(
        {(item["repository"], item["revision"]) for item in row["artifact_files"]}
    )
    for repository, revision in repositories:
        snapshot_download(
            repository,
            revision=revision,
            cache_dir=str(material_root),
            allow_patterns=matrix["artifact_download_allow_patterns"],
            ignore_patterns=matrix["artifact_download_ignore_patterns"],
        )
    _verify_artifacts(row, material_root)
    return {
        "candidate_id": candidate_id,
        "artifact_repositories": len(repositories),
        "verified": True,
    }


def _check_resources(
    row: dict[str, Any], material_root: Path, *, before_stage: bool
) -> dict[str, int]:
    floors = row["resource_floor"]
    page_size = os.sysconf("SC_PAGE_SIZE")
    physical_memory = os.sysconf("SC_PHYS_PAGES") * page_size
    if sys.platform == "darwin":
        output = subprocess.run(
            ["memory_pressure"], capture_output=True, check=True, text=True, timeout=5
        ).stdout
        marker = "System-wide memory free percentage:"
        line = next(
            (item for item in output.splitlines() if item.startswith(marker)), None
        )
        if line is None:
            raise MatrixRunError("could not read current macOS memory pressure")
        free_percent = int(line.removeprefix(marker).strip().rstrip("%"))
        free_memory = physical_memory * free_percent // 100
    else:
        free_memory = os.sysconf("SC_AVPHYS_PAGES") * page_size
    if free_memory < floors["minimum_free_memory_bytes"]:
        raise MatrixRunError(
            "current free memory is below the approved candidate floor"
        )
    free_disk = shutil.disk_usage(material_root).free
    disk_floor_key = (
        "minimum_free_disk_before_stage_bytes"
        if before_stage
        else "minimum_free_disk_after_stage_bytes"
    )
    if free_disk < floors[disk_floor_key]:
        raise MatrixRunError("current free disk is below the approved candidate floor")
    return {"free_memory_bytes_estimate": free_memory, "free_disk_bytes": free_disk}


def _load_julia(model_dir: Path) -> tuple[Callable[..., Any], Any, Any]:
    sys.path.insert(0, str(model_dir))
    import julia

    engine = julia.load_model(str(model_dir), device="cpu", backend="torch")

    def infer(row: dict[str, Any]) -> dict[str, Any]:
        question = row["question"]
        qid = question["id"]
        raw = engine.predict(
            state=json.dumps(row["state"], ensure_ascii=False, sort_keys=True),
            questions={
                qid: {
                    "type": "choice",
                    "instructions": question["text"],
                    "criteria": {
                        option["id"]: option["label"] for option in question["options"]
                    },
                }
            },
        )
        answer = raw["answers"][qid]
        return {
            "status": "ok",
            "choice": answer["choice"],
            "score_semantics": "probability",
            "scores": answer["probabilities"],
        }

    return (
        infer,
        lambda row: len(engine.tokenizer.encode(_normalized_text(row))),
        engine,
    )


def _load_kev(row: dict[str, Any], source: Path) -> tuple[Callable[..., Any], Any, Any]:
    sys.path.insert(0, str(source))
    import torch
    from kev.api import Choice, SystemOneRequest, to_record
    from kev.checkpoint import Checkpoint, LoadOptions
    from kev.model import SERVE_MAX_BRANCH, SERVE_MAX_STATE

    checkpoint = Checkpoint(f"{row['model']['id']}@{row['model']['revision']}")
    if (
        checkpoint.meta.base != row["base_model"]["id"]
        or checkpoint.meta.base_revision != row["base_model"]["revision"]
    ):
        raise MatrixRunError("Kev adapter base identity differs from the matrix")
    tokenizer, model = checkpoint.load(
        "cpu",
        LoadOptions(dtype=torch.float32, merge=True, attn="eager", backend="torch"),
    )
    model.eval()

    def infer(item: dict[str, Any]) -> dict[str, Any]:
        question = item["question"]
        qid = question["id"]
        request = SystemOneRequest(
            state=item["state"],
            model="kev-4b",
            questions={
                qid: Choice(
                    type="choice",
                    instructions=question["text"],
                    criteria={
                        option["id"]: option["label"] for option in question["options"]
                    },
                )
            },
        )
        record, metadata = to_record(request)
        encoded = model.encode(
            tokenizer, record, max_state=SERVE_MAX_STATE, max_branch=SERVE_MAX_BRANCH
        )
        with torch.inference_mode():
            probs = model.probs(encoded)[0].tolist()
        scores = {
            key: float(value)
            for key, value in zip(metadata[0]["keys"], probs, strict=True)
        }
        return {
            "status": "ok",
            "choice": max(scores, key=scores.get),
            "score_semantics": "probability",
            "scores": scores,
        }

    return (
        infer,
        lambda item: len(tokenizer.encode(_normalized_text(item))),
        (tokenizer, model),
    )


def _load_lev(
    row: dict[str, Any], model_dir: Path, base_dir: Path, source: Path
) -> tuple[Callable[..., Any], Any, Any]:
    sys.path.insert(0, str(source / "packages" / "lev" / "src"))
    import torch
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from lev.calibrate import CalibrationProfile
    from lev.model import DecisionEngine, EngineConfig, _load_head, _set_adapter_scale

    os.environ["HF_HUB_OFFLINE"] = "1"
    manifest = json.loads((model_dir / "lev_release.json").read_text(encoding="utf-8"))
    tokenizer = AutoTokenizer.from_pretrained(str(model_dir), local_files_only=True)
    model = AutoModelForCausalLM.from_pretrained(
        str(base_dir), dtype=torch.float32, local_files_only=True
    )
    model = PeftModel.from_pretrained(model, str(model_dir), local_files_only=True)
    scale = float(manifest.get("adapter_scale", 1.0))
    if scale != 1.0:
        _set_adapter_scale(model, scale)
    model = model.merge_and_unload().eval()
    head = _load_head(model_dir / "mode_b_head.pt", model)
    calibration = (
        CalibrationProfile.load(model_dir / "calibration.json")
        if (model_dir / "calibration.json").is_file()
        else CalibrationProfile()
    )
    engine = DecisionEngine(
        model,
        tokenizer,
        EngineConfig(
            model_id=row["base_model"]["id"],
            prompt_style=manifest.get("prompt_style", "plain"),
        ),
        calibration,
        mode_b_head=head,
    )

    def infer(item: dict[str, Any]) -> dict[str, Any]:
        question = item["question"]
        answer = engine.system_one(
            item["state"],
            {question["id"]: _lev_choice_question(question)},
        ).answers[question["id"]]
        return {
            "status": "ok",
            "choice": answer.choice,
            "score_semantics": "calibrated_probability",
            "scores": answer.probabilities,
        }

    return (
        infer,
        lambda item: len(tokenizer.encode(_normalized_text(item))),
        engine,
    )


def _lev_choice_question(question: dict[str, Any]) -> Any:
    from lev import Choice

    return Choice(
        type="choice",
        instructions=question["text"],
        criteria={option["id"]: option["label"] for option in question["options"]},
    )


def _load_strands(
    row: dict[str, Any], model_dir: Path, source: Path
) -> tuple[Callable[..., Any], Any, Any]:
    sys.path.insert(0, str(source / "src"))
    from strands_decider.infer import load_engine
    from strands_decider.schema import ChoiceQuestion

    engine = load_engine(str(model_dir), device="cpu")

    def infer(item: dict[str, Any]) -> dict[str, Any]:
        question = item["question"]
        answer = engine.ask(
            item["state"],
            {
                question["id"]: ChoiceQuestion(
                    instructions=question["text"],
                    criteria={
                        option["id"]: option["label"] for option in question["options"]
                    },
                )
            },
        ).answers[question["id"]]
        return {
            "status": "ok",
            "choice": answer.choice,
            "score_semantics": "calibrated_probability",
            "scores": answer.probabilities,
        }

    return (
        infer,
        lambda item: len(engine.tok.encode(_normalized_text(item))),
        engine,
    )


def _preflight_candidate(
    arguments: argparse.Namespace,
) -> tuple[dict[str, Any], dict[str, Any]]:
    matrix = verify_matrix_approval(
        arguments.matrix, arguments.corpus_manifest, arguments.approval
    )
    row = next(
        (item for item in matrix["rows"] if item["id"] == arguments.candidate), None
    )
    if row is None:
        raise MatrixRunError("candidate is outside the approved matrix")
    if _sha256(arguments.inputs) != matrix["normalized_input_sha256"]:
        raise MatrixRunError("normalized inputs differ from the approved corpus")
    if _sha256(arguments.labels) != matrix["gold_label_sha256"]:
        raise MatrixRunError("gold labels differ from the approved corpus")
    lock_path = ROOT / row["runtime"]["lock_path"]
    if _sha256(lock_path) != row["runtime"]["lock_sha256"]:
        raise MatrixRunError("candidate runtime lock differs from the approved matrix")
    if sys.version.split()[0] != row["runtime"]["python_version"]:
        raise MatrixRunError("Python version differs from the approved row")
    for package, version in row["runtime"]["packages"].items():
        if importlib.metadata.version(package) != version:
            raise MatrixRunError(f"{package} version differs from the approved row")
    _verify_source_checkout(row, arguments.source)
    return row, _verify_artifacts(row, arguments.material_root)


def _verify_source_checkout(row: dict[str, Any], source: Path) -> None:
    if row["id"] == "julia-1":
        return
    actual = subprocess.run(
        ["git", "-C", str(source), "rev-parse", "HEAD"],
        capture_output=True,
        check=True,
        text=True,
        timeout=5,
    ).stdout.strip()
    if actual != row["source"]["revision"]:
        raise MatrixRunError("candidate source checkout differs from the matrix")
    lock_sha256 = row["source"].get("lock_sha256")
    if lock_sha256 and _sha256(source / "uv.lock") != lock_sha256:
        raise MatrixRunError("candidate source lock differs from the matrix")


def _load_selected_candidate(
    row: dict[str, Any], snapshots: dict[str, Path], source: Path
) -> tuple[Callable[..., Any], Any, Any]:
    if row["id"] == "julia-1":
        return _load_julia(snapshots["model"])
    if row["id"] == "kev-4b":
        return _load_kev(row, source)
    if row["id"] == "lev":
        return _load_lev(row, snapshots["model"], snapshots["base"], source)
    return _load_strands(row, snapshots["model"], source)


def run_candidate(arguments: argparse.Namespace) -> dict[str, Any]:
    row, snapshots = _preflight_candidate(arguments)
    resources = _check_resources(row, arguments.material_root, before_stage=False)
    os.environ["HF_HOME"] = str(arguments.material_root)
    os.environ["HF_HUB_CACHE"] = str(arguments.material_root)
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    source = arguments.source
    started = time.perf_counter()
    infer, count_tokens, engine = _load_selected_candidate(row, snapshots, source)
    cold_load_ms = (time.perf_counter() - started) * 1000
    input_rows = [
        json.loads(line)
        for line in arguments.inputs.read_text(encoding="utf-8").splitlines()
    ]
    max_tokens = max(count_tokens(item) for item in input_rows)
    if max_tokens > _CONTENT_TOKEN_LIMIT:
        raise MatrixRunError(
            f"common normalized-content token budget exceeded ({max_tokens})"
        )
    inference_times: list[float] = []

    def timed_infer(item: dict[str, Any]) -> dict[str, Any]:
        started_infer = time.perf_counter()
        result = infer(item)
        inference_times.append((time.perf_counter() - started_infer) * 1000)
        return result

    predictions = run_rows(input_rows, timed_infer)
    arguments.predictions.parent.mkdir(parents=True, exist_ok=True)
    arguments.predictions.write_text(
        "".join(json.dumps(item, sort_keys=True) + "\n" for item in predictions),
        encoding="utf-8",
    )
    peak = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    if sys.platform != "darwin":
        peak *= 1024
    receipt = {
        "candidate_id": row["id"],
        "model": row["model"],
        "source": row["source"],
        "runtime": row["runtime"],
        "device": row["device"],
        "precision": row["precision"],
        "execution_mode": "in_process",
        "model_server": False,
        "rows": len(input_rows),
        "prediction_count": len(predictions),
        "failures": sum(item["status"] != "ok" for item in predictions),
        "cold_load_ms": cold_load_ms,
        "inference_latency_ms": inference_times,
        "peak_rss_bytes": peak,
        "resource_preflight": resources,
        "matrix_sha256": _sha256(arguments.matrix),
        "corpus_manifest_sha256": _sha256(arguments.corpus_manifest),
        "host_platform": platform.platform(),
        "common_max_token_count": max_tokens,
        "provenance_limit": row.get("training_provenance"),
    }
    arguments.measurements.parent.mkdir(parents=True, exist_ok=True)
    arguments.measurements.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    del engine
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--approval", type=Path, required=True)
    parser.add_argument("--candidate", choices=sorted(_LEAD_IDS), required=True)
    parser.add_argument("--matrix", type=Path, default=MATRIX_PATH)
    parser.add_argument("--corpus-manifest", type=Path, default=CORPUS_PATH)
    parser.add_argument("--inputs", type=Path)
    parser.add_argument("--labels", type=Path)
    parser.add_argument("--material-root", type=Path, required=True)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--predictions", type=Path)
    parser.add_argument("--measurements", type=Path)
    parser.add_argument("--stage-only", action="store_true")
    arguments = parser.parse_args()
    try:
        if arguments.stage_only:
            receipt = stage_candidate(
                arguments.matrix,
                arguments.corpus_manifest,
                arguments.approval,
                arguments.candidate,
                arguments.material_root,
            )
        else:
            if not all(
                (
                    arguments.inputs,
                    arguments.labels,
                    arguments.source,
                    arguments.predictions,
                    arguments.measurements,
                )
            ):
                parser.error(
                    "inference requires inputs, labels, source, predictions, and measurements"
                )
            receipt = run_candidate(arguments)
    except (MatrixRunError, OSError, ValueError, subprocess.SubprocessError) as exc:
        parser.error(str(exc))
    print(json.dumps(receipt, sort_keys=True))


if __name__ == "__main__":
    main()
