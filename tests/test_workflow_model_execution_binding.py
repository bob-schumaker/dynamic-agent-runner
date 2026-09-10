"""Tests for sealed generic model-execution binding admission."""

from __future__ import annotations

import pytest

from dynamic_agent_runner.workflow_host.capabilities import (
    CapabilityContract,
    CapabilityRequirement,
    CapabilityRequirements,
)
from dynamic_agent_runner.workflow_host.model_execution_binding import (
    ModelExecutionBindingError,
    ModelRunnerProvider,
    ModelRunnerRegistry,
    derive_model_execution_binding,
)
from dynamic_agent_runner.workflow_host.model_materials import (
    parse_model_dependency_lock,
)


def _lock():
    return parse_model_dependency_lock(
        {
            "format_version": 1,
            "logical_model_id": "example",
            "runner_contract": {"id": "llama-cpp-v1", "version": "1"},
            "loader_profile_contract": {"id": "llama-cpp-text-v1", "version": "1"},
            "sources": [
                {
                    "role": "base_model",
                    "group": "base",
                    "source_type": "huggingface_file",
                    "repository": "example/model",
                    "revision": "a" * 40,
                    "filename": "model.gguf",
                    "sha256": "b" * 64,
                }
            ],
            "preparation": [],
        }
    )


def _requirements(*, converter: bool = False):
    entries = [CapabilityRequirement("model.execution.test.v1", "1", "c" * 64, ())]
    bindings = {"runner": "model.execution.test.v1"}
    if converter:
        entries.append(
            CapabilityRequirement("model.converter.test.v1", "1", "d" * 64, ())
        )
        entries.sort(key=lambda item: item.capability_id)
        bindings["converter"] = "model.converter.test.v1"
    return CapabilityRequirements(tuple(entries), bindings)


def test_binding_derives_exact_lock_and_capability_identity() -> None:
    binding = derive_model_execution_binding(lock=_lock(), requirements=_requirements())

    assert binding.runner_contract_id == "llama-cpp-v1"
    assert binding.loader_profile_contract_id == "llama-cpp-text-v1"
    assert len(binding.digest) == 64


def test_binding_rejects_missing_converter_capability_and_registry_has_no_fallback() -> (
    None
):
    lock = _lock()
    with pytest.raises(ModelExecutionBindingError, match="converter"):
        derive_model_execution_binding(
            lock=lock,
            requirements=_requirements(),
            converter_capability_id="model.converter.test.v1",
        )
    binding = derive_model_execution_binding(lock=lock, requirements=_requirements())
    runner = ModelRunnerProvider(
        "private-runner",
        CapabilityContract("model.execution.test.v1", "1", "c" * 64, ()),
        (("llama-cpp-v1", "1", "llama-cpp-text-v1", "1"),),
    )

    with pytest.raises(ModelExecutionBindingError, match="runner_unavailable"):
        ModelRunnerRegistry(()).resolve(binding)
    assert ModelRunnerRegistry((runner,)).resolve(binding) is runner
