"""Tests for caller-owned provider context compaction contracts."""

from dynamic_agent_runner import (
    ProviderContextCompactionRequest,
    ProviderContextCompactionResult,
    ProviderContextCompactor,
)
from dynamic_agent_runner.openai_client import OpenAIMessage


def test_provider_context_compaction_contract_is_public() -> None:
    request = ProviderContextCompactionRequest(
        messages=(OpenAIMessage(role="user", content="hello"),),
        model="gpt-test",
        phase="pre_turn",
        provider_capability="responses_compact",
        max_replacement_messages=32,
        preserve_system_messages=True,
        tokens_before=4,
    )
    result = ProviderContextCompactionResult(messages=request.messages)

    assert ProviderContextCompactor is not None
    assert result.messages == request.messages
