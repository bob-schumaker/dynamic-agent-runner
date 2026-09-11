"""Private local host configuration and no-tool runner composition."""

from __future__ import annotations

import json
import os
import stat
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Sequence
from typing import Mapping

from dynamic_agent_runner.apple_foundation_models import (
    AppleFoundationModelConfig,
    create_apple_foundation_model_async_adapter,
)
from dynamic_agent_runner.local_model_preparation import (
    LocalModelPreparationCatalog,
    LocalModelPreparationResult,
    LocalModelPreparationService,
    PinnedLlamaCppLoraConverter,
)
from dynamic_agent_runner.workflow_host.catalog import (
    PackageCatalog,
    PackageCatalogError,
)
from dynamic_agent_runner.workflow_host.action_ledger import WorkflowActionLedger
from dynamic_agent_runner.workflow_host.approvals import WorkflowApprovalStore
from dynamic_agent_runner.workflow_host.authoring_materials import (
    AuthoringMaterialInput,
    AuthoringMaterialService,
    AuthoringMaterialSetProjection,
    AuthoringMaterialSetReceipt,
)
from dynamic_agent_runner.workflow_host.authoring_output import (
    AuthoredPackageValidation,
    AuthoringOutputError,
    finalize_authored_package,
)
from dynamic_agent_runner.workflow_host.authoring_outputs import (
    AuthoredFileReceipt,
    AuthoringOutputReceipt,
    AuthoringOutputService,
)
from dynamic_agent_runner.workflow_host.authorized_tools import (
    LocalActionApprovalBroker,
)
from dynamic_agent_runner.guardrails import InMemoryGuardrailRegistry
from dynamic_agent_runner.workflow_host.connections import (
    MCPAuthentication,
    MCPConnection,
    MCPConnectionControlPlane,
    MCPConnectionError,
)
from dynamic_agent_runner.workflow_host.mcp_binding import (
    MCPWorkflowCapabilityBinding,
    MCPWorkflowCapabilityBindingControlPlane,
    MCPWorkflowCapabilityBindingError,
)
from dynamic_agent_runner.workflow_host.mcp_client import (
    HTTPSJSONRPCMCPTransportFactory,
    MCPClientConfiguration,
    MCPConnectionClient,
    MCPConnectionClientError,
)
from dynamic_agent_runner.workflow_host.mcp_surfaces import (
    MCPDiscoveredTool,
    MCPSurfaceSnapshot,
    MCPSurfaceSnapshotControlPlane,
    MCPSurfaceSnapshotError,
)
from dynamic_agent_runner.workflow_host.local_tools import (
    execute_macos_sandbox_exec,
)
from dynamic_agent_runner.workflow_host.local_model_runners import (
    LocalModelRunner,
    LocalModelRunnerCatalog,
)
from dynamic_agent_runner.workflow_host.model_execution_binding import (
    ModelRunnerRegistry,
)
from dynamic_agent_runner.workflow_host.artifact_tools import (
    ReviewedArtifactToolExecutor,
)
from dynamic_agent_runner.workflow_host.reviewed_tool_packages import (
    ReviewedToolPackage,
    ReviewedToolPackageBinding,
    ReviewedToolPackageControlPlane,
)
from dynamic_agent_runner.workflow_host.oauth import (
    OAuthAuthorizationService,
    OAuthClientConfiguration,
    OAuthError,
)
from dynamic_agent_runner.workflow_host.oauth_discovery import (
    OAuthDiscoveryError,
    OAuthDiscoveryRecordStore,
    OAuthMetadataDiscovery,
    UrllibOAuthMetadataHTTPTransport,
)
from dynamic_agent_runner.workflow_host.oauth_registration import (
    OAuthClientRegistrationError,
    OAuthClientRegistrationService,
)
from dynamic_agent_runner.workflow_host.oauth_revalidation import (
    DiscoveredOAuthRevalidator,
)
from dynamic_agent_runner.workflow_host.package_export import (
    ExportedPackage,
    PackageExportError,
    export_signed_staged_package,
)
from dynamic_agent_runner.workflow_host.package_sources import (
    PackageSourceSelectionPolicy,
)
from dynamic_agent_runner.workflow_host.capabilities import CapabilityCatalog
from dynamic_agent_runner.workflow_host.execution_descriptors import (
    ExecutionDescriptorValidatorRegistry,
)
from dynamic_agent_runner.workflow_host.embedding_execution import (
    EmbeddingExecutionService,
    EmbeddingLimitProjectorRegistry,
)
from dynamic_agent_runner.workflow_host.embedding_sealed_artifact_callback import (
    EmbeddingSealedArtifactCallbackResolver,
)
from dynamic_agent_runner.workflow_host.locked_inference_execution import (
    LockedInferenceHostLimits,
)
from dynamic_agent_runner.workflow_host.locked_inference_provider_registry import (
    LockedInferenceProviderRegistry,
)
from dynamic_agent_runner.workflow_host.locked_inference_sealed_artifact_callback import (
    LockedInferenceExecutionFactory,
    LockedInferenceSealedArtifactCallbackResolver,
)
from dynamic_agent_runner.workflow_host.policy import (
    PolicyCompilationError,
    compile_workflow_policy,
    resolve_capabilities,
)
from dynamic_agent_runner.workflow_host.publisher_trust import (
    PublisherTrustError,
    PublisherTrustStore,
    TrustedPublisher,
)
from dynamic_agent_runner.workflow_host.preparation import (
    PreparedWorkflowInput,
    WorkflowInvocationPreparationService,
)
from dynamic_agent_runner.workflow_host.profiles import (
    InstallationIdentityProvider,
    LocalModelProfile,
    LocalModelProfileControlPlane,
    LocalModelProfileError,
    FASTMAIL_TRIAGE_LLAMA_CPP_ADAPTER_ID,
    create_fastmail_triage_llama_cpp_adapter,
    create_hosted_openai_adapter,
    create_local_adapter,
)
from dynamic_agent_runner.workflow_host.registration import (
    WorkflowRegistration,
    WorkflowRegistrationError,
    WorkflowRegistrationService,
)
from dynamic_agent_runner.workflow_host.runner import (
    DebugRunWorkflowResult,
    DebugWorkflowDiagnostic,
    DryRunDarWorkflowResult,
    RedactedRunTrace,
    RunDarWorkflowRequest,
    RunDarWorkflowResult,
    WorkflowRunner,
)
from dynamic_agent_runner.workflow_host.sealed_artifact_preparation import (
    SealedArtifactInputPreparationService,
)
from dynamic_agent_runner.workflow_host.sealed_artifact_runner import (
    SealedArtifactHandleService,
    SealedArtifactOutputHandleService,
)
from dynamic_agent_runner.workflow_host.sealed_artifact_workflow_runner import (
    SealedArtifactCallbackResolver,
    SealedArtifactInvocation,
    SealedArtifactInvocationResult,
    SealedArtifactWorkflowRunner,
)
from dynamic_agent_runner.workflow_host.staging import (
    PrivatePackageStager,
    StagedPackage,
)
from dynamic_agent_runner.workflow_host.state import PrivateStateStore
from dynamic_agent_runner.workflow_host.workspace_ingress import (
    WorkspaceIngressError,
    WorkspaceIngressPolicy,
    WorkspaceIngressService,
    WorkspaceInputArtifact,
)
from dynamic_agent_runner.workflow_host.workflow_authoring_registration import (
    AuthoringContractError,
    CanonicalWorkflowContract,
    DeclarativeWorkflowDefinition,
    ReadyAuthoredWorkflow,
    UnavailableAuthoredWorkflow,
    validate_definition,
)
from dynamic_agent_runner.errors import ModelExecutionError


_DEFAULT_WORKSPACE_INPUT_MAX_BYTES = 8 * 1024 * 1024
_AUTHORING_MATERIAL_MAX_BYTES = 256 * 1024
_AUTHORING_MATERIAL_MAX_MEMBERS = 16
_AUTHORING_MATERIAL_TTL = timedelta(hours=1)
_AUTHORING_OUTPUT_MAX_FILE_BYTES = 1024 * 1024
_AUTHORING_OUTPUT_TTL = timedelta(hours=1)
_SEALED_ARTIFACT_OUTPUT_TTL = timedelta(minutes=5)


