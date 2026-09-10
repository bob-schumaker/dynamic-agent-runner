"""Generic sealed-artifact descriptor validation and ordered admission."""

from __future__ import annotations

import hashlib
import json
import re
import stat
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, SchemaError

from dynamic_agent_runner.workflow_host.capabilities import CapabilityRequirements
from dynamic_agent_runner.workflow_host.state import (
    OpaqueRecordError,
    PrivateStateStore,
)


_DIGEST = re.compile(r"[0-9a-f]{64}")
_NAME = re.compile(r"[a-z][a-z0-9_]{0,63}")
_MEDIA_TYPE = re.compile(r"[a-z0-9!#$&^_.+-]+/[a-z0-9!#$&^_.+-]+")
_MAX_INTEGER = 9007199254740991


class SealedArtifactRunnerDescriptorError(ValueError):
    """Raised when a sealed-artifact descriptor is not canonical or valid."""


class SealedArtifactRunnerAdmissionError(ValueError):
    """Raised when one admission boundary rejects an invocation."""


class SealedArtifactHandleError(ValueError):
    """Raised without disclosing private prepared artifact bytes."""


@dataclass(frozen=True)
class SealedArtifactRunnerDescriptor:
    """The validated public identity of one v1 sealed-artifact runner."""

    digest: str
    asset_path: str
    asset_digest: str
    capability_requirements_digest: str
    schema_assets: tuple["SealedArtifactSchemaAsset", ...]
    child_contract_digests: tuple[str, ...]
    callbacks: tuple["SealedArtifactCallback", ...]
    output_roles: tuple[str, ...]


@dataclass(frozen=True)
class SealedArtifactSchemaAsset:
    """One schema file bound by a runner descriptor."""

    path: str
    digest: str


@dataclass(frozen=True)
class SealedArtifactCallback:
    """One descriptor-bound callback and its child contract identity."""

    name: str
    requirement: str
    child_contract_digest: str


@dataclass(frozen=True)
class SealedArtifactHandle:
    """One receiver-private prepared artifact receipt."""

    handle_id: str
    expires_at: datetime


def parse_sealed_artifact_runner_descriptor(
    value: bytes,
) -> SealedArtifactRunnerDescriptor:
    """Parse and validate one canonical v1 sealed-artifact descriptor."""

    mapping = _canonical_mapping(value)
    _require_exact_keys(
        mapping,
        {
            "artifact_runner_digest",
            "asset",
            "callbacks",
            "capability_requirements_digest",
            "child_contract_digests",
            "format_version",
            "inputs",
            "limits",
            "outputs",
            "profile_digest",
            "schemas",
        },
    )
    if mapping["format_version"] != 1 or isinstance(mapping["format_version"], bool):
        _invalid()
    declared_digest = mapping["artifact_runner_digest"]
    _digest(declared_digest)
    unsigned = dict(mapping)
    del unsigned["artifact_runner_digest"]
    if hashlib.sha256(_canonical_bytes(unsigned)).hexdigest() != declared_digest:
        raise SealedArtifactRunnerDescriptorError("descriptor digest does not match")
    asset_path, asset_digest = _asset(mapping["asset"])
    capability_requirements_digest = _digest(mapping["capability_requirements_digest"])
    _digest(mapping["profile_digest"])
    schema_assets = _schemas(mapping["schemas"])
    schema_digests = frozenset(item.digest for item in schema_assets)
    _artifacts(mapping["inputs"], output=False, schema_digests=schema_digests)
    output_roles = _artifacts(
        mapping["outputs"], output=True, schema_digests=schema_digests
    )
    _limits(mapping["limits"])
    child_digests = _child_digests(mapping["child_contract_digests"])
    callbacks = _callbacks(mapping["callbacks"], child_digests)
    return SealedArtifactRunnerDescriptor(
        digest=declared_digest,
        asset_path=asset_path,
        asset_digest=asset_digest,
        capability_requirements_digest=capability_requirements_digest,
        schema_assets=schema_assets,
        child_contract_digests=child_digests,
        callbacks=callbacks,
        output_roles=output_roles,
    )


