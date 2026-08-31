"""Static contract tests for tool-descriptor benchmark fixtures."""

from __future__ import annotations

import json
from pathlib import Path


FIXTURE_PATH = (
    Path(__file__).parent
    / "fixtures"
    / "tool-descriptor-budgeting"
    / "benchmark-v1.json"
)
EXPECTED_CASE_IDS = {
    "read_explicit_local_file",
    "find_local_symbol",
    "research_current_external_fact",
    "inspect_then_modify_config",
    "query_structured_retention_record",
}


def test_benchmark_fixture_has_a_complete_local_evaluator_contract() -> None:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

    assert set(fixture) == {"cases", "format_version"}
    assert fixture["format_version"] == "tool-descriptor-benchmark-v1"
    assert {case["id"] for case in fixture["cases"]} == EXPECTED_CASE_IDS

    for case in fixture["cases"]:
        assert set(case) == {
            "acceptable_optional_tools",
            "eligible_tools",
            "expected_required_tools",
            "false_omission_checks",
            "id",
            "prompt",
        }
        assert case["id"].strip()
        assert case["prompt"].strip()
        assert case["eligible_tools"]

        eligible_ids = [tool["id"] for tool in case["eligible_tools"]]
        assert len(eligible_ids) == len(set(eligible_ids))
        for tool in case["eligible_tools"]:
            assert set(tool) == {
                "description_for_llm",
                "id",
                "input_schema",
                "label",
                "tool_type",
            }
            assert tool["id"].strip()
            assert tool["label"].strip()
            assert tool["tool_type"].strip()
            assert tool["description_for_llm"].strip()
            assert set(tool["input_schema"]) == {"properties", "required", "type"}
            assert tool["input_schema"]["type"] == "object"
            assert isinstance(tool["input_schema"]["properties"], dict)
            assert isinstance(tool["input_schema"]["required"], list)
            assert set(tool["input_schema"]["required"]) <= set(
                tool["input_schema"]["properties"]
            )

        required_ids = case["expected_required_tools"]
        optional_ids = case["acceptable_optional_tools"]
        assert required_ids
        assert len(required_ids) == len(set(required_ids))
        assert len(optional_ids) == len(set(optional_ids))
        assert set(required_ids) <= set(eligible_ids)
        assert set(optional_ids) <= set(eligible_ids)
        assert not set(required_ids) & set(optional_ids)
        assert len(case["eligible_tools"]) > len(required_ids)

        omission_ids = []
        for check in case["false_omission_checks"]:
            assert set(check) == {"rationale", "tool_id"}
            assert check["rationale"].strip()
            omission_ids.append(check["tool_id"])
        assert len(omission_ids) == len(set(omission_ids))
        assert set(omission_ids) == set(required_ids)
