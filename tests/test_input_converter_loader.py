"""Fake-only tests for manifest-bound workflow input converter loading."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path

import pytest

from dynamic_agent_runner.workflow_host.descriptor import DeclaredInputConverter


def _converter(asset: Path) -> DeclaredInputConverter:
    return DeclaredInputConverter(
        converter_id="converter-v1",
        converter_contract_version="v1",
        compatible_runner_contract_id="transformers-generate-v1",
        entrypoint=asset.name,
        asset_digest=sha256(asset.read_bytes()).hexdigest(),
        max_input_bytes=1024,
        max_output_bytes=1024,
        timeout_seconds=1,
    )


def test_loader_uses_only_the_manifest_bound_entrypoint(tmp_path: Path) -> None:
    from dynamic_agent_runner.workflow_host.input_converter_loader import (
        load_input_converter,
    )

    asset = tmp_path / "converter.py"
    asset.write_text(
        "converter_contract_version = 'v1'\n"
        "compatible_runner_contract_id = 'transformers-generate-v1'\n"
        "class Converter:\n"
        "    def pack(self, *, prompt, payload, context):\n"
        "        return context.pack({'prompt': prompt, 'payload': payload})\n"
        "converter = Converter\n",
        encoding="utf-8",
    )
    alternate = tmp_path / "alternate.py"
    alternate.write_text(
        "converter_contract_version = 'v1'\n"
        "compatible_runner_contract_id = 'transformers-generate-v1'\n"
        "converter = object()\n",
        encoding="utf-8",
    )

    loaded = load_input_converter(package_root=tmp_path, converter=_converter(asset))

    assert type(loaded).__name__ == "Converter"
    assert alternate.exists()


@pytest.mark.parametrize(
    "source",
    [
        "compatible_runner_contract_id = 'transformers-generate-v1'\nconverter = object()\n",
        "converter_contract_version = 'v1'\nconverter = object()\n",
        "converter_contract_version = 'v1'\n"
        "compatible_runner_contract_id = 'transformers-generate-v1'\n"
        "def pack(*_args, **_kwargs): pass\n",
        "converter_contract_version = 'v1'\n"
        "compatible_runner_contract_id = 'different-runner'\n"
        "converter = object()\n",
    ],
)
def test_loader_rejects_missing_contract_attributes_or_converter_object(
    tmp_path: Path, source: str
) -> None:
    from dynamic_agent_runner.workflow_host.input_converter_loader import (
        InputConverterLoadError,
        load_input_converter,
    )

    asset = tmp_path / "converter.py"
    asset.write_text(source, encoding="utf-8")

    with pytest.raises(InputConverterLoadError, match="input converter package"):
        load_input_converter(package_root=tmp_path, converter=_converter(asset))


def test_loader_rejects_a_stale_manifest_bound_asset(tmp_path: Path) -> None:
    from dynamic_agent_runner.workflow_host.input_converter_loader import (
        InputConverterLoadError,
        load_input_converter,
    )

    asset = tmp_path / "converter.py"
    asset.write_text(
        "converter_contract_version = 'v1'\n"
        "compatible_runner_contract_id = 'transformers-generate-v1'\n"
        "converter = object()\n",
        encoding="utf-8",
    )
    converter = _converter(asset)
    asset.write_text("converter = object()\n", encoding="utf-8")

    with pytest.raises(InputConverterLoadError, match="input converter package"):
        load_input_converter(package_root=tmp_path, converter=converter)
