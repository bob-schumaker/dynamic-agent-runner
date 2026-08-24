"""Closed no-tool DAR execution for registered local workflow packages."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping
from uuid import uuid4

from dynamic_agent_runner import (
    create_host_tool_registry,
    load_agent_package_workflow,
    run_agent_workflow,
)
from dynamic_agent_runner.openai_client import OpenAIClientAdapter

from dar_workflow_server.catalog import PackageCatalog, PackageCatalogError
from dar_workflow_server.mcp_binding import MCPWorkflowCapabilityBindingControlPlane
from dar_workflow_server.mcp_surfaces import MCPSurfaceSnapshotControlPlane
from dar_workflow_server.mcp_tools import (
    MCPReadOnlyToolClient,
    MCPToolBindingError,
    create_read_only_mcp_tool_bindings,
)
from dar_workflow_server.policy import PolicyCompilationError, compile_workflow_policy
from dar_workflow_server.preparation import (
    PreparedWorkflowInputError,
    WorkflowInvocationPreparationService,
)
from dar_workflow_server.registration import (
    WorkflowRegistration,
    WorkflowRegistrationError,
    WorkflowRegistrationService,
)


class RunDarWorkflowError(ValueError):
    """Raised when a closed workflow-run request cannot be executed."""


@dataclass(frozen=True)
class RunDarWorkflowRequest:
    """The only model-facing run request shape for v1 no-tool workflows."""

    workflow_id: str
    prepared_input_id: str

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> RunDarWorkflowRequest:
        """Parse the closed versioned request without accepting raw input fields."""

        if not isinstance(value, Mapping) or set(value) != {
            "format_version",
            "workflow_id",
            "prepared_input_id",
        }:
            raise RunDarWorkflowError("run request must contain exactly its v1 fields")
        if value.get("format_version") != 1:
            raise RunDarWorkflowError("run request format_version must be 1")
        workflow_id = value.get("workflow_id")
        prepared_input_id = value.get("prepared_input_id")
        if not isinstance(workflow_id, str) or not workflow_id:
            raise RunDarWorkflowError("workflow_id must be a non-empty string")
        if not isinstance(prepared_input_id, str) or not prepared_input_id:
            raise RunDarWorkflowError("prepared_input_id must be a non-empty string")
        return cls(workflow_id, prepared_input_id)


@dataclass(frozen=True)
class RunDarWorkflowResult:
    """A bounded completed result without prompt, paths, or raw trace payloads."""

    status: str
    run_id: str
    output: dict[str, str]


@dataclass(frozen=True)
class DryRunDarWorkflowResult:
    """Non-executing proof that a sealed no-tool run remains runnable."""

    status: str
    workflow_id: str


@dataclass(frozen=True)
class RedactedRunTrace:
    """Minimal wrapper trace metadata that excludes raw workflow input and output."""

    run_id: str
    workflow_id: str
    status: str
    output_byte_count: int


class WorkflowRunner:
    """Run one registered package through a configured strict-local adapter."""

    def __init__(
        self,
        *,
        registrations: WorkflowRegistrationService,
        catalog: PackageCatalog,
        preparation: WorkflowInvocationPreparationService,
        model_adapter: OpenAIClientAdapter,
        mcp_bindings: MCPWorkflowCapabilityBindingControlPlane | None = None,
        mcp_client: MCPReadOnlyToolClient | None = None,
        mcp_surfaces: MCPSurfaceSnapshotControlPlane | None = None,
    ) -> None:
        self._registrations = registrations
        self._catalog = catalog
        self._preparation = preparation
        self._model_adapter = model_adapter
        self._mcp_bindings = mcp_bindings
        self._mcp_client = mcp_client
        self._mcp_surfaces = mcp_surfaces
        self._traces: list[RedactedRunTrace] = []

    def run(
        self, request: RunDarWorkflowRequest, *, now: datetime
    ) -> RunDarWorkflowResult:
        """Preflight, consume, and execute one sealed saved no-tool workflow."""

        run_id = str(uuid4())
        try:
            (
                registration,
                package_root,
                max_steps,
                tool_registry,
                terminal_output_contract,
            ) = self._preflight(request.workflow_id)
            self._validate_adapter(registration)
            sealed = self._preparation.consume(
                request.prepared_input_id, registration=registration, now=now
            )
            prompt = _render_prompt(sealed.prompt, sealed.additional_context)
            final_result = run_agent_workflow(
                package_directory=str(package_root),
                prompt=prompt,
                model_adapter=self._model_adapter,
                tool_registry=tool_registry,
                max_steps=max_steps,
                run_id=run_id,
            )
            output = _terminal_output(final_result, terminal_output_contract)
        except (
            WorkflowRegistrationError,
            PackageCatalogError,
            PolicyCompilationError,
            PreparedWorkflowInputError,
            RunDarWorkflowError,
        ) as error:
            self._traces.append(
                RedactedRunTrace(run_id, request.workflow_id, "failed", 0)
            )
            if isinstance(error, RunDarWorkflowError):
                raise
            raise RunDarWorkflowError("registered workflow run failed") from error
        except Exception as error:
            self._traces.append(
                RedactedRunTrace(run_id, request.workflow_id, "failed", 0)
            )
            raise RunDarWorkflowError("DAR workflow execution failed") from error
        self._traces.append(
            RedactedRunTrace(
                run_id,
                request.workflow_id,
                "completed",
                len(output["message"].encode("utf-8")),
            )
        )
        return RunDarWorkflowResult("completed", run_id, output)

    def traces(self) -> tuple[RedactedRunTrace, ...]:
        """Return copy-safe redacted run metadata for the host audit surface."""

        return tuple(self._traces)

    def dry_run(
        self, request: RunDarWorkflowRequest, *, now: datetime
    ) -> DryRunDarWorkflowResult:
        """Validate a sealed run without consuming input or invoking DAR."""

        try:
            registration, _, _, _, _ = self._preflight(request.workflow_id)
            self._validate_adapter(registration)
            self._preparation.load(
                request.prepared_input_id, registration=registration, now=now
            )
        except (
            WorkflowRegistrationError,
            PackageCatalogError,
            PolicyCompilationError,
            PreparedWorkflowInputError,
            RunDarWorkflowError,
        ) as error:
            if isinstance(error, RunDarWorkflowError):
                raise
            raise RunDarWorkflowError("registered workflow dry run failed") from error
        return DryRunDarWorkflowResult("ready", request.workflow_id)

    def _preflight(
        self, workflow_id: str
    ) -> tuple[WorkflowRegistration, Any, int, Any | None, Mapping[str, Any]]:
        registration = self._registrations.resolve(workflow_id)
        revision = self._catalog.revision(
            registration.package_id, registration.revision_digest
        )
        policy = compile_workflow_policy(revision)
        if policy.policy_digest != registration.policy_digest:
            raise RunDarWorkflowError("registered workflow policy does not match")
        tool_registry = self._tool_registry(policy, registration)
        workflow = load_agent_package_workflow(
            str(revision.package_root), tool_registry=tool_registry
        )
        terminal_output_contract = workflow.runtime_manifest.output_contracts.get(
            policy.task_invocation.terminal_output_schema_ref
        )
        if not isinstance(terminal_output_contract, Mapping):
            raise RunDarWorkflowError("registered terminal output contract is missing")
        return (
            registration,
            revision.package_root,
            policy.limits.max_steps,
            tool_registry,
            terminal_output_contract,
        )

    def _tool_registry(self, policy: Any, registration: WorkflowRegistration) -> Any:
        if not policy.declared_tools:
            if registration.mcp_binding_id is not None:
                raise RunDarWorkflowError("no-tool registration has an MCP binding")
            return None
        if (
            registration.mcp_binding_id is None
            or self._mcp_bindings is None
            or self._mcp_client is None
            or self._mcp_surfaces is None
        ):
            raise RunDarWorkflowError("registered MCP capability is unavailable")
        try:
            return create_host_tool_registry(
                create_read_only_mcp_tool_bindings(
                    policy=policy,
                    binding_id=registration.mcp_binding_id,
                    binding_control=self._mcp_bindings,
                    client=self._mcp_client,
                    surfaces=self._mcp_surfaces,
                )
            )
        except MCPToolBindingError as error:
            raise RunDarWorkflowError(
                "registered MCP capability is unavailable"
            ) from error

    def _validate_adapter(self, registration: WorkflowRegistration) -> None:
        if not self._model_adapter.is_local:
            raise RunDarWorkflowError("configured adapter is not strict local")
        if registration.model_id not in self._model_adapter.models:
            raise RunDarWorkflowError(
                "configured adapter does not advertise registered model"
            )


def _render_prompt(prompt: str, additional_context: str) -> str:
    if not additional_context:
        return prompt
    return f"{prompt}\n\nAdditional context:\n{additional_context}"


def _terminal_output(value: object, contract: Mapping[str, Any]) -> dict[str, str]:
    if not isinstance(value, str) or not value:
        raise RunDarWorkflowError("workflow terminal output is not a message")
    if len(value.encode("utf-8")) > 32 * 1024:
        raise RunDarWorkflowError("workflow terminal output exceeds the response limit")
    output = {"message": value}
    required_fields = contract.get("required_fields")
    if not isinstance(required_fields, list) or any(
        not isinstance(field, str) or not field for field in required_fields
    ):
        raise RunDarWorkflowError("registered terminal output contract is invalid")
    if any(field not in output for field in required_fields):
        raise RunDarWorkflowError(
            "terminal output does not satisfy registered contract"
        )
    return output