def verify_sealed_artifact_runner_files(
    root: Path, descriptor_bytes: bytes
) -> SealedArtifactRunnerDescriptor:
    """Verify descriptor-referenced asset and schema files below one package root."""

    descriptor = parse_sealed_artifact_runner_descriptor(descriptor_bytes)
    _file_digest(root, descriptor.asset_path, descriptor.asset_digest)
    for schema in descriptor.schema_assets:
        _validate_schema(_file_digest(root, schema.path, schema.digest))
    child_contracts = {
        digest: _child_contract_mapping(root, digest)
        for digest in descriptor.child_contract_digests
    }
    for callback in descriptor.callbacks:
        _validate_callback_child_contract(
            child_contracts[callback.child_contract_digest], callback
        )
    return descriptor


def validate_sealed_artifact_runner_capabilities(
    descriptor: SealedArtifactRunnerDescriptor,
    capability_requirements: CapabilityRequirements | None,
) -> None:
    """Require the descriptor's callbacks to match one sealed capability record."""

    if (
        not isinstance(capability_requirements, CapabilityRequirements)
        or descriptor.capability_requirements_digest != capability_requirements.digest
    ):
        raise SealedArtifactRunnerDescriptorError(
            "sealed artifact runner capabilities are invalid"
        )
    capability_ids = {
        item.capability_id for item in capability_requirements.required_capabilities
    }
    if any(
        callback.requirement not in capability_ids for callback in descriptor.callbacks
    ):
        raise SealedArtifactRunnerDescriptorError(
            "sealed artifact runner capabilities are invalid"
        )


class SealedArtifactRunnerAdmission:
    """Invoke one injected admission pipeline in the specified fail-closed order."""

    def __init__(
        self,
        *,
        provenance: Callable[..., object],
        package_verification: Callable[..., object],
        authorization: Callable[..., object],
        identity_resolution: Callable[..., object],
        handle_validation: Callable[..., object],
        collector_allocation: Callable[..., object],
        asset_execution: Callable[..., object],
    ) -> None:
        self._stages = (
            provenance,
            package_verification,
            authorization,
            identity_resolution,
            handle_validation,
            collector_allocation,
            asset_execution,
        )

    def run(self, *, invocation: object) -> object:
        """Run every boundary once, stopping before every later boundary on error."""

        current = invocation
        try:
            for stage in self._stages:
                current = stage(current)
        except Exception as error:
            raise SealedArtifactRunnerAdmissionError(
                "sealed artifact runner is unavailable"
            ) from error
        return current


