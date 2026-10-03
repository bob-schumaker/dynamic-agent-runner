from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).parent / "manual" / "smoke_dms16.py"
_SPEC = importlib.util.spec_from_file_location("smoke_dms16", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
_SMOKE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_SMOKE)


class FakeAdapter:
    identity = None

    def __init__(self, result: object) -> None:
        self.result = result
        self.calls = 0

    def decide(self, request: object) -> object:
        self.calls += 1
        self.request = request
        return self.result


def _valid_adapter() -> FakeAdapter:
    from dynamic_agent_runner.decision_models import (
        DecisionModelIdentity,
        DecisionModelResult,
        DecisionModelResultItem,
    )

    identity = DecisionModelIdentity("test", "test", "test", "rev", "runtime")
    adapter = FakeAdapter(
        DecisionModelResult(
            identity, (DecisionModelResultItem("route", choice="billing"),)
        )
    )
    adapter.identity = identity
    return adapter


def test_smoke_rejects_missing_or_wrong_approval_before_staging(
    monkeypatch, tmp_path: Path
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(_SMOKE, "ROOT", tmp_path)
    monkeypatch.setattr(_SMOKE, "scope_digest", lambda _profile_id: "expected")
    monkeypatch.setattr(_SMOKE, "stage_profile", lambda *_args: calls.append("stage"))

    for approval in (None, "wrong"):
        with pytest.raises(_SMOKE.SmokeError, match="approval"):
            _SMOKE.run_profile("julia1", tmp_path, approval)

    assert calls == []


def test_smoke_checks_materials_before_loading_and_invokes_once(
    monkeypatch, tmp_path: Path
) -> None:
    from dynamic_agent_runner.decision_models import (
        DecisionModelIdentity,
        DecisionModelProfile,
        DecisionMode,
    )

    identity = DecisionModelIdentity("test", "test", "test", "rev", "runtime")
    profile = DecisionModelProfile(
        identity, 10000, 1000, 1, 3, 1000, frozenset({DecisionMode.CHOICE})
    )
    monkeypatch.setattr(_SMOKE, "ROOT", tmp_path)
    monkeypatch.setitem(_SMOKE.IDENTITIES, "julia1", identity)
    monkeypatch.setattr(_SMOKE, "scope_digest", lambda _profile_id: "approved")
    monkeypatch.setattr(_SMOKE, "_runtime_ready", lambda _profile_id: None)
    monkeypatch.setattr(_SMOKE, "decision_profile", lambda _profile_id: profile)
    monkeypatch.setattr(_SMOKE, "stage_profile", lambda *_args: tmp_path)
    events: list[str] = []
    monkeypatch.setattr(
        _SMOKE, "verify_materials", lambda *_args: events.append("verify")
    )
    adapter = _valid_adapter()

    def load(_profile_id: str, _material_dir: Path) -> FakeAdapter:
        events.append("load")
        assert __import__("os").environ["HF_HUB_OFFLINE"] == "1"
        return adapter

    monkeypatch.setattr(_SMOKE, "load_adapter", load)
    receipt = _SMOKE.run_profile("julia1", tmp_path, "approved")

    assert events == ["verify", "load"]
    assert adapter.calls == 1
    assert receipt["inference_count"] == 1
    assert receipt["result_valid"] is True
    assert receipt["approval_scope"] == "approved"
    assert receipt["missing_materials_before_staging"] is True
    receipt_path = (
        tmp_path / "specs/decision-model-support/evaluation/dms16-smoke-julia1.json"
    )
    assert json.loads(receipt_path.read_text(encoding="utf-8"))["result_valid"] is True


def test_smoke_does_not_load_when_material_verification_fails(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(_SMOKE, "ROOT", tmp_path)
    monkeypatch.setattr(_SMOKE, "scope_digest", lambda _profile_id: "approved")
    monkeypatch.setattr(_SMOKE, "_runtime_ready", lambda _profile_id: None)
    monkeypatch.setattr(_SMOKE, "stage_profile", lambda *_args: tmp_path)
    monkeypatch.setattr(
        _SMOKE,
        "verify_materials",
        lambda *_args: (_ for _ in ()).throw(_SMOKE.SmokeError("materials")),
    )
    loaded: list[bool] = []
    monkeypatch.setattr(_SMOKE, "load_adapter", lambda *_args: loaded.append(True))

    with pytest.raises(_SMOKE.SmokeError, match="materials"):
        _SMOKE.run_profile("julia1", tmp_path, "approved")

    assert loaded == []


def test_smoke_scope_binds_profile_materials_lock_and_code(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(_SMOKE, "ROOT", tmp_path)
    monkeypatch.setattr(_SMOKE, "PROFILE_MANIFESTS", {"julia1": {"revision": "one"}})
    monkeypatch.setattr(_SMOKE, "POETRY_LOCK_SHA256", "lock")
    monkeypatch.setattr(_SMOKE, "SCOPE_FILES", ())
    (tmp_path / "poetry.lock").write_text("lock", encoding="utf-8")
    first = _SMOKE.scope_digest("julia1")
    assert _SMOKE.scope_payload("julia1")["receipt_path"].endswith(
        "dms16-smoke-julia1.json"
    )
    _SMOKE.PROFILE_MANIFESTS["julia1"]["revision"] = "two"

    assert first != _SMOKE.scope_digest("julia1")


def test_smoke_refuses_to_reuse_a_receipt_path(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(_SMOKE, "ROOT", tmp_path)
    monkeypatch.setattr(_SMOKE, "scope_digest", lambda _profile_id: "approved")
    monkeypatch.setattr(_SMOKE, "_runtime_ready", lambda _profile_id: None)
    target = (
        tmp_path / "specs/decision-model-support/evaluation/dms16-smoke-julia1.json"
    )
    target.parent.mkdir(parents=True)
    target.write_text("{}", encoding="utf-8")
    staged: list[bool] = []

    with pytest.raises(_SMOKE.SmokeError, match="already exists"):
        _SMOKE.run_profile(
            "julia1",
            tmp_path,
            "approved",
            stage=lambda *_args: staged.append(True),
        )

    assert staged == []


def test_smoke_receipt_writer_emits_only_redacted_metadata(tmp_path: Path) -> None:
    target = tmp_path / "receipt.json"
    _SMOKE.write_receipt(target, {"profile_id": "julia1", "result_valid": True})

    assert json.loads(target.read_text(encoding="utf-8")) == {
        "profile_id": "julia1",
        "result_valid": True,
    }
