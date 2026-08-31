"""Caller-owned provider context-compaction contracts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, Protocol

from dynamic_agent_runner.openai_client import OpenAIMessage


@dataclass(frozen=True)
class ProviderContextCompactionRequest:
    """One bounded provider-compaction request prepared by DAR."""

    messages: tuple[OpenAIMessage, ...]
    model: str
    phase: Literal["pre_turn", "overflow_retry"]
    provider_capability: str
    max_replacement_messages: int
    preserve_system_messages: bool
    tokens_before: int


@dataclass(frozen=True)
class ProviderContextCompactionResult:
    """Validated-shape replacement history returned by a caller collaborator."""

    messages: tuple[OpenAIMessage, ...]
    provider_window_id: str | None = None
    token_baseline: int | None = None


class ProviderContextCompactor(Protocol):
    """Caller-owned provider compaction capability and transport boundary."""

    capabilities: Mapping[str, bool]

    def compact(
        self,
        request: ProviderContextCompactionRequest,
    ) -> ProviderContextCompactionResult:
        """Return bounded replacement history for a prepared request."""


__all__ = [
    "ProviderContextCompactionRequest",
    "ProviderContextCompactionResult",
    "ProviderContextCompactor",
]
