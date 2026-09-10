"""Generic sealed-artifact descriptor validation and ordered admission."""

from __future__ import annotations

import hashlib
import json
import re
import stat
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from jsonschema import Draft202012Validator, SchemaError, ValidationError

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


class SealedArtifactOutputCollectorError(ValueError):
    """Raised after destroying unavailable or invalid output candidates."""


class SealedArtifactExecutionError(ValueError):
    """Raised without exposing asset internals or private candidate bytes."""


@dataclass(frozen=True)
class SealedArtifactRunnerDescriptor:
    """The validated public identity of one v1 sealed-artifact runner."""

    digest: str
    asset_path: str
    asset_digest: str
    capability_requirements_digest: str
    inputs: tuple["SealedArtifactInput", ...]
    outputs: tuple["SealedArtifactOutput", ...]
    schema_assets: tuple["SealedArtifactSchemaAsset", ...]
    child_contract_digests: tuple[str, ...]
    callbacks: tuple["SealedArtifactCallback", ...]
    output_roles: tuple[str, ...]


@dataclass(frozen=True)
class SealedArtifactSchemaAsset:
    """One schema file bound by a runner descriptor."""

    path: str
    digest: str
    document: object | None = None


@dataclass(frozen=True)
class SealedArtifactInput:
    """One declared sealed input role and its byte contract."""

    role: str
    media_type: str
    max_bytes: int
    required: bool
    schema_digest: str | None


@dataclass(frozen=True)
class SealedArtifactOutput:
    """One declared sealed output role and its byte contract."""

    role: str
    media_type: str
    max_bytes: int
    schema_digest: str | None


