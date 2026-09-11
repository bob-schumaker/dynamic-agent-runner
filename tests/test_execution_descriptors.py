"""Tests for sealed execution-descriptor parsing and ABI admission."""

from __future__ import annotations

from hashlib import sha256

import pytest

from dynamic_agent_runner.workflow_host.execution_descriptors import (
    ExecutionDescriptorAbi,
    ExecutionDescriptorError,
    ExecutionDescriptorValidatorRegistry,
    parse_execution_descriptor,
)


def _descriptor(*, abi: dict[str, str] | None = None) -> dict[str, object]:
    return {
        "format_version": 1,
        "architecture_abi": abi
        or {"id": "bert-encoder-v1", "version": "1", "contract_digest": "a" * 64},
        "material_roles": ["tokenizer", "weights"],
        "abi_fields": {"pooling": "masked_mean"},
    }


def _abi() -> ExecutionDescriptorAbi:
    return ExecutionDescriptorAbi("bert-encoder-v1", "1", "a" * 64)


def test_descriptor_has_canonical_bytes_and_digest() -> None:
    descriptor = parse_execution_descriptor(_descriptor())

    assert descriptor.canonical_bytes == (
        b'{"abi_fields":{"pooling":"masked_mean"},"architecture_abi":'
        b'{"contract_digest":"' + b"a" * 64 + b'","id":"bert-encoder-v1",'
        b'"version":"1"},"format_version":1,"material_roles":'
        b'["tokenizer","weights"]}'
    )
    assert descriptor.digest == sha256(descriptor.canonical_bytes).hexdigest()


@pytest.mark.parametrize(
    "mutate",
    (
        lambda value: value.update(unexpected="value"),
        lambda value: value.update(material_roles=["weights", "tokenizer"]),
        lambda value: value.update(material_roles=["weights", "weights"]),
        lambda value: value["architecture_abi"].update(contract_digest="A" * 64),
        lambda value: value.update(abi_fields=[]),
    ),
)
def test_descriptor_rejects_noncanonical_or_malformed_values(mutate) -> None:
    value = _descriptor()
    mutate(value)

    with pytest.raises(ExecutionDescriptorError):
        parse_execution_descriptor(value)


def test_registry_resolves_only_the_exact_abi_without_side_effects() -> None:
    calls: list[str] = []

    class _Validator:
        identity = _abi()

        def validate(self, descriptor) -> None:
            calls.append(descriptor.digest)

    descriptor = parse_execution_descriptor(_descriptor())
    registry = ExecutionDescriptorValidatorRegistry((_Validator(),))

    assert registry.validate(descriptor) is None
    assert calls == [descriptor.digest]


@pytest.mark.parametrize(
    "abi",
    (
        {"id": "unknown", "version": "1", "contract_digest": "a" * 64},
        {"id": "bert-encoder-v1", "version": "2", "contract_digest": "a" * 64},
        {"id": "bert-encoder-v1", "version": "1", "contract_digest": "b" * 64},
    ),
)
def test_registry_rejects_unknown_or_changed_abi_before_validator_call(
    abi: dict[str, str],
) -> None:
    calls: list[str] = []

    class _Validator:
        identity = _abi()

        def validate(self, descriptor) -> None:
            calls.append(descriptor.digest)

    with pytest.raises(ExecutionDescriptorError):
        ExecutionDescriptorValidatorRegistry((_Validator(),)).validate(
            parse_execution_descriptor(_descriptor(abi=abi))
        )
    assert calls == []
