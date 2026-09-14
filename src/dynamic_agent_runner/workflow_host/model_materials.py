"""Canonical sealed model-material lock values with no runtime dependencies."""

from __future__ import annotations

import hashlib
import json
import unicodedata
from dataclasses import dataclass
from typing import Mapping


class ModelMaterialsError(ValueError):
    """Raised when a sealed model-material declaration is invalid."""


@dataclass(frozen=True)
class MaterialContract:
    """One exact public runner or loader-profile contract reference."""

    contract_id: str
    version: str

    def __post_init__(self) -> None:
        _text(self.contract_id, "contract id")
        _text(self.version, "contract version")

    def to_mapping(self) -> dict[str, str]:
        return {"id": self.contract_id, "version": self.version}


@dataclass(frozen=True)
class ExecutionDescriptorReference:
    """One v2 lock reference to its ABI-neutral sealed descriptor asset."""

    filename: str
    sha256: str

    def __post_init__(self) -> None:
        if self.filename != "execution-descriptor.json":
            raise ModelMaterialsError("execution descriptor filename is invalid")
        _hex(self.sha256, 64, "execution descriptor sha256")

    def to_mapping(self) -> dict[str, str]:
        return {"filename": self.filename, "sha256": self.sha256}


@dataclass(frozen=True)
class ModelMaterialSource:
    """One exact Hugging Face file dependency."""

    role: str
    group: str
    repository: str
    revision: str
    filename: str
    sha256: str

    def __post_init__(self) -> None:
        for name, value in (
            ("source role", self.role),
            ("source group", self.group),
            ("source repository", self.repository),
            ("source filename", self.filename),
        ):
            _text(value, name)
        _hex(self.revision, 40, "source revision")
        _hex(self.sha256, 64, "source sha256")

    def to_mapping(self) -> dict[str, str]:
        return {
            "role": self.role,
            "group": self.group,
            "source_type": "huggingface_file",
            "repository": self.repository,
            "revision": self.revision,
            "filename": self.filename,
            "sha256": self.sha256,
        }


@dataclass(frozen=True)
class MaterialOutput:
    """One lock-declared generated artifact."""

    role: str
    group: str
    filename: str
    sha256: str

    def __post_init__(self) -> None:
        _text(self.role, "output role")
        _text(self.group, "output group")
        _text(self.filename, "output filename")
        _hex(self.sha256, 64, "output sha256")

    def to_mapping(self) -> dict[str, str]:
        return {
            "role": self.role,
            "group": self.group,
            "filename": self.filename,
            "sha256": self.sha256,
        }


@dataclass(frozen=True)
class PreparationOperation:
    """One deterministic capability-selected material transformation."""

    capability_id: str
    contract_version: str
    contract_digest: str
    inputs: tuple[str, ...]
    output: MaterialOutput
    transformation_digest: str

    def __post_init__(self) -> None:
        _text(self.capability_id, "preparation capability id")
        _text(self.contract_version, "preparation contract version")
        _hex(self.contract_digest, 64, "preparation contract digest")
        if not self.inputs or any(
            not isinstance(value, str) or not value for value in self.inputs
        ):
            raise ModelMaterialsError("preparation inputs are invalid")
        if len(set(self.inputs)) != len(self.inputs):
            raise ModelMaterialsError("preparation inputs are invalid")
        _hex(self.transformation_digest, 64, "transformation digest")
        if self.transformation_digest != transformation_digest(self.to_mapping()):
            raise ModelMaterialsError("transformation digest does not match")

    def to_mapping(self) -> dict[str, object]:
        return {
            "capability_id": self.capability_id,
            "contract_version": self.contract_version,
            "contract_digest": self.contract_digest,
            "inputs": list(self.inputs),
            "output": self.output.to_mapping(),
            "transformation_digest": self.transformation_digest,
        }