@dataclass(frozen=True)
class SealedArtifactCallback:
    """One descriptor-bound callback and its child contract identity."""

    name: str
    requirement: str
    child_contract_digest: str
    max_calls: int
    max_concurrency: int
    max_request_bytes: int
    max_response_bytes: int
    max_total_request_bytes: int
    max_total_response_bytes: int
    timeout_milliseconds: int


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
    inputs = _inputs(mapping["inputs"], schema_digests=schema_digests)
    outputs = _outputs(mapping["outputs"], schema_digests=schema_digests)
    output_roles = tuple(item.role for item in outputs)
    _limits(mapping["limits"])
    child_digests = _child_digests(mapping["child_contract_digests"])
    callbacks = _callbacks(mapping["callbacks"], child_digests)
    return SealedArtifactRunnerDescriptor(
        digest=declared_digest,
        asset_path=asset_path,
        asset_digest=asset_digest,
        capability_requirements_digest=capability_requirements_digest,
        inputs=inputs,
        outputs=outputs,
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
    schema_assets = tuple(
        replace(
            schema,
            document=_validate_schema(_file_digest(root, schema.path, schema.digest)),
        )
        for schema in descriptor.schema_assets
    )
    child_contracts = {
        digest: _child_contract_mapping(root, digest)
        for digest in descriptor.child_contract_digests
    }
    for callback in descriptor.callbacks:
        _validate_callback_child_contract(
            child_contracts[callback.child_contract_digest], callback
        )
    return replace(descriptor, schema_assets=schema_assets)


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


class SealedArtifactWorkflowReceiverHost(Protocol):
    """Host-owned operations performed by one sealed receiver invocation."""

    def registration(self, invocation: object) -> object: ...

    def verify_package(self, registration: object) -> object: ...

    def authorize(self, package: object) -> object: ...

    def resolve_identities(self, authorization: object) -> object: ...

    def validate_handles(self, identities: object) -> object: ...

    def allocate_collector(self, handles: object) -> object: ...

    def execute_asset(self, collector: object) -> object: ...


class SealedArtifactWorkflowReceiver:
    """Run one host-owned sealed-artifact invocation in the fixed admission order."""

    _HOST_METHODS = (
        "registration",
        "verify_package",
        "authorize",
        "resolve_identities",
        "validate_handles",
        "allocate_collector",
        "execute_asset",
    )

    def __init__(self, *, host: SealedArtifactWorkflowReceiverHost) -> None:
        if any(not callable(getattr(host, name, None)) for name in self._HOST_METHODS):
            raise SealedArtifactRunnerAdmissionError(
                "sealed artifact runner is unavailable"
            )
        self._host = host

    def run(self, *, invocation: object) -> object:
        """Stop at the first rejected boundary without invoking a later operation."""

        try:
            registration = self._host.registration(invocation)
            package = self._host.verify_package(registration)
            authorization = self._host.authorize(package)
            identities = self._host.resolve_identities(authorization)
            handles = self._host.validate_handles(identities)
            collector = self._host.allocate_collector(handles)
            return self._host.execute_asset(collector)
        except Exception as error:
            raise SealedArtifactRunnerAdmissionError(
                "sealed artifact runner is unavailable"
            ) from error


class SealedArtifactOutputCollector:
    """Collect declared outputs privately until every slot atomically seals."""

    def __init__(self, *, descriptor: SealedArtifactRunnerDescriptor) -> None:
        if not isinstance(descriptor, SealedArtifactRunnerDescriptor):
            raise SealedArtifactOutputCollectorError("output collector is unavailable")
        self._descriptor = descriptor
        self._candidates: list[tuple[str, str, bytes]] = []
        self._state = "collecting"

    def write(self, *, role: str, media_type: str, content: bytes) -> None:
        """Accept exactly the next declared output slot or destroy candidates."""

        if self._state != "collecting":
            raise SealedArtifactOutputCollectorError("output collector is unavailable")
        try:
            expected = self._descriptor.outputs[len(self._candidates)]
            if (
                not isinstance(content, bytes)
                or role != expected.role
                or media_type != expected.media_type
                or len(content) > expected.max_bytes
            ):
                self._invalidate()
            if expected.schema_digest is not None:
                schema_matches = [
                    item
                    for item in self._descriptor.schema_assets
                    if item.digest == expected.schema_digest
                ]
                if len(schema_matches) != 1 or schema_matches[0].document is None:
                    self._invalidate()
                _validate_json_against_schema(content, schema_matches[0].document)
            self._candidates.append((role, media_type, content))
        except (IndexError, SealedArtifactHandleError):
            self._invalidate()

    def seal(self) -> tuple[tuple[str, str, bytes], ...]:
        """Return all outputs only after every declared slot has been collected."""

        if self._state != "collecting" or len(self._candidates) != len(
            self._descriptor.outputs
        ):
            self._destroy()
            raise SealedArtifactOutputCollectorError("output collector is unavailable")
        self._state = "sealed"
        return tuple(self._candidates)

    def abort(self) -> None:
        """Destroy all candidate bytes without publication."""

        self._destroy()

    def _invalidate(self) -> None:
        self._destroy()
        raise SealedArtifactOutputCollectorError("output collector is invalid")

    def _destroy(self) -> None:
        self._candidates.clear()
        self._state = "destroyed"


class SealedArtifactExecutionContext:
    """The narrow, non-introspectable ABI surface for one verified asset."""

    __slots__ = (
        "_callback",
        "_callback_counts",
        "_callback_request_bytes",
        "_callback_response_bytes",
        "_collector",
        "_descriptor",
        "_read_input",
        "_reads",
    )

    def __init__(
        self,
        *,
        descriptor: SealedArtifactRunnerDescriptor,
        read_input: Callable[[str], bytes],
        invoke_callback: Callable[[str, bytes], bytes],
        collector: SealedArtifactOutputCollector,
    ) -> None:
        if (
            not isinstance(descriptor, SealedArtifactRunnerDescriptor)
            or not callable(read_input)
            or not callable(invoke_callback)
            or not isinstance(collector, SealedArtifactOutputCollector)
        ):
            raise SealedArtifactExecutionError(
                "sealed artifact execution is unavailable"
            )
        object.__setattr__(self, "_descriptor", descriptor)
        object.__setattr__(self, "_read_input", read_input)
        object.__setattr__(self, "_callback", invoke_callback)
        object.__setattr__(self, "_collector", collector)
        object.__setattr__(self, "_reads", set())
        object.__setattr__(self, "_callback_counts", {})
        object.__setattr__(self, "_callback_request_bytes", {})
        object.__setattr__(self, "_callback_response_bytes", {})

    def __getattribute__(self, name: str) -> object:
        if name in {"read_input", "invoke_callback", "write_output"}:
            return object.__getattribute__(self, name)
        raise AttributeError("sealed artifact context member is unavailable")

    def read_input(self, role: str) -> bytes:
        """Return one declared input exactly once."""

        descriptor = object.__getattribute__(self, "_descriptor")
        reads = object.__getattribute__(self, "_reads")
        matching = [item for item in descriptor.inputs if item.role == role]
        if len(matching) != 1 or role in reads:
            raise SealedArtifactExecutionError("sealed artifact input is unavailable")
        content = object.__getattribute__(self, "_read_input")(role)
        if not isinstance(content, bytes) or len(content) > matching[0].max_bytes:
            raise SealedArtifactExecutionError("sealed artifact input is unavailable")
        reads.add(role)
        return content

    def invoke_callback(self, name: str, request: bytes) -> bytes:
        """Invoke one descriptor-declared callback with opaque bytes."""

        descriptor = object.__getattribute__(self, "_descriptor")
        matches = [item for item in descriptor.callbacks if item.name == name]
        if not isinstance(request, bytes) or len(matches) != 1:
            raise SealedArtifactExecutionError(
                "sealed artifact callback is unavailable"
            )
        callback = matches[0]
        counts = object.__getattribute__(self, "_callback_counts")
        request_bytes = object.__getattribute__(self, "_callback_request_bytes")
        response_bytes = object.__getattribute__(self, "_callback_response_bytes")
        count = counts.get(name, 0)
        total_request = request_bytes.get(name, 0)
        if (
            count >= callback.max_calls
            or len(request) > callback.max_request_bytes
            or total_request + len(request) > callback.max_total_request_bytes
        ):
            raise SealedArtifactExecutionError(
                "sealed artifact callback is unavailable"
            )
        counts[name] = count + 1
        request_bytes[name] = total_request + len(request)
        response = object.__getattribute__(self, "_callback")(name, request)
        total_response = response_bytes.get(name, 0)
        if (
            not isinstance(response, bytes)
            or len(response) > callback.max_response_bytes
            or total_response + len(response) > callback.max_total_response_bytes
        ):
            raise SealedArtifactExecutionError(
                "sealed artifact callback is unavailable"
            )
        response_bytes[name] = total_response + len(response)
        return response

    def write_output(self, role: str, media_type: str, content: bytes) -> None:
        """Write one ordered output through the private collector."""

        try:
            object.__getattribute__(self, "_collector").write(
                role=role, media_type=media_type, content=content
            )
        except SealedArtifactOutputCollectorError as error:
            raise SealedArtifactExecutionError(
                "sealed artifact output is unavailable"
            ) from error


class SealedArtifactAssetRuntime:
    """Execute one verified Python asset with imports and host objects unavailable."""

    def execute(
        self, *, asset: bytes, context: SealedArtifactExecutionContext
    ) -> tuple[tuple[str, str, bytes], ...]:
        """Call only ``run(context) -> None`` or destroy the private collector."""

        if not isinstance(asset, bytes) or not isinstance(
            context, SealedArtifactExecutionContext
        ):
            raise SealedArtifactExecutionError(
                "sealed artifact execution is unavailable"
            )
        try:
            namespace: dict[str, object] = {"__builtins__": {}}
            exec(compile(asset, "<sealed-artifact>", "exec"), namespace)
            run = namespace.get("run")
            if not callable(run) or run(context) is not None:
                raise SealedArtifactExecutionError(
                    "sealed artifact execution is unavailable"
                )
            return object.__getattribute__(context, "_collector").seal()
        except Exception as error:
            object.__getattribute__(context, "_collector").abort()
            if isinstance(error, SealedArtifactExecutionError):
                raise
            raise SealedArtifactExecutionError(
                "sealed artifact execution is unavailable"
            ) from error


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
        descriptor: SealedArtifactRunnerDescriptor,
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

        if not isinstance(descriptor, SealedArtifactRunnerDescriptor):
            raise SealedArtifactHandleError("artifact handle is invalid")
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
        matching_inputs = [item for item in descriptor.inputs if item.role == role]
        if (
            len(matching_inputs) != 1
            or matching_inputs[0].media_type != media_type
            or matching_inputs[0].schema_digest != schema_digest
            or len(content) > matching_inputs[0].max_bytes
        ):
            raise SealedArtifactHandleError("artifact handle is invalid")
        if matching_inputs[0].schema_digest is not None:
            schema_matches = [
                item
                for item in descriptor.schema_assets
                if item.digest == matching_inputs[0].schema_digest
            ]
            if len(schema_matches) != 1 or schema_matches[0].document is None:
                raise SealedArtifactHandleError("artifact handle is invalid")
            _validate_json_against_schema(content, schema_matches[0].document)
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


def _inputs(
    value: object, *, schema_digests: frozenset[str]
) -> tuple[SealedArtifactInput, ...]:
    items = _list(value)
    inputs: list[SealedArtifactInput] = []
    roles: list[str] = []
    for item in items:
        mapping = _mapping(item)
        _require_exact_keys(
            mapping, {"max_bytes", "media_type", "required", "role", "schema_digest"}
        )
        role = _name(mapping["role"])
        media_type = _media_type(mapping["media_type"])
        schema_digest = mapping["schema_digest"]
        if schema_digest is not None:
            _digest(schema_digest)
            if schema_digest not in schema_digests or media_type != "application/json":
                _invalid()
        max_bytes = mapping["max_bytes"]
        _positive(max_bytes)
        if not isinstance(mapping["required"], bool):
            _invalid()
        inputs.append(
            SealedArtifactInput(
                role=role,
                media_type=media_type,
                max_bytes=max_bytes,
                required=mapping["required"],
                schema_digest=schema_digest,
            )
        )
        roles.append(role)
    if roles != sorted(roles) or len(set(roles)) != len(roles):
        _invalid()
    return tuple(inputs)


def _outputs(
    value: object, *, schema_digests: frozenset[str]
) -> tuple[SealedArtifactOutput, ...]:
    items = _list(value)
    if not items:
        _invalid()
    outputs: list[SealedArtifactOutput] = []
    roles: list[str] = []
    for item in items:
        mapping = _mapping(item)
        _require_exact_keys(
            mapping, {"max_bytes", "media_type", "role", "schema_digest"}
        )
        role = _name(mapping["role"])
        media_type = _media_type(mapping["media_type"])
        schema_digest = mapping["schema_digest"]
        if schema_digest is not None:
            _digest(schema_digest)
            if schema_digest not in schema_digests or media_type != "application/json":
                _invalid()
        max_bytes = mapping["max_bytes"]
        _positive(max_bytes)
        outputs.append(
            SealedArtifactOutput(
                role=role,
                media_type=media_type,
                max_bytes=max_bytes,
                schema_digest=schema_digest,
            )
        )
        roles.append(role)
    if roles != sorted(roles) or len(set(roles)) != len(roles):
        _invalid()
    return tuple(outputs)


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
                max_calls=mapping["max_calls"],  # type: ignore[arg-type]
                max_concurrency=mapping["max_concurrency"],  # type: ignore[arg-type]
                max_request_bytes=mapping["max_request_bytes"],  # type: ignore[arg-type]
                max_response_bytes=mapping["max_response_bytes"],  # type: ignore[arg-type]
                max_total_request_bytes=mapping["max_total_request_bytes"],  # type: ignore[arg-type]
                max_total_response_bytes=mapping["max_total_response_bytes"],  # type: ignore[arg-type]
                timeout_milliseconds=mapping["timeout_milliseconds"],  # type: ignore[arg-type]
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


def _validate_schema(value: bytes) -> object:
    try:
        schema = json.loads(
            value.decode("utf-8"), object_pairs_hook=_no_duplicate_object
        )
        Draft202012Validator.check_schema(schema)
        return schema
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        SchemaError,
        SealedArtifactRunnerDescriptorError,
    ) as error:
        raise SealedArtifactRunnerDescriptorError(
            "sealed artifact runner schema is invalid"
        ) from error


def _validate_json_against_schema(content: bytes, schema: object) -> None:
    try:
        value = json.loads(
            content.decode("utf-8"), object_pairs_hook=_no_duplicate_object
        )
        Draft202012Validator(schema).validate(value)
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        SealedArtifactRunnerDescriptorError,
        ValidationError,
    ) as error:
        raise SealedArtifactHandleError("artifact handle is invalid") from error


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
