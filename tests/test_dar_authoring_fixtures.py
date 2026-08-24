"""Static contract tests for DAR authoring target-invocation fixtures."""

from __future__ import annotations

import json
from pathlib import Path


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "dar-authoring" / "invocations"
EXPECTED_SKILLS = {
    "agent-development",
    "agent-tool-contract-design",
    "agent-evaluation",
}


def test_target_invocation_fixtures_have_complete_deidentified_contracts() -> None:
    fixtures = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(FIXTURE_ROOT.glob("*.json"))
    ]

    assert {fixture["skill"] for fixture in fixtures} == EXPECTED_SKILLS
    for fixture in fixtures:
        assert fixture["schema_version"] == 1
        assert fixture["request"].strip()
        assert fixture["selected_materials"]
        assert fixture["expected_artifacts"]
        assert fixture["expected_capability_or_refusal"]
        assert fixture["private_material_exclusions"]
        for material in fixture["selected_materials"]:
            assert set(material) == {"artifact_id", "digest", "disposition", "role"}
            assert material["disposition"] in {"reference_only", "distributable"}
            assert material["artifact_id"].startswith("authoring-material-")
            assert len(material["digest"]) == 64
