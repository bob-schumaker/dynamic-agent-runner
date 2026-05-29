"""Retry policy helpers for dynamic-agent workflow execution."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any, TypeVar

from tenacity import (
    AsyncRetrying,
    Retrying,
    retry_if_exception,
    retry_if_exception_type,
    stop_after_attempt,
    wait_fixed,
)

from dynamic_agent_runner.errors import WorkflowExecutionError

T = TypeVar("T")


@dataclass(frozen=True)
class RetryPolicy:
    """Package-owned bounded retry policy for model and tool calls."""

    max_attempts: int = 1
    wait_seconds: float = 0.0
    retry_on: tuple[str, ...] = ()

    @property
    def enabled(self) -> bool:
        """Return whether this policy allows retry attempts after the first try."""

        return self.max_attempts > 1 and bool(self.retry_on)


@dataclass(frozen=True)
class RetryRecord:
    """Observed retry outcome for a single workflow call site."""

    node_id: str
    operation: str
    attempts: int
    outcome: str
    final_error: str | None = None


def retry_policy_from_value(value: Any) -> RetryPolicy:
    """Parse manifest or registry retry metadata into a runtime policy."""

    if value in (None, False, "", "none"):
        return RetryPolicy()
    if value in (True, "default", "bounded"):
        return RetryPolicy(max_attempts=3, retry_on=("exception", "failure"))
    if not isinstance(value, Mapping):
        raise WorkflowExecutionError(f"unsupported retry policy {value!r}")
    max_attempts = _positive_int(
        value.get("max_attempts") or value.get("attempts") or 1,
        field_name="max_attempts",
    )
    wait_seconds = _non_negative_float(
        value.get("wait_seconds") or value.get("wait") or 0,
        field_name="wait_seconds",
    )
    retry_on = _retry_on(value.get("retry_on"), default=("exception", "failure"))
    return RetryPolicy(
        max_attempts=max_attempts,
        wait_seconds=wait_seconds,
        retry_on=retry_on,
    )


def run_with_retry(
    operation: Callable[[], T],
    *,
    policy: RetryPolicy,
    retry_exceptions: tuple[type[BaseException], ...],
) -> tuple[T, int]:
    """Run ``operation`` under a Tenacity-backed bounded retry policy."""

    if not policy.enabled:
        return operation(), 1
    attempts = 0
    for attempt in Retrying(
        stop=stop_after_attempt(policy.max_attempts),
        wait=wait_fixed(policy.wait_seconds),
        retry=retry_if_exception_type(retry_exceptions),
        reraise=True,
    ):
        attempts = attempt.retry_state.attempt_number
        with attempt:
            return operation(), attempts
    raise AssertionError("retry loop exited without returning or raising")


async def run_with_retry_async(
    operation: Callable[[], Awaitable[T]],
    *,
    policy: RetryPolicy,
    retry_exceptions: tuple[type[BaseException], ...],
) -> tuple[T, int]:
    """Run an async ``operation`` under a bounded retry policy.

    ``asyncio.CancelledError`` always propagates without retry so workflow
    cancellation is not converted into an ordinary model or tool failure.
    """

    if not policy.enabled:
        return await operation(), 1
    attempts = 0
    async for attempt in AsyncRetrying(
        stop=stop_after_attempt(policy.max_attempts),
        wait=wait_fixed(policy.wait_seconds),
        retry=retry_if_exception(
            lambda exc: (
                isinstance(exc, retry_exceptions)
                and not isinstance(exc, asyncio.CancelledError)
            )
        ),
        reraise=True,
    ):
        attempts = attempt.retry_state.attempt_number
        with attempt:
            return await operation(), attempts
    raise AssertionError("async retry loop exited without returning or raising")


def _retry_on(value: Any, *, default: tuple[str, ...]) -> tuple[str, ...]:
    if value is None:
        return default
    if isinstance(value, str):
        if value == "none":
            return ()
        return (value,)
    if isinstance(value, list | tuple):
        return tuple(str(item) for item in value)
    raise WorkflowExecutionError(f"retry_on must be a string or list, got {value!r}")


def _positive_int(value: Any, *, field_name: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise WorkflowExecutionError(
            f"retry policy {field_name} must be an integer"
        ) from exc
    if parsed < 1:
        raise WorkflowExecutionError(f"retry policy {field_name} must be at least 1")
    return parsed


def _non_negative_float(value: Any, *, field_name: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise WorkflowExecutionError(
            f"retry policy {field_name} must be a number"
        ) from exc
    if parsed < 0:
        raise WorkflowExecutionError(f"retry policy {field_name} must be non-negative")
    return parsed
