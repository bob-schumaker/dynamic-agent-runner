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
from dynamic_agent_runner.openai_client import (
    AsyncOpenAIClientAdapter,
    OpenAIClientAdapter,
)

from dynamic_agent_runner.workflow_host.action_ledger import WorkflowActionLedger
from dynamic_agent_runner.workflow_host.argument_provenance import (
    ArgumentVerificationContext,
)
from dynamic_agent_runner.workflow_host.approvals import WorkflowApprovalStore
from dynamic_agent_runner.workflow_host.authorized_tools import (
    AuthorizedMCPToolClient,
    AuthorizedToolBindingError,
    LocalActionApprovalBroker,
    create_authorized_mcp_tool_bindings,
)
from dynamic_agent_runner.workflow_host.catalog import (
    PackageCatalog,
    PackageCatalogError,
)
from dynamic_agent_runner.workflow_host.mcp_binding import (
    MCPWorkflowCapabilityBindingControlPlane,
)
from dynamic_agent_runner.workflow_host.mcp_surfaces import (
    MCPSurfaceSnapshotControlPlane,
)
from dynamic_agent_runner.workflow_host.mcp_tools import (
    MCPToolBindingError,
    create_read_only_mcp_tool_bindings,
)
from dynamic_agent_runner.workflow_host.policy import (
    PolicyCompilationError,
    compile_workflow_policy,
)
from dynamic_agent_runner.workflow_host.preparation import (
    PreparedWorkflowInputError,
    SealedWorkflowInput,
    WorkflowInvocationPreparationService,
)
from dynamic_agent_runner.workflow_host.registration import (
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
        model_adapter: OpenAIClientAdapter | AsyncOpenAIClientAdapter,
        configured_profile_id: str,
        mcp_bindings: MCPWorkflowCapabilityBindingControlPlane | None = None,
        mcp_client: AuthorizedMCPToolClient | None = None,
        mcp_surfaces: MCPSurfaceSnapshotControlPlane | None = None,
        action_ledger: WorkflowActionLedger | None = None,
        approval_store: WorkflowApprovalStore | None = None,
    ) -> None:
        self._registrations = registrations
        self._catalog = catalog
        self._preparation = preparation
        self._model_adapter = model_adapter
        self._configured_profile_id = configured_profile_id
        self._mcp_bindings = mcp_bindings
        self._mcp_client = mcp_client
        self._mcp_surfaces = mcp_surfaces
        self._action_ledger = action_ledger
        self._approval_store = approval_store
        self._traces: list[RedactedRunTrace] = []

    def run(
        self,
        request: RunDarWorkflowRequest,
        *,
        now: datetime,
        approval_broker: LocalActionApprovalBroker | None = None,
    ) -> RunDarWorkflowResult:
        """Preflight, consume, and execute one sealed saved workflow."""

        run_id = str(uuid4())
        try:
            (
                registration,
                package_root,
                policy,
                terminal_output_contract,
            ) = self._preflight(request.workflow_id)
            self._validate_adapter(registration)
            sealed = self._preparation.load(
                request.prepared_input_id, registration=registration, now=now
            )
            tool_registry = self._tool_registry(
                policy,
                registration,
                sealed=sealed,
                run_id=run_id,
                approval_broker=approval_broker,
                now=now,
            )
            sealed = self._preparation.consume(
                request.prepared_input_id, registration=registration, now=now
            )
            prompt = _render_prompt(sealed.prompt, sealed.additional_context)
            final_result = run_agent_workflow(
                package_directory=str(package_root),
                prompt=prompt,
                model_adapter=self._model_adapter,
                tool_registry=tool_registry,
                max_steps=policy.limits.max_steps,
                model_adapter_coverage="strict",
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
            registration, _, policy, _ = self._preflight(request.workflow_id)
            self._validate_adapter(registration)
            sealed = self._preparation.load(
                request.prepared_input_id, registration=registration, now=now
            )
            self._tool_registry(
                policy, registration, sealed=sealed, run_id="dry-run", now=now
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
    ) -> tuple[WorkflowRegistration, Any, Any, Mapping[str, Any]]:
        registration = self._registrations.resolve(workflow_id)
        revision = self._catalog.revision(
            registration.package_id, registration.revision_digest
        )
        policy = compile_workflow_policy(revision)
        if policy.policy_digest != registration.policy_digest:
            raise RunDarWorkflowError("registered workflow policy does not match")
        workflow = load_agent_package_workflow(str(revision.package_root))
        terminal_output_contract = workflow.runtime_manifest.output_contracts.get(
            policy.task_invocation.terminal_output_schema_ref
        )
        if not isinstance(terminal_output_contract, Mapping):
            raise RunDarWorkflowError("registered terminal output contract is missing")
        return (
            registration,
            revision.package_root,
            policy,
            terminal_output_contract,
        )

    def _tool_registry(
        self,
        policy: Any,
        registration: WorkflowRegistration,
        *,
        sealed: SealedWorkflowInput,
        run_id: str,
        approval_broker: LocalActionApprovalBroker | None = None,
        now: datetime,
    ) -> Any:
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
            if "mcp_side_effects" in policy.required_capabilities:
                if self._action_ledger is None:
                    raise RunDarWorkflowError("external action audit is unavailable")
                if approval_broker is not None and self._approval_store is None:
                    raise RunDarWorkflowError("local approval is unavailable")
                artifacts = self._preparation.materialize_workspace_artifacts(
                    sealed, registration=registration, now=now
                )
                return create_host_tool_registry(
                    create_authorized_mcp_tool_bindings(
                        policy=policy,
                        registration=registration,
                        binding_id=registration.mcp_binding_id,
                        binding_control=self._mcp_bindings,
                        client=self._mcp_client,
                        surfaces=self._mcp_surfaces,
                        provenance=ArgumentVerificationContext(
                            original_prompt=sealed.prompt,
                            sealed_fields=sealed.structured_input,
                            artifact_values={
                                artifact.role: artifact.content
                                for artifact in artifacts
                            },
                            constants={},
                            argument_policies={},
                        ),
                        workspace_artifact_hashes={
                            artifact.artifact_id: artifact.content_hash
                            for artifact in artifacts
                        },
                        trace_correlation=run_id,
                        ledger=self._action_ledger,
                        approval_store=(
                            self._approval_store
                            if approval_broker is not None
                            else None
                        ),
                        approval_broker=approval_broker,
                        now=now,
                    )
                )
            return create_host_tool_registry(
                create_read_only_mcp_tool_bindings(
                    policy=policy,
                    binding_id=registration.mcp_binding_id,
                    binding_control=self._mcp_bindings,
                    client=self._mcp_client,
                    surfaces=self._mcp_surfaces,
                )
            )
        except (AuthorizedToolBindingError, MCPToolBindingError) as error:
            raise RunDarWorkflowError(
                "registered MCP capability is unavailable"
            ) from error

    def _validate_adapter(self, registration: WorkflowRegistration) -> None:
        if registration.profile_id != self._configured_profile_id:
            raise RunDarWorkflowError(
                "registered workflow is not bound to the configured profile"
            )
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
