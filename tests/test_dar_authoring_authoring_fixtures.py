"""Tests for static target-invocation contracts of the future adapted skills."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


PLUGIN_ROOT = Path(__file__).resolve().parents[1] / "dar-authoring"
sys.path.insert(0, str(PLUGIN_ROOT / "server"))

from dar_workflow_server.authoring_fixtures import (  # noqa: E402
    AuthoringFixtureError,
    load_authoring_fixture,
)


def test_target_invocation_fixtures_are_versioned_and_deidentified() -> None:
    fixtures = sorted((PLUGIN_ROOT / "fixtures" / "authoring").glob("*.json"))

    loaded = [load_authoring_fixture(path) for path in fixtures]

    assert [fixture.skill_id for fixture in loaded] == [
        "agent-development",
        "agent-evaluation",
        "agent-tool-contract-design",
    ]
    assert all(fixture.format_version == 1 for fixture in loaded)
    assert all("@" not in fixture.request for fixture in loaded)


def test_fixture_rejects_private_material_and_unknown_fields(tmp_path: Path) -> None:
    path = tmp_path / "invalid.json"
    path.write_text(
        json.dumps(
            {
                "format_version": 1,
                "skill_id": "agent-development",
                "request": "Design a workflow.",
                "materials": [
                    {
                        "artifact_id": "doc-1",
                        "version": "1",
                        "classification": "reference_only",
                        "content_projection": "private source text",
                    }
                ],
                "expected": {
                    "artifact_properties": ["agent-runtime.yaml"],
                    "capability_result": "accepted",
                    "refusal_fields": [],
                },
                "private_material_exclusions": ["private source text"],
                "extra": True,
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(AuthoringFixtureError):
        load_authoring_fixture(path)