class LocalWorkflowHostError(ValueError):
    """Raised when required human-owned host configuration is unavailable."""


class LocalModelPreparationRequired(LocalWorkflowHostError):
    """Raised when invocation needs the separately authorized model preparation."""

    def __init__(self, result: LocalModelPreparationResult) -> None:
        self.status = result.status
        super().__init__("local model preparation is required")


class DiscoveredOAuthSetupError(LocalWorkflowHostError):
    """One stable redacted status for a discovered OAuth setup failure."""

    def __init__(self, status: str) -> None:
        self.status = status
        super().__init__(status)


def _create_model_adapter(
    profile: LocalModelProfile,
    *,
    resolve_prepared_set: Callable[[], object] | None = None,
    runners: LocalModelRunnerCatalog | None = None,
):
    if profile.adapter_id == "strict-local-adapter-v1":
        return create_local_adapter(profile)
    if profile.adapter_id == "apple-foundation-models-adapter-v1":
        return create_apple_foundation_model_async_adapter(
            AppleFoundationModelConfig(model_aliases=(profile.model_id,))
        )
    if profile.adapter_id == FASTMAIL_TRIAGE_LLAMA_CPP_ADAPTER_ID:
        return create_fastmail_triage_llama_cpp_adapter(profile)
    if profile.runner_id == "transformers-peft-v1":
        if resolve_prepared_set is None:
            raise LocalWorkflowHostError("local model preparation is unavailable")
        from dynamic_agent_runner.workflow_host.transformers_peft_model import (
            DeferredTransformersPeftSingleImageAdapter,
        )

        return DeferredTransformersPeftSingleImageAdapter(
            model_id=profile.model_id,
            adapter_id=profile.adapter_id,
            resolve_prepared_set=resolve_prepared_set,  # type: ignore[arg-type]
        )
    if profile.adapter_id == "hosted-openai-adapter-v1":
        return create_hosted_openai_adapter(profile)
    if resolve_prepared_set is not None and runners is not None:
        return runners.create_adapter(profile, resolve_prepared_set)  # type: ignore[arg-type]
    raise LocalWorkflowHostError("configured execution profile is unavailable")


@dataclass(frozen=True)
class DiscoveredOAuthAuthorizationResult:
    """Redaction-safe result of one human-only discovered OAuth setup operation."""

    authentication_id: str
    registration_id: str


@dataclass(frozen=True)
class DiscoveredOAuthSetupPreview:
    """Human-only metadata display, never a machine-readable workflow receipt."""

    endpoint: str
    challenged_scopes: tuple[str, ...]
    advertised_scopes: tuple[str, ...]


@dataclass(frozen=True)
class SavedWorkflowDryRunResult:
    """Redaction-safe resolution receipt for one saved workflow dry run."""

    status: str
    workflow_id: str
    registration_digest: str
    package_id: str
    revision_digest: str
    profile_id: str


@dataclass(frozen=True)
class LocalWorkflowHostConfiguration:
    """Private setup record for one OS-user local workflow host."""

    package_root: Path
    profile_id: str
    workspace_input_root: Path | None = None
    workspace_input_max_bytes: int = _DEFAULT_WORKSPACE_INPUT_MAX_BYTES
    mcp_client_configuration: MCPClientConfiguration | None = None


def configure_local_host(
    *,
    root: Path,
    package_root: Path,
    model_id: str,
    base_url: str,
    workspace_input_root: Path | None = None,
    workspace_input_max_bytes: int = _DEFAULT_WORKSPACE_INPUT_MAX_BYTES,
    mcp_client_configuration: MCPClientConfiguration | None = None,
) -> LocalWorkflowHostConfiguration:
    """Create the human-owned v1 local model profile and host configuration."""

    _validate_root(root)
    _validate_package_root(package_root)
    if workspace_input_root is not None:
        _validate_workspace_input_root(workspace_input_root)
    _validate_workspace_input_max_bytes(workspace_input_max_bytes)
    store = PrivateStateStore(root)
    profile = LocalModelProfileControlPlane(store=store).create(
        model_id=model_id,
        adapter_id="strict-local-adapter-v1",
        base_url=base_url,
        capabilities={"text_generation"},
    )
    configuration = LocalWorkflowHostConfiguration(
        package_root,
        profile.profile_id,
        workspace_input_root,
        workspace_input_max_bytes,
        mcp_client_configuration,
    )
    _write_configuration(root, configuration)
    return configuration


def configure_apple_local_host(
    *,
    root: Path,
    package_root: Path,
    model_id: str,
    workspace_input_root: Path | None = None,
    workspace_input_max_bytes: int = _DEFAULT_WORKSPACE_INPUT_MAX_BYTES,
) -> LocalWorkflowHostConfiguration:
    """Create one human-owned on-device Apple model host configuration."""

    _validate_root(root)
    _validate_package_root(package_root)
    if workspace_input_root is not None:
        _validate_workspace_input_root(workspace_input_root)
    _validate_workspace_input_max_bytes(workspace_input_max_bytes)
    try:
        profile = LocalModelProfileControlPlane(
            store=PrivateStateStore(root)
        ).create_apple(model_id=model_id)
    except ModelExecutionError as error:
        raise LocalWorkflowHostError(
            "Apple model eligibility is unavailable"
        ) from error
    configuration = LocalWorkflowHostConfiguration(
        package_root,
        profile.profile_id,
        workspace_input_root,
        workspace_input_max_bytes,
    )
    _write_configuration(root, configuration)
    return configuration


def configure_fastmail_triage_llama_cpp_host(
    *,
    root: Path,
    package_root: Path,
    workspace_input_root: Path | None = None,
    workspace_input_max_bytes: int = _DEFAULT_WORKSPACE_INPUT_MAX_BYTES,
    mcp_client_configuration: MCPClientConfiguration | None = None,
) -> LocalWorkflowHostConfiguration:
    """Configure the fixed offline Qwen host profile for Fastmail triage."""

    _validate_root(root)
    _validate_package_root(package_root)
    if workspace_input_root is not None:
        _validate_workspace_input_root(workspace_input_root)
    _validate_workspace_input_max_bytes(workspace_input_max_bytes)
    profile = LocalModelProfileControlPlane(
        store=PrivateStateStore(root)
    ).create_fastmail_triage_llama_cpp()
    configuration = LocalWorkflowHostConfiguration(
        package_root,
        profile.profile_id,
        workspace_input_root,
        workspace_input_max_bytes,
        mcp_client_configuration,
    )
    _write_configuration(root, configuration)
    return configuration


def configure_hosted_openai_host(
    *,
    root: Path,
    package_root: Path,
    model_id: str,
    base_url: str,
    workspace_input_root: Path | None = None,
    workspace_input_max_bytes: int = _DEFAULT_WORKSPACE_INPUT_MAX_BYTES,
) -> LocalWorkflowHostConfiguration:
    """Create one human-owned hosted OpenAI-compatible host configuration."""

    _validate_root(root)
    _validate_package_root(package_root)
    if workspace_input_root is not None:
        _validate_workspace_input_root(workspace_input_root)
    _validate_workspace_input_max_bytes(workspace_input_max_bytes)
    profile = LocalModelProfileControlPlane(
        store=PrivateStateStore(root)
    ).create_hosted_openai(
        model_id=model_id,
        base_url=base_url,
        capabilities={"text_generation"},
    )
    configuration = LocalWorkflowHostConfiguration(
        package_root,
        profile.profile_id,
        workspace_input_root,
        workspace_input_max_bytes,
    )
    _write_configuration(root, configuration)
    return configuration


def trust_package_publisher(
    *, root: Path, key_id: str, public_key: bytes
) -> TrustedPublisher:
    """Persist one human-confirmed portable package publisher key."""

    _validate_root(root)
    try:
        return PublisherTrustStore(root).add(key_id=key_id, public_key=public_key)
    except PublisherTrustError as error:
        raise LocalWorkflowHostError(
            "package publisher could not be trusted"
        ) from error


