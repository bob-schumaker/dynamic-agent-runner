"""Receiver-owned lifecycle for explicitly approved external adapters."""

from __future__ import annotations

from dataclasses import dataclass
from contextlib import contextmanager
import hashlib
import importlib.util
import json
from pathlib import Path
import os
import secrets
import sys
import tempfile
from types import ModuleType
from typing import Any, Callable
import zipfile

from dynamic_agent_runner.external_adapter import (
    ExternalAdapterError,
    ExternalModelAdapterDescriptor,
    ExternalModelAdapterFacade,
    DARExternalAdapterProtocol,
)


class ExternalAdapterRegistryError(ExternalAdapterError):
    """Raised when an external adapter cannot be installed or resolved."""


@dataclass(frozen=True)
class ExternalAdapterReceipt:
    adapter_id: str
    protocol_id: str
    protocol_version: str
    descriptor_digest: str
    artifact_digest: str
    artifact_locator: str
    factory_reference: str
    distribution_name: str
    distribution_version: str
    trusted_origin: str

    def to_mapping(self) -> dict[str, str]:
        return {
            "adapter_id": self.adapter_id,
            "protocol_id": self.protocol_id,
            "protocol_version": self.protocol_version,
            "descriptor_digest": self.descriptor_digest,
            "artifact_digest": self.artifact_digest,
            "artifact_locator": self.artifact_locator,
            "factory_reference": self.factory_reference,
            "distribution_name": self.distribution_name,
            "distribution_version": self.distribution_version,
            "trusted_origin": self.trusted_origin,
        }


@dataclass(frozen=True)
class InstalledExternalAdapter:
    receipt: ExternalAdapterReceipt
    facade: ExternalModelAdapterFacade


class ExternalAdapterRegistry:
    """Manage explicitly installed adapters without discovery or fallback."""

    _STATE_FILENAME = "external_adapters.json"

    def __init__(self, state_root: str | Path, *, load: bool = True) -> None:
        self.state_root = Path(state_root)
        self._state_path = self.state_root / self._STATE_FILENAME
        self._installed: dict[str, InstalledExternalAdapter] = {}
        if load:
            self.reload()

    def install(self, approved_local_plugin: str | Path) -> ExternalAdapterReceipt:
        source = Path(approved_local_plugin).expanduser().resolve()
        with _materialize_plugin(source) as (
            manifest_path,
            artifact_root,
            artifact_locator,
            digest_path,
        ):
            manifest = _read_static_manifest(manifest_path)
            _validate_static_manifest(manifest)
            artifact_digest = _artifact_digest(digest_path)
            expected_digest = manifest.get("artifact_digest")
            if expected_digest is not None and expected_digest != artifact_digest:
                raise ExternalAdapterRegistryError(
                    "external adapter artifact digest mismatch"
                )
            factory_reference = str(manifest["factory"])
            module, factory = _load_factory(artifact_root, factory_reference)
            try:
                adapter = factory()
                facade = ExternalModelAdapterFacade(adapter)
            except Exception as error:  # noqa: BLE001 - plugin boundary is redacted.
                raise ExternalAdapterRegistryError(
                    "external adapter factory is invalid"
                ) from error
            descriptor = facade.descriptor
            _validate_manifest_descriptor(manifest, descriptor)
            if descriptor.adapter_id in self._installed:
                raise ExternalAdapterRegistryError(
                    "external adapter is already installed"
                )
            receipt = ExternalAdapterReceipt(
                adapter_id=descriptor.adapter_id,
                protocol_id=descriptor.protocol_id,
                protocol_version=descriptor.protocol_version,
                descriptor_digest=descriptor.contract_digest,
                artifact_digest=artifact_digest,
                artifact_locator=str(artifact_locator),
                factory_reference=factory_reference,
                distribution_name=str(manifest["distribution_name"]),
                distribution_version=str(manifest["distribution_version"]),
                trusted_origin="local-approved-path",
            )
            self._write_receipts(
                {**self._receipts(), descriptor.adapter_id: receipt.to_mapping()}
            )
            self._installed[descriptor.adapter_id] = InstalledExternalAdapter(
                receipt, facade
            )
            del module
            return receipt

    def remove(self, adapter_id: str) -> None:
        if adapter_id not in self._installed:
            raise ExternalAdapterRegistryError("external adapter is not installed")
        installed = dict(self._installed)
        removed = installed.pop(adapter_id)
        removed.facade.revoke()
        self._write_receipts(
            {key: value.receipt.to_mapping() for key, value in installed.items()}
        )
        self._installed = installed

    def list(self) -> tuple[ExternalAdapterReceipt, ...]:
        return tuple(item.receipt for item in self._installed.values())

    def resolve(
        self,
        adapter_id: str,
        *,
        contract_digest: str,
        model_alias: str,
        canonical_model_id: str,
    ) -> ExternalModelAdapterFacade:
        installed = self._installed.get(adapter_id)
        if installed is None:
            raise ExternalAdapterRegistryError("external adapter is not installed")
        descriptor = installed.facade.descriptor
        if (
            descriptor.contract_digest != contract_digest
            or descriptor.model_alias != model_alias
            or descriptor.canonical_model_id != canonical_model_id
        ):
            raise ExternalAdapterRegistryError(
                "external adapter identity tuple mismatch"
            )
        return installed.facade

    def select(self, adapter_id: str) -> ExternalModelAdapterFacade:
        installed = self._installed.get(adapter_id)
        if installed is None:
            raise ExternalAdapterRegistryError("external adapter is not installed")
        return installed.facade

    def reload(self) -> None:
        self._installed = {}
        if not self._state_path.exists():
            return
        try:
            raw = json.loads(self._state_path.read_text(encoding="utf-8"))
            records = raw["adapters"]
            if not isinstance(records, list):
                raise ValueError
        except Exception as error:  # noqa: BLE001 - state is untrusted input.
            raise ExternalAdapterRegistryError(
                "external adapter state is invalid"
            ) from error
        loaded: dict[str, InstalledExternalAdapter] = {}
        for record in records:
            receipt = _receipt_from_mapping(record)
            try:
                with _materialize_plugin(Path(receipt.artifact_locator)) as (
                    manifest_path,
                    resolved_root,
                    _locator,
                    digest_path,
                ):
                    manifest = _read_static_manifest(manifest_path)
                    _validate_static_manifest(manifest)
                    if _artifact_digest(digest_path) != receipt.artifact_digest:
                        raise ValueError
                    if str(manifest["factory"]) != receipt.factory_reference:
                        raise ValueError
                    _validate_manifest_receipt(manifest, receipt)
                    _module, factory = _load_factory(
                        resolved_root, receipt.factory_reference
                    )
                    facade = ExternalModelAdapterFacade(factory())
                    if facade.descriptor.contract_digest != receipt.descriptor_digest:
                        raise ValueError
                    loaded[receipt.adapter_id] = InstalledExternalAdapter(
                        receipt, facade
                    )
            except Exception:
                continue
        self._installed = loaded

    def _receipts(self) -> dict[str, dict[str, str]]:
        return {
            key: value.receipt.to_mapping() for key, value in self._installed.items()
        }

    def _write_receipts(self, receipts: dict[str, dict[str, str]]) -> None:
        self.state_root.mkdir(parents=True, exist_ok=True)
        os.chmod(self.state_root, 0o700)
        payload = json.dumps(
            {"format_version": 1, "adapters": list(receipts.values())},
            sort_keys=True,
            indent=2,
        )
        temporary = self._state_path.with_name(
            f".{self._STATE_FILENAME}.{secrets.token_hex(8)}.tmp"
        )
        try:
            temporary.write_text(payload + "\n", encoding="utf-8")
            os.chmod(temporary, 0o600)
            os.replace(temporary, self._state_path)
            os.chmod(self._state_path, 0o600)
        except Exception as error:  # noqa: BLE001 - filesystem boundary.
            try:
                temporary.unlink()
            except OSError:
                pass
            raise ExternalAdapterRegistryError(
                "external adapter state update failed"
            ) from error


