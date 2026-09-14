"""Host-owned bounded execution for sealed structured inference roles."""

from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Protocol


class LockedInferenceExecutionError(ValueError):
    """Raised with a stable redacted callback failure classification."""


class LockedInferenceProvider(Protocol):
    """Receiver-local provider seam; package assets never see this object."""

    def generate(
        self, *, binding: object, instruction_bytes: bytes, request_bytes: bytes
    ) -> bytes:
        """Return one bounded canonical structured response."""


@dataclass(frozen=True)
class LockedInferenceHostLimits:
    """Positive execution ceilings shared by a package role and receiver."""

    max_calls: int
    max_input_bytes: int
    max_output_bytes: int
    timeout_milliseconds: int
    max_concurrency: int

    def __post_init__(self) -> None:
        if any(
            not isinstance(value, int) or isinstance(value, bool) or value <= 0
            for value in self.__dict__.values()
        ):
            raise LockedInferenceExecutionError("inference limits are invalid")


class LockedInferenceExecutionService:
    """Validate and execute only pre-bound role callbacks with no fallback."""

    def __init__(
        self,
        *,
        providers: Mapping[str, LockedInferenceProvider],
        bindings: Mapping[str, object],
        instructions: Mapping[str, bytes],
        request_schemas: Mapping[str, bytes],
        response_schemas: Mapping[str, bytes],
        package_limits: Mapping[str, LockedInferenceHostLimits],
        host_limits: LockedInferenceHostLimits,
        revalidate: Callable[[str], bool],
    ) -> None:
        roles = tuple(sorted(providers))
        if not roles or any(
            set(mapping) != set(roles)
            for mapping in (
                bindings,
                instructions,
                request_schemas,
                response_schemas,
                package_limits,
            )
        ):
            raise LockedInferenceExecutionError("inference bindings are invalid")
        self._providers = dict(providers)
        self._bindings = dict(bindings)
        self._instructions = dict(instructions)
        self._request_schemas = {
            role: _schema(value) for role, value in request_schemas.items()
        }
        self._response_schemas = {
            role: _schema(value) for role, value in response_schemas.items()
        }
        self._limits = {
            role: _effective(package_limits[role], host_limits) for role in roles
        }
        self._revalidate = revalidate
        self._remaining = {role: self._limits[role].max_calls for role in roles}
        self._active = dict.fromkeys(roles, 0)
        self._lock = threading.Lock()

    def generate(self, role: str, request_bytes: bytes) -> bytes:  # noqa: C901
        """Execute one role after canonical validation and atomic quota reservation."""

        if role not in self._providers:
            raise LockedInferenceExecutionError("inference role is unavailable")
        limits = self._limits[role]
        request = _canonical_value(request_bytes, "request")
        try:
            _validate_value(request, self._request_schemas[role], depth=1)
        except LockedInferenceExecutionError as error:
            raise LockedInferenceExecutionError(
                "inference request is invalid"
            ) from error
        if len(request_bytes) > limits.max_input_bytes:
            raise LockedInferenceExecutionError("inference request exceeds limit")
        if not self._revalidate(role):
            raise LockedInferenceExecutionError("inference provider is unavailable")
        with self._lock:
            if (
                self._remaining[role] <= 0
                or self._active[role] >= limits.max_concurrency
            ):
                raise LockedInferenceExecutionError("inference quota is unavailable")
            self._remaining[role] -= 1
            self._active[role] += 1
        try:
            executor = ThreadPoolExecutor(max_workers=1)
            future = executor.submit(
                self._providers[role].generate,
                binding=self._bindings[role],
                instruction_bytes=self._instructions[role],
                request_bytes=request_bytes,
            )
            try:
                response_bytes = future.result(limits.timeout_milliseconds / 1000)
            except TimeoutError as error:
                future.cancel()
                raise LockedInferenceExecutionError("inference timeout") from error
            finally:
                executor.shutdown(wait=False, cancel_futures=True)
        except LockedInferenceExecutionError:
            raise
        except Exception as error:  # noqa: BLE001 - provider internals stay private.
            raise LockedInferenceExecutionError("inference provider failed") from error
        finally:
            with self._lock:
                self._active[role] -= 1
        if (
            not isinstance(response_bytes, bytes)
            or len(response_bytes) > limits.max_output_bytes
        ):
            raise LockedInferenceExecutionError("inference response exceeds limit")
        response = _canonical_value(response_bytes, "response")
        try:
            _validate_value(response, self._response_schemas[role], depth=1)
        except LockedInferenceExecutionError as error:
            raise LockedInferenceExecutionError(
                "inference response is invalid"
            ) from error
        return response_bytes


