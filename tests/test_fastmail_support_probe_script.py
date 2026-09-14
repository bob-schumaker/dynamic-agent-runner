"""Offline tests for the operator-only Fastmail support command."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


_SCRIPT = Path(__file__).parents[1] / "scripts" / "run_fastmail_support_probe.py"


@pytest.fixture
def command_module():
    spec = importlib.util.spec_from_file_location("fastmail_support_probe", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _inspection(*, package_id: str = "fastmail-inbox-triage-qwen") -> object:
    material = SimpleNamespace(
        digest="a" * 64,
        sources=(SimpleNamespace(role="weights", sha256="b" * 64),),
    )
    registration = SimpleNamespace(
        workflow_id="fastmail-inbox-triage-qwen-v4",
        package_id=package_id,
        revision_digest="c" * 64,
        policy_digest="d" * 64,
        mcp_binding_id="binding-1",
    )
    policy = SimpleNamespace(
        package_id=package_id,
        revision_digest="c" * 64,
        policy_digest="d" * 64,
        model_materials=material,
        declared_tools=(SimpleNamespace(tool_id="search_email", side_effect="read"),),
        task_invocation=SimpleNamespace(
            allowed_tool_ids=("search_email",), max_total_tool_calls=1
        ),
    )
    profile = SimpleNamespace(
        adapter_id="fastmail-triage-llama-cpp-adapter-v1",
    )
    return SimpleNamespace(registration=registration, policy=policy, profile=profile)


def _arguments(tmp_path: Path, receipt: Path) -> list[str]:
    return [
        "--state-root",
        str(tmp_path / "state"),
        "--workflow-id",
        "fastmail-inbox-triage-qwen-v4",
        "--target",
        "fastmail-primary",
        "--profile",
        "fastmail-triage-live-v1",
        "--authorization-reference",
        "operator-20260913",
        "--receipt",
        str(receipt),
    ]


def test_command_requires_opt_in_before_inspecting_or_opening_a_host(
    command_module, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    receipt = tmp_path / "receipt.json"
    monkeypatch.delenv(command_module._OPT_IN_ENV, raising=False)
    monkeypatch.setattr(
        command_module,
        "inspect_saved_workflow",
        lambda *_args, **_kwargs: pytest.fail(
            "workflow must not inspect without opt-in"
        ),
    )
    monkeypatch.setattr(
        command_module.LocalWorkflowHost,
        "open",
        lambda _root: pytest.fail("host must not open without opt-in"),
    )

    assert command_module.main(_arguments(tmp_path, receipt)) == 2
    assert not receipt.exists()


def test_command_rejects_an_unknown_workflow_before_opening_a_host(
    command_module, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    receipt = tmp_path / "receipt.json"
    monkeypatch.setenv(command_module._OPT_IN_ENV, "1")
    monkeypatch.setattr(
        command_module,
        "inspect_saved_workflow",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError("unavailable")),
    )
    monkeypatch.setattr(
        command_module.LocalWorkflowHost,
        "open",
        lambda _root: pytest.fail("host must not open for an unknown workflow"),
    )

    assert command_module.main(_arguments(tmp_path, receipt)) == 2
    assert not receipt.exists()


def test_command_rejects_static_policy_mismatch_before_opening_a_host(
    command_module, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    receipt = tmp_path / "receipt.json"
    inspected = _inspection()
    inspected.policy.policy_digest = "e" * 64
    monkeypatch.setenv(command_module._OPT_IN_ENV, "1")
    monkeypatch.setattr(
        command_module, "inspect_saved_workflow", lambda *_args, **_kwargs: inspected
    )
    monkeypatch.setattr(
        command_module.LocalWorkflowHost,
        "open",
        lambda _root: pytest.fail("host must not open for stale policy facts"),
    )

    assert command_module.main(_arguments(tmp_path, receipt)) == 2
    assert not receipt.exists()


def test_command_rejects_the_removed_support_facts_argument(
    command_module, tmp_path: Path
) -> None:
    receipt = tmp_path / "receipt.json"

    with pytest.raises(SystemExit):
        command_module.main(
            [*_arguments(tmp_path, receipt), "--support-facts", "facts.json"]
        )


def test_command_runs_one_inspected_saved_workflow_and_writes_redacted_receipt(
    command_module, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    receipt = tmp_path / "receipt.json"
    calls: list[dict[str, object]] = []

    class Host:
        def invoke_saved(self, **kwargs: object) -> object:
            calls.append(kwargs)
            return {"raw_mailbox": "must not be retained"}

    monkeypatch.setenv(command_module._OPT_IN_ENV, "1")
    monkeypatch.setattr(
        command_module,
        "inspect_saved_workflow",
        lambda *_args, **_kwargs: _inspection(),
    )
    monkeypatch.setattr(command_module.LocalWorkflowHost, "open", lambda _root: Host())

    assert command_module.main(_arguments(tmp_path, receipt)) == 0
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
    assert "fastmail-inbox-triage-qwen" in rendered
