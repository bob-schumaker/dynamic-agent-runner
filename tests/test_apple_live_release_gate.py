"""Tests for the standalone Apple Foundation Models release gate."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
GATE = REPO_ROOT / "scripts" / "run_apple_live_release_gate.py"


def _gate_module() -> object:
    spec = importlib.util.spec_from_file_location("apple_live_release_gate", GATE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_release_gate_runs_direct_runtime_checks(monkeypatch) -> None:
    module = _gate_module()
    calls: list[str] = []

    monkeypatch.setattr(module, "_require_eligible_apple", lambda: object())
    monkeypatch.setattr(module, "_run_text", lambda: calls.append("text"))
    monkeypatch.setattr(module, "_run_structured", lambda: calls.append("structured"))
    monkeypatch.setattr(
        module, "_run_strict_workflow", lambda: calls.append("workflow")
    )

    assert module.run_release_gate() == {
        "checks": ["text", "structured_output", "strict_workflow"],
        "format_version": 1,
        "status": "passed",
    }
    assert calls == ["text", "structured", "workflow"]


def test_release_gate_main_emits_a_redacted_unavailable_receipt(
    monkeypatch, capsys
) -> None:
    module = _gate_module()

    def fail() -> dict[str, object]:
        raise module.AppleLiveReleaseGateUnavailable("native model is unavailable")

    monkeypatch.setattr(module, "run_release_gate", fail)

    assert module.main() == 2
    assert json.loads(capsys.readouterr().out) == {
        "format_version": 1,
        "reason": "native_model_unavailable",
        "status": "unavailable",
    }


def test_release_gate_main_emits_a_redacted_failed_receipt(monkeypatch, capsys) -> None:
    module = _gate_module()

    def fail() -> dict[str, object]:
        raise module.AppleLiveReleaseGateError("Apple text generation returned no text")

    monkeypatch.setattr(module, "run_release_gate", fail)

    assert module.main() == 1
    assert json.loads(capsys.readouterr().out) == {
        "format_version": 1,
        "reason": "native_generation_failed",
        "status": "failed",
    }
