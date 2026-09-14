"""Offline tests for the operator-only floorplan MPS completion command."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


_SCRIPT = (
    Path(__file__).parents[1] / "scripts" / "run_floorplan_mps_completion_probe.py"
)


@pytest.fixture
def command_module():
    spec = importlib.util.spec_from_file_location(
        "floorplan_mps_completion_probe", _SCRIPT
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _arguments(tmp_path: Path) -> list[str]:
    return [
        "--state-root",
        str(tmp_path / "state"),
        "--package-name",
        "floorplan-from-image",
        "--image",
        str(tmp_path / "floorplan.png"),
        "--target",
        "mps-local",
        "--authorization-reference",
        "operator-20260913",
        "--receipt",
        str(tmp_path / "receipt.json"),
    ]


def test_command_requires_opt_in_before_inspecting_or_opening_a_host(
    command_module, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(command_module._OPT_IN_ENV, raising=False)
    monkeypatch.setattr(
        command_module,
        "inspect_saved_workflow",
        lambda *_args, **_kwargs: pytest.fail("package must not be inspected"),
    )
    monkeypatch.setattr(
        command_module.LocalWorkflowHost,
        "open",
        lambda *_args, **_kwargs: pytest.fail("host must not open"),
    )

    assert command_module.main(_arguments(tmp_path)) == 2
    assert not (tmp_path / "receipt.json").exists()
