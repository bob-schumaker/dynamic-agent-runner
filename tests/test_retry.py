"""Tests for retry policy helpers."""

from __future__ import annotations

import asyncio

import pytest

from dynamic_agent_runner.errors import ModelExecutionError
from dynamic_agent_runner.retry import RetryPolicy, run_with_retry_async


def test_run_with_retry_async_retries_retryable_failures() -> None:
    calls = 0

    async def operation() -> str:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise ModelExecutionError("temporary outage")
        return "done"

    result, attempts = asyncio.run(
        run_with_retry_async(
            operation,
            policy=RetryPolicy(max_attempts=3, retry_on=("exception",)),
            retry_exceptions=(ModelExecutionError,),
        )
    )

    assert result == "done"
    assert attempts == 2
    assert calls == 2


def test_run_with_retry_async_propagates_cancellation_without_retry() -> None:
    calls = 0

    async def operation() -> str:
        nonlocal calls
        calls += 1
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(
            run_with_retry_async(
                operation,
                policy=RetryPolicy(max_attempts=3, retry_on=("exception",)),
                retry_exceptions=(BaseException,),
            )
        )

    assert calls == 1
