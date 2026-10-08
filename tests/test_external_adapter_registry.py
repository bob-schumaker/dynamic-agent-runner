from __future__ import annotations

import json
from pathlib import Path

import pytest

from dynamic_agent_runner.external_adapter import ExternalModelAdapterDescriptor
from dynamic_agent_runner.workflow_host.external_adapter_registry import (
    ExternalAdapterRegistry,
    ExternalAdapterRegistryError,
)


def descriptor(**overrides: object) -> ExternalModelAdapterDescriptor:
    values: dict[str, object] = {
        "adapter_id": "test.external",
        "provider_id": "test",
        "protocol_id": "dar.external-model.v1",
        "protocol_version": "1.0",
        "model_alias": "test-model",
        "canonical_model_id": "test-canonical",
        "execution_location": "local",
        "execution_modes": frozenset({"sync", "async"}),
        "input_modalities": frozenset({"text"}),
        "output_modalities": frozenset({"text"}),
        "response_formats": frozenset({"text", "json_schema"}),
        "capabilities": frozenset({"text_generation", "structured_output"}),
        "limits": {"max_context_tokens": 4096, "max_output_tokens": 512},
        "contract_digest": "0" * 64,
    }
    values.update(overrides)
    provisional = object.__new__(ExternalModelAdapterDescriptor)
    for key, value in values.items():
        object.__setattr__(provisional, key, value)
    from dynamic_agent_runner.external_adapter import canonical_descriptor_digest

    values["contract_digest"] = canonical_descriptor_digest(provisional)
    return ExternalModelAdapterDescriptor(**values)


def _write_plugin(root: Path) -> tuple[Path, object]:
    plugin = root / "plugin"
    plugin.mkdir()
    current = descriptor(
        adapter_id="registry.external",
        model_alias="registry-model",
        canonical_model_id="registry-canonical",
        execution_modes=frozenset({"sync"}),
    )
    module = f'''
from dynamic_agent_runner.external_adapter import (
    ExternalModelAdapterDescriptor,
    ExternalModelAdapterHealth,
)
from dynamic_agent_runner.openai_client import ModelResponse

class Adapter:
    adapter_id = "{current.adapter_id}"
    protocol_id = "dar.external-model.v1"
    protocol_version = "1.0"

    def describe(self):
        return ExternalModelAdapterDescriptor(
            adapter_id="{current.adapter_id}", provider_id="test",
            protocol_id="dar.external-model.v1", protocol_version="1.0",
            model_alias="{current.model_alias}",
            canonical_model_id="{current.canonical_model_id}",
            execution_location="local", execution_modes=frozenset({{"sync"}}),
            input_modalities=frozenset({{"text"}}), output_modalities=frozenset({{"text"}}),
            response_formats=frozenset({{"text", "json_schema"}}),
            capabilities=frozenset({{"text_generation", "structured_output"}}),
            limits={{"max_context_tokens": 4096, "max_output_tokens": 512}},
            contract_digest="{current.contract_digest}",
        )

    def health(self):
        return ExternalModelAdapterHealth(status="ready")

    def create_response(self, request):
        return ModelResponse(content="registry response")

def create_adapter():
    return Adapter()
'''
    (plugin / "registry_plugin.py").write_text(module, encoding="utf-8")
    manifest = {
        "manifest_version": 1,
        "adapter_id": current.adapter_id,
        "protocol_id": current.protocol_id,
        "protocol_version": current.protocol_version,
        "factory": "registry_plugin:create_adapter",
        "distribution_name": "test-registry-plugin",
        "distribution_version": "1.0.0",
        "descriptor": {
            "adapter_id": current.adapter_id,
            "provider_id": current.provider_id,
            "protocol_id": current.protocol_id,
            "protocol_version": current.protocol_version,
            "model_alias": current.model_alias,
            "canonical_model_id": current.canonical_model_id,
            "execution_location": current.execution_location,
            "execution_modes": sorted(current.execution_modes),
            "input_modalities": sorted(current.input_modalities),
            "output_modalities": sorted(current.output_modalities),
            "response_formats": sorted(current.response_formats),
            "capabilities": sorted(current.capabilities),
            "limits": dict(current.limits),
            "contract_digest": current.contract_digest,
        },
    }
    (plugin / "dar_external_adapter.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    return plugin, current


def test_registry_install_resolve_reload_and_remove(tmp_path: Path) -> None:
    plugin, current = _write_plugin(tmp_path)
    state = tmp_path / "state"
    registry = ExternalAdapterRegistry(state)

    receipt = registry.install(plugin)
    assert receipt.adapter_id == current.adapter_id
    assert registry.resolve(
        current.adapter_id,
        contract_digest=current.contract_digest,
        model_alias=current.model_alias,
        canonical_model_id=current.canonical_model_id,
    ).models == (current.model_alias,)
    assert (state / "external_adapters.json").stat().st_mode & 0o777 == 0o600

    reloaded = ExternalAdapterRegistry(state)
    assert [item.adapter_id for item in reloaded.list()] == [current.adapter_id]
    with pytest.raises(ExternalAdapterRegistryError):
        reloaded.resolve(
            current.adapter_id,
            contract_digest=current.contract_digest,
            model_alias="wrong",
            canonical_model_id=current.canonical_model_id,
        )

    reloaded.remove(current.adapter_id)
    assert reloaded.list() == ()
    assert (state / "external_adapters.json").exists()


def test_registry_reload_disables_changed_artifact(tmp_path: Path) -> None:
    plugin, current = _write_plugin(tmp_path)
    state = tmp_path / "state"
    registry = ExternalAdapterRegistry(state)
    registry.install(plugin)
    (plugin / "registry_plugin.py").write_text(
        (plugin / "registry_plugin.py").read_text(encoding="utf-8") + "\n# changed\n",
        encoding="utf-8",
    )

    reloaded = ExternalAdapterRegistry(state)

    assert reloaded.list() == ()