class SealedArtifactHandleService:
    """Issue and atomically consume role-bound prepared artifact handles."""

    def __init__(self, *, store: PrivateStateStore, owner: str) -> None:
        if (
            not isinstance(store, PrivateStateStore)
            or not isinstance(owner, str)
            or not owner
        ):
            raise SealedArtifactHandleError("handle service is unavailable")
        self._store = store
        self._owner = owner

    def prepare(
        self,
        *,
        receiver_id: str,
        revision_digest: str,
        invocation_id: str,
        role: str,
        media_type: str,
        schema_digest: str | None,
        content: bytes,
        expires_at: datetime,
        now: datetime,
    ) -> SealedArtifactHandle:
        """Seal validated private bytes behind one opaque receiver-bound handle."""

        fields = _handle_fields(
            receiver_id=receiver_id,
            revision_digest=revision_digest,
            invocation_id=invocation_id,
            role=role,
            media_type=media_type,
            schema_digest=schema_digest,
        )
        if not isinstance(content, bytes):
            raise SealedArtifactHandleError("artifact handle is invalid")
        issued_at = _utc(now)
        expiry = _utc(expires_at)
        if expiry <= issued_at:
            raise SealedArtifactHandleError("artifact handle is invalid")
        payload = {
            **fields,
            "byte_count": len(content),
            "content": content.hex(),
            "content_digest": hashlib.sha256(content).hexdigest(),
        }
        try:
            handle_id = self._store.issue(
                kind="sealed_artifact_handle",
                owner=self._owner,
                payload=payload,
                expires_at=expiry,
                now=issued_at,
            )
        except OpaqueRecordError as error:
            raise SealedArtifactHandleError("artifact handle is unavailable") from error
        return SealedArtifactHandle(handle_id, expiry)

    def consume(
        self,
        handle_id: str,
        *,
        receiver_id: str,
        revision_digest: str,
        invocation_id: str,
        role: str,
        media_type: str,
        schema_digest: str | None,
        now: datetime,
    ) -> bytes:
        """Return matching bytes once, after immutable binding and digest checks."""

        fields = _handle_fields(
            receiver_id=receiver_id,
            revision_digest=revision_digest,
            invocation_id=invocation_id,
            role=role,
            media_type=media_type,
            schema_digest=schema_digest,
        )
        instant = _utc(now)
        try:
            record = self._store.load_state(
                handle_id,
                expected_kind="sealed_artifact_handle",
                owner=self._owner,
                expected_state="reserved",
                now=instant,
            )
        except OpaqueRecordError as error:
            raise SealedArtifactHandleError("artifact handle is unavailable") from error
        payload = record.payload
        if any(payload.get(name) != value for name, value in fields.items()):
            raise SealedArtifactHandleError("artifact handle does not match")
        try:
            record = self._store.transition(
                handle_id,
                expected_kind="sealed_artifact_handle",
                owner=self._owner,
                expected_state="reserved",
                new_state="consumed",
                now=instant,
            )
        except OpaqueRecordError as error:
            raise SealedArtifactHandleError("artifact handle is unavailable") from error
        return _handle_content(record.payload)

    def reserve(
        self,
        handle_id: str,
        *,
        receiver_id: str,
        revision_digest: str,
        invocation_id: str,
        role: str,
        media_type: str,
        schema_digest: str | None,
        now: datetime,
    ) -> None:
        """Atomically reserve one matching prepared handle without reading bytes."""

        fields = _handle_fields(
            receiver_id=receiver_id,
            revision_digest=revision_digest,
            invocation_id=invocation_id,
            role=role,
            media_type=media_type,
            schema_digest=schema_digest,
        )
        instant = _utc(now)
        try:
            record = self._store.load(
                handle_id,
                expected_kind="sealed_artifact_handle",
                owner=self._owner,
                now=instant,
            )
        except OpaqueRecordError as error:
            raise SealedArtifactHandleError("artifact handle is unavailable") from error
        if any(record.payload.get(name) != value for name, value in fields.items()):
            raise SealedArtifactHandleError("artifact handle does not match")
        try:
            self._store.transition(
                handle_id,
                expected_kind="sealed_artifact_handle",
                owner=self._owner,
                expected_state="active",
                new_state="reserved",
                now=instant,
            )
        except OpaqueRecordError as error:
            raise SealedArtifactHandleError("artifact handle is unavailable") from error

    def revoke(self, handle_id: str, *, now: datetime) -> None:
        """Irreversibly revoke one caller-owned handle."""

        try:
            self._store.revoke(handle_id, owner=self._owner, now=_utc(now))
        except OpaqueRecordError as error:
            raise SealedArtifactHandleError("artifact handle is unavailable") from error


