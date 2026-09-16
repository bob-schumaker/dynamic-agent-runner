"""Host-owned names for fixed reviewed artifact-aware tool bindings."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from dynamic_agent_runner.workflow_host.capabilities import (
    CapabilityError,
    ReviewedCapabilityTemplate,
    validate_vector_index_build_template,
)
from dynamic_agent_runner.workflow_host.state import (
    OpaqueRecordError,
    PrivateStateStore,
)


class ReviewedToolPackageError(ValueError):
    """Raised when a reviewed tool package is unavailable or unsafe."""


@dataclass(frozen=True)
class ReviewedToolPackageBinding:
    """One exact reviewed binding and its artifact-aware tool allowlist."""

    binding_id: str
    binding_digest: str
    allowed_tool_ids: tuple[str, ...]
    artifact_aware_tool_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_identifier(self.binding_id)
        _require_digest(self.binding_digest)
        _require_tool_ids(self.allowed_tool_ids)
        _require_tool_ids(self.artifact_aware_tool_ids)
        if not set(self.artifact_aware_tool_ids) <= set(self.allowed_tool_ids):
            raise ReviewedToolPackageError("reviewed tool package is invalid")


@dataclass(frozen=True)
class ReviewedToolPackage:
    """One host-owned name bound to a fixed reviewed tool binding."""

    package_name: str
    binding: ReviewedToolPackageBinding

    def __post_init__(self) -> None:
        _require_identifier(self.package_name)
        if not isinstance(self.binding, ReviewedToolPackageBinding):
            raise ReviewedToolPackageError("reviewed tool package is invalid")


class ReviewedToolPackageControlPlane:
    """Persist explicit names without package discovery or fallback resolution."""

    def __init__(self, *, store: PrivateStateStore, owner: str) -> None:
        if not isinstance(owner, str) or not owner:
            raise ReviewedToolPackageError("reviewed tool package is invalid")
        self._store = store
        self._owner = owner

    def create(
        self, *, package_name: str, binding: ReviewedToolPackageBinding
    ) -> ReviewedToolPackage:
        _require_identifier(package_name)
        if not isinstance(binding, ReviewedToolPackageBinding):
            raise ReviewedToolPackageError("reviewed tool package is invalid")
        now = datetime.now(UTC)
        try:
            if any(
                record.payload.get("package_name") == package_name
                for _, record in self._store.active_records(
                    kind="reviewed_tool_package", owner=self._owner, now=now
                )
            ):
                raise ReviewedToolPackageError("reviewed tool package is unavailable")
            self._store.issue(
                kind="reviewed_tool_package",
                owner=self._owner,
                payload={
                    "format_version": 1,
                    "package_name": package_name,
                    "binding_id": binding.binding_id,
                    "binding_digest": binding.binding_digest,
                    "allowed_tool_ids": list(binding.allowed_tool_ids),
                    "artifact_aware_tool_ids": list(binding.artifact_aware_tool_ids),
                },
                expires_at=now + timedelta(days=3650),
                now=now,
            )
        except OpaqueRecordError as error:
            raise ReviewedToolPackageError(
                "reviewed tool package is unavailable"
            ) from error
        return ReviewedToolPackage(package_name, binding)

    def resolve(
        self, *, package_name: str, current_binding: ReviewedToolPackageBinding
    ) -> ReviewedToolPackageBinding:
        _require_identifier(package_name)
        if not isinstance(current_binding, ReviewedToolPackageBinding):
            raise ReviewedToolPackageError("reviewed tool package is unavailable")
        now = datetime.now(UTC)
        try:
            records = self._store.active_records(
                kind="reviewed_tool_package", owner=self._owner, now=now
            )
        except OpaqueRecordError as error:
            raise ReviewedToolPackageError(
                "reviewed tool package is unavailable"
            ) from error
        matches = [
            record
            for _, record in records
            if record.payload.get("package_name") == package_name
        ]
        if len(matches) != 1:
            raise ReviewedToolPackageError("reviewed tool package is unavailable")
        try:
            stored = _binding_from_payload(matches[0].payload)
        except (KeyError, TypeError, ReviewedToolPackageError) as error:
            raise ReviewedToolPackageError(
                "reviewed tool package is unavailable"
            ) from error
        if stored != current_binding:
            raise ReviewedToolPackageError("reviewed tool package is unavailable")
        return stored

    def require_artifact_tool(
        self,
        *,
        package_name: str,
        tool_id: str,
        current_binding: ReviewedToolPackageBinding,
    ) -> ReviewedToolPackageBinding:
        binding = self.resolve(
            package_name=package_name, current_binding=current_binding
        )
        if tool_id not in binding.artifact_aware_tool_ids:
            raise ReviewedToolPackageError("reviewed tool is not artifact-aware")
        return binding


class ReviewedCapabilityTemplateControlPlane:
    """Persist one exact host-reviewed capability template without fallback."""

    def __init__(self, *, store: PrivateStateStore, owner: str) -> None:
        if not isinstance(owner, str) or not owner:
            raise ReviewedToolPackageError("reviewed template is invalid")
        self._store = store
        self._owner = owner

    def create(self, *, template: ReviewedCapabilityTemplate) -> None:
        _validate_template(template)
        now = datetime.now(UTC)
        try:
            if any(
                record.payload.get("capability_id") == template.capability_id
                for _, record in self._store.active_records(
                    kind="reviewed_capability_template", owner=self._owner, now=now
                )
            ):
                raise ReviewedToolPackageError("reviewed template is unavailable")
            self._store.issue(
                kind="reviewed_capability_template",
                owner=self._owner,
                payload=_template_payload(template),
                expires_at=now + timedelta(days=3650),
                now=now,
            )
        except OpaqueRecordError as error:
            raise ReviewedToolPackageError(
                "reviewed template is unavailable"
            ) from error

    def resolve(
        self, *, capability_id: str, current_template: ReviewedCapabilityTemplate
    ) -> ReviewedCapabilityTemplate:
        _require_identifier(capability_id)
        _validate_template(current_template)
        if (
            current_template.capability_id != capability_id
            or not current_template.enabled
        ):
            raise ReviewedToolPackageError("reviewed template is unavailable")
        now = datetime.now(UTC)
        try:
            records = self._store.active_records(
                kind="reviewed_capability_template", owner=self._owner, now=now
            )
        except OpaqueRecordError as error:
            raise ReviewedToolPackageError(
                "reviewed template is unavailable"
            ) from error
        matches = [
            record
            for _, record in records
            if record.payload.get("capability_id") == capability_id
        ]
        if len(matches) != 1 or matches[0].payload != _template_payload(
            current_template
        ):
            raise ReviewedToolPackageError("reviewed template is unavailable")
        return current_template


def _binding_from_payload(payload: object) -> ReviewedToolPackageBinding:
    if (
        not isinstance(payload, dict)
        or set(payload)
        != {
            "format_version",
            "package_name",
            "binding_id",
            "binding_digest",
            "allowed_tool_ids",
            "artifact_aware_tool_ids",
        }
        or payload["format_version"] != 1
    ):
        raise ReviewedToolPackageError("reviewed tool package is invalid")
    _require_identifier(payload["package_name"])
    return ReviewedToolPackageBinding(
        binding_id=payload["binding_id"],
        binding_digest=payload["binding_digest"],
        allowed_tool_ids=tuple(payload["allowed_tool_ids"]),
        artifact_aware_tool_ids=tuple(payload["artifact_aware_tool_ids"]),
    )


def _validate_template(template: object) -> None:
    try:
        if not isinstance(template, ReviewedCapabilityTemplate):
            raise ValueError
        if template.capability_id == "vector_index.build.v1":
            validate_vector_index_build_template(template)
    except (CapabilityError, ValueError) as error:
        raise ReviewedToolPackageError("reviewed template is invalid") from error


def _template_payload(template: ReviewedCapabilityTemplate) -> dict[str, object]:
    return {
        "format_version": 1,
        "capability_id": template.capability_id,
        "contract_version": template.contract_version,
        "template_digest": template.template_digest,
        "extension_binding": template.extension_binding,
    }


def _require_identifier(value: object) -> None:
    if not isinstance(value, str) or not value or len(value) > 128 or "/" in value:
        raise ReviewedToolPackageError("reviewed tool package is invalid")


def _require_digest(value: object) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(c not in "0123456789abcdef" for c in value)
    ):
        raise ReviewedToolPackageError("reviewed tool package is invalid")


def _require_tool_ids(value: object) -> None:
    if not isinstance(value, tuple) or not value or len(set(value)) != len(value):
        raise ReviewedToolPackageError("reviewed tool package is invalid")
    for tool_id in value:
        _require_identifier(tool_id)