def trusted_package_publishers(*, root: Path) -> tuple[TrustedPublisher, ...]:
    """Return redaction-safe human-configured publisher identities."""

    _validate_root(root)
    try:
        return PublisherTrustStore(root).publishers()
    except PublisherTrustError as error:
        raise LocalWorkflowHostError(
            "package publisher trust is unavailable"
        ) from error


def revoke_package_publisher(*, root: Path, key_id: str) -> None:
    """Revoke one human-configured portable package publisher key."""

    _validate_root(root)
    try:
        PublisherTrustStore(root).revoke(key_id)
    except PublisherTrustError as error:
        raise LocalWorkflowHostError(
            "package publisher could not be revoked"
        ) from error


def create_mcp_connection(
    *,
    root: Path,
    endpoint: str,
    scopes: Sequence[str],
    authentication_method: str,
) -> MCPConnection:
    """Create one human-selected generic HTTPS MCP connection for this host."""

    configuration, connections = _connection_control(root)
    try:
        return connections.create(
            profile_id=configuration.profile_id,
            endpoint=endpoint,
            scopes=scopes,
            authentication_method=authentication_method,
        )
    except MCPConnectionError as error:
        raise LocalWorkflowHostError(
            "MCP connection could not be configured"
        ) from error


def configure_mcp_api_token(
    *, root: Path, connection_id: str, token: str
) -> MCPAuthentication:
    """Store one human-provided API token outside local host state."""

    _, connections = _connection_control(root)
    try:
        return connections.configure_api_token(connection_id, token)
    except MCPConnectionError as error:
        raise LocalWorkflowHostError(
            "MCP authentication could not be configured"
        ) from error


def authorize_mcp_oauth(
    *,
    root: Path,
    connection_id: str,
    authorization_endpoint: str,
    token_endpoint: str,
    client_id: str,
) -> MCPAuthentication:
    """Complete one human OAuth PKCE loopback authorization for a connection."""

    _, connections = _connection_control(root)
    try:
        return OAuthAuthorizationService(connections=connections).authorize(
            connection_id,
            configuration=OAuthClientConfiguration(
                authorization_endpoint=authorization_endpoint,
                token_endpoint=token_endpoint,
                client_id=client_id,
            ),
        )
    except (MCPConnectionError, OAuthError) as error:
        raise LocalWorkflowHostError("MCP OAuth authorization failed") from error


def authorize_discovered_mcp_oauth(
    *,
    root: Path,
    connection_id: str,
    persistent_reconnect: bool,
    existing_registration_id: str | None = None,
) -> DiscoveredOAuthAuthorizationResult:
    """Discover, register, revalidate, and authorize one human-configured MCP endpoint."""

    _, connections = _connection_control(root)
    transport = UrllibOAuthMetadataHTTPTransport()
    discovery = OAuthMetadataDiscovery(transport=transport)
    try:
        connection = connections.load(connection_id)
        protected_resource = discovery.discover_protected_resource(connection.endpoint)
        authorization_server = discovery.discover_authorization_server(
            protected_resource
        )
        scopes = discovery.confirm_scope_selection(
            protected_resource,
            selected_scopes=set(connection.scopes),
            persistent_reconnect=persistent_reconnect,
        )
        OAuthDiscoveryRecordStore(
            store=PrivateStateStore(root),
            owner=InstallationIdentityProvider().principal,
        ).record(
            connection_id=connection.connection_id,
            protected_resource=protected_resource,
            authorization_server=authorization_server,
            scopes=scopes,
        )
        registration = OAuthClientRegistrationService(
            store=PrivateStateStore(root),
            owner=InstallationIdentityProvider().principal,
            transport=transport,
        ).register_or_reuse(
            metadata=authorization_server,
            scopes=scopes,
            resource=protected_resource.resource,
            connection_id=connection.connection_id,
            existing_registration_id=existing_registration_id,
        )
        revalidated_resource = discovery.discover_protected_resource(
            connection.endpoint
        )
        if revalidated_resource != protected_resource:
            raise DiscoveredOAuthSetupError("metadata_drift")
        revalidated_server = discovery.discover_authorization_server(
            revalidated_resource
        )
        revalidated_scopes = discovery.confirm_scope_selection(
            revalidated_resource,
            selected_scopes=set(connection.scopes),
            persistent_reconnect=persistent_reconnect,
        )
        if revalidated_server != authorization_server or revalidated_scopes != scopes:
            raise DiscoveredOAuthSetupError("metadata_drift")
        authentication = OAuthAuthorizationService(connections=connections).authorize(
            connection.connection_id,
            configuration=OAuthClientConfiguration(
                authorization_endpoint=authorization_server.authorization_endpoint,
                token_endpoint=authorization_server.token_endpoint,
                client_id=registration.client_id,
                resource=protected_resource.resource,
                issuer=authorization_server.issuer,
                registered_redirect_template=registration.redirect_template,
                registration_id=registration.registration_id,
                persistent_reconnect=persistent_reconnect,
                scope_is_omitted=scopes.scope_is_omitted,
                require_issuer_callback=(
                    authorization_server.authorization_response_iss_parameter_supported
                ),
            ),
        )
        return DiscoveredOAuthAuthorizationResult(
            authentication_id=authentication.authentication_id,
            registration_id=registration.registration_id,
        )
    except OAuthDiscoveryError as error:
        raise DiscoveredOAuthSetupError(_discovery_status(error)) from error
    except OAuthClientRegistrationError as error:
        raise DiscoveredOAuthSetupError("registration_unavailable") from error
    except MCPConnectionError as error:
        raise DiscoveredOAuthSetupError("authorization_required") from error


def inspect_discovered_mcp_oauth(
    *, root: Path, connection_id: str
) -> DiscoveredOAuthSetupPreview:
    """Return a human-only scope preview for a configured MCP endpoint."""

    _, connections = _connection_control(root)
    try:
        connection = connections.load(connection_id)
        protected_resource = OAuthMetadataDiscovery(
            transport=UrllibOAuthMetadataHTTPTransport()
        ).discover_protected_resource(connection.endpoint)
        return DiscoveredOAuthSetupPreview(
            endpoint=protected_resource.resource,
            challenged_scopes=tuple(sorted(protected_resource.challenged_scopes)),
            advertised_scopes=tuple(sorted(protected_resource.scopes_supported)),
        )
    except OAuthDiscoveryError as error:
        raise DiscoveredOAuthSetupError(_discovery_status(error)) from error
    except MCPConnectionError as error:
        raise DiscoveredOAuthSetupError("authorization_required") from error


def _discovery_status(error: OAuthDiscoveryError) -> str:
    message = str(error)
    if message == "authorization server selection required":
        return "authorization_server_selection_required"
    if "unavailable" in message:
        return "metadata_unavailable"
    return "metadata_invalid"


def attach_mcp_client(
    *,
    root: Path,
    connection_id: str,
    authentication_id: str,
    peer_certificate_sha256: str,
    timeout_seconds: int,
    max_response_bytes: int,
) -> LocalWorkflowHostConfiguration:
    """Attach one authenticated, certificate-pinned MCP client to this host."""

    configuration, connections = _connection_control(root)
    try:
        connection = connections.load(connection_id)
        authentication = connections.load_authentication(authentication_id)
    except MCPConnectionError as error:
        raise LocalWorkflowHostError("MCP authentication is unavailable") from error
    if (
        connection.profile_id != configuration.profile_id
        or authentication.connection_id != connection.connection_id
    ):
        raise LocalWorkflowHostError("MCP connection is not configured for this host")
    try:
        client_configuration = MCPClientConfiguration(
            connection_id=connection.connection_id,
            authentication_id=authentication.authentication_id,
            peer_certificate_sha256=peer_certificate_sha256,
            timeout_seconds=timeout_seconds,
            max_response_bytes=max_response_bytes,
        )
    except MCPConnectionClientError as error:
        raise LocalWorkflowHostError("MCP client configuration is invalid") from error
    configured = LocalWorkflowHostConfiguration(
        configuration.package_root,
        configuration.profile_id,
        configuration.workspace_input_root,
        configuration.workspace_input_max_bytes,
        client_configuration,
    )
    _write_configuration(root, configured)
    return configured


