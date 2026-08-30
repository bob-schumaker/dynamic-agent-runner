"""Measurement contract for the descriptor benchmark comparison."""

from __future__ import annotations

from tool_descriptor_benchmark import load_benchmark_cases, measure_benchmark


def test_measurement_accounts_for_every_case_and_requested_metric() -> None:
    measurement = measure_benchmark(iterations=2, warmups=0)
    case_ids = {case["id"] for case in load_benchmark_cases()}

    assert measurement.corpus_format == "tool-descriptor-benchmark-v1"
    assert measurement.corpus_digest
    assert measurement.model == "gpt-4o-mini"
    assert measurement.nltk_dependency.direct_version
    assert measurement.nltk_dependency.direct_bytes > 0
    assert "nltk" in measurement.nltk_dependency.closure_names
    assert set(measurement.nltk_dependency.incremental_names) <= set(
        measurement.nltk_dependency.closure_names
    )

    assert {scorer.scorer_id for scorer in measurement.scorers} == {
        "deterministic_metadata",
        "nltk_lexical",
    }
    for scorer in measurement.scorers:
        assert {case.case_id for case in scorer.cases} == case_ids
        assert scorer.relevant_tool_count == sum(
            len(case["expected_required_tools"]) for case in load_benchmark_cases()
        )
        assert scorer.false_omission_count == len(scorer.false_omission_tool_ids)
        assert scorer.all_descriptor_tokens >= scorer.selected_descriptor_tokens
        assert 0 <= scorer.descriptor_token_reduction <= 1
        assert scorer.median_runtime_ns >= 0
        assert scorer.token_encoding


def test_measurement_keeps_oracle_metrics_outside_scorer_selection() -> None:
    measurement = measure_benchmark(iterations=1, warmups=0)

    for scorer in measurement.scorers:
        for case in scorer.cases:
            assert case.selected_tool_ids
            assert set(case.false_omission_tool_ids) <= set(case.required_tool_ids)


def test_fixed_corpus_records_no_nltk_selection_quality_gain() -> None:
    measurement = measure_benchmark(iterations=1, warmups=0)
    scorers = {scorer.scorer_id: scorer for scorer in measurement.scorers}

    deterministic = scorers["deterministic_metadata"]
    nltk = scorers["nltk_lexical"]
    assert deterministic.recalled_tool_count == nltk.recalled_tool_count == 4
    assert deterministic.relevant_tool_count == nltk.relevant_tool_count == 6
    assert (
        deterministic.false_omission_tool_ids
        == nltk.false_omission_tool_ids
        == (
            "inspect_then_modify_config:read_file",
            "inspect_then_modify_config:write_file",
        )
    )
    assert deterministic.descriptor_token_reduction == nltk.descriptor_token_reduction
    assert measurement.nltk_dependency.closure_names == (
        "click",
        "defusedxml",
        "joblib",
        "nltk",
        "regex",
        "tqdm",
    )
    assert measurement.nltk_dependency.incremental_names == (
        "defusedxml",
        "joblib",
        "nltk",
    )
