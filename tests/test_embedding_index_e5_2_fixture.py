"""Keep the E5.2 model choice in the manual test harness only."""

from __future__ import annotations

import json
import importlib.util
from pathlib import Path


_ROOT = Path(__file__).parents[1]
_FIXTURE = _ROOT / "tests/fixtures/embedding-index-e5-2/model-material.json"
_HARNESS = _ROOT / "tests/manual/run_embedding_index_e5_2.py"


def test_e5_2_material_fixture_is_pinned_and_not_a_dar_contract() -> None:
    material = json.loads(_FIXTURE.read_text(encoding="utf-8"))

    assert material == {
        "filename": "gte-small.Q4_K_M.gguf",
        "repository": "ChristianAzinn/gte-small-gguf",
        "revision": "240acca7b64619cd22093a380dc266c4122d99b2",
        "sha256": "2b330c1579bac032397b48f5aa92b7b5ab2b94d72cc43cd15925db3ffd03fd61",
    }

    scenario_values = (material["repository"], material["filename"])
    generic_paths = (
        *_ROOT.joinpath("src").rglob("*.py"),
        _ROOT / "specs/workflow-embedding-index-artifacts/spec.md",
        _ROOT / "specs/workflow-embedding-index-artifacts/plan.md",
        _ROOT / "specs/workflow-embedding-index-artifacts/tasks.md",
    )
    for path in generic_paths:
        contents = path.read_text(encoding="utf-8")
        assert all(value not in contents for value in scenario_values), path


def test_e5_2_harness_accepts_only_the_host_prepared_fixture_snapshot() -> None:
    spec = importlib.util.spec_from_file_location("embedding_e5_2_harness", _HARNESS)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    snapshot = module._snapshot(
        _ROOT / "tests/fixtures/embedding-index-e5-2/snapshot.json"
    )

    assert len(snapshot.documents) == 1
    assert "acceptance document" not in repr(snapshot)
