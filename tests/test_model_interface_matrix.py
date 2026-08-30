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
    with pytest.raises(module.LiveMatrixError, match="unknown matrix scenario"):
        module._selected_scenarios(["not-a-scenario"])


def test_live_runner_executes_a_selected_shared_row_without_exposing_real_tools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _runner_module()
    monkeypatch.setenv(module.LIVE_ENV, "1")
    monkeypatch.setattr(module, "_adapter", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(module, "execute_workflow", lambda *_args, **_kwargs: object())

    receipt = module.run_live_matrix(
        SimpleNamespace(target="apple", mode="sync", scenarios=["S5"])
    )

    assert receipt == {
        "format_version": 1,
        "rows": [{"mode": "sync", "scenario": "S5", "status": "passed"}],
        "status": "passed",
        "target": "apple",
    }
