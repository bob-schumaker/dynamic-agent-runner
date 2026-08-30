"""Comparison contract for the optional lexical benchmark scorers."""

from __future__ import annotations

from pathlib import Path

import nltk

from tool_descriptor_benchmark import compare_case, load_benchmark_cases


def test_benchmark_scorers_rank_the_fixed_corpus_without_oracle_inputs() -> None:
    cases = load_benchmark_cases()

    for case in cases:
        expected_ids = tuple(tool["id"] for tool in case["eligible_tools"])

        first = compare_case(case)
        second = compare_case(case)

        assert first == second
        assert set(first.deterministic.ranked_tool_ids) == set(expected_ids)
        assert set(first.nltk.ranked_tool_ids) == set(expected_ids)
        assert set(first.deterministic.selected_tool_ids) <= set(expected_ids)
        assert set(first.nltk.selected_tool_ids) <= set(expected_ids)


def test_nltk_comparison_uses_no_downloaded_corpora(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        nltk,
        "download",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("download")),
    )

    comparison = compare_case(load_benchmark_cases()[0])

    assert comparison.nltk.scorer_id == "nltk_lexical"


def test_nltk_stemming_changes_lexical_ranking_without_changing_ties() -> None:
    case = {
        "prompt": "reading",
        "eligible_tools": [
            {
                "id": "other",
                "label": "Other",
                "tool_type": "local",
                "description_for_llm": "Unrelated operation.",
                "input_schema": {"type": "object", "properties": {}, "required": []},
            },
            {
                "id": "read_file",
                "label": "Read file",
                "tool_type": "local",
                "description_for_llm": "Read a file.",
                "input_schema": {"type": "object", "properties": {}, "required": []},
            },
        ],
        "expected_required_tools": ["read_file"],
    }

    comparison = compare_case(case)

    assert comparison.deterministic.selected_tool_ids == ()
    assert comparison.nltk.selected_tool_ids == ("read_file",)


def test_deterministic_scorer_matches_the_exact_tool_id_bonus() -> None:
    case = {
        "prompt": "lookup",
        "eligible_tools": [
            {
                "id": "other",
                "label": "Other",
                "tool_type": "local",
                "description_for_llm": "Lookup information.",
                "input_schema": {"type": "object", "properties": {}, "required": []},
            },
            {
                "id": "lookup",
                "label": "Other",
                "tool_type": "local",
                "description_for_llm": "Unrelated operation.",
                "input_schema": {"type": "object", "properties": {}, "required": []},
            },
        ],
        "expected_required_tools": [],
    }

    comparison = compare_case(case)

    assert comparison.deterministic.ranked_tool_ids[0] == "lookup"


def test_selection_does_not_read_benchmark_oracle_fields() -> None:
    case = load_benchmark_cases()[0]
    changed_oracle = {**case, "expected_required_tools": ["search_web"]}

    assert compare_case(changed_oracle) == compare_case(case)


def test_nltk_stemming_does_not_create_an_exact_id_bonus() -> None:
    case = {
        "prompt": "skies",
        "eligible_tools": [
            {
                "id": "other",
                "label": "Other",
                "tool_type": "local",
                "description_for_llm": "Skies information.",
                "input_schema": {"type": "object", "properties": {}, "required": []},
            },
            {
                "id": "sky",
                "label": "Other",
                "tool_type": "local",
                "description_for_llm": "Unrelated operation.",
                "input_schema": {"type": "object", "properties": {}, "required": []},
            },
        ],
        "expected_required_tools": [],
    }

    comparison = compare_case(case)

    assert comparison.nltk.ranked_tool_ids[0] == "other"


def test_runtime_package_does_not_import_nltk() -> None:
    source_root = Path(__file__).resolve().parents[1] / "src"

    assert "import nltk" not in "\n".join(
        path.read_text(encoding="utf-8") for path in source_root.rglob("*.py")
    )
