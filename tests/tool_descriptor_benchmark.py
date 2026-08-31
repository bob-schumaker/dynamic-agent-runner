"""Test-only scorer comparison support for the descriptor benchmark corpus."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
import hashlib
from importlib import metadata
import json
from pathlib import Path
import re
from statistics import median
import time
import tomllib
from typing import Any

from dynamic_agent_runner.token_budget import estimate_text_tokens
from packaging.requirements import Requirement


FIXTURE_PATH = (
    Path(__file__).parent
    / "fixtures"
    / "tool-descriptor-budgeting"
    / "benchmark-v1.json"
)
LOCK_PATH = Path(__file__).resolve().parents[1] / "poetry.lock"
BENCHMARK_MODEL = "gpt-4o-mini"


@dataclass(frozen=True)
class ScorerResult:
    scorer_id: str
    ranked_tool_ids: tuple[str, ...]
    selected_tool_ids: tuple[str, ...]


@dataclass(frozen=True)
class BenchmarkComparison:
    deterministic: ScorerResult
    nltk: ScorerResult


@dataclass(frozen=True)
class CaseMeasurement:
    case_id: str
    selected_tool_ids: tuple[str, ...]
    required_tool_ids: tuple[str, ...]
    false_omission_tool_ids: tuple[str, ...]
    all_descriptor_tokens: int
    selected_descriptor_tokens: int


@dataclass(frozen=True)
class ScorerMeasurement:
    scorer_id: str
    cases: tuple[CaseMeasurement, ...]
    relevant_tool_count: int
    recalled_tool_count: int
    false_omission_tool_ids: tuple[str, ...]
    all_descriptor_tokens: int
    selected_descriptor_tokens: int
    descriptor_token_reduction: float
    token_encoding: str
    used_fallback_encoding: bool
    median_runtime_ns: int

    @property
    def false_omission_count(self) -> int:
        return len(self.false_omission_tool_ids)


@dataclass(frozen=True)
class NLTKDependencyMeasurement:
    direct_version: str
    direct_bytes: int
    closure_names: tuple[str, ...]
    closure_bytes: int
    incremental_names: tuple[str, ...]
    incremental_bytes: int


@dataclass(frozen=True)
class BenchmarkMeasurement:
    corpus_format: str
    corpus_digest: str
    model: str
    scorers: tuple[ScorerMeasurement, ...]
    nltk_dependency: NLTKDependencyMeasurement


def load_benchmark_cases() -> tuple[dict[str, Any], ...]:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    return tuple(fixture["cases"])


def compare_case(case: Mapping[str, Any]) -> BenchmarkComparison:
    return BenchmarkComparison(
        deterministic=score_case(case, "deterministic_metadata"),
        nltk=score_case(case, "nltk_lexical"),
    )


def score_case(case: Mapping[str, Any], scorer_id: str) -> ScorerResult:
    if scorer_id == "deterministic_metadata":
        return _score_case(case, scorer_id=scorer_id, terms=_terms)
    if scorer_id == "nltk_lexical":
        return _score_case(case, scorer_id=scorer_id, terms=_nltk_terms)
    raise ValueError(f"unknown benchmark scorer {scorer_id!r}")


def measure_benchmark(
    *,
    iterations: int = 100,
    warmups: int = 1,
    clock: Callable[[], int] = time.perf_counter_ns,
) -> BenchmarkMeasurement:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    cases = tuple(fixture["cases"])
    scorers = tuple(
        _measure_scorer(
            scorer_id, cases, iterations=iterations, warmups=warmups, clock=clock
        )
        for scorer_id in ("deterministic_metadata", "nltk_lexical")
    )
    return BenchmarkMeasurement(
        corpus_format=str(fixture["format_version"]),
        corpus_digest=hashlib.sha256(FIXTURE_PATH.read_bytes()).hexdigest(),
        model=BENCHMARK_MODEL,
        scorers=scorers,
        nltk_dependency=_nltk_dependency_measurement(),
    )


def _measure_scorer(
    scorer_id: str,
    cases: Sequence[Mapping[str, Any]],
    *,
    iterations: int,
    warmups: int,
    clock: Callable[[], int],
) -> ScorerMeasurement:
    for _ in range(warmups):
        for case in cases:
            score_case(case, scorer_id)

    samples = []
    for _ in range(iterations):
        start = clock()
        for case in cases:
            score_case(case, scorer_id)
        samples.append(clock() - start)

    case_measurements = tuple(
        _measure_case(case, score_case(case, scorer_id)) for case in cases
    )
    all_tokens = sum(case.all_descriptor_tokens for case in case_measurements)
    selected_tokens = sum(case.selected_descriptor_tokens for case in case_measurements)
    relevant_ids = tuple(
        tool_id for case in case_measurements for tool_id in case.required_tool_ids
    )
    false_omission_ids = tuple(
        f"{case.case_id}:{tool_id}"
        for case in case_measurements
        for tool_id in case.false_omission_tool_ids
    )
    encoding, used_fallback = _token_estimator_metadata(cases)
    return ScorerMeasurement(
        scorer_id=scorer_id,
        cases=case_measurements,
        relevant_tool_count=len(relevant_ids),
        recalled_tool_count=sum(
            tool_id in case.selected_tool_ids
            for case in case_measurements
            for tool_id in case.required_tool_ids
        ),
        false_omission_tool_ids=false_omission_ids,
        all_descriptor_tokens=all_tokens,
        selected_descriptor_tokens=selected_tokens,
        descriptor_token_reduction=(all_tokens - selected_tokens) / all_tokens,
        token_encoding=encoding,
        used_fallback_encoding=used_fallback,
        median_runtime_ns=int(median(samples)),
    )


def _measure_case(case: Mapping[str, Any], result: ScorerResult) -> CaseMeasurement:
    eligible_by_id = {str(tool["id"]): tool for tool in case["eligible_tools"]}
    selected_tools = tuple(
        eligible_by_id[tool_id] for tool_id in result.selected_tool_ids
    )
    required_ids = tuple(str(tool_id) for tool_id in case["expected_required_tools"])
    false_omission_ids = tuple(
        str(check["tool_id"])
        for check in case["false_omission_checks"]
        if str(check["tool_id"]) not in result.selected_tool_ids
    )
    return CaseMeasurement(
        case_id=str(case["id"]),
        selected_tool_ids=result.selected_tool_ids,
        required_tool_ids=required_ids,
        false_omission_tool_ids=false_omission_ids,
        all_descriptor_tokens=_descriptor_tokens(case["eligible_tools"])[0],
        selected_descriptor_tokens=_descriptor_tokens(selected_tools)[0],
    )


def _descriptor_tokens(tools: Sequence[Mapping[str, Any]]) -> tuple[int, str, bool]:
    estimates = tuple(
        estimate_text_tokens(
            json.dumps(_openai_descriptor(tool), sort_keys=True, separators=(",", ":")),
            model=BENCHMARK_MODEL,
        )
        for tool in tools
    )
    if not estimates:
        estimate = estimate_text_tokens("", model=BENCHMARK_MODEL)
        return 0, estimate.encoding_name, estimate.used_fallback_encoding
    return (
        sum(estimate.token_count for estimate in estimates),
        estimates[0].encoding_name,
        any(estimate.used_fallback_encoding for estimate in estimates),
    )


def _openai_descriptor(tool: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "type": "function",
        "name": str(tool["id"]),
        "description": str(tool["description_for_llm"]),
        "parameters": dict(tool["input_schema"]),
    }


def _token_estimator_metadata(
    cases: Sequence[Mapping[str, Any]],
) -> tuple[str, bool]:
    return _descriptor_tokens(cases[0]["eligible_tools"])[1:]


def _nltk_dependency_measurement() -> NLTKDependencyMeasurement:
    closure = _distribution_closure("nltk")
    incremental = _incremental_test_closure(closure)
    direct = metadata.distribution("nltk")
    return NLTKDependencyMeasurement(
        direct_version=direct.version,
        direct_bytes=_distribution_bytes(direct),
        closure_names=tuple(sorted(closure)),
        closure_bytes=sum(
            _distribution_bytes(metadata.distribution(name)) for name in closure
        ),
        incremental_names=tuple(sorted(incremental)),
        incremental_bytes=sum(
            _distribution_bytes(metadata.distribution(name)) for name in incremental
        ),
    )


def _distribution_closure(name: str) -> set[str]:
    pending = [name]
    closure: set[str] = set()
    while pending:
        current = pending.pop()
        normalized = current.lower().replace("_", "-")
        if normalized in closure:
            continue
        closure.add(normalized)
        try:
            distribution = metadata.distribution(normalized)
        except metadata.PackageNotFoundError:
            closure.remove(normalized)
            continue
        pending.extend(
            requirement_name
            for requirement in distribution.requires or ()
            if (requirement_name := _requirement_name(requirement)) is not None
        )
    return closure


def _requirement_name(requirement: str) -> str | None:
    parsed = Requirement(requirement)
    if parsed.marker is not None and not parsed.marker.evaluate({"extra": ""}):
        return None
    return parsed.name


def _incremental_test_closure(closure: set[str]) -> set[str]:
    lock = tomllib.loads(LOCK_PATH.read_text(encoding="utf-8"))
    groups = {
        str(package["name"]).lower().replace("_", "-"): set(package["groups"])
        for package in lock["package"]
    }
    return {name for name in closure if groups[name] == {"test"}}


def _distribution_bytes(distribution: metadata.Distribution) -> int:
    return sum(
        path.stat().st_size
        for file in distribution.files or ()
        if (path := Path(distribution.locate_file(file))).is_file()
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
