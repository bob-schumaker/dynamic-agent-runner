"""Exact immutable capability contracts and receiver-local resolution."""

from __future__ import annotations

import hashlib
import json
import unicodedata
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Callable, Mapping, Sequence


class CapabilityError(ValueError):
    """Raised when a capability value is malformed or noncanonical."""


class ProviderAvailability(StrEnum):
    """Redacted receiver-local provider availability classifications."""

    AVAILABLE = "available"
    DISABLED = "disabled"
    PLATFORM_INCOMPATIBLE = "platform_incompatible"
    OPTIONAL_COMPONENT_MISSING = "optional_component_missing"


@dataclass(frozen=True)
class CapabilityContract:
    """One exact public DAR behavior contract."""

    capability_id: str
    contract_version: str
    contract_digest: str
    features: tuple[str, ...]

    def __post_init__(self) -> None:
        _text(self.capability_id, "capability_id")
        _text(self.contract_version, "contract_version")
        _digest(self.contract_digest, "contract_digest")
        _canonical_strings(self.features, "features")
        object.__setattr__(self, "features", tuple(self.features))


@dataclass(frozen=True)
class ReviewedCapabilityTemplateOutput:
    """One bounded opaque output role in a reviewed template."""

    role: str
    media_type: str
    max_bytes: int
    retention_seconds: int

    def __post_init__(self) -> None:
        _text(self.role, "role")
        _text(self.media_type, "media_type")
        if (
            not isinstance(self.max_bytes, int)
            or isinstance(self.max_bytes, bool)
            or self.max_bytes < 1
            or not isinstance(self.retention_seconds, int)
            or isinstance(self.retention_seconds, bool)
            or self.retention_seconds < 1
        ):
            raise CapabilityError("reviewed capability template output is invalid")


