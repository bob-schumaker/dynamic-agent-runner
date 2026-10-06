from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).parent / "manual" / "smoke_jevstyle_dms17.py"
_SPEC = importlib.util.spec_from_file_location("smoke_jevstyle_dms17", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
_SMOKE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_SMOKE)


class FakeEngine:
    def __init__(self) -> None:
        self.calls = 0

    def decide(self, _state: object, _question: object) -> dict[str, object]:
        self.calls += 1
        return {"answer": "billing", "probabilities": {"billing": 0.8, "other": 0.2}}


def _write_approval(path: Path, scope: str, profiles: list[str]) -> None:
    assert profiles
    assert all(profile in _SMOKE.PROFILE_RECORDS for profile in profiles)
    path.write_text(
        json.dumps(
            {
                "run_allowed": True,
                "profile_set_id": _SMOKE.LEDGER["profile_set_id"],
                "scope_sha256": scope,
                "approval": {
                    "status": "approved",
                    "scope_sha256": scope,
                    "profiles": profiles,
                },
            }
        ),
        encoding="utf-8",
    )


@pytest.mark.parametrize("profile_id", sorted(_SMOKE.PROFILE_RECORDS))
def test_smoke_requires_exact_run_authorization_before_loading(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, profile_id: str
) -> None:
    monkeypatch.setattr(_SMOKE, "ROOT", tmp_path)
    monkeypatch.setattr(_SMOKE, "scope_digest", lambda *_args, **_kwargs: "expected")
    events: list[str] = []
    monkeypatch.setattr(
        _SMOKE, "_runtime_ready", lambda *_args: events.append("runtime")
    )
    monkeypatch.setattr(_SMOKE, "_engine_loader", lambda *_args: events.append("load"))

    with pytest.raises(_SMOKE.SmokeError, match="approval"):
        _SMOKE.run_profile(profile_id, tmp_path, tmp_path / "scorer", None)

    assert events == []


def test_smoke_rejects_scope_without_approval_receipt(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(_SMOKE, "ROOT", tmp_path)
    monkeypatch.setattr(_SMOKE, "scope_digest", lambda *_args, **_kwargs: "approved")
    monkeypatch.setattr(_SMOKE, "PREFLIGHT_PATH", tmp_path / "preflight.json")
    loaded: list[bool] = []
    monkeypatch.setattr(_SMOKE, "_runtime_ready", lambda *_args: None)
    monkeypatch.setattr(_SMOKE, "_engine_loader", lambda *_args: loaded.append(True))

    with pytest.raises(_SMOKE.SmokeError, match="approval receipt"):
        _SMOKE.run_profile("gguf-f16-cpu", tmp_path, tmp_path / "scorer", "approved")

    assert loaded == []


def test_smoke_verifies_materials_then_runs_one_adapter_decision(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from dynamic_agent_runner.workflow_host.jevstyle_decision_adapter import (
        JEVSTYLE_V3_GGUF_PROFILE,
    )

    profile_id = "gguf-f16-cpu"
    monkeypatch.setattr(_SMOKE, "ROOT", tmp_path)
    monkeypatch.setattr(_SMOKE, "scope_digest", lambda *_args, **_kwargs: "approved")
    monkeypatch.setattr(_SMOKE, "PREFLIGHT_PATH", tmp_path / "preflight.json")
    _write_approval(_SMOKE.PREFLIGHT_PATH, "approved", [profile_id])
    monkeypatch.setattr(_SMOKE, "_runtime_ready", lambda *_args: None)
    monkeypatch.setattr(_SMOKE, "_materials_present", lambda *_args: True)
    monkeypatch.setattr(
        _SMOKE, "_verify_materials", lambda *_args: events.append("verify")
    )
    monkeypatch.setattr(_SMOKE, "_host_has_resource_budget", lambda *_args: True)
    events: list[str] = []
    engine = FakeEngine()

    def load(*_args: object) -> FakeEngine:
        events.append("load")
        assert __import__("os").environ["HF_HUB_OFFLINE"] == "1"
        return engine

    monkeypatch.setattr(_SMOKE, "_engine_loader", load)
    report = _SMOKE.run_profile(profile_id, tmp_path, tmp_path / "scorer", "approved")

    assert events == ["verify", "load"]
    assert engine.calls == 1
    assert report["selected_profile_id"] == JEVSTYLE_V3_GGUF_PROFILE.identity.profile_id
    assert report["inference_count"] == 1
    assert report["result_valid"] is True
    receipt = json.loads(_SMOKE._receipt_path(profile_id).read_text(encoding="utf-8"))
    assert receipt["approval_scope"] == "approved"


def test_smoke_scope_binds_exact_profiles_runtimes_and_runner_sources(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(_SMOKE, "ROOT", tmp_path)
    monkeypatch.setattr(_SMOKE, "SCOPE_FILES", ())
    record = _SMOKE.PROFILE_RECORDS["gguf-f16-cpu"]
    monkeypatch.setitem(record, "model_revision", "a")
    first = _SMOKE.scope_digest(tmp_path, tmp_path / "scorer")
    monkeypatch.setitem(record, "model_revision", "b")

    assert first != _SMOKE.scope_digest(tmp_path, tmp_path / "scorer")


def test_smoke_does_not_load_when_exact_material_verification_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    profile_id = "gguf-f16-cpu"
    monkeypatch.setattr(_SMOKE, "ROOT", tmp_path)
    monkeypatch.setattr(_SMOKE, "scope_digest", lambda *_args, **_kwargs: "approved")
    monkeypatch.setattr(_SMOKE, "PREFLIGHT_PATH", tmp_path / "preflight.json")
    _write_approval(_SMOKE.PREFLIGHT_PATH, "approved", [profile_id])
    monkeypatch.setattr(_SMOKE, "_runtime_ready", lambda *_args: None)
    monkeypatch.setattr(_SMOKE, "_materials_present", lambda *_args: True)
    monkeypatch.setattr(
        _SMOKE,
        "_verify_materials",
        lambda *_args: (_ for _ in ()).throw(_SMOKE.SmokeError("digest mismatch")),
    )
    loaded: list[bool] = []
    monkeypatch.setattr(_SMOKE, "_engine_loader", lambda *_args: loaded.append(True))

    with pytest.raises(_SMOKE.SmokeError, match="digest mismatch"):
        _SMOKE.run_profile(profile_id, tmp_path, tmp_path / "scorer", "approved")

    assert loaded == []