def validate_locked_inference_schema(value: bytes) -> None:
    """Reject noncanonical or unsupported structured-value-v1 schema bytes."""

    _schema(value)


def _effective(
    package: LockedInferenceHostLimits, host: LockedInferenceHostLimits
) -> LockedInferenceHostLimits:
    return LockedInferenceHostLimits(
        *(
            min(left, right)
            for left, right in zip(
                package.__dict__.values(), host.__dict__.values(), strict=True
            )
        )
    )


def _schema(value: bytes) -> Mapping[str, object]:
    schema = _canonical_value(value, "schema")
    if not isinstance(schema, dict):
        raise LockedInferenceExecutionError("inference schema is invalid")
    _validate_schema(schema)
    return schema


def _canonical_value(value: object, kind: str) -> object:
    if not isinstance(value, bytes):
        raise LockedInferenceExecutionError(f"inference {kind} is invalid")
    try:
        decoded = json.loads(value.decode("utf-8"), object_pairs_hook=_unique_object)
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        LockedInferenceExecutionError,
    ) as error:
        raise LockedInferenceExecutionError(f"inference {kind} is invalid") from error
    canonical = json.dumps(
        decoded, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    if value != canonical:
        raise LockedInferenceExecutionError(f"inference {kind} is noncanonical")
    return decoded


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise LockedInferenceExecutionError(
                "inference JSON contains duplicate keys"
            )
        value[key] = item
    return value


def _validate_schema(schema: Mapping[str, object]) -> None:
    kind = schema.get("type")
    allowed = {
        "type",
        "properties",
        "required",
        "items",
        "enum",
        "max_depth",
        "max_items",
        "max_string_bytes",
    }
    if (
        kind not in {"object", "array", "string", "boolean", "null"}
        or set(schema) - allowed
    ):
        raise LockedInferenceExecutionError("inference schema is invalid")
    if kind == "object":
        properties = schema.get("properties")
        required = schema.get("required")
        if (
            not isinstance(properties, dict)
            or not isinstance(required, list)
            or set(required) != set(properties)
        ):
            raise LockedInferenceExecutionError("inference schema is invalid")
        for value in properties.values():
            if not isinstance(value, dict):
                raise LockedInferenceExecutionError("inference schema is invalid")
            _validate_schema(value)
    if kind == "array":
        items = schema.get("items")
        if not isinstance(items, dict):
            raise LockedInferenceExecutionError("inference schema is invalid")
        _validate_schema(items)


def _validate_value(  # noqa: C901
    value: object, schema: Mapping[str, object], *, depth: int
) -> None:
    max_depth = schema.get("max_depth", 64)
    if not isinstance(max_depth, int) or depth > max_depth:
        raise LockedInferenceExecutionError("inference value is invalid")
    kind = schema["type"]
    if kind == "object":
        properties = schema["properties"]
        if not isinstance(value, dict) or set(value) != set(properties):
            raise LockedInferenceExecutionError("inference value is invalid")
        for name, child in properties.items():
            _validate_value(value[name], child, depth=depth + 1)
    elif kind == "array":
        if not isinstance(value, list) or len(value) > schema.get("max_items", 0):
            raise LockedInferenceExecutionError("inference value is invalid")
        for item in value:
            _validate_value(item, schema["items"], depth=depth + 1)
    elif kind == "string":
        if not isinstance(value, str) or len(value.encode("utf-8")) > schema.get(
            "max_string_bytes", 0
        ):
            raise LockedInferenceExecutionError("inference value is invalid")
    elif kind == "boolean" and not isinstance(value, bool):
        raise LockedInferenceExecutionError("inference value is invalid")
    elif kind == "null" and value is not None:
        raise LockedInferenceExecutionError("inference value is invalid")
    if "enum" in schema and value not in schema["enum"]:
        raise LockedInferenceExecutionError("inference value is invalid")