@contextmanager
def _materialize_plugin(source: Path):
    source = source.resolve()
    if source.is_file() and source.name == "dar_external_adapter.json":
        yield source, source.parent, source.parent, source.parent
        return
    if source.is_dir():
        manifest = source / "dar_external_adapter.json"
        if manifest.is_file():
            yield manifest, source, source, source
            return
    if source.is_file() and source.suffix == ".whl":
        with tempfile.TemporaryDirectory(prefix="dar-external-adapter-") as temporary:
            root = Path(temporary)
            try:
                with zipfile.ZipFile(source) as archive:
                    for member in archive.infolist():
                        member_path = Path(member.filename)
                        if member_path.is_absolute() or ".." in member_path.parts:
                            raise ValueError
                        archive.extract(member, root)
            except Exception as error:  # noqa: BLE001 - artifact is untrusted.
                raise ExternalAdapterRegistryError(
                    "external adapter artifact is invalid"
                ) from error
            manifest = root / "dar_external_adapter.json"
            if not manifest.is_file():
                raise ExternalAdapterRegistryError(
                    "approved local plugin manifest is missing"
                )
            yield manifest, root, source, source
            return
    raise ExternalAdapterRegistryError("approved local plugin manifest is missing")


def _read_static_manifest(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception as error:  # noqa: BLE001 - static plugin metadata is untrusted.
        raise ExternalAdapterRegistryError(
            "external adapter manifest is invalid"
        ) from error
    if not isinstance(value, dict):
        raise ExternalAdapterRegistryError("external adapter manifest is invalid")
    return value


def _validate_static_manifest(manifest: dict[str, Any]) -> None:
    required = {
        "manifest_version",
        "adapter_id",
        "protocol_id",
        "protocol_version",
        "factory",
        "distribution_name",
        "distribution_version",
        "descriptor",
    }
    if not required.issubset(manifest) or manifest["manifest_version"] != 1:
        raise ExternalAdapterRegistryError("external adapter manifest is unsupported")
    if (
        manifest["protocol_id"] != "dar.external-model.v1"
        or manifest["protocol_version"] != "1.0"
    ):
        raise ExternalAdapterRegistryError(
            "external adapter manifest protocol mismatch"
        )
    if not isinstance(manifest["factory"], str) or ":" not in manifest["factory"]:
        raise ExternalAdapterRegistryError(
            "external adapter factory reference is invalid"
        )
    try:
        _descriptor_from_manifest(manifest)
    except Exception as error:  # noqa: BLE001 - static metadata is untrusted.
        raise ExternalAdapterRegistryError(
            "external adapter descriptor metadata is invalid"
        ) from error


def _descriptor_from_manifest(
    manifest: dict[str, Any],
) -> ExternalModelAdapterDescriptor:
    value = manifest["descriptor"]
    if not isinstance(value, dict):
        raise ValueError
    return ExternalModelAdapterDescriptor(
        adapter_id=str(value["adapter_id"]),
        provider_id=str(value["provider_id"]),
        protocol_id=value["protocol_id"],
        protocol_version=value["protocol_version"],
        model_alias=str(value["model_alias"]),
        canonical_model_id=str(value["canonical_model_id"]),
        execution_location=value["execution_location"],
        execution_modes=frozenset(value["execution_modes"]),
        input_modalities=frozenset(value["input_modalities"]),
        output_modalities=frozenset(value["output_modalities"]),
        response_formats=frozenset(value["response_formats"]),
        capabilities=frozenset(value["capabilities"]),
        limits=dict(value["limits"]),
        contract_digest=str(value["contract_digest"]),
    )


def _validate_manifest_descriptor(
    manifest: dict[str, Any], descriptor: ExternalModelAdapterDescriptor
) -> None:
    if descriptor.adapter_id != manifest["adapter_id"]:
        raise ExternalAdapterRegistryError("manifest adapter identity mismatch")
    static = _descriptor_from_manifest(manifest)
    if static != descriptor:
        raise ExternalAdapterRegistryError("manifest descriptor digest mismatch")


def _validate_manifest_receipt(
    manifest: dict[str, Any], receipt: ExternalAdapterReceipt
) -> None:
    if (
        manifest.get("adapter_id") != receipt.adapter_id
        or manifest.get("protocol_id") != receipt.protocol_id
        or manifest.get("protocol_version") != receipt.protocol_version
        or manifest.get("distribution_name") != receipt.distribution_name
        or manifest.get("distribution_version") != receipt.distribution_version
    ):
        raise ValueError


def _receipt_from_mapping(value: object) -> ExternalAdapterReceipt:
    if not isinstance(value, dict):
        raise ValueError
    fields = (
        "adapter_id",
        "protocol_id",
        "protocol_version",
        "descriptor_digest",
        "artifact_digest",
        "artifact_locator",
        "factory_reference",
        "distribution_name",
        "distribution_version",
        "trusted_origin",
    )
    if any(
        not isinstance(value.get(field), str) or not value[field] for field in fields
    ):
        raise ValueError
    return ExternalAdapterReceipt(**{field: value[field] for field in fields})


def _artifact_digest(path: Path) -> str:
    digest = hashlib.sha256()
    if path.is_file():
        digest.update(path.read_bytes())
        return digest.hexdigest()
    for child in sorted(path.rglob("*")):
        if (
            not child.is_file()
            or "__pycache__" in child.parts
            or child.suffix == ".pyc"
        ):
            continue
        relative = child.relative_to(path).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        content = child.read_bytes()
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()


def _load_factory(
    root: Path, reference: str
) -> tuple[ModuleType, Callable[[], DARExternalAdapterProtocol]]:
    module_name, separator, function_name = reference.partition(":")
    if not separator or not module_name or not function_name:
        raise ExternalAdapterRegistryError(
            "external adapter factory reference is invalid"
        )
    module_path = root / (module_name.replace(".", "/") + ".py")
    if not module_path.is_file():
        module_path = root / module_name.replace(".", "/") / "__init__.py"
    if not module_path.is_file():
        raise ExternalAdapterRegistryError("external adapter factory module is missing")
    unique_name = f"_dar_external_adapter_{hashlib.sha256(str(module_path).encode()).hexdigest()[:16]}"
    spec = importlib.util.spec_from_file_location(unique_name, module_path)
    if spec is None or spec.loader is None:
        raise ExternalAdapterRegistryError("external adapter factory cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[unique_name] = module
    spec.loader.exec_module(module)
    factory = getattr(module, function_name, None)
    if not callable(factory):
        raise ExternalAdapterRegistryError("external adapter factory is missing")
    return module, factory


__all__ = [
    "ExternalAdapterReceipt",
    "ExternalAdapterRegistry",
    "ExternalAdapterRegistryError",
    "InstalledExternalAdapter",
]