def _canonical_mapping(value: bytes) -> dict[str, Any]:
    if not isinstance(value, bytes) or value.startswith(b"\xef\xbb\xbf"):
        _invalid()
    try:
        decoded = value.decode("utf-8")
        parsed = json.loads(decoded, object_pairs_hook=_no_duplicate_object)
    except (TypeError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SealedArtifactRunnerDescriptorError("descriptor is invalid") from error
    if not isinstance(parsed, dict) or _canonical_bytes(parsed) != value:
        _invalid()
    return parsed


def _no_duplicate_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, item in pairs:
        if key in result:
            raise SealedArtifactRunnerDescriptorError(
                "descriptor contains duplicate keys"
            )
        result[key] = item
    return result


def _canonical_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise SealedArtifactRunnerDescriptorError("descriptor is invalid") from error


def _asset(value: object) -> tuple[str, str]:
    mapping = _mapping(value)
    _require_exact_keys(mapping, {"abi_version", "entrypoint", "path", "sha256"})
    if mapping["abi_version"] != 1 or mapping["entrypoint"] != "run":
        _invalid()
    path = _path(mapping["path"])
    if not path.endswith(".py"):
        _invalid()
    return path, _digest(mapping["sha256"])


def _schemas(value: object) -> tuple[SealedArtifactSchemaAsset, ...]:
    items = _list(value)
    paths: list[str] = []
    assets: list[SealedArtifactSchemaAsset] = []
    for item in items:
        mapping = _mapping(item)
        _require_exact_keys(mapping, {"dialect", "path", "sha256"})
        if mapping["dialect"] != "json-schema-draft-2020-12":
            _invalid()
        path = _path(mapping["path"])
        paths.append(path)
        assets.append(SealedArtifactSchemaAsset(path, _digest(mapping["sha256"])))
    if paths != sorted(paths) or len(set(paths)) != len(paths):
        _invalid()
    if len({item.digest for item in assets}) != len(assets):
        _invalid()
    return tuple(assets)


def _artifacts(
    value: object, *, output: bool, schema_digests: frozenset[str]
) -> tuple[str, ...]:
    items = _list(value)
    if output and not items:
        _invalid()
    roles: list[str] = []
    keys = {"max_bytes", "media_type", "role", "schema_digest"}
    if not output:
        keys.add("required")
    for item in items:
        mapping = _mapping(item)
        _require_exact_keys(mapping, keys)
        role = _name(mapping["role"])
        media_type = _media_type(mapping["media_type"])
        schema = mapping["schema_digest"]
        if schema is not None:
            _digest(schema)
            if schema not in schema_digests or media_type != "application/json":
                _invalid()
        _positive(mapping["max_bytes"])
        if not output and not isinstance(mapping["required"], bool):
            _invalid()
        roles.append(role)
    if roles != sorted(roles) or len(set(roles)) != len(roles):
        _invalid()
    return tuple(roles)


def _limits(value: object) -> None:
    mapping = _mapping(value)
    _require_exact_keys(
        mapping,
        {
            "max_concurrency",
            "max_cpu_milliseconds",
            "max_io_bytes",
            "max_memory_bytes",
            "max_runtime_milliseconds",
        },
    )
    for item in mapping.values():
        _positive(item)


def _child_digests(value: object) -> tuple[str, ...]:
    items = tuple(_digest(item) for item in _list(value))
    if items != tuple(sorted(items)) or len(set(items)) != len(items):
        _invalid()
    return items


def _callbacks(
    value: object, child_digests: tuple[str, ...]
) -> tuple[SealedArtifactCallback, ...]:
    items = _list(value)
    names: list[str] = []
    callbacks: list[SealedArtifactCallback] = []
    keys = {
        "child_contract_digest",
        "max_calls",
        "max_concurrency",
        "max_request_bytes",
        "max_response_bytes",
        "max_total_request_bytes",
        "max_total_response_bytes",
        "name",
        "requirement",
        "timeout_milliseconds",
    }
    for item in items:
        mapping = _mapping(item)
        _require_exact_keys(mapping, keys)
        child = _digest(mapping["child_contract_digest"])
        if child not in child_digests or not isinstance(mapping["requirement"], str):
            _invalid()
        name = _name(mapping["name"])
        names.append(name)
        callbacks.append(
            SealedArtifactCallback(
                name=name,
                requirement=mapping["requirement"],  # type: ignore[arg-type]
                child_contract_digest=child,
            )
        )
        for key, item_value in mapping.items():
            if key not in {"child_contract_digest", "name", "requirement"}:
                _positive(item_value)
    if names != sorted(names) or len(set(names)) != len(names):
        _invalid()
    return tuple(callbacks)


def _mapping(value: object) -> Mapping[str, object]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        _invalid()
    return value


def _list(value: object) -> list[object]:
    if not isinstance(value, list):
        _invalid()
    return value


def _path(value: object) -> str:
    if not isinstance(value, str) or not value or value.startswith("/"):
        _invalid()
    parts = value.split("/")
    if any(not part or part in {".", ".."} for part in parts):
        _invalid()
    return value


def _name(value: object) -> str:
    if not isinstance(value, str) or not _NAME.fullmatch(value):
        _invalid()
    return value


def _media_type(value: object) -> str:
    if not isinstance(value, str) or not _MEDIA_TYPE.fullmatch(value):
        _invalid()
    return value


def _digest(value: object) -> str:
    if not isinstance(value, str) or not _DIGEST.fullmatch(value):
        _invalid()
    return value


def _positive(value: object) -> None:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or value <= 0
        or value > _MAX_INTEGER
    ):
        _invalid()


def _require_exact_keys(mapping: Mapping[str, object], keys: set[str]) -> None:
    if set(mapping) != keys:
        _invalid()


def _invalid() -> None:
    raise SealedArtifactRunnerDescriptorError("descriptor is invalid")