def reviewed_capability_template_digest(
    *,
    capability_id: str,
    contract_version: str,
    input_fields: tuple[str, ...],
    required_dependency: str,
    outputs: tuple[ReviewedCapabilityTemplateOutput, ...],
    max_receipt_bytes: int,
    approval_class: str,
    extension_binding: str,
    recovery_operations: tuple[str, ...],
    success_receipt_schema_digest: str,
    failure_classifications: tuple[str, ...],
    enabled: bool,
) -> str:
    """Return the SHA-256 digest of canonical reviewed-template content."""

    canonical = json.dumps(
        {
            "approval_class": approval_class,
            "capability_id": capability_id,
            "contract_version": contract_version,
            "enabled": enabled,
            "extension_binding": extension_binding,
            "input_fields": list(input_fields),
            "max_receipt_bytes": max_receipt_bytes,
            "outputs": [
                {
                    "max_bytes": output.max_bytes,
                    "media_type": output.media_type,
                    "retention_seconds": output.retention_seconds,
                    "role": output.role,
                }
                for output in outputs
            ],
            "recovery_operations": list(recovery_operations),
            "required_dependency": required_dependency,
            "success_receipt_schema_digest": success_receipt_schema_digest,
            "failure_classifications": list(failure_classifications),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(canonical).hexdigest()


@dataclass(frozen=True)
class ReviewedCapabilityTemplate:
    """One immutable host-reviewed capability template."""

    capability_id: str
    contract_version: str
    template_digest: str
    input_fields: tuple[str, ...]
    required_dependency: str
    outputs: tuple[ReviewedCapabilityTemplateOutput, ...]
    max_receipt_bytes: int
    approval_class: str
    extension_binding: str
    recovery_operations: tuple[str, ...]
    success_receipt_schema_digest: str
    failure_classifications: tuple[str, ...]
    enabled: bool

    def __post_init__(self) -> None:
        _text(self.capability_id, "capability_id")
        _text(self.contract_version, "contract_version")
        _digest(self.template_digest, "template_digest")
        _canonical_strings(self.input_fields, "input_fields")
        _text(self.required_dependency, "required_dependency")
        outputs = tuple(self.outputs)
        if (
            not outputs
            or not all(
                isinstance(item, ReviewedCapabilityTemplateOutput) for item in outputs
            )
            or len({item.role for item in outputs}) != len(outputs)
        ):
            raise CapabilityError("reviewed capability template is invalid")
        if (
            not isinstance(self.max_receipt_bytes, int)
            or isinstance(self.max_receipt_bytes, bool)
            or self.max_receipt_bytes < 1
        ):
            raise CapabilityError("reviewed capability template is invalid")
        _text(self.approval_class, "approval_class")
        _text(self.extension_binding, "extension_binding")
        _canonical_strings(self.recovery_operations, "recovery_operations")
        _digest(self.success_receipt_schema_digest, "success_receipt_schema_digest")
        _canonical_strings(self.failure_classifications, "failure_classifications")
        if not self.failure_classifications:
            raise CapabilityError("failure_classifications must not be empty")
        if not isinstance(self.enabled, bool):
            raise CapabilityError("reviewed capability template is invalid")
        if self.template_digest != reviewed_capability_template_digest(
            capability_id=self.capability_id,
            contract_version=self.contract_version,
            input_fields=tuple(self.input_fields),
            required_dependency=self.required_dependency,
            outputs=outputs,
            max_receipt_bytes=self.max_receipt_bytes,
            approval_class=self.approval_class,
            extension_binding=self.extension_binding,
            recovery_operations=tuple(self.recovery_operations),
            success_receipt_schema_digest=self.success_receipt_schema_digest,
            failure_classifications=tuple(self.failure_classifications),
            enabled=self.enabled,
        ):
            raise CapabilityError("reviewed capability template digest does not match")
        object.__setattr__(self, "input_fields", tuple(self.input_fields))
        object.__setattr__(self, "outputs", outputs)
        object.__setattr__(self, "recovery_operations", tuple(self.recovery_operations))
        object.__setattr__(
            self, "failure_classifications", tuple(self.failure_classifications)
        )


@dataclass(frozen=True)
class ReviewedCapabilityTemplateDiscovery:
    """One redacted reviewed-template discovery result."""

    status: str
    template: ReviewedCapabilityTemplate | None


class ReviewedCapabilityTemplateRegistry:
    """Discover one exact available reviewed template without fallback."""

    def __init__(self, templates: Sequence[ReviewedCapabilityTemplate]) -> None:
        if not all(isinstance(item, ReviewedCapabilityTemplate) for item in templates):
            raise CapabilityError("reviewed capability template is invalid")
        self._templates = tuple(templates)

    def discover(self, capability_id: str) -> ReviewedCapabilityTemplateDiscovery:
        """Return one available template or a stable unavailable/ambiguous result."""

        _text(capability_id, "capability_id")
        matches = tuple(
            item
            for item in self._templates
            if item.capability_id == capability_id and item.enabled
        )
        if not matches:
            return ReviewedCapabilityTemplateDiscovery(
                "authoring_runtime_unavailable", None
            )
        if len(matches) != 1:
            return ReviewedCapabilityTemplateDiscovery(
                "authoring_runtime_ambiguous", None
            )
        return ReviewedCapabilityTemplateDiscovery("available", matches[0])


def validate_vector_index_build_template(template: ReviewedCapabilityTemplate) -> None:
    """Require the closed reusable vector-index host-extension contract."""

    if (
        not isinstance(template, ReviewedCapabilityTemplate)
        or template.capability_id != "vector_index.build.v1"
        or template.input_fields != ("job_handle",)
        or template.required_dependency != "embedding.execute.v1"
        or tuple((item.role, item.media_type) for item in template.outputs)
        != (
            ("index_generation", "application/octet-stream"),
            ("index_manifest", "application/json"),
            ("coverage_report", "application/json"),
        )
        or set(template.recovery_operations)
        != {
            "begin_pending_publication",
            "query_current_outcome",
            "acknowledge_visibility",
            "compensate",
        }
    ):
        raise CapabilityError("reviewed vector-index template is invalid")


@dataclass(frozen=True)
class CapabilityRequirement:
    """One package-visible request for an exact capability contract."""

    capability_id: str
    contract_version: str
    contract_digest: str
    required_features: tuple[str, ...]

    def __post_init__(self) -> None:
        _text(self.capability_id, "capability_id")
        _text(self.contract_version, "contract_version")
        _digest(self.contract_digest, "contract_digest")
        _canonical_strings(self.required_features, "required_features")
        object.__setattr__(self, "required_features", tuple(self.required_features))

    def to_mapping(self) -> dict[str, object]:
        """Return the canonical JSON information content for this requirement."""

        return {
            "capability_id": self.capability_id,
            "contract_digest": self.contract_digest,
            "contract_version": self.contract_version,
            "required_features": list(self.required_features),
        }


@dataclass(frozen=True)
class CapabilityRequirements:
    """Canonical package capability requirements excluding their declared digest."""

    required_capabilities: tuple[CapabilityRequirement, ...] = ()
    bindings: Mapping[str, str] = MappingProxyType({})
    format_version: int = 1

    def __post_init__(self) -> None:
        if self.format_version != 1:
            raise CapabilityError("capability requirements format_version must be 1")
        requirements = tuple(self.required_capabilities)
        identifiers = tuple(item.capability_id for item in requirements)
        if identifiers != tuple(sorted(identifiers)) or len(set(identifiers)) != len(
            identifiers
        ):
            raise CapabilityError("required_capabilities must be sorted and unique")
        bindings = dict(self.bindings)
        if set(bindings) - {"runner", "converter"}:
            raise CapabilityError("capability requirement binding is invalid")
        if any(
            not isinstance(value, str) or value not in identifiers
            for value in bindings.values()
        ):
            raise CapabilityError("capability requirement binding is invalid")
        object.__setattr__(self, "required_capabilities", requirements)
        object.__setattr__(self, "bindings", MappingProxyType(bindings))

    @classmethod
    def from_mapping(cls, value: object) -> "CapabilityRequirements":
        """Parse the strict descriptor mapping and verify its declared digest."""

        if not isinstance(value, Mapping) or set(value) != {
            "format_version",
            "required_capabilities",
            "capability_requirements_digest",
            "bindings",
        }:
            raise CapabilityError("capability requirements mapping is invalid")
        raw_requirements = value["required_capabilities"]
        if not isinstance(raw_requirements, list):
            raise CapabilityError("required_capabilities must be a list")
        requirements = tuple(
            _requirement_from_mapping(item) for item in raw_requirements
        )
        raw_bindings = value["bindings"]
        if not isinstance(raw_bindings, Mapping):
            raise CapabilityError("capability requirement bindings are invalid")
        bindings: dict[str, str] = {}
        for name, binding in raw_bindings.items():
            if (
                not isinstance(name, str)
                or not isinstance(binding, Mapping)
                or set(binding) != {"capability_id"}
            ):
                raise CapabilityError("capability requirement binding is invalid")
            capability_id = binding["capability_id"]
            if not isinstance(capability_id, str):
                raise CapabilityError("capability requirement binding is invalid")
            bindings[name] = capability_id
        result = cls(requirements, bindings, value["format_version"])
        declared_digest = value["capability_requirements_digest"]
        _digest(declared_digest, "capability_requirements_digest")
        if declared_digest != result.digest:
            raise CapabilityError("capability requirements digest does not match")
        return result

    @property
    def canonical_bytes(self) -> bytes:
        """Return UTF-8 canonical JSON bytes whose hash is package-bound."""

        return _canonical_json(
            {
                "format_version": self.format_version,
                "required_capabilities": [
                    requirement.to_mapping()
                    for requirement in self.required_capabilities
                ],
                "bindings": {
                    name: {"capability_id": capability_id}
                    for name, capability_id in sorted(self.bindings.items())
                },
            }
        )

    @property
    def digest(self) -> str:
        """Return the lowercase SHA-256 digest of canonical requirements bytes."""

        return hashlib.sha256(self.canonical_bytes).hexdigest()


@dataclass(frozen=True)
class CapabilityProvider:
    """A receiver-local implementation eligible for one exact contract."""

    provider_id: str
    contract: CapabilityContract
    availability: ProviderAvailability = ProviderAvailability.AVAILABLE
    conformance_passed: bool = False
    conformance_vector_ids: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        _text(self.provider_id, "provider_id")


@dataclass(frozen=True)
class UnavailableCapability:
    """Redacted requirement outcome with no receiver implementation identity."""

    capability_id: str
    classification: str | None


@dataclass(frozen=True)
class CapabilityResolution:
    """Exact catalog result; selected providers stay internal to workflow host code."""

    status: str
    unavailable: tuple[UnavailableCapability, ...] = ()
    _selected_providers: tuple[CapabilityProvider, ...] = ()

    @property
    def selected_provider_ids(self) -> tuple[str, ...]:
        """Return private IDs for host-only deferred-boundary revalidation."""

        return tuple(provider.provider_id for provider in self._selected_providers)


class CapabilityCatalog:
    """Resolve exact contracts against an immutable receiver-local snapshot."""

    def __init__(
        self,
        built_in_contracts: Sequence[CapabilityContract],
        providers: Sequence[CapabilityProvider],
        *,
        availability_provider: Callable[[CapabilityProvider], ProviderAvailability]
        | None = None,
    ) -> None:
        self._contracts = tuple(built_in_contracts)
        self._providers = tuple(providers)
        self._availability_provider = availability_provider or (
            lambda provider: provider.availability
        )
        contract_keys = tuple(
            (item.capability_id, item.contract_version, item.contract_digest)
            for item in self._contracts
        )
        if len(set(contract_keys)) != len(contract_keys):
            raise CapabilityError("capability contracts must be unique")

    def resolve(self, requirements: CapabilityRequirements) -> CapabilityResolution:
        """Resolve requirements without disclosing provider identity on failure."""

        selected: list[CapabilityProvider] = []
        unavailable: list[UnavailableCapability] = []
        for requirement in requirements.required_capabilities:
            contract = self._contract_for(requirement)
            if contract is None or not set(requirement.required_features).issubset(
                contract.features
            ):
                unavailable.append(
                    UnavailableCapability(requirement.capability_id, None)
                )
                continue
            provider = self._provider_for(contract)
            if provider is None:
                unavailable.append(
                    UnavailableCapability(requirement.capability_id, None)
                )
            else:
                availability = self._availability_provider(provider)
                if availability is not ProviderAvailability.AVAILABLE:
                    unavailable.append(
                        UnavailableCapability(
                            requirement.capability_id, availability.value
                        )
                    )
                else:
                    selected.append(provider)
        if unavailable:
            return CapabilityResolution("capability_unavailable", tuple(unavailable))
        return CapabilityResolution("eligible", (), tuple(selected))

    def revalidate(
        self,
        provider_ids: Sequence[str],
        *,
        availability: Mapping[str, ProviderAvailability] | None = None,
    ) -> CapabilityResolution:
        """Fail closed if an already-selected private provider becomes unavailable."""

        availability = availability or {}
        unavailable = []
        selected = []
        for provider_id in provider_ids:
            provider = next(
                (item for item in self._providers if item.provider_id == provider_id),
                None,
            )
            state = availability.get(
                provider_id,
                self._availability_provider(provider) if provider else None,
            )
            if provider is None or state is not ProviderAvailability.AVAILABLE:
                capability_id = (
                    provider.contract.capability_id if provider else "unknown"
                )
                classification = (
                    state.value if isinstance(state, ProviderAvailability) else None
                )
                unavailable.append(UnavailableCapability(capability_id, classification))
            else:
                selected.append(provider)
        if unavailable:
            return CapabilityResolution("capability_unavailable", tuple(unavailable))
        return CapabilityResolution("eligible", (), tuple(selected))

    def _contract_for(
        self, requirement: CapabilityRequirement
    ) -> CapabilityContract | None:
        return next(
            (
                contract
                for contract in self._contracts
                if (
                    contract.capability_id,
                    contract.contract_version,
                    contract.contract_digest,
                )
                == (
                    requirement.capability_id,
                    requirement.contract_version,
                    requirement.contract_digest,
                )
            ),
            None,
        )

    def _provider_for(self, contract: CapabilityContract) -> CapabilityProvider | None:
        required_vectors = _BUILTIN_CONFORMANCE_VECTORS.get(_contract_key(contract), ())
        return next(
            (
                provider
                for provider in self._providers
                if (
                    provider.conformance_passed
                    and provider.contract == contract
                    and set(required_vectors).issubset(provider.conformance_vector_ids)
                )
            ),
            None,
        )


def selected_provider_id_for_requirement(
    *,
    requirements: CapabilityRequirements,
    selected_provider_ids: Sequence[str],
    capability_id: str,
) -> str:
    """Return one prior selection by canonical requirement position."""

    selected = tuple(selected_provider_ids)
    declared = requirements.required_capabilities
    if len(selected) != len(declared) or not all(
        isinstance(provider_id, str) and provider_id for provider_id in selected
    ):
        raise CapabilityError("selected capability providers are invalid")
    matches = [
        index
        for index, requirement in enumerate(declared)
        if requirement.capability_id == capability_id
    ]
    if len(matches) != 1:
        raise CapabilityError("selected capability provider is unavailable")
    return selected[matches[0]]


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        _normalize(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _contract_key(contract: CapabilityContract) -> tuple[str, str, str]:
    return (
        contract.capability_id,
        contract.contract_version,
        contract.contract_digest,
    )


def _normalize(value: object) -> object:
    if isinstance(value, str):
        normalized = unicodedata.normalize("NFC", value)
        if normalized != value:
            raise CapabilityError("capability values must use NFC Unicode")
        return value
    if isinstance(value, dict):
        return {str(key): _normalize(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_normalize(item) for item in value]
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    raise CapabilityError("capability canonical JSON value is invalid")


def _text(value: object, name: str) -> None:
    if (
        not isinstance(value, str)
        or not value
        or unicodedata.normalize("NFC", value) != value
    ):
        raise CapabilityError(f"{name} must be a non-empty NFC string")


def _digest(value: object, name: str) -> None:
    if not (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    ):
        raise CapabilityError(f"{name} must be a lowercase SHA-256 digest")


def _canonical_strings(values: Sequence[str], name: str) -> None:
    if (
        tuple(values) != tuple(sorted(values))
        or len(set(values)) != len(values)
        or any(not isinstance(value, str) or not value for value in values)
    ):
        raise CapabilityError(f"{name} must be sorted unique non-empty strings")
    for value in values:
        _text(value, name)


def _requirement_from_mapping(value: object) -> CapabilityRequirement:
    if not isinstance(value, Mapping) or set(value) != {
        "capability_id",
        "contract_version",
        "contract_digest",
        "required_features",
    }:
        raise CapabilityError("capability requirement is invalid")
    features = value["required_features"]
    if not isinstance(features, list):
        raise CapabilityError("required_features must be a list")
    return CapabilityRequirement(
        capability_id=value["capability_id"],
        contract_version=value["contract_version"],
        contract_digest=value["contract_digest"],
        required_features=tuple(features),
    )


def _published_contract(
    capability_id: str, contract_version: str, features: tuple[str, ...]
) -> CapabilityContract:
    document = {
        "capability_id": capability_id,
        "contract_version": contract_version,
        "features": list(features),
    }
    return CapabilityContract(
        capability_id=capability_id,
        contract_version=contract_version,
        contract_digest=hashlib.sha256(_canonical_json(document)).hexdigest(),
        features=features,
    )


BUILTIN_CAPABILITY_CONTRACTS = (
    _published_contract("model.execution.llama-cpp.v1", "1", ("multimodal",)),
    _published_contract("model.generate.v1", "1", ("structured",)),
)
"""DAR-owned built-in contracts that workflow packages may require."""


_BUILTIN_CONFORMANCE_VECTORS = {
    _contract_key(BUILTIN_CAPABILITY_CONTRACTS[0]): frozenset(
        {
            "requested_features",
            "output_integrity",
            "resource_limits",
            "redacted_failure",
        }
    ),
    _contract_key(BUILTIN_CAPABILITY_CONTRACTS[1]): frozenset(
        {"bounded_io", "deadline", "structured_value", "redacted_failure"}
    ),
}
