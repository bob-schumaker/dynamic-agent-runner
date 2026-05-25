"""Tests for token budgeting and context preflight helpers."""

from __future__ import annotations

import pytest

from dynamic_agent_runner.errors import WorkflowExecutionError
from dynamic_agent_runner.token_budget import (
    TokenBudgetPolicy,
    estimate_messages_tokens,
    token_budget_policy_from_value,
)


def test_estimate_messages_tokens_counts_rendered_messages() -> None:
    estimate = estimate_messages_tokens(
        [{"role": "user", "content": "hello world"}],
        model="gpt-4o-mini",
    )

    assert estimate.token_count > 0
    assert estimate.encoding_name
    assert estimate.used_fallback_encoding is False


def test_estimate_messages_tokens_uses_fallback_for_unknown_model() -> None:
    estimate = estimate_messages_tokens(
        [{"role": "user", "content": "hello"}],
        model="unknown-local-model",
    )

    assert estimate.token_count > 0
    assert estimate.encoding_name == "cl100k_base"
    assert estimate.used_fallback_encoding is True


def test_token_budget_policy_is_disabled_by_default() -> None:
    assert token_budget_policy_from_value(None) == TokenBudgetPolicy()
    assert token_budget_policy_from_value("none") == TokenBudgetPolicy()


def test_token_budget_policy_parses_mapping() -> None:
    policy = token_budget_policy_from_value(
        {"max_prompt_tokens": 12, "model": "gpt-test", "on_exceed": "error"}
    )

    assert policy.max_prompt_tokens == 12
    assert policy.model == "gpt-test"
    assert policy.on_exceed == "error"


@pytest.mark.parametrize(
    "value",
    ["bad", {"max_prompt_tokens": 0}, {"max_prompt_tokens": "nope"}],
)
def test_token_budget_policy_rejects_bad_values(value: object) -> None:
    with pytest.raises(WorkflowExecutionError):
        token_budget_policy_from_value(value)