def _file_digest(root: Path, path: str, expected_digest: str) -> bytes:
    try:
        candidate = root.joinpath(*path.split("/"))
        metadata = candidate.lstat()
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            _invalid()
        content = candidate.read_bytes()
    except OSError as error:
        raise SealedArtifactRunnerDescriptorError(
            "sealed artifact runner file is unavailable"
        ) from error
    if hashlib.sha256(content).hexdigest() != expected_digest:
        raise SealedArtifactRunnerDescriptorError(
            "sealed artifact runner file is invalid"
        )
    return content


def _validate_schema(value: bytes) -> None:
    try:
        schema = json.loads(
            value.decode("utf-8"), object_pairs_hook=_no_duplicate_object
        )
        Draft202012Validator.check_schema(schema)
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        SchemaError,
        SealedArtifactRunnerDescriptorError,
    ) as error:
        raise SealedArtifactRunnerDescriptorError(
            "sealed artifact runner schema is invalid"
        ) from error


def _child_contract_mapping(root: Path, digest: str) -> Mapping[str, object]:
    matches: list[bytes] = []
    for candidate in root.rglob("*"):
        try:
            metadata = candidate.lstat()
            if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
                continue
            content = candidate.read_bytes()
        except OSError as error:
            raise SealedArtifactRunnerDescriptorError(
                "sealed artifact child contract is unavailable"
            ) from error
        if hashlib.sha256(content).hexdigest() == digest:
            matches.append(content)
    if len(matches) != 1:
        raise SealedArtifactRunnerDescriptorError(
            "sealed artifact child contract is unavailable"
        )
    try:
        return _canonical_mapping(matches[0])
    except SealedArtifactRunnerDescriptorError as error:
        raise SealedArtifactRunnerDescriptorError(
            "sealed artifact child contract is invalid"
        ) from error


def _validate_callback_child_contract(
    mapping: Mapping[str, object], callback: SealedArtifactCallback
) -> None:
    try:
        _require_exact_keys(
            mapping,
            {"body", "callback_name", "capability_requirement", "format_version"},
        )
        if (
            not isinstance(mapping["body"], dict)
            or mapping["format_version"] != 1
            or mapping["callback_name"] != callback.name
            or mapping["capability_requirement"] != callback.requirement
        ):
            _invalid()
    except SealedArtifactRunnerDescriptorError as error:
        raise SealedArtifactRunnerDescriptorError(
            "sealed artifact child contract is invalid"
        ) from error


def _handle_fields(
    *,
    receiver_id: object,
    revision_digest: object,
    invocation_id: object,
    role: object,
    media_type: object,
    schema_digest: object,
) -> dict[str, str | None]:
    if not isinstance(receiver_id, str) or not receiver_id:
        raise SealedArtifactHandleError("artifact handle is invalid")
    if not isinstance(invocation_id, str) or not invocation_id:
        raise SealedArtifactHandleError("artifact handle is invalid")
    try:
        revision = _digest(revision_digest)
        name = _name(role)
        media = _media_type(media_type)
        if schema_digest is not None:
            _digest(schema_digest)
    except SealedArtifactRunnerDescriptorError as error:
        raise SealedArtifactHandleError("artifact handle is invalid") from error
    return {
        "receiver_id": receiver_id,
        "revision_digest": revision,
        "invocation_id": invocation_id,
        "role": name,
        "media_type": media,
        "schema_digest": schema_digest,
    }


def _handle_content(payload: Mapping[str, object]) -> bytes:
    expected = {
        "receiver_id",
        "revision_digest",
        "invocation_id",
        "role",
        "media_type",
        "schema_digest",
        "byte_count",
        "content",
        "content_digest",
    }
    if set(payload) != expected or not isinstance(payload.get("content"), str):
        raise SealedArtifactHandleError("artifact handle is unavailable")
    try:
        content = bytes.fromhex(payload["content"])
    except ValueError as error:
        raise SealedArtifactHandleError("artifact handle is unavailable") from error
    if (
        payload.get("byte_count") != len(content)
        or payload.get("content_digest") != hashlib.sha256(content).hexdigest()
    ):
        raise SealedArtifactHandleError("artifact handle is unavailable")
    return content


def _utc(value: object) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise SealedArtifactHandleError("artifact handle is invalid")
    return value.astimezone(UTC)
