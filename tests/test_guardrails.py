"""Tests for caller-registered guardrail helpers."""

from __future__ import annotations


def test_guardrail_contract_is_exported() -> None:
    import dynamic_agent_runner

    assert dynamic_agent_runner.GuardrailDecision is not None
    assert dynamic_agent_runner.GuardrailResult is not None
    assert dynamic_agent_runner.InMemoryGuardrailRegistry is not None


def test_guardrail_result_defaults_to_input_pass() -> None:
    from dynamic_agent_runner import GuardrailDecision, GuardrailResult

    result = GuardrailResult(guardrail_id="no_secrets")

    assert result.guardrail_id == "no_secrets"
    assert result.phase == "input"
    assert result.decision is GuardrailDecision.PASS
    assert result.reason_code is None


def test_in_memory_guardrail_registry_runs_registered_handler() -> None:
    from dynamic_agent_runner import (
        GuardrailDecision,
        GuardrailResult,
        InMemoryGuardrailRegistry,
    )

    registry = InMemoryGuardrailRegistry(
        {
            "no_secrets": lambda subject: GuardrailResult(
                guardrail_id="no_secrets",
                decision=(
                    GuardrailDecision.ABORT
                    if "secret" in str(subject)
                    else GuardrailDecision.PASS
                ),
                reason_code="secret_detected",
            )
        }
    )

    result = registry.run("no_secrets", "contains secret")

    assert result.decision is GuardrailDecision.ABORT
    assert result.reason_code == "secret_detected"
