"""Prompt-cache intent parsing and trace-evidence helpers."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from dynamic_agent_runner.errors import WorkflowExecutionError
from dynamic_agent_runner.openai_client import OpenAIMessage
from dynamic_agent_runner.token_budget import estimate_messages_tokens

_ALLOWED_PREFIX_PARTS = {
    "system",
    "developer",
    "skill_instructions",
    "tool_schemas",
}
_ALLOWED_VARIABLE_PARTS = {"user_prompt", "run_state"}
_SUPPORTED_STRATEGIES = {"stable_prefix"}


@dataclass(frozen=True)
class PromptCachePolicy:
    """Provider-neutral prompt-cache intent from runtime metadata."""

    enabled: bool = False
    strategy: str = "stable_prefix"
    min_prefix_tokens: int | None = None
    prefix_parts: tuple[str, ...] = ()
    variable_parts: tuple[str, ...] = ()
    cache_key_hint: str | None = None
    provider_hints: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PromptCacheObservation:
    """Runtime evidence for one prompt-cache eligibility check."""

    payload: Mapping[str, Any]


def prompt_cache_policy_from_value(value: Any) -> PromptCachePolicy:
    """Parse optional prompt-cache metadata into a provider-neutral policy."""

    if value in (None, False, "", "none"):
        return PromptCachePolicy()
    if not isinstance(value, Mapping):
        raise WorkflowExecutionError("prompt_cache policy must be a mapping")
    enabled = value.get("enabled", True)
    if not isinstance(enabled, bool):
        raise WorkflowExecutionError("prompt_cache enabled must be a boolean")
    strategy = str(value.get("strategy") or "stable_prefix")
    if strategy not in _SUPPORTED_STRATEGIES:
        raise WorkflowExecutionError(
            f"prompt_cache strategy {strategy!r} is unsupported"
        )
    min_prefix_tokens = _optional_positive_int(
        value.get("min_prefix_tokens"), field_name="min_prefix_tokens"
    )
    prefix_parts = _parts_tuple(
        value.get("prefix_parts"),
        field_name="prefix_parts",
        allowed_parts=_ALLOWED_PREFIX_PARTS,
        allow_extensions=True,
    )
    variable_parts = _parts_tuple(
        value.get("variable_parts"),
        field_name="variable_parts",
        allowed_parts=_ALLOWED_VARIABLE_PARTS,
        allow_extensions=True,
    )
    provider_hints = value.get("provider_hints") or {}
    if not isinstance(provider_hints, Mapping):
        raise WorkflowExecutionError("prompt_cache provider_hints must be a mapping")
    return PromptCachePolicy(
        enabled=enabled,
        strategy=strategy,
        min_prefix_tokens=min_prefix_tokens,
        prefix_parts=prefix_parts,
        variable_parts=variable_parts,
        cache_key_hint=(
            str(value["cache_key_hint"])
            if value.get("cache_key_hint") is not None
            else None
        ),
        provider_hints=dict(provider_hints),
    )


def build_prompt_cache_observation(
    *,
    policy: PromptCachePolicy,
    message_parts: Sequence[tuple[str, OpenAIMessage]],
    model: str,
    caller_override: str,
) -> PromptCacheObservation | None:
    """Build trace payload for prompt-cache eligibility without provider I/O."""

    if not policy.enabled and caller_override == "manifest_absent":
        return None
    prefix_messages = _stable_prefix_messages(policy, message_parts)
    first_variable_part = _first_variable_part(policy, message_parts)
    payload: dict[str, Any] = {
        "enabled": policy.enabled,
        "eligible": False,
        "strategy": policy.strategy,
        "stable_prefix_part_names": [part for part, _message in prefix_messages],
        "first_variable_part": first_variable_part,
        "estimated_prefix_tokens": None,
        "prefix_hash": None,
        "provider_hints": sorted(str(key) for key in policy.provider_hints),
        "caller_override": caller_override,
        "adapter_fallback": "not_applied",
    }
    if not policy.enabled:
        payload["ineligibility_reason"] = "disabled"
        return PromptCacheObservation(payload)
    if not prefix_messages:
        payload["ineligibility_reason"] = "no_stable_prefix"
        return PromptCacheObservation(payload)
    try:
        estimate = estimate_messages_tokens(
            tuple(message.to_mapping() for _part, message in prefix_messages),
            model=model,
        )
    except Exception as exc:  # noqa: BLE001 - estimators can fail by environment.
        payload["ineligibility_reason"] = "token_estimation_unavailable"
        payload["estimation_error"] = str(exc)
        payload["prefix_hash"] = _prefix_hash(prefix_messages)
        return PromptCacheObservation(payload)
    payload["estimated_prefix_tokens"] = estimate.token_count
    payload["prefix_hash"] = _prefix_hash(prefix_messages)
    if (
        policy.min_prefix_tokens is not None
        and estimate.token_count < policy.min_prefix_tokens
    ):
        payload["ineligibility_reason"] = "below_min_prefix_tokens"
        return PromptCacheObservation(payload)
    payload["eligible"] = True
    return PromptCacheObservation(payload)


def _stable_prefix_messages(
    policy: PromptCachePolicy,
    message_parts: Sequence[tuple[str, OpenAIMessage]],
) -> tuple[tuple[str, OpenAIMessage], ...]:
    allowed = set(policy.prefix_parts) if policy.prefix_parts else _ALLOWED_PREFIX_PARTS
    prefix: list[tuple[str, OpenAIMessage]] = []
    for part, message in message_parts:
        if part in _ALLOWED_VARIABLE_PARTS:
            break
        if part in allowed:
            prefix.append((part, message))
    return tuple(prefix)


def _first_variable_part(
    policy: PromptCachePolicy,
    message_parts: Sequence[tuple[str, OpenAIMessage]],
) -> str | None:
    variable_parts = (
        set(policy.variable_parts) if policy.variable_parts else _ALLOWED_VARIABLE_PARTS
    )
    for part, _message in message_parts:
        if part in variable_parts:
            return part
    return None


def _prefix_hash(prefix_messages: Sequence[tuple[str, OpenAIMessage]]) -> str:
    payload = [
        {"part": part, "message": message.to_mapping()}
        for part, message in prefix_messages
    ]
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _parts_tuple(
    value: Any,
    *,
    field_name: str,
    allowed_parts: set[str],
    allow_extensions: bool,
) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str) or not isinstance(value, Sequence):
        raise WorkflowExecutionError(f"prompt_cache {field_name} must be a list")
    parts = tuple(str(part) for part in value)
    for part in parts:
        if part in allowed_parts:
            continue
        if allow_extensions and part.startswith("x-"):
            continue
        raise WorkflowExecutionError(
            f"prompt_cache {field_name} contains unsupported part {part!r}"
        )
    return parts


def _optional_positive_int(value: Any, *, field_name: str) -> int | None:
    if value is None:
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise WorkflowExecutionError(
            f"prompt_cache {field_name} must be an integer"
        ) from exc
    if parsed < 1:
        raise WorkflowExecutionError(f"prompt_cache {field_name} must be at least 1")
    return parsed