@dataclass(frozen=True)
class ModelDependencyLock:
    """The complete canonical dependency declaration for one model binding."""

    logical_model_id: str
    runner_contract: MaterialContract
    loader_profile_contract: MaterialContract | None
    sources: tuple[ModelMaterialSource, ...]
    preparation: tuple[PreparationOperation, ...]
    execution_descriptor: ExecutionDescriptorReference | None = None
    format_version: int = 1

    def __post_init__(self) -> None:
        if not _has_valid_execution_identity(self):
            raise ModelMaterialsError("model-material execution identity is invalid")
        _text(self.logical_model_id, "logical model id")
        if not self.sources:
            raise ModelMaterialsError("model-material sources are required")
        roles = tuple(source.role for source in self.sources)
        if roles != tuple(sorted(roles)) or len(set(roles)) != len(roles):
            raise ModelMaterialsError("model-material source roles are invalid")
        known_roles = set(roles)
        output_roles: list[str] = []
        for operation in self.preparation:
            if any(role not in known_roles for role in operation.inputs):
                raise ModelMaterialsError("preparation input role is unavailable")
            if operation.output.role in known_roles:
                raise ModelMaterialsError("preparation output role is invalid")
            known_roles.add(operation.output.role)
            output_roles.append(operation.output.role)
        consumed = {role for operation in self.preparation for role in operation.inputs}
        if any(role not in consumed for role in output_roles[:-1]):
            raise ModelMaterialsError("preparation output role is orphaned")
        object.__setattr__(self, "sources", tuple(self.sources))
        object.__setattr__(self, "preparation", tuple(self.preparation))

    @property
    def canonical_bytes(self) -> bytes:
        value: dict[str, object] = {
            "format_version": self.format_version,
            "logical_model_id": self.logical_model_id,
            "runner_contract": self.runner_contract.to_mapping(),
            "sources": [source.to_mapping() for source in self.sources],
            "preparation": [item.to_mapping() for item in self.preparation],
        }
        if self.format_version == 1:
            assert self.loader_profile_contract is not None
            value["loader_profile_contract"] = self.loader_profile_contract.to_mapping()
        else:
            assert self.execution_descriptor is not None
            value["execution_descriptor"] = self.execution_descriptor.to_mapping()
        return _canonical_json(value)

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.canonical_bytes).hexdigest()


def parse_model_dependency_lock(value: object) -> ModelDependencyLock:
    """Parse a strict v1 or v2 mapping or JSON byte payload into a canonical lock."""

    mapping = _mapping(value)
    format_version = _format_version(mapping.get("format_version"))
    execution_field = (
        "loader_profile_contract" if format_version == 1 else "execution_descriptor"
    )
    if format_version not in (1, 2) or set(mapping) != {
        "format_version",
        "logical_model_id",
        "runner_contract",
        execution_field,
        "sources",
        "preparation",
    }:
        raise ModelMaterialsError("model-material lock fields are invalid")
    sources_value = mapping["sources"]
    preparation_value = mapping["preparation"]
    if not isinstance(sources_value, list) or not isinstance(preparation_value, list):
        raise ModelMaterialsError("model-material sources or preparation are invalid")
    return ModelDependencyLock(
        logical_model_id=_required_text(
            mapping["logical_model_id"], "logical model id"
        ),
        runner_contract=_contract(mapping["runner_contract"], "runner contract"),
        loader_profile_contract=(
            _contract(mapping["loader_profile_contract"], "loader profile contract")
            if format_version == 1
            else None
        ),
        sources=tuple(_source(item) for item in sources_value),
        preparation=tuple(_operation(item) for item in preparation_value),
        execution_descriptor=(
            _execution_descriptor(mapping["execution_descriptor"])
            if format_version == 2
            else None
        ),
        format_version=format_version,
    )


def transformation_digest(value: Mapping[str, object]) -> str:
    """Return the digest of a transformation record excluding its own digest."""

    record = dict(value)
    record.pop("transformation_digest", None)
    return hashlib.sha256(_canonical_json(record)).hexdigest()


