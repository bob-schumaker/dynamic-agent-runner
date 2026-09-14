"""Offline tests for the operator-only Fastmail support command."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


_SCRIPT = Path(__file__).parents[1] / "scripts" / "run_fastmail_support_probe.py"


@pytest.fixture
def command_module():
    spec = importlib.util.spec_from_file_location("fastmail_support_probe", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _facts() -> dict[str, object]:
    material = {
        "package_id": "fastmail-inbox-triage-qwen-v4",
        "material_lock_digest": "a" * 64,
        "material_roles": ["reviewed_search_email_surface", "weights"],
        "artifact_digests": {"reviewed_search_email_surface": "b" * 64},
    }
    return {
        "profile": {
            "profile_id": "fastmail-triage-live-v1",
            "workflow_family": "fastmail-triage",
            "required_adapter_capabilities": ["search_email", "tool_use"],
            "required_abi_capabilities": ["llama-cpp-function-calling-v1"],
            "required_provider_capabilities": ["fastmail.search_email.read.v1"],
            "required_host_capabilities": [],
            "material_identity": material,
            "execution_mode": "live",
            "authorization_required": True,
            "implemented": True,
        },
        "candidate": {
            "adapter_id": "fastmail-triage-llama-cpp-adapter-v1",
            "adapter_capabilities": ["search_email", "tool_use"],
            "available_abi_capabilities": ["llama-cpp-function-calling-v1"],
            "provider_capabilities": ["fastmail.search_email.read.v1"],
            "host_capabilities": [],
            "material_identity": material,
            "authorization_granted": True,
        },
    }


def _arguments(tmp_path: Path, facts: Path, receipt: Path) -> list[str]:
    return [
        "--state-root",
        str(tmp_path / "state"),
        "--package-name",
        "fastmail-inbox-triage-qwen-v4",
        "--target",
        "fastmail-primary",
        "--profile",
        "fastmail-triage-live-v1",
        "--authorization-reference",
        "operator-20260913",
        "--support-facts",
        str(facts),
        "--receipt",
        str(receipt),
    ]


def test_command_requires_opt_in_before_opening_a_host(
    command_module, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    facts = tmp_path / "facts.json"
    facts.write_text(json.dumps(_facts()), encoding="utf-8")
    receipt = tmp_path / "receipt.json"
    monkeypatch.delenv(command_module._OPT_IN_ENV, raising=False)
    monkeypatch.setattr(
        command_module.LocalWorkflowHost,
        "open",
        lambda _root: pytest.fail("host must not open without opt-in"),
    )

    assert command_module.main(_arguments(tmp_path, facts, receipt)) == 2
    assert not receipt.exists()


def test_command_rejects_a_package_outside_the_admitted_material_identity(
    command_module, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    facts = tmp_path / "facts.json"
    facts.write_text(json.dumps(_facts()), encoding="utf-8")
    receipt = tmp_path / "receipt.json"
    arguments = _arguments(tmp_path, facts, receipt)
    arguments[3] = "other-package"
    monkeypatch.setenv(command_module._OPT_IN_ENV, "1")
    monkeypatch.setattr(
        command_module.LocalWorkflowHost,
        "open",
        lambda _root: pytest.fail("host must not open for another package"),
    )

    assert command_module.main(arguments) == 2
    assert not receipt.exists()


def test_command_runs_one_pre_admitted_saved_workflow_and_writes_redacted_receipt(
    command_module, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    facts = tmp_path / "facts.json"
    facts.write_text(json.dumps(_facts()), encoding="utf-8")
    receipt = tmp_path / "receipt.json"
    calls: list[dict[str, object]] = []

    class Host:
        def invoke_saved(self, **kwargs: object) -> object:
            calls.append(kwargs)
            return {"raw_mailbox": "must not be retained"}

    monkeypatch.setenv(command_module._OPT_IN_ENV, "1")
    monkeypatch.setattr(command_module.LocalWorkflowHost, "open", lambda _root: Host())

    assert command_module.main(_arguments(tmp_path, facts, receipt)) == 0
    assert len(calls) == 1
    assert calls[0]["package_name"] == "fastmail-inbox-triage-qwen-v4"
    assert calls[0]["prompt"] == "Triage the previous 24 hours of unread messages."
    assert calls[0]["workspace_files"] == ()
    assert calls[0]["dry_run"] is False
    assert calls[0]["approval_broker"] is None
    rendered = receipt.read_text(encoding="utf-8")
    assert "fastmail-primary" not in rendered
    assert "operator-20260913" not in rendered
    assert "must not be retained" not in rendered
