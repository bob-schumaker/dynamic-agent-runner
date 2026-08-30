"""Unit coverage for the shared deterministic and live matrix catalog."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from model_interface_matrix import (
    controlled_tool_registry,
    controlled_tool_scenarios,
    controlled_tool_workflow,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
RUNNER = REPO_ROOT / "scripts" / "run_live_model_interface_matrix.py"


def _runner_module() -> object:
    spec = importlib.util.spec_from_file_location("live_model_interface_matrix", RUNNER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_shared_catalog_contains_every_current_matrix_scenario() -> None:
    scenarios = controlled_tool_scenarios()

    assert [scenario.id for scenario in scenarios] == [
        "S1",
        "S2",
        "S2-invalid",
        "S2-wrong-type",
        "S2-invalid-enum",
        "S2-unknown",
        "S2-malformed",
        "S3",
        "S4",
        "S5",
        "S6",
    ]
    assert controlled_tool_workflow(scenarios[0]).runtime_manifest.package_id == (
        "controlled-tool-matrix"
    )


def test_shared_registry_is_harmless_and_records_one_invocation() -> None:
    registry, invocations, results = controlled_tool_registry()

    assert registry.get_tool("create_record").handler(
        {"title": "DAR", "body": "controlled"}
    ) == {"record_id": "record-created"}
    assert invocations == [("create_record", {"title": "DAR", "body": "controlled"})]
    assert results == [("create_record", {"record_id": "record-created"})]


def test_live_runner_requires_explicit_environment_opt_in(monkeypatch) -> None:
    module = _runner_module()
    monkeypatch.delenv(module.LIVE_ENV, raising=False)

    with pytest.raises(module.LiveMatrixError, match=module.LIVE_ENV):
        module.run_live_matrix(
            SimpleNamespace(target="apple", mode="sync", scenarios=["S5"])
        )


def test_live_runner_selects_shared_catalog_by_identifier() -> None:
    module = _runner_module()

    assert [scenario.id for scenario in module._selected_scenarios(["S3", "S5"])] == [
        "S3",
        "S5",
    ]
    for identifiers in (["not-a-scenario"], ["S2-invalid"], ["S1", "S1"], []):
        with pytest.raises(module.LiveMatrixError):
            module._selected_scenarios(identifiers)


def test_live_runner_preflight_rejects_unsafe_endpoint_without_constructing_adapter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _runner_module()
    monkeypatch.setenv(module.LIVE_ENV, "1")
    calls = 0

    def unexpected_adapter(*_args: object, **_kwargs: object) -> object:
        nonlocal calls
        calls += 1
        return object()

    monkeypatch.setattr(module, "_adapter", unexpected_adapter)
    receipt = module.run_live_matrix(
        SimpleNamespace(
            target="endpoint",
            model="test-model",
            mode="sync",
            scenarios=["S5"],
            base_url="https://user:pass@example.test/v1?token=secret",
            model_path=None,
            expected_model_id=None,
            authorization_reference="matrix-20260830",
        )
    )

    assert calls == 0
    assert receipt["rows"][0]["status"] == "unavailable"
    assert receipt["rows"][0]["reason"] == "invalid_base_url"


def test_live_runner_preflight_rejects_secret_like_authorization_reference(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _runner_module()
    monkeypatch.setenv(module.LIVE_ENV, "1")
    monkeypatch.setattr(
        module,
        "_adapter",
        lambda *_args, **_kwargs: pytest.fail("adapter must not be constructed"),
    )

    receipt = module.run_live_matrix(
        SimpleNamespace(
            target="openai",
            model="test-model",
            mode="sync",
            scenarios=["S5"],
            base_url=None,
            model_path=None,
            expected_model_id=None,
            authorization_reference="token-123",
        )
    )

    assert receipt["rows"][0]["reason"] == "invalid_authorization_reference"


def test_live_runner_plans_apple_both_with_per_scenario_sync_skip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _runner_module()
    monkeypatch.setenv(module.LIVE_ENV, "1")
    monkeypatch.setattr(module, "_adapter", lambda *_args, **_kwargs: object())

    async def execute(*_args: object, **_kwargs: object) -> object:
        return SimpleNamespace(final_result="ok")

    monkeypatch.setattr(module, "execute_workflow_async", execute)
    receipt = module.run_live_matrix(
        SimpleNamespace(
            target="apple",
            model=None,
            mode="both",
            scenarios=["S5"],
            base_url=None,
            model_path=None,
            expected_model_id=None,
            authorization_reference="matrix-20260830",
        )
    )

    assert [(row["mode"], row["status"]) for row in receipt["rows"]] == [
        ("sync", "skipped"),
        ("async", "passed"),
    ]


def test_live_runner_continues_after_row_local_adapter_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _runner_module()
    monkeypatch.setenv(module.LIVE_ENV, "1")

    def unavailable_adapter(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("credential=should-not-appear")

    monkeypatch.setattr(module, "_adapter", unavailable_adapter)
    receipt = module.run_live_matrix(
        SimpleNamespace(
            target="openai",
            model="test-model",
            mode="sync",
            scenarios=["S1", "S5"],
            base_url=None,
            model_path=None,
            expected_model_id=None,
            authorization_reference="matrix-20260830",
        )
    )

    assert [row["status"] for row in receipt["rows"]] == [
        "adapter_error",
        "adapter_error",
    ]
    assert "credential=should-not-appear" not in repr(receipt)


def test_live_runner_receipt_redacts_free_form_and_secret_values() -> None:
    module = _runner_module()

    projected = module._safe_value(
        {"api_key": "secret", "message": "operator supplied free-form text"}
    )

    assert projected["api_key"] == "redacted"
    assert projected["message"] == {
        "type": "string",
        "length": 32,
        "digest": module._digest("operator supplied free-form text"),
    }
    assert module._summary([{"status": "passed"}, {"status": "adapter_error"}]) == (
        "adapter_error",
        {
            "passed": 1,
            "behavioral_mismatch": 0,
            "adapter_error": 1,
            "unavailable": 0,
            "skipped": 0,
        },
    )


def test_live_runner_executes_a_selected_shared_row_without_exposing_real_tools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _runner_module()
    monkeypatch.setenv(module.LIVE_ENV, "1")
    monkeypatch.setattr(module, "_adapter", lambda *_args, **_kwargs: object())

    async def execute(*_args: object, **_kwargs: object) -> object:
        return SimpleNamespace(final_result="ok")

    monkeypatch.setattr(module, "execute_workflow_async", execute)

    receipt = module.run_live_matrix(
        SimpleNamespace(
            target="apple",
            model=None,
            mode="async",
            scenarios=["S5"],
            base_url=None,
            model_path=None,
            expected_model_id=None,
            authorization_reference="matrix-20260830",
        )
    )

    assert receipt["format_version"] == 2
    assert receipt["status"] == "passed"
    assert receipt["rows"][0]["status"] == "passed"
    assert receipt["manual_authorization"]["reference_digest"]
    assert "matrix-20260830" not in repr(receipt)