class LocalWorkflowHost:
    """One local-principal composition root for sealed no-tool workflow runs."""

    def __init__(
        self,
        *,
        configuration: LocalWorkflowHostConfiguration,
        sources: PackageSourceSelectionPolicy,
        stager: PrivatePackageStager,
        catalog: PackageCatalog,
        registrations: WorkflowRegistrationService,
        preparation: WorkflowInvocationPreparationService,
        model_preparation: LocalModelPreparationService,
        profile: LocalModelProfile,
        runner: WorkflowRunner,
        workspace_ingress: WorkspaceIngressService | None,
        authoring_materials: AuthoringMaterialService,
        authoring_outputs: AuthoringOutputService,
        mcp_client: MCPConnectionClient | None = None,
        mcp_surfaces: MCPSurfaceSnapshotControlPlane | None = None,
        mcp_bindings: MCPWorkflowCapabilityBindingControlPlane | None = None,
        reviewed_tool_packages: ReviewedToolPackageControlPlane,
        capability_catalog: CapabilityCatalog | None = None,
        descriptor_validators: ExecutionDescriptorValidatorRegistry | None = None,
        sealed_artifact_preparation: SealedArtifactInputPreparationService
        | None = None,
        sealed_artifact_runner: SealedArtifactWorkflowRunner | None = None,
    ) -> None:
        self._configuration = configuration
        self._sources = sources
        self._stager = stager
        self._catalog = catalog
        self._registrations = registrations
        self._preparation = preparation
        self._model_preparation = model_preparation
        self._profile = profile
        self._runner = runner
        self._workspace_ingress = workspace_ingress
        self._authoring_materials = authoring_materials
        self._authoring_outputs = authoring_outputs
        self._mcp_client = mcp_client
        self._mcp_surfaces = mcp_surfaces
        self._mcp_bindings = mcp_bindings
        self._reviewed_tool_packages = reviewed_tool_packages
        self._capability_catalog = capability_catalog
        self._descriptor_validators = descriptor_validators
        self._sealed_artifact_preparation = sealed_artifact_preparation
        self._sealed_artifact_runner = sealed_artifact_runner

    @classmethod
    def open(
        cls,
        root: Path,
        *,
        mcp_client_factory: Callable[[MCPClientConfiguration], MCPConnectionClient]
        | None = None,
        mcp_connections: MCPConnectionControlPlane | None = None,
        reviewed_artifact_tool_executors: Mapping[str, ReviewedArtifactToolExecutor]
        | None = None,
        local_model_runners: Sequence[LocalModelRunner] = (),
        model_runner_registry: ModelRunnerRegistry | None = None,
        capability_catalog: CapabilityCatalog | None = None,
        descriptor_validators: ExecutionDescriptorValidatorRegistry | None = None,
        sealed_artifact_callback_resolver: SealedArtifactCallbackResolver | None = None,
        embedding_execution: EmbeddingExecutionService | None = None,
        embedding_limit_projectors: EmbeddingLimitProjectorRegistry | None = None,
        locked_inference_provider_registry: LockedInferenceProviderRegistry
        | None = None,
        locked_inference_host_limits: LockedInferenceHostLimits | None = None,
    ) -> LocalWorkflowHost:
        """Open a configured local host for the current OS user."""

        _validate_root(root)
        if (embedding_execution is None) != (embedding_limit_projectors is None) or (
            embedding_execution is not None
            and (
                capability_catalog is None
                or sealed_artifact_callback_resolver is not None
            )
        ):
            raise LocalWorkflowHostError(
                "embedding execution configuration is unavailable"
            )
        if (locked_inference_provider_registry is None) != (
            locked_inference_host_limits is None
        ) or (
            locked_inference_provider_registry is not None
            and (
                capability_catalog is None
                or sealed_artifact_callback_resolver is not None
                or embedding_execution is not None
            )
        ):
            raise LocalWorkflowHostError(
                "locked inference configuration is unavailable"
            )
        if locked_inference_provider_registry is not None:
            sealed_artifact_callback_resolver = (
                LockedInferenceSealedArtifactCallbackResolver(
                    execution_factory=LockedInferenceExecutionFactory(
                        capability_catalog=capability_catalog,
                        provider_registry=locked_inference_provider_registry,
                        host_limits=locked_inference_host_limits,
                    )
                )
            )
        elif embedding_execution is not None:
            sealed_artifact_callback_resolver = EmbeddingSealedArtifactCallbackResolver(
                execution=embedding_execution,
                limit_projectors=embedding_limit_projectors,
            )
        configuration = _read_configuration(root)
        store = PrivateStateStore(root)
        profiles = LocalModelProfileControlPlane(store=store)
        profile = profiles.load(configuration.profile_id)
        connections = mcp_connections or MCPConnectionControlPlane(
            store=store, profiles=profiles
        )
        surfaces = MCPSurfaceSnapshotControlPlane(store=store, connections=connections)
        mcp_bindings = MCPWorkflowCapabilityBindingControlPlane(
            store=store, surfaces=surfaces
        )
        reviewed_tool_packages = ReviewedToolPackageControlPlane(
            store=store, owner=InstallationIdentityProvider().principal
        )
        if mcp_client_factory is None:
            mcp_client = _mcp_client(
                root=root, configuration=configuration, connections=connections
            )
        elif configuration.mcp_client_configuration is None:
            raise LocalWorkflowHostError("MCP client is not configured")
        else:
            mcp_client = mcp_client_factory(configuration.mcp_client_configuration)
        catalog = PackageCatalog(root / "catalog")
        model_preparation = LocalModelPreparationService(
            catalog=LocalModelPreparationCatalog(()),
            cache_root=root / "model-preparation",
            approved_cache_roots=(Path.home() / ".cache" / "huggingface" / "hub",),
            converter=PinnedLlamaCppLoraConverter(
                checkout=root / "model-preparation" / "llama.cpp"
            ),
        )
        registrations = WorkflowRegistrationService(
            profiles=profiles,
            configured_profile_id=profile.profile_id,
            root=root / "registrations",
            mcp_bindings=mcp_bindings if mcp_client is not None else None,
            mcp_client=mcp_client,
            mcp_surfaces=surfaces if mcp_client is not None else None,
            model_recipe_digest_provider=lambda candidate: (
                model_preparation.recipe_digest(
                    model_id=candidate.model_id,
                    adapter_id=candidate.adapter_id,
                    runner_id=candidate.runner_id,
                )
            ),
        )
        workspace_ingress = _workspace_ingress_service(
            root=root, configuration=configuration, store=store
        )
        preparation = WorkflowInvocationPreparationService(
            registrations=registrations,
            catalog=catalog,
            store=store,
            artifact_verifier=workspace_ingress,
            capability_catalog=capability_catalog,
            descriptor_validators=descriptor_validators,
        )
        sealed_handles = SealedArtifactHandleService(
            store=store, owner=InstallationIdentityProvider().principal
        )
        sealed_outputs = SealedArtifactOutputHandleService(
            store=store, owner=InstallationIdentityProvider().principal
        )
        sealed_preparation = (
            SealedArtifactInputPreparationService(
                registrations=registrations,
                catalog=catalog,
                handles=sealed_handles,
                capability_catalog=capability_catalog or CapabilityCatalog((), ()),
                descriptor_validators=descriptor_validators,
                callback_resolver=sealed_artifact_callback_resolver,
            )
            if sealed_artifact_callback_resolver is not None
            else None
        )
        sealed_runner = (
            SealedArtifactWorkflowRunner(
                registrations=registrations,
                catalog=catalog,
                handles=sealed_handles,
                outputs=sealed_outputs,
                callback_resolver=sealed_artifact_callback_resolver,
                capability_catalog=capability_catalog,
                descriptor_validators=descriptor_validators,
                output_ttl=_SEALED_ARTIFACT_OUTPUT_TTL,
            )
            if sealed_artifact_callback_resolver is not None
            else None
        )
        return cls(
            configuration=configuration,
            sources=PackageSourceSelectionPolicy(
                allowed_root=configuration.package_root, store=store
            ),
            stager=PrivatePackageStager(
                store=store,
                private_root=root / "staging",
                trusted_keys=PublisherTrustStore(root).trusted_keys,
            ),
            catalog=catalog,
            registrations=registrations,
            preparation=preparation,
            model_preparation=model_preparation,
            profile=profile,
            runner=WorkflowRunner(
                registrations=registrations,
                catalog=catalog,
                preparation=preparation,
                model_adapter=_create_model_adapter(
                    profile,
                    resolve_prepared_set=lambda: model_preparation.resolve(
                        model_id=profile.model_id,
                        adapter_id=profile.adapter_id,
                        runner_id=profile.runner_id,
                    ),
                    runners=LocalModelRunnerCatalog(local_model_runners),
                ),
                configured_profile=profile,
                mcp_bindings=mcp_bindings if mcp_client is not None else None,
                mcp_client=mcp_client,
                mcp_surfaces=surfaces if mcp_client is not None else None,
                action_ledger=(
                    WorkflowActionLedger(
                        store=store,
                        owner=InstallationIdentityProvider().principal,
                    )
                    if mcp_client is not None
                    else None
                ),
                approval_store=WorkflowApprovalStore(
                    store=store, owner=InstallationIdentityProvider().principal
                ),
                local_tool_executor=execute_macos_sandbox_exec,
                reviewed_tool_packages=reviewed_tool_packages,
                reviewed_artifact_tool_executors=reviewed_artifact_tool_executors,
                terminal_diagnostic_store=store,
                terminal_diagnostic_owner=InstallationIdentityProvider().principal,
                capability_catalog=capability_catalog,
                model_runner_registry=model_runner_registry,
                descriptor_validators=descriptor_validators,
            ),
            workspace_ingress=workspace_ingress,
            authoring_materials=AuthoringMaterialService(
                store=store,
                owner=InstallationIdentityProvider().principal,
                max_material_bytes=_AUTHORING_MATERIAL_MAX_BYTES,
                max_materials=_AUTHORING_MATERIAL_MAX_MEMBERS,
                material_ttl=_AUTHORING_MATERIAL_TTL,
            ),
            authoring_outputs=AuthoringOutputService(
                store=store,
                owner=InstallationIdentityProvider().principal,
                output_root=configuration.package_root,
                max_file_bytes=_AUTHORING_OUTPUT_MAX_FILE_BYTES,
                output_ttl=_AUTHORING_OUTPUT_TTL,
            ),
            mcp_client=mcp_client,
            mcp_surfaces=surfaces if mcp_client is not None else None,
            mcp_bindings=mcp_bindings if mcp_client is not None else None,
            reviewed_tool_packages=reviewed_tool_packages,
            capability_catalog=capability_catalog,
            descriptor_validators=descriptor_validators,
            sealed_artifact_preparation=sealed_preparation,
            sealed_artifact_runner=sealed_runner,
        )

    def select_package(self, path: Path, *, now: datetime) -> str:
        """Return an opaque handle for one human-selected directory or ZIP package."""

        if path.suffix.lower() == ".zip":
            return self._sources.select_zip(path, now=now)
        return self._sources.select_directory(path, now=now)

    def configure_reviewed_tool_package(
        self, *, package_name: str, binding: ReviewedToolPackageBinding
    ) -> ReviewedToolPackage:
        """Persist one host-reviewed package name without discovery or fallback."""

        return self._reviewed_tool_packages.create(
            package_name=package_name, binding=binding
        )

    def register_authored_workflow(
        self,
        *,
        contract: CanonicalWorkflowContract,
        definition: DeclarativeWorkflowDefinition,
        now: datetime,
    ) -> ReadyAuthoredWorkflow | UnavailableAuthoredWorkflow:
        """Compose one validated closed authoring request into a saved workflow."""

        try:
            validate_definition(contract=contract, definition=definition)
        except AuthoringContractError:
            return UnavailableAuthoredWorkflow(
                capability="authoring_contract",
                requirement="the workflow definition does not match the requested contract",
            )
        try:
            material = json.dumps(
                {
                    "workflow_name": contract.workflow_name,
                    "model_id": contract.model_id,
                    "adapter_id": contract.adapter_id,
                    "input_kind": contract.input_kind,
                    "output_contract": contract.output_contract,
                    "required_capabilities": contract.required_capabilities,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            receipt = self.issue_authoring_materials(
                materials=(
                    AuthoringMaterialInput(
                        role="canonical_workflow_contract",
                        content=material,
                        disposition="distributable",
                    ),
                ),
                now=now,
            )
            output = self.create_authored_package(
                package_name=contract.workflow_name, now=now
            )
            for relative_path, content in definition.package_artifacts.items():
                self.write_authored_package_file(
                    output_id=output.output_id,
                    relative_path=relative_path,
                    content=content,
                    now=now,
                )
            _validation, source_handle = self.finalize_and_select_authored_output(
                output_id=output.output_id,
                material_set_id=receipt.material_set_id,
                now=now,
            )
            self.register(
                workflow_id=contract.workflow_name,
                package_source_handle=source_handle,
                now=now,
            )
            return ReadyAuthoredWorkflow(
                workflow_name=contract.workflow_name,
                input_contract=_authored_input_contract(contract.input_kind),
                output_contract=contract.output_contract,
                invocation=(
                    "dar-package invoke --package-name "
                    f"{contract.workflow_name} --prompt-stdin"
                ),
            )
        except Exception:  # noqa: BLE001 - preserve the façade's redacted boundary.
            return UnavailableAuthoredWorkflow(
                capability="authoring_registration",
                requirement="the authored workflow could not be registered",
            )

    def select_authored_package(self, package_name: str, *, now: datetime) -> str:
        """Select one configured-root authored package by its user-facing name."""

        return self.select_package(
            self._authoring_outputs.package_path_for_name(package_name), now=now
        )

    def issue_authoring_materials(
        self,
        *,
        materials: tuple[AuthoringMaterialInput, ...],
        now: datetime,
    ) -> AuthoringMaterialSetReceipt:
        """Persist the authoring input explicitly approved for one skill run."""

        return self._authoring_materials.issue(materials=materials, now=now)

    def issue_human_authoring_material_manifest(
        self, *, manifest_path: Path, now: datetime
    ) -> AuthoringMaterialSetReceipt:
        """Issue an authoring material set from a human-selected file manifest."""

        return self._authoring_materials.issue_human_manifest(
            manifest_path=manifest_path, now=now
        )

    def project_authoring_materials(
        self, material_set_id: str, *, now: datetime
    ) -> AuthoringMaterialSetProjection:
        """Return the exact host-approved content projection to an authoring skill."""

        return self._authoring_materials.project(material_set_id, now=now)

    def finalize_authored_package(
        self,
        *,
        package_root: Path,
        material_set_id: str,
        now: datetime,
    ) -> AuthoredPackageValidation:
        """Finalize one allowed-root package after deterministic material checks."""

        self._sources.select_directory(package_root, now=now)
        return self._validate_authored_package(
            package_root=package_root, material_set_id=material_set_id, now=now
        )

    def _validate_authored_package(
        self,
        *,
        package_root: Path,
        material_set_id: str,
        now: datetime,
    ) -> AuthoredPackageValidation:
        try:
            return finalize_authored_package(
                package_root=package_root,
                materials=self.project_authoring_materials(material_set_id, now=now),
            )
        except AuthoringOutputError as error:
            raise LocalWorkflowHostError("authored package is invalid") from error

    def create_authored_package(
        self, *, package_name: str, now: datetime
    ) -> AuthoringOutputReceipt:
        """Create an opaque host-owned package directory for one authoring run."""

        return self._authoring_outputs.create(package_name=package_name, now=now)

    def write_authored_package_file(
        self,
        *,
        output_id: str,
        relative_path: str,
        content: str,
        now: datetime,
    ) -> AuthoredFileReceipt:
        """Atomically write one file in an opaque authored-package directory."""

        return self._authoring_outputs.write_file(
            output_id=output_id,
            relative_path=relative_path,
            content=content,
            now=now,
        )

    def finalize_authored_output(
        self,
        *,
        output_id: str,
        material_set_id: str,
        now: datetime,
    ) -> AuthoredPackageValidation:
        """Finalize a host-owned authoring output without exposing its path."""

        return self.finalize_authored_package(
            package_root=self._authoring_outputs.consume_package_path(
                output_id, now=now
            ),
            material_set_id=material_set_id,
            now=now,
        )

    def finalize_and_select_authored_output(
        self,
        *,
        output_id: str,
        material_set_id: str,
        now: datetime,
    ) -> tuple[AuthoredPackageValidation, str]:
        """Consume one finalized authoring output into an opaque source handle."""

        package_root = self._authoring_outputs.consume_package_path(output_id, now=now)
        validation = self._validate_authored_package(
            package_root=package_root, material_set_id=material_set_id, now=now
        )
        return validation, self.select_package(package_root, now=now)

    def select_publisher_package(self, path: Path, *, now: datetime) -> str:
        """Return an opaque handle for one human-selected publisher ZIP package."""

        if path.suffix.lower() != ".zip":
            raise LocalWorkflowHostError("publisher package must be a ZIP")
        return self._sources.select_publisher_zip(path, now=now)

    def export_signed_package(
        self,
        *,
        package_source_handle: str,
        destination: Path,
        key_id: str,
        private_key: bytes,
        expected_content_digest: str,
        now: datetime,
    ) -> ExportedPackage:
        """Create one human-directed signed portable ZIP without retaining its key."""

        staged = self.preview_package(
            package_source_handle=package_source_handle, now=now
        )
        if expected_content_digest != staged.digest:
            raise LocalWorkflowHostError("package content digest was not confirmed")
        try:
            return export_signed_staged_package(
                staged=staged,
                destination=destination,
                key_id=key_id,
                private_key=private_key,
            )
        except PackageExportError as error:
            raise LocalWorkflowHostError("package export failed") from error

    def preview_package(
        self, *, package_source_handle: str, now: datetime
    ) -> StagedPackage:
        """Stage one human-selected package and return its redaction-safe digest."""

        return self._stager.stage(package_source_handle, now=now)

    def review_mcp_surface(
        self,
        *,
        approved_read_only_tool_names: Sequence[str],
        approved_tool_side_effects: dict[str, str] | None = None,
    ) -> MCPSurfaceSnapshot:
        """Discover and persist exactly one human-approved configured MCP surface."""

        self._ensure_mcp_client(policy_requires_mcp=True)
        if self._mcp_client is None or self._mcp_surfaces is None:
            raise LocalWorkflowHostError("MCP client is not configured")
        try:
            return self._mcp_surfaces.create(
                connection_id=self._mcp_client.connection_id,
                authentication_id=self._mcp_client.authentication_id,
                connection_generation=self._mcp_client.current_generation,
                tools=self._mcp_client.list_tools(),
                approved_read_only_tool_names=approved_read_only_tool_names,
                approved_tool_side_effects=approved_tool_side_effects,
            )
        except (MCPConnectionClientError, MCPSurfaceSnapshotError) as error:
            raise LocalWorkflowHostError("MCP surface review is unavailable") from error

    def preflight_apple_mcp_tool_schema(self, *, snapshot_id: str, tool_name: str):
        """Classify one current reviewed read-only MCP schema without dispatch."""

        self._ensure_mcp_client(policy_requires_mcp=True)
        if self._mcp_client is None or self._mcp_surfaces is None:
            raise LocalWorkflowHostError("MCP client is not configured")
        try:
            return self._mcp_surfaces.preflight_apple_reviewed_tool_schema(
                snapshot_id, self._mcp_client, tool_name=tool_name
            )
        except (
            MCPConnectionClientError,
            MCPSurfaceSnapshotError,
            ModelExecutionError,
        ) as error:
            raise LocalWorkflowHostError(
                "Apple MCP schema preflight is unavailable"
            ) from error

    def discover_mcp_tools(self) -> tuple[MCPDiscoveredTool, ...]:
        """Return the current configured MCP tool names and schemas for human review."""

        self._ensure_mcp_client(policy_requires_mcp=True)
        if self._mcp_client is None:
            raise LocalWorkflowHostError("MCP client is not configured")
        try:
            return self._mcp_client.list_tools()
        except MCPConnectionClientError as error:
            raise LocalWorkflowHostError(
                "MCP surface discovery is unavailable"
            ) from error

    def bind_mcp_package(
        self,
        *,
        package_source_handle: str,
        snapshot_id: str,
        now: datetime,
    ) -> MCPWorkflowCapabilityBinding:
        """Bind one staged declared-tool policy to a current reviewed MCP surface."""

        revision = self._catalog.import_staged(
            self._stager.stage(package_source_handle, now=now)
        )
        policy = compile_workflow_policy(
            revision,
            capability_catalog=self._capability_catalog,
            descriptor_validators=self._descriptor_validators,
        )
        self._ensure_mcp_client(policy_requires_mcp=True)
        if self._mcp_client is None or self._mcp_bindings is None:
            raise LocalWorkflowHostError("MCP client is not configured")
        try:
            return self._mcp_bindings.bind(
                policy=policy, snapshot_id=snapshot_id, client=self._mcp_client
            )
        except (MCPWorkflowCapabilityBindingError, MCPSurfaceSnapshotError) as error:
            raise LocalWorkflowHostError(
                "MCP package binding is unavailable"
            ) from error

    def register(
        self,
        *,
        workflow_id: str,
        package_source_handle: str,
        now: datetime,
        mcp_binding_id: str | None = None,
    ) -> WorkflowRegistration:
        """Stage, compile, and bind a human-selected package to a local alias."""

        revision = self._catalog.import_staged(
            self._stager.stage(package_source_handle, now=now)
        )
        policy = compile_workflow_policy(
            revision,
            capability_catalog=self._capability_catalog,
            descriptor_validators=self._descriptor_validators,
        )
        self._ensure_mcp_client(policy_requires_mcp=bool(policy.declared_tools))
        profile = self._registrations.configured_profile()
        return self._registrations.register(
            workflow_id=workflow_id,
            policy=policy,
            capability_resolution=resolve_capabilities(
                policy,
                available_capabilities={
                    *profile.capabilities,
                    *(
                        {"local_tool_sandbox"}
                        if self._runner.local_tool_execution_available
                        else set()
                    ),
                    *(
                        {"mcp_read_only", "mcp_side_effects"}
                        if self._mcp_client is not None
                        else set()
                    ),
                },
            ),
            mcp_binding_id=mcp_binding_id,
        )

    def prepare(
        self,
        *,
        workflow_id: str,
        prompt: str,
        workspace_artifact_ids: Sequence[str] = (),
        now: datetime,
    ) -> PreparedWorkflowInput:
        """Seal a local CLI prompt for a registered workflow."""

        return self._preparation.prepare(
            workflow_id=workflow_id,
            prompt=prompt,
            workspace_artifact_ids=workspace_artifact_ids,
            now=now,
        )

    def prepare_sealed_artifact_input(
        self,
        *,
        workflow_id: str,
        invocation_id: str,
        role: str,
        media_type: str,
        schema_digest: str | None,
        content: bytes,
        expires_at: datetime,
        now: datetime,
    ):
        """Seal one declared artifact input for an enabled sealed receiver."""

        if self._sealed_artifact_preparation is None:
            raise LocalWorkflowHostError("sealed artifact runner is unavailable")
        return self._sealed_artifact_preparation.prepare(
            workflow_id=workflow_id,
            receiver_id=InstallationIdentityProvider().principal,
            invocation_id=invocation_id,
            role=role,
            media_type=media_type,
            schema_digest=schema_digest,
            content=content,
            expires_at=expires_at,
            now=now,
        )

    def run_sealed_artifact(
        self, invocation: SealedArtifactInvocation, *, now: datetime
    ) -> SealedArtifactInvocationResult:
        """Run one enabled sealed-artifact invocation through the host composition."""

        if self._sealed_artifact_runner is None:
            raise LocalWorkflowHostError("sealed artifact runner is unavailable")
        try:
            return self._sealed_artifact_runner.run(invocation, now=now)
        except Exception as error:
            raise LocalWorkflowHostError(
                "sealed artifact runner is unavailable"
            ) from error

    def invoke_saved(
        self,
        *,
        package_name: str,
        prompt: str,
        workspace_files: Sequence[Path],
        workspace_artifact_ids: Sequence[str] = (),
        dry_run: bool,
        approval_broker: LocalActionApprovalBroker | None,
        guardrail_registry: InMemoryGuardrailRegistry | None = None,
        now: datetime,
    ) -> SavedWorkflowDryRunResult | RunDarWorkflowResult:
        """Run one registered saved package without accepting source authority."""

        if workspace_files and workspace_artifact_ids:
            raise LocalWorkflowHostError(
                "workspace files and artifacts cannot be combined"
            )
        if dry_run and (workspace_files or workspace_artifact_ids):
            raise LocalWorkflowHostError("dry run cannot accept workspace files")
        try:
            registration = self._registrations.resolve(package_name)
            revision = self._catalog.revision(
                registration.package_id, registration.revision_digest
            )
            policy = compile_workflow_policy(
                revision,
                capability_catalog=self._capability_catalog,
                descriptor_validators=self._descriptor_validators,
            )
        except WorkflowRegistrationError as error:
            raise LocalWorkflowHostError("saved package is unavailable") from error
        except (PackageCatalogError, PolicyCompilationError) as error:
            raise LocalWorkflowHostError("saved package is unavailable") from error
        if policy.policy_digest != registration.policy_digest:
            raise LocalWorkflowHostError("saved package policy does not match")
        self._revalidate_capability_providers(registration, policy)
        artifact_ids = tuple(workspace_artifact_ids) or tuple(
            self.ingress_default_file(
                workflow_id=registration.workflow_id, path=path, now=now
            ).artifact_id
            for path in workspace_files
        )
        prepared = self.prepare(
            workflow_id=registration.workflow_id,
            prompt=prompt,
            workspace_artifact_ids=artifact_ids,
            now=now,
        )
        if dry_run:
            self.dry_run(
                workflow_id=registration.workflow_id,
                prepared_input_id=prepared.prepared_input_id,
                now=now,
            )
            return SavedWorkflowDryRunResult(
                status="ready",
                workflow_id=registration.workflow_id,
                registration_digest=registration.registration_digest,
                package_id=registration.package_id,
                revision_digest=registration.revision_digest,
                profile_id=registration.profile_id,
            )
        return self.run(
            workflow_id=registration.workflow_id,
            prepared_input_id=prepared.prepared_input_id,
            now=now,
            approval_broker=approval_broker,
            guardrail_registry=guardrail_registry,
        )

    def prepare_local_model(self, *, model_id: str) -> LocalModelPreparationResult:
        """Prepare the configured reviewed model through this authorized action."""

        if model_id != self._profile.model_id:
            return LocalModelPreparationResult(model_id, "recipe_unavailable")
        return self._model_preparation.prepare(
            model_id=model_id,
            adapter_id=self._profile.adapter_id,
            runner_id=self._profile.runner_id,
            authorized=True,
        )

    def ingress_file(
        self,
        *,
        workflow_id: str,
        path: Path,
        role: str,
        media_type: str,
        now: datetime,
    ) -> WorkspaceInputArtifact:
        """Copy one trusted CLI-selected file under its registered policy."""

        if self._workspace_ingress is None:
            raise LocalWorkflowHostError("workspace file ingress is not configured")
        try:
            registration = self._registrations.resolve(workflow_id)
            revision = self._catalog.revision(
                registration.package_id, registration.revision_digest
            )
            policy = compile_workflow_policy(
                revision,
                capability_catalog=self._capability_catalog,
                descriptor_validators=self._descriptor_validators,
            )
        except (
            WorkflowRegistrationError,
            PackageCatalogError,
            PolicyCompilationError,
        ) as error:
            raise LocalWorkflowHostError(
                "workflow registration is unavailable"
            ) from error
        if policy.policy_digest != registration.policy_digest:
            raise LocalWorkflowHostError("workflow registration policy does not match")
        self._revalidate_capability_providers(registration, policy)
        try:
            return self._workspace_ingress.ingress(
                source_path=path,
                role=role,
                media_type=media_type,
                policy=WorkspaceIngressPolicy(
                    workflow_id=registration.workflow_id,
                    registration_digest=registration.registration_digest,
                    accepted_roles=policy.task_invocation.allowed_artifact_roles,
                    accepted_media_types=policy.workspace.accepted_input_types,
                ),
                now=now,
            )
        except WorkspaceIngressError as error:
            raise LocalWorkflowHostError(
                "workspace input artifact is unavailable"
            ) from error

    def ingress_default_file(
        self,
        *,
        workflow_id: str,
        path: Path,
        now: datetime,
    ) -> WorkspaceInputArtifact:
        """Ingress one file only when its registered contract is unambiguous."""

        try:
            registration = self._registrations.resolve(workflow_id)
            revision = self._catalog.revision(
                registration.package_id, registration.revision_digest
            )
            policy = compile_workflow_policy(
                revision,
                capability_catalog=self._capability_catalog,
                descriptor_validators=self._descriptor_validators,
            )
        except (
            WorkflowRegistrationError,
            PackageCatalogError,
            PolicyCompilationError,
        ) as error:
            raise LocalWorkflowHostError(
                "workflow registration is unavailable"
            ) from error
        if policy.policy_digest != registration.policy_digest:
            raise LocalWorkflowHostError("workflow registration policy does not match")
        self._revalidate_capability_providers(registration, policy)
        roles = policy.task_invocation.allowed_artifact_roles
        media_types = policy.workspace.accepted_input_types
        if len(roles) != 1 or len(media_types) != 1:
            raise LocalWorkflowHostError(
                "workspace input requires an explicit role and media type"
            )
        return self.ingress_file(
            workflow_id=workflow_id,
            path=path,
            role=roles[0],
            media_type=media_types[0],
            now=now,
        )

    def _revalidate_capability_providers(self, registration: Any, policy: Any) -> None:
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
            raise LocalWorkflowHostError(
                "package capability requirements are unavailable"
            )

    def dry_run(
        self, *, workflow_id: str, prepared_input_id: str, now: datetime
    ) -> DryRunDarWorkflowResult:
        """Validate a sealed run without invoking a model or consuming input."""

        self._ensure_mcp_client_for_workflow(workflow_id)
        return self._runner.dry_run(_request(workflow_id, prepared_input_id), now=now)

    def run(
        self,
        *,
        workflow_id: str,
        prepared_input_id: str,
        now: datetime,
        approval_broker: LocalActionApprovalBroker | None = None,
        guardrail_registry: InMemoryGuardrailRegistry | None = None,
    ) -> RunDarWorkflowResult:
        """Execute a sealed local no-tool workflow through the one runner."""

        self._ensure_mcp_client_for_workflow(workflow_id)
        return self._runner.run(
            _request(workflow_id, prepared_input_id),
            now=now,
            approval_broker=approval_broker,
            guardrail_registry=guardrail_registry,
        )

    def run_debug(
        self,
        *,
        workflow_id: str,
        prepared_input_id: str,
        now: datetime,
        approval_broker: LocalActionApprovalBroker | None = None,
        guardrail_registry: InMemoryGuardrailRegistry | None = None,
    ) -> DebugRunWorkflowResult:
        """Run one sealed workflow with authenticated local diagnostics."""

        self._ensure_mcp_client_for_workflow(workflow_id)
        return self._runner.run_debug(
            _request(workflow_id, prepared_input_id),
            now=now,
            approval_broker=approval_broker,
            guardrail_registry=guardrail_registry,
        )

    def debug_diagnostic(
        self, diagnostic_id: str, *, now: datetime
    ) -> DebugWorkflowDiagnostic:
        """Return one current-principal debug diagnostic by its opaque identifier."""

        return self._runner.debug_diagnostic(diagnostic_id, now=now)

    def delete_debug_diagnostic(self, diagnostic_id: str, *, now: datetime) -> None:
        """Revoke one current-principal debug diagnostic."""

        self._runner.delete_debug_diagnostic(diagnostic_id, now=now)

    def run_traces(self) -> tuple[RedactedRunTrace, ...]:
        """Return redaction-safe traces for completed or failed local runs."""

        return self._runner.traces()

    def _ensure_mcp_client_for_workflow(self, workflow_id: str) -> None:
        try:
            registration = self._registrations.resolve(workflow_id)
        except WorkflowRegistrationError as error:
            raise LocalWorkflowHostError(
                "workflow registration is unavailable"
            ) from error
        self._ensure_mcp_client(
            policy_requires_mcp=registration.mcp_binding_id is not None
        )

    def _ensure_mcp_client(self, *, policy_requires_mcp: bool) -> None:
        if not policy_requires_mcp:
            return
        if self._mcp_client is None:
            raise LocalWorkflowHostError("MCP client is not configured")
        try:
            generation = self._mcp_client.current_generation
        except MCPConnectionClientError:
            try:
                self._mcp_client.initialize()
            except MCPConnectionClientError as error:
                raise LocalWorkflowHostError(
                    "configured MCP connection is unavailable"
                ) from error
        else:
            if generation <= 0:
                raise LocalWorkflowHostError("configured MCP connection is unavailable")


def _request(workflow_id: str, prepared_input_id: str) -> RunDarWorkflowRequest:
    return RunDarWorkflowRequest.from_mapping(
        {
            "format_version": 1,
            "workflow_id": workflow_id,
            "prepared_input_id": prepared_input_id,
        }
    )


def _configuration_path(root: Path) -> Path:
    return root / "host.json"


def _read_configuration(root: Path) -> LocalWorkflowHostConfiguration:
    try:
        value = json.loads(_configuration_path(root).read_text(encoding="utf-8"))
        package_root = Path(value["package_root"])
        profile_id = value["profile_id"]
        configured_input_root = value.get("workspace_input_root")
        input_max_bytes = value.get(
            "workspace_input_max_bytes", _DEFAULT_WORKSPACE_INPUT_MAX_BYTES
        )
    except (FileNotFoundError, KeyError, TypeError, json.JSONDecodeError) as error:
        raise LocalWorkflowHostError("local host is not configured") from error
    _validate_package_root(package_root)
    workspace_input_root = (
        Path(configured_input_root) if isinstance(configured_input_root, str) else None
    )
    if configured_input_root is not None and workspace_input_root is None:
        raise LocalWorkflowHostError("local host configuration is invalid")
    if workspace_input_root is not None:
        _validate_workspace_input_root(workspace_input_root)
    _validate_workspace_input_max_bytes(input_max_bytes)
    if not isinstance(profile_id, str) or not profile_id.startswith("v1."):
        raise LocalWorkflowHostError("local host configuration is invalid")
    return LocalWorkflowHostConfiguration(
        package_root,
        profile_id,
        workspace_input_root,
        input_max_bytes,
        _mcp_configuration(value.get("mcp_client_configuration")),
    )


def _write_configuration(root: Path, value: LocalWorkflowHostConfiguration) -> None:
    destination = _configuration_path(root)
    temporary = destination.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(
            {
                "format_version": 1,
                "package_root": str(value.package_root),
                "profile_id": value.profile_id,
                "workspace_input_root": (
                    str(value.workspace_input_root)
                    if value.workspace_input_root is not None
                    else None
                ),
                "workspace_input_max_bytes": value.workspace_input_max_bytes,
                "mcp_client_configuration": _mcp_configuration_mapping(
                    value.mcp_client_configuration
                ),
            },
            sort_keys=True,
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )
    os.chmod(temporary, 0o600)
    os.replace(temporary, destination)


def _mcp_client(
    *,
    root: Path,
    configuration: LocalWorkflowHostConfiguration,
    connections: MCPConnectionControlPlane,
) -> MCPConnectionClient | None:
    client_configuration = configuration.mcp_client_configuration
    if client_configuration is None:
        return None
    return MCPConnectionClient(
        connections=connections,
        configuration=client_configuration,
        transport_factory=HTTPSJSONRPCMCPTransportFactory(),
        oauth_revalidator=DiscoveredOAuthRevalidator(
            store=PrivateStateStore(root),
            transport=UrllibOAuthMetadataHTTPTransport(),
        ),
    )


def _connection_control(
    root: Path,
) -> tuple[LocalWorkflowHostConfiguration, MCPConnectionControlPlane]:
    _validate_root(root)
    configuration = _read_configuration(root)
    store = PrivateStateStore(root)
    profiles = LocalModelProfileControlPlane(store=store)
    try:
        profiles.load(configuration.profile_id)
    except LocalModelProfileError as error:
        raise LocalWorkflowHostError(
            "configured local profile is unavailable"
        ) from error
    return configuration, MCPConnectionControlPlane(store=store, profiles=profiles)


def _mcp_configuration_mapping(
    value: MCPClientConfiguration | None,
) -> dict[str, object] | None:
    if value is None:
        return None
    return {
        "connection_id": value.connection_id,
        "authentication_id": value.authentication_id,
        "peer_certificate_sha256": value.peer_certificate_sha256,
        "timeout_seconds": value.timeout_seconds,
        "max_response_bytes": value.max_response_bytes,
    }


def _mcp_configuration(value: object) -> MCPClientConfiguration | None:
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != {
        "connection_id",
        "authentication_id",
        "peer_certificate_sha256",
        "timeout_seconds",
        "max_response_bytes",
    }:
        raise LocalWorkflowHostError("local host configuration is invalid")
    try:
        return MCPClientConfiguration(**value)
    except (TypeError, MCPConnectionClientError) as error:
        raise LocalWorkflowHostError("local host configuration is invalid") from error


def _validate_root(path: Path) -> None:
    if not path.is_absolute() or "." in path.parts or ".." in path.parts:
        raise LocalWorkflowHostError("host root must be an absolute canonical path")
    path.mkdir(mode=0o700, parents=True, exist_ok=True)


def _authored_input_contract(input_kind: str) -> str:
    if input_kind == "image_artifact":
        return "one image artifact"
    return input_kind.replace("_", " ")


def _validate_package_root(path: Path) -> None:
    if not path.is_absolute() or "." in path.parts or ".." in path.parts:
        raise LocalWorkflowHostError("package root must be an absolute canonical path")
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    mode = os.lstat(path).st_mode
    if os.path.islink(path) or not stat.S_ISDIR(mode):
        raise LocalWorkflowHostError("package root is unavailable")


def _validate_workspace_input_root(path: Path) -> None:
    if not path.is_absolute() or "." in path.parts or ".." in path.parts:
        raise LocalWorkflowHostError("workspace input root must be canonical")
    try:
        mode = os.lstat(path).st_mode
    except FileNotFoundError as error:
        raise LocalWorkflowHostError("workspace input root is unavailable") from error
    if not os.path.isdir(path) or os.path.islink(path) or not stat.S_ISDIR(mode):
        raise LocalWorkflowHostError("workspace input root is unavailable")


def _validate_workspace_input_max_bytes(value: object) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise LocalWorkflowHostError("workspace input maximum bytes is invalid")


def _workspace_ingress_service(
    *,
    root: Path,
    configuration: LocalWorkflowHostConfiguration,
    store: PrivateStateStore,
) -> WorkspaceIngressService | None:
    if configuration.workspace_input_root is None:
        return None
    parent = root / "workspace-inputs"
    parent.mkdir(mode=0o700, exist_ok=True)
    return WorkspaceIngressService(
        input_root=configuration.workspace_input_root,
        private_workspace_parent=parent,
        store=store,
        owner=InstallationIdentityProvider().principal,
        max_file_bytes=configuration.workspace_input_max_bytes,
        artifact_ttl=timedelta(minutes=5),
    )