def _mapping(value: object) -> Mapping[str, object]:
    if isinstance(value, bytes):
        if value.startswith(b"\xef\xbb\xbf"):
            raise ModelMaterialsError(
                "model-material JSON must not contain a byte-order mark"
            )
        try:
            value = json.loads(value.decode("utf-8"), object_pairs_hook=_unique_object)
        except (UnicodeDecodeError, json.JSONDecodeError, ModelMaterialsError) as error:
            raise ModelMaterialsError("model-material JSON is invalid") from error
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        raise ModelMaterialsError("model-material lock is invalid")
    return value


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, item in pairs:
        if key in result:
            raise ModelMaterialsError("model-material JSON contains duplicate keys")
        result[key] = item
    return result


def _contract(value: object, name: str) -> MaterialContract:
    if not isinstance(value, Mapping) or set(value) != {"id", "version"}:
        raise ModelMaterialsError(f"{name} is invalid")
    return MaterialContract(
        _required_text(value["id"], name), _required_text(value["version"], name)
    )


def _execution_descriptor(value: object) -> ExecutionDescriptorReference:
    if not isinstance(value, Mapping) or set(value) != {"filename", "sha256"}:
        raise ModelMaterialsError("execution descriptor is invalid")
    return ExecutionDescriptorReference(
        _required_text(value["filename"], "execution descriptor filename"),
        _required_text(value["sha256"], "execution descriptor sha256"),
    )


def _has_valid_execution_identity(lock: ModelDependencyLock) -> bool:
    return (
        lock.format_version == 1
        and lock.loader_profile_contract is not None
        and lock.execution_descriptor is None
    ) or (
        lock.format_version == 2
        and lock.loader_profile_contract is None
        and lock.execution_descriptor is not None
    )


def _source(value: object) -> ModelMaterialSource:
    if (
        not isinstance(value, Mapping)
        or set(value)
        != {
            "role",
            "group",
            "source_type",
            "repository",
            "revision",
            "filename",
            "sha256",
        }
        or value.get("source_type") != "huggingface_file"
    ):
        raise ModelMaterialsError("model-material source is invalid")
    return ModelMaterialSource(
        _required_text(value["role"], "source role"),
        _required_text(value["group"], "source group"),
        _required_text(value["repository"], "source repository"),
        _required_text(value["revision"], "source revision"),
        _required_text(value["filename"], "source filename"),
        _required_text(value["sha256"], "source sha256"),
    )


def _operation(value: object) -> PreparationOperation:
    if (
        not isinstance(value, Mapping)
        or set(value)
        != {
            "capability_id",
            "contract_version",
            "contract_digest",
            "inputs",
            "output",
            "transformation_digest",
        }
        or not isinstance(value["inputs"], list)
    ):
        raise ModelMaterialsError("preparation operation is invalid")
    output = value["output"]
    if not isinstance(output, Mapping) or set(output) != {
        "role",
        "group",
        "filename",
        "sha256",
    }:
        raise ModelMaterialsError("preparation output is invalid")
    return PreparationOperation(
        _required_text(value["capability_id"], "preparation capability id"),
        _required_text(value["contract_version"], "preparation contract version"),
        _required_text(value["contract_digest"], "preparation contract digest"),
        tuple(_required_text(item, "preparation input") for item in value["inputs"]),
        MaterialOutput(
            _required_text(output["role"], "output role"),
            _required_text(output["group"], "output group"),
            _required_text(output["filename"], "output filename"),
            _required_text(output["sha256"], "output sha256"),
        ),
        _required_text(value["transformation_digest"], "transformation digest"),
    )


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        _normalize(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _normalize(value: object) -> object:
    if isinstance(value, str):
        _text(value, "model-material value")
        return value
    if isinstance(value, Mapping):
        return {str(key): _normalize(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_normalize(item) for item in value]
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    raise ModelMaterialsError("model-material canonical JSON value is invalid")


def _format_version(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ModelMaterialsError("model-material format_version is invalid")
    return value


def _required_text(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise ModelMaterialsError(f"{name} is invalid")
    _text(value, name)
    return value


def _text(value: str, name: str) -> None:
    if not value or unicodedata.normalize("NFC", value) != value:
        raise ModelMaterialsError(f"{name} is invalid")


def _hex(value: str, length: int, name: str) -> None:
    if len(value) != length or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise ModelMaterialsError(f"{name} is invalid")
