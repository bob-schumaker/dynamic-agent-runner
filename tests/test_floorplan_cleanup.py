"""Regression boundaries for scenario-neutral production source."""

from __future__ import annotations

import json
from pathlib import Path

from dynamic_agent_runner.workflow_host.profiles import (
    LocalModelProfileControlPlane,
)
from dynamic_agent_runner.workflow_host.state import PrivateStateStore


_ROOT = Path(__file__).parents[1]
_FORBIDDEN = (
    "qwen25-vl-3b-floorplan-grpo",
    "floorplan-vision-llama-cpp-adapter-v1",
    "qwen-floorplan-input-v1",
    "svg_floorplan",
    "floorplan_vision_model",
    "qwen25_vl_3b_grpo_converter",
)


def test_production_source_has_no_floorplan_scenario_identity() -> None:
    for path in _ROOT.joinpath("src").rglob("*.py"):
        contents = path.read_text(encoding="utf-8")
        assert all(value not in contents for value in _FORBIDDEN), path


def test_generic_multimodal_profile_needs_no_scenario_constructor(
    tmp_path: Path,
) -> None:
    profile = LocalModelProfileControlPlane(
        store=PrivateStateStore(tmp_path / "state")
    ).create(
        model_id="test-multimodal-model",
        execution_model_id="test-multimodal-model",
        adapter_id="strict-local-adapter-v1",
        base_url="http://127.0.0.1:11434/v1",
        profile_requirement="local-multimodal-model-v1",
        capabilities={"text_generation", "multimodal_input"},
    )

    assert profile.runner_id == "local-openai-endpoint-v1"
    assert profile.capabilities == frozenset({"text_generation", "multimodal_input"})


def test_scenario_recipe_records_are_test_fixture_assets() -> None:
    path = (
        _ROOT
        / "tests/fixtures/natural-language-workflow-authoring/floorplan-svg/legacy-model-recipes.json"
    )
    records = json.loads(path.read_text(encoding="utf-8"))

    assert len(records["recipes"]) == 2
    assert all(recipe["artifacts"] for recipe in records["recipes"])
