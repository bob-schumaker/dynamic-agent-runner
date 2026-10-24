"""Fake-backed tests for the pinned Nimble MPS-kernel variant."""

from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace
from pathlib import Path

import hashlib
import json

import pytest

sys.path.insert(
    0,
    str(__import__("pathlib").Path(__file__).resolve().parents[1] / "tests" / "manual"),
)

from run_dms20_nimble_mps import (  # noqa: E402
    ExtensionRunError,
    _configure_optimized_kernels,
    _verify_matrix_and_approval,
)
import run_dms20_nimble_mps as runner  # noqa: E402


def _fake_kernel_modules(monkeypatch: pytest.MonkeyPatch, *, has_metal: bool = True):
    def kernel(*_args: object, **_kwargs: object) -> None:
        return None

    delta = ModuleType("mps_linear_attn.delta_rule")
    delta._HAS_METAL = has_metal  # type: ignore[attr-defined]
    delta._C = SimpleNamespace(delta_rule_fused=kernel)  # type: ignore[attr-defined]
    delta.fused_recurrent_gated_delta_rule = kernel  # type: ignore[attr-defined]

    conv = ModuleType("mps_linear_attn.causal_conv1d")
    conv._HAS_METAL = has_metal  # type: ignore[attr-defined]
    conv._C = SimpleNamespace(causal_conv1d=kernel)  # type: ignore[attr-defined]

    package = ModuleType("mps_linear_attn")
    package.__version__ = "0.1.0"  # type: ignore[attr-defined]
    package.delta_rule = delta  # type: ignore[attr-defined]
    package.causal_conv1d = conv  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "mps_linear_attn", package)
    monkeypatch.setitem(sys.modules, "mps_linear_attn.delta_rule", delta)
    monkeypatch.setitem(sys.modules, "mps_linear_attn.causal_conv1d", conv)

    gated_delta = ModuleType("fla.ops.gated_delta_rule")
    gated_delta.chunk_gated_delta_rule = object()  # type: ignore[attr-defined]
    gated_delta.fused_recurrent_gated_delta_rule = kernel  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "fla.ops.gated_delta_rule", gated_delta)
    return delta, conv, gated_delta


def test_optimized_dispatch_routes_prefill_to_metal_recurrent_and_counts_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    delta, conv, gated_delta = _fake_kernel_modules(monkeypatch)

    counters = _configure_optimized_kernels()

    assert (
        gated_delta.chunk_gated_delta_rule
        is gated_delta.fused_recurrent_gated_delta_rule
    )
    delta._C.delta_rule_fused()  # type: ignore[attr-defined]
    conv._C.causal_conv1d()  # type: ignore[attr-defined]
    assert counters == {"delta_rule_fused": 1, "causal_conv1d": 1}


def test_optimized_dispatch_fails_closed_without_compiled_metal_kernels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_kernel_modules(monkeypatch, has_metal=False)

    with pytest.raises(ExtensionRunError, match="compiled Metal kernels"):
        _configure_optimized_kernels()


def test_optimized_matrix_requires_approval_for_exact_matrix_and_inputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    inputs = tmp_path / "inputs.jsonl"
    labels = tmp_path / "labels.jsonl"
    corpus = tmp_path / "corpus.json"
    harness = tmp_path / "runner.py"
    inputs.write_text("input\n", encoding="utf-8")
    labels.write_text("label\n", encoding="utf-8")
    harness.write_text("pass\n", encoding="utf-8")

    def digest(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    corpus.write_text(
        json.dumps(
            {
                "license_review_status": "cleared",
                "normalized_input_sha256": digest(inputs),
                "gold_label_sha256": digest(labels),
            }
        ),
        encoding="utf-8",
    )
    row = {
        "id": runner.CANDIDATE_ID,
        "disposition": "selected",
        "optimizer": {"revision": runner.OPTIMIZER_REVISION},
    }
    matrix = {
        "approval_scope": "one exact optimized row",
        "corpus_manifest_sha256": digest(corpus),
        "normalized_input_sha256": digest(inputs),
        "gold_label_sha256": digest(labels),
        "input_files": {
            "inputs": {"path": str(inputs), "sha256": digest(inputs)},
            "labels": {"path": str(labels), "sha256": digest(labels)},
        },
        "rows": [row],
        "runnable_cohort": [runner.CANDIDATE_ID],
        "harness_files": [
            {"path": "runner.py", "sha256": digest(harness)},
        ],
    }
    matrix_path = tmp_path / "matrix.json"
    matrix_path.write_text(json.dumps(matrix), encoding="utf-8")
    approval = {
        "approved": True,
        "matrix_sha256": digest(matrix_path),
        "corpus_manifest_sha256": digest(corpus),
        "approval_scope": matrix["approval_scope"],
        "dispositions": {runner.CANDIDATE_ID: "selected"},
        "runnable_cohort": [runner.CANDIDATE_ID],
        "optimizer_revision": runner.OPTIMIZER_REVISION,
    }
    approval_path = tmp_path / "approval.json"
    approval_path.write_text(json.dumps(approval), encoding="utf-8")

    assert _verify_matrix_and_approval(matrix_path, corpus, approval_path) == matrix

    approval["matrix_sha256"] = "00" * 32
    approval_path.write_text(json.dumps(approval), encoding="utf-8")
    with pytest.raises(ExtensionRunError, match="does not bind"):
        _verify_matrix_and_approval(matrix_path, corpus, approval_path)
