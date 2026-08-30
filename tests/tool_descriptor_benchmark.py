"""Test-only scorer comparison support for the descriptor benchmark corpus."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any


FIXTURE_PATH = (
    Path(__file__).parent
    / "fixtures"
    / "tool-descriptor-budgeting"
    / "benchmark-v1.json"
)


@dataclass(frozen=True)
class ScorerResult:
    scorer_id: str
    ranked_tool_ids: tuple[str, ...]
    selected_tool_ids: tuple[str, ...]


@dataclass(frozen=True)
class BenchmarkComparison:
    deterministic: ScorerResult
    nltk: ScorerResult


def load_benchmark_cases() -> tuple[dict[str, Any], ...]:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    return tuple(fixture["cases"])


def compare_case(case: Mapping[str, Any]) -> BenchmarkComparison:
    return BenchmarkComparison(
        deterministic=_score_case(
            case, scorer_id="deterministic_metadata", terms=_terms
        ),
        nltk=_score_case(case, scorer_id="nltk_lexical", terms=_nltk_terms),
    )


def _score_case(
    case: Mapping[str, Any],
    *,
    scorer_id: str,
    terms: Callable[[str], set[str]],
) -> ScorerResult:
    prompt = str(case["prompt"])
    prompt_terms = terms(prompt)
    exact_prompt_terms = _terms(prompt)
    scored = [
        (index, tool, _score_tool(tool, prompt_terms, exact_prompt_terms, terms))
        for index, tool in enumerate(case["eligible_tools"])
    ]
    ranked = sorted(
        scored,
        key=lambda item: (-item[2], item[0]),
    )
    ranked_ids = tuple(str(tool["id"]) for _, tool, _ in ranked)
    return ScorerResult(
        scorer_id=scorer_id,
        ranked_tool_ids=ranked_ids,
        selected_tool_ids=tuple(
            str(tool["id"]) for _, tool, score in ranked if score > 0
        ),
    )


def _score_tool(
    tool: Mapping[str, Any],
    prompt_terms: set[str],
    exact_prompt_terms: set[str],
    terms: Callable[[str], set[str]],
) -> int:
    metadata = " ".join(
        str(value)
        for value in (
            tool["id"],
            tool["label"],
            tool["tool_type"],
            tool["description_for_llm"],
        )
    )
    score = len(
        (terms(metadata) | _schema_terms(tool["input_schema"], terms)) & prompt_terms
    )
    if str(tool["id"]).lower() in " ".join(sorted(exact_prompt_terms)):
        score += 4
    return score


def _schema_terms(value: Any, terms: Callable[[str], set[str]]) -> set[str]:
    if isinstance(value, Mapping):
        return set().union(
            *(
                terms(str(key)) | _schema_terms(item, terms)
                for key, item in value.items()
            )
        )
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return set().union(*(_schema_terms(item, terms) for item in value))
    return terms(value) if isinstance(value, str) else set()


def _terms(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", value.lower()))


def _nltk_terms(value: str) -> set[str]:
    from nltk.stem import PorterStemmer
    from nltk.tokenize import wordpunct_tokenize

    stemmer = PorterStemmer()
    return {
        stemmer.stem(token.lower())
        for token in wordpunct_tokenize(value)
        if token.isalnum()
    }
