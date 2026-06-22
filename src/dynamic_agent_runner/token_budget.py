"""Token estimation and budget preflight helpers for workflow execution."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from dynamic_agent_runner.errors import WorkflowExecutionError

_FALLBACK_ENCODING = "cl100k_base"


@dataclass(frozen=True)
class TokenBudgetPolicy:
    """Optional token-budget policy for rendered model input messages."""

    max_prompt_tokens: int | None = None
    model: str | None = None
    on_exceed: str = "error"

    @property
    def enabled(self) -> bool:
        """Return whether this policy should run preflight enforcement."""

        return self.max_prompt_tokens is not None


@dataclass(frozen=True)
class TokenUsageRecord:
    """Observed token estimate for one model call site."""

    node_id: str
    model: str
    estimated_prompt_tokens: int
    max_prompt_tokens: int | None = None
    encoding_name: str | None = None
    used_fallback_encoding: bool = False
    exceeded: bool = False


@dataclass(frozen=True)
class TokenEstimate:
    """Token estimate details returned by the estimator."""

    token_count: int
    encoding_name: str
    used_fallback_encoding: bool = False


def token_budget_policy_from_value(value: Any) -> TokenBudgetPolicy:
    """Parse optional token budget metadata into a package-owned policy."""

    if value in (None, False, "", "none"):
        return TokenBudgetPolicy()
    if not isinstance(value, Mapping):
        raise WorkflowExecutionError(f"unsupported token budget policy {value!r}")
    max_prompt_tokens = value.get("max_prompt_tokens")
    if max_prompt_tokens is None:
        max_prompt_tokens = value.get("max_tokens")
    return TokenBudgetPolicy(
        max_prompt_tokens=(
            _positive_int(max_prompt_tokens, field_name="max_prompt_tokens")
            if max_prompt_tokens is not None
            else None
        ),
        model=str(value["model"]) if value.get("model") is not None else None,
        on_exceed=str(value.get("on_exceed") or "error"),
    )


def estimate_messages_tokens(
    messages: Sequence[Mapping[str, Any]],
    *,
    model: str,
) -> TokenEstimate:
    """Estimate prompt tokens for rendered OpenAI-compatible messages."""

    encoding, encoding_name, used_fallback = _encoding_for_model(model)
    token_count = 3
    for message in messages:
        token_count += 3
        role = message.get("role")
        content = message.get("content")
        if role is not None:
            token_count += len(encoding.encode(str(role)))
        if content is not None:
            token_count += len(encoding.encode(str(content)))
    return TokenEstimate(
        token_count=token_count,
        encoding_name=encoding_name,
        used_fallback_encoding=used_fallback,
    )


def estimate_text_tokens(text: str, *, model: str) -> TokenEstimate:
    """Estimate tokens for a plain text payload."""

    encoding, encoding_name, used_fallback = _encoding_for_model(model)
    return TokenEstimate(
        token_count=len(encoding.encode(text)),
        encoding_name=encoding_name,
        used_fallback_encoding=used_fallback,
    )


def _encoding_for_model(model: str) -> tuple[Any, str, bool]:
    try:
        import tiktoken
    except Exception as exc:  # noqa: BLE001 - dependency import errors vary.
        raise WorkflowExecutionError("tiktoken package is not available") from exc
    try:
        encoding = tiktoken.encoding_for_model(model)
        return encoding, encoding.name, False
    except KeyError:
        encoding = tiktoken.get_encoding(_FALLBACK_ENCODING)
        return encoding, encoding.name, True


def _positive_int(value: Any, *, field_name: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise WorkflowExecutionError(
            f"token budget policy {field_name} must be an integer"
        ) from exc
    if parsed < 1:
        raise WorkflowExecutionError(
            f"token budget policy {field_name} must be at least 1"
        )
    return parsed
