"""Closed contracts for registering an Agent Engineering workflow design."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping


_DECLARATIVE_ARTIFACT_PATHS = frozenset(
    {
        "agent-design.md",
        "agent-graph.mmd",
        "agent-runtime.yaml",
        "workflow-descriptor.yaml",
    }
)


class AuthoringContractError(ValueError):
    """Raised when a skill-to-host authoring contract is not self-contained."""


@dataclass(frozen=True)
class CanonicalWorkflowContract:
    """The workflow intent agreed by Agent Engineering before registration."""

    workflow_name: str
    model_id: str
    adapter_id: str
    input_kind: str
    output_contract: str
    required_capabilities: tuple[str, ...]

    def __post_init__(self) -> None:
        _validate_workflow_name(self.workflow_name)
        _validate_identifier(self.model_id, "model")
        _validate_identifier(self.adapter_id, "adapter")
        _validate_identifier(self.input_kind, "input kind")
        _validate_identifier(self.output_contract, "output contract")
        _validate_capabilities(self.required_capabilities)


@dataclass(frozen=True)
class DeclarativeWorkflowDefinition:
    """A package-relative, non-executable realization of one workflow intent."""

    workflow_name: str
    model_id: str
    adapter_id: str
    input_kind: str
    output_contract: str
    required_capabilities: tuple[str, ...]
    package_artifacts: Mapping[str, str]

    def __post_init__(self) -> None:
        CanonicalWorkflowContract(
            workflow_name=self.workflow_name,
            model_id=self.model_id,
            adapter_id=self.adapter_id,
            input_kind=self.input_kind,
            output_contract=self.output_contract,
            required_capabilities=self.required_capabilities,
        )
        object.__setattr__(
            self,
            "package_artifacts",
            MappingProxyType(_validated_artifacts(self.package_artifacts)),
        )


@dataclass(frozen=True)
class ReadyAuthoredWorkflow:
    """The redacted execution handoff for a saved workflow."""

    workflow_name: str
    input_contract: str
    output_contract: str
    invocation: str

    def __post_init__(self) -> None:
        _validate_workflow_name(self.workflow_name)
        _validate_user_facing_text(self.input_contract, "input contract")
        _validate_user_facing_text(self.output_contract, "output contract")
        _validate_user_facing_text(self.invocation, "invocation")

    def to_mapping(self) -> dict[str, str]:
        """Return the complete user-facing ready result."""

        return {
            "status": "ready",
            "workflow_name": self.workflow_name,
            "input_contract": self.input_contract,
            "output_contract": self.output_contract,
            "invocation": self.invocation,
        }


@dataclass(frozen=True)
class UnavailableAuthoredWorkflow:
    """The redacted result when a configured capability cannot run a design."""

    capability: str
    requirement: str

    def __post_init__(self) -> None:
        _validate_identifier(self.capability, "capability")
        _validate_user_facing_text(self.requirement, "requirement")

    def to_mapping(self) -> dict[str, str]:
        """Return the complete user-facing unavailable result."""

        return {
            "status": "unavailable",
            "capability": self.capability,
            "requirement": self.requirement,
        }


def validate_definition(
    *,
    contract: CanonicalWorkflowContract,
    definition: DeclarativeWorkflowDefinition,
) -> None:
    """Reject a definition whose declared workflow intent differs from its contract."""

    if not isinstance(contract, CanonicalWorkflowContract) or not isinstance(
        definition, DeclarativeWorkflowDefinition
    ):
        raise AuthoringContractError("authoring contract is invalid")
    if (
        contract.workflow_name,
        contract.model_id,
        contract.adapter_id,
        contract.input_kind,
        contract.output_contract,
        contract.required_capabilities,
    ) != (
        definition.workflow_name,
        definition.model_id,
        definition.adapter_id,
        definition.input_kind,
        definition.output_contract,
        definition.required_capabilities,
    ):
        raise AuthoringContractError("workflow definition does not match contract")


def _validated_artifacts(value: Mapping[str, str]) -> dict[str, str]:
    if not isinstance(value, Mapping) or not value:
        raise AuthoringContractError("workflow artifacts are invalid")
    artifacts: dict[str, str] = {}
    for path, content in value.items():
        if not isinstance(path, str) or not isinstance(content, str):
            raise AuthoringContractError("workflow artifact is invalid")
        if path not in _DECLARATIVE_ARTIFACT_PATHS:
            raise AuthoringContractError("workflow artifact is invalid")
        if path in artifacts:
            raise AuthoringContractError("workflow artifacts are invalid")
        artifacts[path] = content
    return artifacts


def _validate_capabilities(value: tuple[str, ...]) -> None:
    if not isinstance(value, tuple) or not value:
        raise AuthoringContractError("required capabilities are invalid")
    if len(set(value)) != len(value):
        raise AuthoringContractError("required capabilities are invalid")
    for capability in value:
        _validate_identifier(capability, "capability")


def _validate_identifier(value: object, name: str) -> None:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 128
        or value.startswith("/")
        or "\x00" in value
    ):
        raise AuthoringContractError(f"{name} is invalid")


def _validate_workflow_name(value: object) -> None:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 64
        or any(
            character not in "abcdefghijklmnopqrstuvwxyz0123456789-_"
            for character in value
        )
    ):
        raise AuthoringContractError("workflow name is invalid")


def _validate_user_facing_text(value: object, name: str) -> None:
    if not isinstance(value, str) or not value:
        raise AuthoringContractError(f"{name} is invalid")
    lowered = value.lower()
    if any(
        marker in lowered
        for marker in (
            "material_set_id",
            "output_id",
            "profile_id",
            "receipt",
            "/private/",
            "/tmp/",
            "/users/",
        )
    ):
        raise AuthoringContractError(f"{name} is invalid")
