"""Load one digest-bound workflow input converter package entry point."""

from __future__ import annotations

import hashlib
import importlib.util
import os
import stat
from pathlib import Path
from types import ModuleType

from dynamic_agent_runner.workflow_host.descriptor import DeclaredInputConverter


class InputConverterLoadError(ValueError):
    """Raised when a manifest-bound converter package cannot be loaded."""


def load_input_converter(
    *, package_root: Path, converter: DeclaredInputConverter
) -> object:
    """Return only the exact package entry point declared by the manifest."""

    asset = _validated_asset(package_root, converter)
    module = _load_module(asset, converter.asset_digest)
    if (
        getattr(module, "converter_contract_version", None)
        != converter.converter_contract_version
        or getattr(module, "compatible_runner_contract_id", None)
        != converter.compatible_runner_contract_id
    ):
        raise InputConverterLoadError("input converter package is invalid")
    candidate = getattr(module, "converter", None)
    if isinstance(candidate, type):
        try:
            candidate = candidate()
        except Exception as error:  # noqa: BLE001 - package constructors vary.
            raise InputConverterLoadError(
                "input converter package is invalid"
            ) from error
    if not callable(getattr(candidate, "pack", None)):
        raise InputConverterLoadError("input converter package is invalid")
    return candidate


def _validated_asset(package_root: Path, converter: DeclaredInputConverter) -> Path:
    try:
        root = package_root.resolve(strict=True)
        asset = (root / converter.entrypoint).resolve(strict=True)
        asset.relative_to(root)
        metadata = os.lstat(asset)
        content = asset.read_bytes()
    except (OSError, ValueError) as error:
        raise InputConverterLoadError(
            "input converter package is unavailable"
        ) from error
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
        or hashlib.sha256(content).hexdigest() != converter.asset_digest
    ):
        raise InputConverterLoadError("input converter package is unavailable")
    return asset


def _load_module(asset: Path, digest: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(f"_dar_converter_{digest}", asset)
    if spec is None or spec.loader is None:
        raise InputConverterLoadError("input converter package is unavailable")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as error:  # noqa: BLE001 - package import failures vary.
        raise InputConverterLoadError("input converter package is invalid") from error
    return module
