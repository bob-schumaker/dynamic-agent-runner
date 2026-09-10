"""Generic sealed-artifact descriptor validation and ordered admission."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any


_DIGEST = re.compile(r"[0-9a-f]{64}")
_NAME = re.compile(r"[a-z][a-z0-9_]{0,63}")
_MEDIA_TYPE = re.compile(r"[a-z0-9!#$&^_.+-]+/[a-z0-9!#$&^_.+-]+")
_MAX_INTEGER = 9007199254740991


class SealedArtifactRunnerDescriptorError(ValueError):
    """Raised when a sealed-artifact descriptor is not canonical or valid."""


class SealedArtifactRunnerAdmissionError(ValueError):
    """Raised when one admission boundary rejects an invocation."""


@dataclass(frozen=True)
class SealedArtifactRunnerDescriptor:
    """The validated public identity of one v1 sealed-artifact runner."""

    digest: str
    asset_path: str
    output_roles: tuple[str, ...]


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
    asset_path = _asset(mapping["asset"])
    _digest(mapping["capability_requirements_digest"])
    _digest(mapping["profile_digest"])
    schema_digests = _schemas(mapping["schemas"])
    _artifacts(mapping["inputs"], output=False, schema_digests=schema_digests)
    output_roles = _artifacts(
        mapping["outputs"], output=True, schema_digests=schema_digests
    )
    _limits(mapping["limits"])
    child_digests = _child_digests(mapping["child_contract_digests"])
    _callbacks(mapping["callbacks"], child_digests)
    return SealedArtifactRunnerDescriptor(
        digest=declared_digest,
        asset_path=asset_path,
        output_roles=output_roles,
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


def _asset(value: object) -> str:
    mapping = _mapping(value)
    _require_exact_keys(mapping, {"abi_version", "entrypoint", "path", "sha256"})
    if mapping["abi_version"] != 1 or mapping["entrypoint"] != "run":
        _invalid()
    path = _path(mapping["path"])
    if not path.endswith(".py"):
        _invalid()
    _digest(mapping["sha256"])
    return path


def _schemas(value: object) -> frozenset[str]:
    items = _list(value)
    paths: list[str] = []
    digests: list[str] = []
    for item in items:
        mapping = _mapping(item)
        _require_exact_keys(mapping, {"dialect", "path", "sha256"})
        if mapping["dialect"] != "json-schema-draft-2020-12":
            _invalid()
        paths.append(_path(mapping["path"]))
        digests.append(_digest(mapping["sha256"]))
    if (
        paths != sorted(paths)
        or len(set(paths)) != len(paths)
        or len(set(digests)) != len(digests)
    ):
        _invalid()
    return frozenset(digests)


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


def _callbacks(value: object, child_digests: tuple[str, ...]) -> None:
    items = _list(value)
    names: list[str] = []
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
        names.append(_name(mapping["name"]))
        for key, item_value in mapping.items():
            if key not in {"child_contract_digest", "name", "requirement"}:
                _positive(item_value)
    if names != sorted(names) or len(set(names)) != len(names):
        _invalid()


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
