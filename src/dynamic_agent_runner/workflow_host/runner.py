"""Closed no-tool DAR execution for registered local workflow packages."""

from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Mapping
from uuid import uuid4

from dynamic_agent_runner import (
    create_host_tool_registry,
    load_agent_package_workflow,
    run_agent_workflow,
)
from dynamic_agent_runner.guardrails import InMemoryGuardrailRegistry
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
    WorkflowRunApprovalGrants,
    create_authorized_mcp_tool_bindings,
)
from dynamic_agent_runner.workflow_host.catalog import (
    PackageCatalog,
    PackageCatalogError,
)
from dynamic_agent_runner.workflow_host.capabilities import CapabilityCatalog
from dynamic_agent_runner.workflow_host.execution_descriptors import (
    ExecutionDescriptorValidatorRegistry,
)
from dynamic_agent_runner.workflow_host.generation_resource_budgets import (
    GenerationExecutionHostPolicy,
)
from dynamic_agent_runner.workflow_host.model_execution_binding import (
    ModelExecutionBindingError,
    ModelRunnerRegistry,
)
from dynamic_agent_runner.workflow_host.fastmail_triage import (
    FastmailTriageBindingError,
    create_fastmail_triage_search_binding,
    default_fastmail_triage_query,
    project_fastmail_triage_result,
)
from dynamic_agent_runner.workflow_host.fastmail_triage_report import (
    FastmailTriageReportError,
    normalize_fastmail_triage_report,
)
from dynamic_agent_runner.workflow_host.mcp_binding import (
    MCPWorkflowCapabilityBindingControlPlane,
)
from dynamic_agent_runner.workflow_host.mcp_surfaces import (
    MCPSurfaceSnapshotControlPlane,
)
from dynamic_agent_runner.workflow_host.mcp_tools import (
    MCPToolCallCounter,
    MCPToolBindingError,
    create_read_only_mcp_tool_bindings,
)
from dynamic_agent_runner.workflow_host.local_tools import (
    LocalToolDefinition,
    LocalToolExecutor,
    LocalToolSandbox,
    LocalToolSandboxError,
    create_local_tool_binding,
)
from dynamic_agent_runner.workflow_host.artifact_tools import (
    ArtifactToolBindingError,
    ReviewedArtifactToolExecutor,
    create_reviewed_artifact_tool_binding,
)
from dynamic_agent_runner.workflow_host.reviewed_tool_packages import (
    ReviewedToolPackageControlPlane,
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
from dynamic_agent_runner.workflow_host.workspace_ingress import (
    MaterializedWorkspaceImageArtifact,
    MaterializedWorkspaceBinaryArtifact,
    OpaqueBinaryArtifactReference,
)
from dynamic_agent_runner.workflow_host.profiles import (
    FASTMAIL_TRIAGE_LLAMA_CPP_ADAPTER_ID,
    InstallationIdentityProvider,
    LocalModelProfile,
)
from dynamic_agent_runner.workflow_host.registration import (
    WorkflowRegistration,
    WorkflowRegistrationError,
    WorkflowRegistrationService,
)
from dynamic_agent_runner.workflow_host.state import (
    OpaqueRecordError,
    PrivateStateStore,
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


@dataclass(frozen=True)
class TerminalProcessorDiagnostic:
    """Authenticated local-only retained processor input and admitted output."""

    original: bytes
    original_digest: str
    admitted: bytes | None
    admitted_digest: str | None
    repair_categories: tuple[str, ...]


@dataclass(frozen=True)
class DebugGeneratedFragment:
    """One authenticated local-only generated fragment from a debug run."""

    content: str
    exhausted: bool
    generated_tokens: int | None
    runner_max_new_tokens: int | None
    backend_max_new_tokens: int | None


@dataclass(frozen=True)
class DebugWorkflowDiagnostic:
    """One local-principal debug record without ordinary trace exposure."""

    diagnostic_id: str
    run_id: str | None
    outcome: str
    fragments: tuple[DebugGeneratedFragment, ...]
    terminal: TerminalProcessorDiagnostic | None
    retention_limited: bool


@dataclass(frozen=True)
class DebugRunWorkflowResult:
    """The debug-only result surface with no retained content."""

    status: str
    diagnostic_id: str
    result: RunDarWorkflowResult | None


_MAX_DEBUG_DIAGNOSTIC_BYTES = 8 * 1024 * 1024


class _DebugDiagnosticCollector:
    """Bounded in-memory collector attached only for one debug invocation."""

    def __init__(self, diagnostic_id: str) -> None:
        self.diagnostic_id = diagnostic_id
        self.run_id: str | None = None
        self.fragments: list[DebugGeneratedFragment] = []
        self.terminal: TerminalProcessorDiagnostic | None = None
        self.retention_limited = False
        self._bytes = 0

    def set_run_id(self, run_id: str) -> None:
        self.run_id = run_id

    def record_fragment(self, value: object) -> None:
        content = getattr(value, "content", None)
        exhausted = getattr(value, "exhausted", None)
        generated_tokens = getattr(value, "generated_tokens", None)
        runner_max_new_tokens = getattr(value, "runner_max_new_tokens", None)
        backend_max_new_tokens = getattr(value, "backend_max_new_tokens", None)
        if (
            not isinstance(content, str)
            or not isinstance(exhausted, bool)
            or (generated_tokens is not None and not isinstance(generated_tokens, int))
            or not _optional_generation_limit(runner_max_new_tokens)
            or not _optional_generation_limit(backend_max_new_tokens)
        ):
            self.retention_limited = True
            return
        byte_count = len(content.encode("utf-8"))
        if self._bytes + byte_count > _MAX_DEBUG_DIAGNOSTIC_BYTES:
            self.retention_limited = True
            return
        self._bytes += byte_count
        self.fragments.append(
            DebugGeneratedFragment(
                content,
                exhausted,
                generated_tokens,
                runner_max_new_tokens,
                backend_max_new_tokens,
            )
        )

    def record_terminal(self, terminal: TerminalProcessorDiagnostic | None) -> None:
        """Retain terminal diagnostics only when they fit this run's byte cap."""

        if terminal is None:
            return
        byte_count = len(terminal.original) + len(terminal.admitted or b"")
        if self._bytes + byte_count > _MAX_DEBUG_DIAGNOSTIC_BYTES:
            self.retention_limited = True
            return
        self._bytes += byte_count
        self.terminal = terminal


class _SealedArtifactReader:
    """Expose one already verified private binary only to its host tool binding."""

    def __init__(self, artifact: MaterializedWorkspaceBinaryArtifact) -> None:
        self._artifact = artifact

    def read(self, reference: OpaqueBinaryArtifactReference) -> bytes:
        if reference != _opaque_reference(self._artifact):
            raise RunDarWorkflowError("sealed artifact is unavailable")
        return self._artifact.content


def _opaque_reference(
    artifact: MaterializedWorkspaceBinaryArtifact,
) -> OpaqueBinaryArtifactReference:
    return OpaqueBinaryArtifactReference(
        artifact_id=artifact.artifact_id,
        content_hash=artifact.content_hash,
        byte_count=len(artifact.content),
        role=artifact.role,
        media_type=artifact.media_type,
    )


class WorkflowRunner:
    """Run one registered package through its configured host execution profile."""

    def __init__(
        self,
        *,
        registrations: WorkflowRegistrationService,
        catalog: PackageCatalog,
        preparation: WorkflowInvocationPreparationService,
        model_adapter: OpenAIClientAdapter | AsyncOpenAIClientAdapter,
        configured_profile: LocalModelProfile,
        mcp_bindings: MCPWorkflowCapabilityBindingControlPlane | None = None,
        mcp_client: AuthorizedMCPToolClient | None = None,
        mcp_surfaces: MCPSurfaceSnapshotControlPlane | None = None,
        action_ledger: WorkflowActionLedger | None = None,
        approval_store: WorkflowApprovalStore | None = None,
        local_tool_executor: LocalToolExecutor | None = None,
        reviewed_tool_packages: ReviewedToolPackageControlPlane | None = None,
        reviewed_artifact_tool_executors: Mapping[str, ReviewedArtifactToolExecutor]
        | None = None,
        terminal_diagnostic_store: PrivateStateStore | None = None,
        terminal_diagnostic_owner: str | None = None,
        capability_catalog: CapabilityCatalog | None = None,
        model_runner_registry: ModelRunnerRegistry | None = None,
        descriptor_validators: ExecutionDescriptorValidatorRegistry | None = None,
        generation_execution_host_policy: GenerationExecutionHostPolicy | None = None,
    ) -> None:
        self._registrations = registrations
        self._catalog = catalog
        self._preparation = preparation
        self._model_adapter = model_adapter
        self._configured_profile = configured_profile
        self._mcp_bindings = mcp_bindings
        self._mcp_client = mcp_client
        self._mcp_surfaces = mcp_surfaces
        self._action_ledger = action_ledger
        self._approval_store = approval_store
        self._local_tool_executor = local_tool_executor
        self._reviewed_tool_packages = reviewed_tool_packages
        self._reviewed_artifact_tool_executors = dict(
            reviewed_artifact_tool_executors or {}
        )
        self._terminal_diagnostic_store = terminal_diagnostic_store
        self._capability_catalog = capability_catalog
        self._model_runner_registry = model_runner_registry
        self._descriptor_validators = descriptor_validators
        self._generation_execution_host_policy = generation_execution_host_policy
        self._terminal_diagnostic_owner = (
            terminal_diagnostic_owner or InstallationIdentityProvider().principal
        )
        self._traces: list[RedactedRunTrace] = []

    def run(
        self,
        request: RunDarWorkflowRequest,
        *,
        now: datetime,
        approval_broker: LocalActionApprovalBroker | None = None,
        guardrail_registry: InMemoryGuardrailRegistry | None = None,
        _on_run_id: Callable[[str], None] | None = None,
    ) -> RunDarWorkflowResult:
        """Preflight, consume, and execute one sealed saved workflow."""

        run_id = str(uuid4())
        if _on_run_id is not None:
            _on_run_id(run_id)
        try:
            (
                registration,
                package_root,
                policy,
                terminal_output_contract,
            ) = self._preflight(request.workflow_id)
            self._validate_model_execution_binding(policy)
            self._validate_adapter(registration)
            self._validate_declared_response_formats(package_root)
            self._validate_guardrail_registry(package_root, guardrail_registry)
            sealed = self._preparation.load(
                request.prepared_input_id, registration=registration, now=now
            )
            tool_registry = self._tool_registry(
                policy,
                registration,
                package_root=package_root,
                sealed=sealed,
                run_id=run_id,
                approval_broker=approval_broker,
                now=now,
            )
            sealed = self._preparation.consume(
                request.prepared_input_id, registration=registration, now=now
            )
            prompt = _render_prompt(sealed.prompt, sealed.additional_context)
            payload = self._sealed_converter_payload_for_run(
                policy=policy,
                package_root=Path(package_root),
                sealed=sealed,
                registration=registration,
                now=now,
            )
            image = (
                None
                if payload is not None
                else self._sealed_image_for_run(
                    policy=policy, sealed=sealed, registration=registration, now=now
                )
            )
            try:
                final_result = run_agent_workflow(
                    package_directory=str(package_root),
                    prompt=prompt,
                    model_adapter=self._model_adapter,
                    tool_registry=tool_registry,
                    guardrail_registry=guardrail_registry,
                    max_steps=policy.limits.max_steps,
                    model_adapter_coverage="strict",
                    run_id=run_id,
                )
            finally:
                self._clear_sealed_converter_payload(payload)
                self._clear_sealed_image(image)
            processed_result = self._process_terminal_output(
                policy=policy,
                package_root=Path(package_root),
                value=final_result,
                run_id=run_id,
                now=now,
            )
            output = _terminal_output(
                processed_result,
                terminal_output_contract,
                adapter_id=self._configured_profile.adapter_id,
            )
            self._validate_terminal_output(
                policy=policy, package_root=Path(package_root), output=output
            )
        except asyncio.CancelledError:
            self._traces.append(
                RedactedRunTrace(run_id, request.workflow_id, "failed", 0)
            )
            raise
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

    def run_debug(
        self,
        request: RunDarWorkflowRequest,
        *,
        now: datetime,
        approval_broker: LocalActionApprovalBroker | None = None,
        guardrail_registry: InMemoryGuardrailRegistry | None = None,
    ) -> DebugRunWorkflowResult:
        """Run once with authenticated local-only intermediate retention."""

        collector = _DebugDiagnosticCollector(str(uuid4()))
        setter = getattr(self._model_adapter, "set_debug_fragment_recorder", None)
        if not callable(setter):
            raise RunDarWorkflowError("debug diagnostic is unavailable")
        setter(collector.record_fragment)
        outcome = "failed"
        result: RunDarWorkflowResult | None = None
        try:
            result = self.run(
                request,
                now=now,
                approval_broker=approval_broker,
                guardrail_registry=guardrail_registry,
                _on_run_id=collector.set_run_id,
            )
            outcome = "completed"
        except asyncio.CancelledError:
            outcome = "cancelled"
            raise
        except RunDarWorkflowError:
            pass
        finally:
            setter(None)
            self._retain_debug_diagnostic(collector, outcome=outcome, now=now)
        return DebugRunWorkflowResult(outcome, collector.diagnostic_id, result)

    def traces(self) -> tuple[RedactedRunTrace, ...]:
        """Return copy-safe redacted run metadata for the host audit surface."""

        return tuple(self._traces)

    @property
    def local_tool_execution_available(self) -> bool:
        """Report whether this host can execute its declared local-tool ABI."""

        return self._local_tool_executor is not None

    def validate_artifact_capability(
        self, *, workflow_id: str, input_kind: str
    ) -> None:
        """Reject artifact kinds that the exact configured profile cannot consume."""

        if input_kind != "image_artifact":
            raise RunDarWorkflowError("workflow artifact input is invalid")
        registration, _, _, _ = self._preflight(workflow_id)
        self._validate_adapter(registration)
        if "multimodal_input" not in self._configured_profile.capabilities:
            raise RunDarWorkflowError("configured profile lacks multimodal_input")
        if not _adapter_supports(self._model_adapter, "multimodal_input"):
            raise RunDarWorkflowError("configured adapter lacks multimodal_input")

    def _sealed_image_for_run(
        self,
        *,
        policy: Any,
        sealed: SealedWorkflowInput,
        registration: WorkflowRegistration,
        now: datetime,
    ) -> MaterializedWorkspaceImageArtifact | None:
        if not any(
            media_type.startswith("image/")
            for media_type in policy.workspace.accepted_input_types
        ):
            return None
        self.validate_artifact_capability(
            workflow_id=registration.workflow_id, input_kind="image_artifact"
        )
        images = self._preparation.materialize_workspace_images(
            sealed, registration=registration, now=now
        )
        if len(images) != 1:
            raise RunDarWorkflowError("registered workflow requires one sealed image")
        bind = getattr(self._model_adapter, "bind_sealed_image", None)
        if not callable(bind):
            raise RunDarWorkflowError("configured adapter lacks multimodal_input")
        bind(content=images[0].content, media_type=images[0].media_type)
        return images[0]

    def _sealed_converter_payload_for_run(
        self,
        *,
        policy: Any,
        package_root: Path,
        sealed: SealedWorkflowInput,
        registration: WorkflowRegistration,
        now: datetime,
    ) -> MaterializedWorkspaceBinaryArtifact | None:
        """Bind opaque bytes only to the workflow's exact converter-capable adapter."""

        converter = policy.input_converter
        if converter is None:
            return None
        self._bind_generation_budget(policy)
        if (
            getattr(self._model_adapter, "input_converter_contract_id", None)
            != converter.compatible_runner_contract_id
        ):
            raise RunDarWorkflowError("configured adapter lacks input converter")
        worker_payload = self._bind_worker_converter_payload(
            converter=converter,
            package_root=package_root,
            sealed=sealed,
            registration=registration,
            now=now,
        )
        if worker_payload is not None:
            return worker_payload
        bind_converter = getattr(self._model_adapter, "bind_input_converter", None)
        if not callable(bind_converter):
            raise RunDarWorkflowError("configured adapter lacks input converter")
        try:
            bind_converter(package_root=package_root, converter=converter)
        except Exception as error:  # noqa: BLE001 - adapter package loaders vary.
            raise RunDarWorkflowError(
                "sealed converter package is unavailable"
            ) from error
        try:
            binaries = self._preparation.materialize_workspace_binaries(
                sealed, registration=registration, now=now
            )
        except PreparedWorkflowInputError as error:
            raise RunDarWorkflowError(
                "sealed converter input is unavailable"
            ) from error
        if len(binaries) != 1 or len(binaries[0].content) > converter.max_input_bytes:
            raise RunDarWorkflowError("sealed converter input is unavailable")
        bind = getattr(self._model_adapter, "bind_sealed_payload", None)
        if not callable(bind):
            raise RunDarWorkflowError("configured adapter lacks input converter")
        bind(content=binaries[0].content)
        return binaries[0]

    def _bind_worker_converter_payload(
        self,
        *,
        converter: object,
        package_root: Path,
        sealed: SealedWorkflowInput,
        registration: WorkflowRegistration,
        now: datetime,
    ) -> MaterializedWorkspaceBinaryArtifact | None:
        """Bind worker-only converter inputs without loading converter code here."""

        bind = getattr(self._model_adapter, "bind_worker_converter_payload", None)
        if not callable(bind):
            return None
        try:
            binaries = self._preparation.materialize_workspace_binaries(
                sealed, registration=registration, now=now
            )
        except PreparedWorkflowInputError as error:
            raise RunDarWorkflowError(
                "sealed converter input is unavailable"
            ) from error
        if len(binaries) != 1 or len(binaries[0].content) > converter.max_input_bytes:
            raise RunDarWorkflowError("sealed converter input is unavailable")
        try:
            bind(
                package_root=package_root,
                converter=converter,
                content=binaries[0].content,
            )
        except Exception as error:  # noqa: BLE001 - adapter boundary stays private.
            raise RunDarWorkflowError(
                "sealed converter package is unavailable"
            ) from error
        return binaries[0]

    def _bind_generation_budget(self, policy: Any) -> None:
        """Bind the immutable descriptor budget before converter payload ingress."""

        if policy.execution_descriptor is None:
            return
        binding = policy.model_execution_binding
        host_policy = self._generation_execution_host_policy
        if binding is None or host_policy is None:
            raise RunDarWorkflowError("model generation budget is unavailable")
        bind_budget = getattr(self._model_adapter, "bind_generation_budget", None)
        if not callable(bind_budget):
            raise RunDarWorkflowError("model generation budget is unavailable")
        try:
            bind_budget(
                descriptor=policy.execution_descriptor,
                material_lock_digest=binding.material_lock_digest,
                host_policy=host_policy,
            )
        except Exception as error:  # noqa: BLE001 - adapter admission stays private.
            raise RunDarWorkflowError(
                "model generation budget is unavailable"
            ) from error

    def _clear_sealed_image(
        self, image: MaterializedWorkspaceImageArtifact | None
    ) -> None:
        if image is None:
            return
        clear = getattr(self._model_adapter, "clear_sealed_image", None)
        if callable(clear):
            clear()

    def _clear_sealed_converter_payload(
        self, payload: MaterializedWorkspaceBinaryArtifact | None
    ) -> None:
        if payload is None:
            return
        clear = getattr(self._model_adapter, "clear_sealed_payload", None)
        if callable(clear):
            clear()

    def _validate_terminal_output(
        self, *, policy: Any, package_root: Path, output: Mapping[str, str]
    ) -> None:
        """Run an optional workflow-owned validator after terminal shaping."""

        validator = policy.terminal_output_validator
        if validator is None:
            return
        if self._local_tool_executor is None:
            raise RunDarWorkflowError("terminal output validation is unavailable")
        try:
            evidence = LocalToolSandbox(
                package_root=package_root, execute=self._local_tool_executor
            ).run(
                LocalToolDefinition(
                    tool_id="terminal-output-validator",
                    asset_path=Path(validator.asset_path),
                    accepted_artifact_role="terminal_output",
                    max_input_bytes=32 * 1024,
                    max_output_bytes=validator.max_output_bytes,
                    timeout_seconds=validator.timeout_seconds,
                ),
                artifact_role="terminal_output",
                artifact_bytes=output["message"].encode("utf-8"),
            )
        except LocalToolSandboxError as error:
            raise RunDarWorkflowError("terminal output validation failed") from error
        if evidence.get("valid") is not True:
            raise RunDarWorkflowError("terminal output validation failed")

    def _process_terminal_output(
        self,
        *,
        policy: Any,
        package_root: Path,
        value: object,
        run_id: str,
        now: datetime,
    ) -> str:
        """Pass private terminal bytes through the package-declared processor chain."""

        processors = policy.terminal_output_processors
        if not processors:
            if not isinstance(value, str):
                raise RunDarWorkflowError("workflow terminal output is not a message")
            return value
        if (
            self._local_tool_executor is None
            or self._terminal_diagnostic_store is None
            or not isinstance(value, str)
        ):
            raise RunDarWorkflowError("terminal output processing failed")
        original = value.encode("utf-8")
        current = original
        repair_categories: list[str] = []
        sandbox = LocalToolSandbox(
            package_root=package_root, execute=self._local_tool_executor
        )
        try:
            for index, processor in enumerate(processors):
                evidence = sandbox.run(
                    LocalToolDefinition(
                        tool_id=f"terminal-output-processor-{index}",
                        asset_path=Path(processor.asset_path),
                        accepted_artifact_role="terminal_output",
                        max_input_bytes=32 * 1024,
                        max_output_bytes=processor.max_output_bytes,
                        timeout_seconds=processor.timeout_seconds,
                    ),
                    artifact_role="terminal_output",
                    artifact_bytes=current,
                )
                repair_categories.append(_terminal_processor_category(evidence))
                current = _terminal_processor_output(evidence)
        except (LocalToolSandboxError, ValueError, UnicodeError) as error:
            self._retain_terminal_processor_diagnostic(
                run_id=run_id,
                original=original,
                admitted=None,
                repair_categories=tuple(repair_categories),
                now=now,
            )
            raise RunDarWorkflowError("terminal output processing failed") from error
        self._retain_terminal_processor_diagnostic(
            run_id=run_id,
            original=original,
            admitted=current,
            repair_categories=tuple(repair_categories),
            now=now,
        )
        try:
            return current.decode("utf-8")
        except UnicodeDecodeError as error:
            raise RunDarWorkflowError("terminal output processing failed") from error

    def terminal_processor_diagnostic(
        self, run_id: str, *, now: datetime
    ) -> TerminalProcessorDiagnostic:
        """Load one authenticated local-user diagnostic by its run identity."""

        if (
            not isinstance(run_id, str)
            or not run_id
            or self._terminal_diagnostic_store is None
        ):
            raise RunDarWorkflowError("terminal processor diagnostic is unavailable")
        try:
            records = self._terminal_diagnostic_store.active_records(
                kind="terminal_processor_diagnostic",
                owner=self._terminal_diagnostic_owner,
                now=now,
            )
        except OpaqueRecordError as error:
            raise RunDarWorkflowError(
                "terminal processor diagnostic is unavailable"
            ) from error
        matches = [
            record for _, record in records if record.payload.get("run_id") == run_id
        ]
        if len(matches) != 1:
            raise RunDarWorkflowError("terminal processor diagnostic is unavailable")
        return _terminal_processor_diagnostic(matches[0].payload)

    def debug_diagnostic(
        self, diagnostic_id: str, *, now: datetime
    ) -> DebugWorkflowDiagnostic:
        """Load one authenticated local-user debug diagnostic by its opaque ID."""

        if (
            not isinstance(diagnostic_id, str)
            or not diagnostic_id
            or self._terminal_diagnostic_store is None
        ):
            raise RunDarWorkflowError("debug diagnostic is unavailable")
        try:
            records = self._terminal_diagnostic_store.active_records(
                kind="debug_workflow_diagnostic",
                owner=self._terminal_diagnostic_owner,
                now=now,
            )
        except OpaqueRecordError as error:
            raise RunDarWorkflowError("debug diagnostic is unavailable") from error
        matches = [
            record
            for _, record in records
            if record.payload.get("diagnostic_id") == diagnostic_id
        ]
        if len(matches) != 1:
            raise RunDarWorkflowError("debug diagnostic is unavailable")
        return _debug_diagnostic(matches[0].payload)

    def delete_debug_diagnostic(self, diagnostic_id: str, *, now: datetime) -> None:
        """Revoke one active local-principal debug diagnostic."""

        if (
            not isinstance(diagnostic_id, str)
            or not diagnostic_id
            or self._terminal_diagnostic_store is None
        ):
            raise RunDarWorkflowError("debug diagnostic is unavailable")
        try:
            records = self._terminal_diagnostic_store.active_records(
                kind="debug_workflow_diagnostic",
                owner=self._terminal_diagnostic_owner,
                now=now,
            )
            matches = [
                handle
                for handle, record in records
                if record.payload.get("diagnostic_id") == diagnostic_id
            ]
            if len(matches) != 1:
                raise RunDarWorkflowError("debug diagnostic is unavailable")
            self._terminal_diagnostic_store.revoke(
                matches[0], owner=self._terminal_diagnostic_owner, now=now
            )
        except OpaqueRecordError as error:
            raise RunDarWorkflowError("debug diagnostic is unavailable") from error

    def _retain_terminal_processor_diagnostic(
        self,
        *,
        run_id: str,
        original: bytes,
        admitted: bytes | None,
        repair_categories: tuple[str, ...],
        now: datetime,
    ) -> None:
        if self._terminal_diagnostic_store is None:
            raise RunDarWorkflowError("terminal output processing failed")
        try:
            self._terminal_diagnostic_store.issue(
                kind="terminal_processor_diagnostic",
                owner=self._terminal_diagnostic_owner,
                payload={
                    "run_id": run_id,
                    "original_base64": base64.b64encode(original).decode("ascii"),
                    "original_digest": _digest_bytes(original),
                    "admitted_base64": (
                        base64.b64encode(admitted).decode("ascii")
                        if admitted is not None
                        else None
                    ),
                    "admitted_digest": _digest_bytes(admitted)
                    if admitted is not None
                    else None,
                    "repair_categories": list(repair_categories),
                },
                expires_at=now.astimezone(UTC) + timedelta(days=7),
                now=now,
            )
        except OpaqueRecordError as error:
            raise RunDarWorkflowError("terminal output processing failed") from error

    def _retain_debug_diagnostic(
        self,
        collector: _DebugDiagnosticCollector,
        *,
        outcome: str,
        now: datetime,
    ) -> None:
        if self._terminal_diagnostic_store is None:
            raise RunDarWorkflowError("debug diagnostic is unavailable")
        terminal: TerminalProcessorDiagnostic | None = None
        if collector.run_id is not None:
            try:
                terminal = self.terminal_processor_diagnostic(collector.run_id, now=now)
            except RunDarWorkflowError:
                pass
        collector.record_terminal(terminal)
        try:
            self._terminal_diagnostic_store.issue(
                kind="debug_workflow_diagnostic",
                owner=self._terminal_diagnostic_owner,
                payload={
                    "diagnostic_id": collector.diagnostic_id,
                    "run_id": collector.run_id,
                    "outcome": outcome,
                    "retention_limited": collector.retention_limited,
                    "fragments": [
                        {
                            "content_base64": base64.b64encode(
                                fragment.content.encode("utf-8")
                            ).decode("ascii"),
                            "exhausted": fragment.exhausted,
                            "generated_tokens": fragment.generated_tokens,
                            "runner_max_new_tokens": fragment.runner_max_new_tokens,
                            "backend_max_new_tokens": fragment.backend_max_new_tokens,
                        }
                        for fragment in collector.fragments
                    ],
                    "terminal": _terminal_diagnostic_payload(collector.terminal),
                },
                expires_at=now.astimezone(UTC) + timedelta(days=7),
                now=now,
            )
        except OpaqueRecordError as error:
            raise RunDarWorkflowError("debug diagnostic is unavailable") from error

    def dry_run(
        self, request: RunDarWorkflowRequest, *, now: datetime
    ) -> DryRunDarWorkflowResult:
        """Validate a sealed run without consuming input or invoking DAR."""

        try:
            registration, package_root, policy, _ = self._preflight(request.workflow_id)
            self._validate_adapter(registration)
            self._validate_declared_response_formats(package_root)
            sealed = self._preparation.load(
                request.prepared_input_id, registration=registration, now=now
            )
            self._tool_registry(
                policy,
                registration,
                package_root=package_root,
                sealed=sealed,
                run_id="dry-run",
                require_approval_broker=False,
                now=now,
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
        policy = compile_workflow_policy(
            revision,
            capability_catalog=self._capability_catalog,
            descriptor_validators=self._descriptor_validators,
        )
        if (
            self._capability_catalog is not None
            and policy.selected_capability_provider_ids
            and (
                registration.selected_capability_provider_ids
                != policy.selected_capability_provider_ids
                or self._capability_catalog.revalidate(
                    registration.selected_capability_provider_ids
                ).status
                != "eligible"
            )
        ):
            raise RunDarWorkflowError("package capability requirements are unavailable")
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

    def _validate_model_execution_binding(self, policy: Any) -> None:
        """Resolve locked execution only through an exact receiver registry."""

        binding = policy.model_execution_binding
        if binding is None:
            return
        if self._model_runner_registry is None:
            raise RunDarWorkflowError("registered model runner is unavailable")
        try:
            self._model_runner_registry.resolve(binding)
        except ModelExecutionBindingError as error:
            raise RunDarWorkflowError(
                "registered model runner is unavailable"
            ) from error

    def _validate_guardrail_registry(
        self,
        package_root: Any,
        guardrail_registry: InMemoryGuardrailRegistry | None,
    ) -> None:
        """Require every declared guardrail before consuming a sealed input."""

        workflow = load_agent_package_workflow(str(package_root))
        for declaration in workflow.runtime_manifest.guardrails:
            guardrail_id = declaration.id
            if (
                not isinstance(guardrail_id, str)
                or guardrail_registry is None
                or not guardrail_registry.has_guardrail(guardrail_id)
            ):
                raise RunDarWorkflowError(
                    "registered workflow guardrail is unavailable"
                )

    def _validate_declared_response_formats(self, package_root: Any) -> None:
        """Reject unavailable response constraints before sealed-input binding."""

        workflow = load_agent_package_workflow(str(package_root))
        for node in workflow.runtime_manifest.nodes:
            response_format = node.raw.get("response_format")
            if response_format is None:
                continue
            if not isinstance(response_format, Mapping):
                raise RunDarWorkflowError("registered response format is unsupported")
            if dict(response_format) != {"type": "json_object"}:
                raise RunDarWorkflowError("registered response format is unsupported")
            if not _adapter_supports(self._model_adapter, "json_mode"):
                raise RunDarWorkflowError("configured adapter lacks json_mode")

    def _tool_registry(
        self,
        policy: Any,
        registration: WorkflowRegistration,
        *,
        package_root: Any,
        sealed: SealedWorkflowInput,
        run_id: str,
        approval_broker: LocalActionApprovalBroker | None = None,
        require_approval_broker: bool = True,
        now: datetime,
    ) -> Any:
        if (
            not policy.declared_tools
            and not policy.declared_local_tools
            and not policy.declared_artifact_tools
        ):
            if registration.mcp_binding_id is not None:
                raise RunDarWorkflowError("no-tool registration has an MCP binding")
            return None
        bindings = []
        if policy.declared_local_tools:
            bindings.extend(
                self._local_tool_bindings(
                    policy=policy,
                    registration=registration,
                    package_root=package_root,
                    sealed=sealed,
                    now=now,
                )
            )
        if policy.declared_artifact_tools:
            bindings.extend(
                self._artifact_tool_bindings(
                    policy=policy,
                    registration=registration,
                    sealed=sealed,
                    now=now,
                )
            )
        if not policy.declared_tools:
            return create_host_tool_registry(tuple(bindings))
        bindings.extend(
            self._mcp_tool_bindings(
                policy=policy,
                registration=registration,
                sealed=sealed,
                run_id=run_id,
                approval_broker=approval_broker,
                require_approval_broker=require_approval_broker,
                now=now,
            )
        )
        return create_host_tool_registry(tuple(bindings))

    def _artifact_tool_bindings(
        self,
        *,
        policy: Any,
        registration: WorkflowRegistration,
        sealed: SealedWorkflowInput,
        now: datetime,
    ) -> list[Any]:
        """Bind reviewed opaque-artifact tools to verified private readers."""

        if self._reviewed_tool_packages is None:
            raise RunDarWorkflowError("reviewed artifact tool is unavailable")
        try:
            binaries = self._preparation.materialize_workspace_binaries(
                sealed, registration=registration, now=now
            )
            by_role = {binary.role: binary for binary in binaries}
            bindings = []
            for declaration in policy.declared_artifact_tools:
                binary = by_role.get(declaration.accepted_artifact_role)
                executor = self._reviewed_artifact_tool_executors.get(
                    declaration.reviewed_package_name
                )
                if binary is None or executor is None:
                    raise ArtifactToolBindingError(
                        "reviewed artifact tool is unavailable"
                    )
                bindings.append(
                    create_reviewed_artifact_tool_binding(
                        declaration=declaration,
                        artifact=_opaque_reference(binary),
                        packages=self._reviewed_tool_packages,
                        executor=executor,
                        reader=_SealedArtifactReader(binary),
                    )
                )
            return bindings
        except (ArtifactToolBindingError, PreparedWorkflowInputError) as error:
            raise RunDarWorkflowError(
                "reviewed artifact tool is unavailable"
            ) from error

    def _mcp_tool_bindings(
        self,
        *,
        policy: Any,
        registration: WorkflowRegistration,
        sealed: SealedWorkflowInput,
        run_id: str,
        approval_broker: LocalActionApprovalBroker | None,
        require_approval_broker: bool,
        now: datetime,
    ) -> list[Any]:
        """Create the existing reviewed MCP bindings without local-tool concerns."""

        if (
            registration.mcp_binding_id is None
            or self._mcp_bindings is None
            or self._mcp_client is None
            or self._mcp_surfaces is None
        ):
            raise RunDarWorkflowError("registered MCP capability is unavailable")
        try:
            read_tools = tuple(
                tool for tool in policy.declared_tools if tool.side_effect == "read"
            )
            side_effect_tools = tuple(
                tool for tool in policy.declared_tools if tool.side_effect != "read"
            )
            counter = MCPToolCallCounter(policy.task_invocation.max_total_tool_calls)
            approval_grants = WorkflowRunApprovalGrants()
            bindings = []
            if read_tools:
                if (
                    self._configured_profile.adapter_id
                    == FASTMAIL_TRIAGE_LLAMA_CPP_ADAPTER_ID
                ):
                    bindings.append(
                        create_fastmail_triage_search_binding(
                            policy=policy,
                            binding_id=registration.mcp_binding_id,
                            binding_control=self._mcp_bindings,
                            client=self._mcp_client,
                            surfaces=self._mcp_surfaces,
                            query_builder=default_fastmail_triage_query,
                            result_projector=project_fastmail_triage_result,
                            now=lambda: now,
                        )
                    )
                else:
                    bindings.extend(
                        create_read_only_mcp_tool_bindings(
                            policy=policy,
                            binding_id=registration.mcp_binding_id,
                            binding_control=self._mcp_bindings,
                            client=self._mcp_client,
                            surfaces=self._mcp_surfaces,
                            tools=read_tools,
                            counter=counter,
                        )
                    )
            if side_effect_tools:
                if self._action_ledger is None:
                    raise RunDarWorkflowError("external action audit is unavailable")
                if (
                    require_approval_broker
                    and any(tool.approval_required for tool in side_effect_tools)
                    and (approval_broker is None or self._approval_store is None)
                ):
                    raise RunDarWorkflowError("local approval is unavailable")
                artifacts = self._preparation.materialize_workspace_artifacts(
                    sealed, registration=registration, now=now
                )
                bindings.extend(
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
                        approval_store=self._approval_store
                        if approval_broker
                        else None,
                        approval_broker=approval_broker,
                        tools=side_effect_tools,
                        counter=counter,
                        approval_grants=approval_grants,
                        now=now,
                    )
                )
            return bindings
        except (
            AuthorizedToolBindingError,
            FastmailTriageBindingError,
            MCPToolBindingError,
        ) as error:
            raise RunDarWorkflowError(
                "registered MCP capability is unavailable"
            ) from error

    def _local_tool_bindings(
        self,
        *,
        policy: Any,
        registration: WorkflowRegistration,
        package_root: Any,
        sealed: SealedWorkflowInput,
        now: datetime,
    ) -> list[Any]:
        """Bind each declared local asset to its role-matched sealed bytes."""

        if self._local_tool_executor is None:
            raise RunDarWorkflowError("local tool execution is unavailable")
        try:
            artifacts = self._preparation.materialize_workspace_binaries(
                sealed, registration=registration, now=now
            )
            artifacts_by_role = {artifact.role: artifact for artifact in artifacts}
            sandbox = LocalToolSandbox(
                package_root=Path(package_root), execute=self._local_tool_executor
            )
            bindings = []
            for tool in policy.declared_local_tools:
                artifact = artifacts_by_role.get(tool.accepted_artifact_role)
                if artifact is None:
                    raise LocalToolSandboxError("local tool artifact is unavailable")
                bindings.append(
                    create_local_tool_binding(
                        sandbox=sandbox,
                        definition=LocalToolDefinition(
                            tool_id=tool.tool_id,
                            asset_path=Path(tool.asset_path),
                            accepted_artifact_role=tool.accepted_artifact_role,
                            max_input_bytes=tool.max_input_bytes,
                            max_output_bytes=tool.max_output_bytes,
                            timeout_seconds=tool.timeout_seconds,
                        ),
                        artifact_role=artifact.role,
                        artifact_bytes=artifact.content,
                    )
                )
            return bindings
        except (LocalToolSandboxError, PreparedWorkflowInputError) as error:
            raise RunDarWorkflowError("local tool execution is unavailable") from error

    def _validate_adapter(self, registration: WorkflowRegistration) -> None:
        profile = self._configured_profile
        if registration.profile_id != profile.profile_id:
            raise RunDarWorkflowError(
                "registered workflow is not bound to the configured profile"
            )
        if registration.profile_digest != profile.profile_digest:
            raise RunDarWorkflowError("configured profile does not match registration")
        if registration.model_id != profile.model_id:
            raise RunDarWorkflowError(
                "configured profile model does not match registration"
            )
        if self._model_adapter.execution_profile_adapter_id != profile.adapter_id:
            raise RunDarWorkflowError("configured adapter does not match profile")
        if "text_generation" not in profile.capabilities:
            raise RunDarWorkflowError("configured profile lacks text_generation")
        if not _adapter_supports(self._model_adapter, "text_generation"):
            raise RunDarWorkflowError("configured adapter lacks text_generation")
        if profile.execution_model_id not in self._model_adapter.models:
            raise RunDarWorkflowError(
                "configured adapter does not advertise execution model"
            )
        if (
            self._model_adapter.resolved_model_id(profile.execution_model_id)
            != registration.model_id
        ):
            raise RunDarWorkflowError(
                "configured adapter does not resolve registered model"
            )


def _adapter_supports(
    adapter: OpenAIClientAdapter | AsyncOpenAIClientAdapter, capability: str
) -> bool:
    capabilities = getattr(adapter, "capabilities", {})
    if not isinstance(capabilities, Mapping):
        return False
    return capabilities.get(capability) is True


def _render_prompt(prompt: str, additional_context: str) -> str:
    if not additional_context:
        return prompt
    return f"{prompt}\n\nAdditional context:\n{additional_context}"


def _terminal_output(
    value: object,
    contract: Mapping[str, Any],
    *,
    adapter_id: str,
) -> dict[str, str]:
    if not isinstance(value, str) or not value:
        raise RunDarWorkflowError("workflow terminal output is not a message")
    if len(value.encode("utf-8")) > 32 * 1024:
        raise RunDarWorkflowError("workflow terminal output exceeds the response limit")
    if adapter_id == FASTMAIL_TRIAGE_LLAMA_CPP_ADAPTER_ID:
        try:
            value = json.dumps(
                normalize_fastmail_triage_report(value), separators=(",", ":")
            )
        except FastmailTriageReportError as error:
            raise RunDarWorkflowError("Fastmail terminal output is invalid") from error
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


def _terminal_processor_output(evidence: Mapping[str, object]) -> bytes:
    """Validate one sealed processor envelope without interpreting its payload."""

    if set(evidence) != {"status", "output_base64", "repair_report"}:
        raise ValueError("terminal processor evidence is invalid")
    if evidence["status"] != "accepted":
        raise ValueError("terminal processor evidence is invalid")
    encoded = evidence["output_base64"]
    report = evidence["repair_report"]
    if (
        not isinstance(encoded, str)
        or not isinstance(report, dict)
        or set(report) != {"category"}
        or not isinstance(report["category"], str)
        or not report["category"]
    ):
        raise ValueError("terminal processor evidence is invalid")
    try:
        output = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as error:
        raise ValueError("terminal processor evidence is invalid") from error
    if not output:
        raise ValueError("terminal processor evidence is invalid")
    return output


def _terminal_processor_category(evidence: Mapping[str, object]) -> str:
    report = evidence.get("repair_report")
    if not isinstance(report, dict) or set(report) != {"category"}:
        raise ValueError("terminal processor evidence is invalid")
    category = report.get("category")
    if not isinstance(category, str) or not category:
        raise ValueError("terminal processor evidence is invalid")
    return category


def _terminal_processor_diagnostic(
    payload: Mapping[str, object],
) -> TerminalProcessorDiagnostic:
    original = _diagnostic_bytes(payload.get("original_base64"))
    admitted_value = payload.get("admitted_base64")
    admitted = _diagnostic_bytes(admitted_value) if admitted_value is not None else None
    original_digest = payload.get("original_digest")
    admitted_digest = payload.get("admitted_digest")
    categories = payload.get("repair_categories")
    if (
        not isinstance(original_digest, str)
        or original_digest != _digest_bytes(original)
        or admitted is not None
        and (
            not isinstance(admitted_digest, str)
            or admitted_digest != _digest_bytes(admitted)
        )
        or admitted is None
        and admitted_digest is not None
        or not isinstance(categories, list)
        or any(not isinstance(category, str) or not category for category in categories)
    ):
        raise RunDarWorkflowError("terminal processor diagnostic is unavailable")
    return TerminalProcessorDiagnostic(
        original=original,
        original_digest=original_digest,
        admitted=admitted,
        admitted_digest=admitted_digest if isinstance(admitted_digest, str) else None,
        repair_categories=tuple(categories),
    )


def _terminal_diagnostic_payload(
    diagnostic: TerminalProcessorDiagnostic | None,
) -> dict[str, object] | None:
    if diagnostic is None:
        return None
    return {
        "original_base64": base64.b64encode(diagnostic.original).decode("ascii"),
        "original_digest": diagnostic.original_digest,
        "admitted_base64": (
            base64.b64encode(diagnostic.admitted).decode("ascii")
            if diagnostic.admitted is not None
            else None
        ),
        "admitted_digest": diagnostic.admitted_digest,
        "repair_categories": list(diagnostic.repair_categories),
    }


def _debug_diagnostic(payload: Mapping[str, object]) -> DebugWorkflowDiagnostic:
    diagnostic_id = payload.get("diagnostic_id")
    run_id = payload.get("run_id")
    outcome = payload.get("outcome")
    limited = payload.get("retention_limited")
    fragments = payload.get("fragments")
    terminal_payload = payload.get("terminal")
    if (
        not isinstance(diagnostic_id, str)
        or not diagnostic_id
        or run_id is not None
        and not isinstance(run_id, str)
        or not isinstance(outcome, str)
        or outcome not in {"completed", "failed", "cancelled"}
        or not isinstance(limited, bool)
        or not isinstance(fragments, list)
        or terminal_payload is not None
        and not isinstance(terminal_payload, Mapping)
    ):
        raise RunDarWorkflowError("debug diagnostic is unavailable")
    parsed: list[DebugGeneratedFragment] = []
    for fragment in fragments:
        if not isinstance(fragment, Mapping):
            raise RunDarWorkflowError("debug diagnostic is unavailable")
        content = _diagnostic_bytes(fragment.get("content_base64"))
        exhausted = fragment.get("exhausted")
        generated_tokens = fragment.get("generated_tokens")
        runner_max_new_tokens = fragment.get("runner_max_new_tokens")
        backend_max_new_tokens = fragment.get("backend_max_new_tokens")
        if (
            not isinstance(exhausted, bool)
            or generated_tokens is not None
            and not isinstance(generated_tokens, int)
            or not _optional_generation_limit(runner_max_new_tokens)
            or not _optional_generation_limit(backend_max_new_tokens)
        ):
            raise RunDarWorkflowError("debug diagnostic is unavailable")
        try:
            parsed.append(
                DebugGeneratedFragment(
                    content.decode("utf-8"),
                    exhausted,
                    generated_tokens,
                    runner_max_new_tokens,
                    backend_max_new_tokens,
                )
            )
        except UnicodeDecodeError as error:
            raise RunDarWorkflowError("debug diagnostic is unavailable") from error
    terminal = (
        _terminal_processor_diagnostic(terminal_payload)
        if isinstance(terminal_payload, Mapping)
        else None
    )
    return DebugWorkflowDiagnostic(
        diagnostic_id, run_id, outcome, tuple(parsed), terminal, limited
    )


def _optional_generation_limit(value: object) -> bool:
    return value is None or (
        isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= 65_536
    )


def _diagnostic_bytes(value: object) -> bytes:
    if not isinstance(value, str):
        raise RunDarWorkflowError("terminal processor diagnostic is unavailable")
    try:
        return base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as error:
        raise RunDarWorkflowError(
            "terminal processor diagnostic is unavailable"
        ) from error


def _digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()
