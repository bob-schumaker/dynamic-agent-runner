"""Private local host configuration and no-tool runner composition."""

from __future__ import annotations

import json
import os
import stat
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Sequence

from dar_workflow_server.catalog import PackageCatalog, PackageCatalogError
from dar_workflow_server.action_ledger import WorkflowActionLedger
from dar_workflow_server.approvals import WorkflowApprovalStore
from dar_workflow_server.authorized_tools import LocalActionApprovalBroker
from dar_workflow_server.connections import (
    MCPAuthentication,
    MCPConnection,
    MCPConnectionControlPlane,
    MCPConnectionError,
)
from dar_workflow_server.mcp_binding import MCPWorkflowCapabilityBindingControlPlane
from dar_workflow_server.mcp_client import (
    HTTPSJSONRPCMCPTransportFactory,
    MCPClientConfiguration,
    MCPConnectionClient,
    MCPConnectionClientError,
)
from dar_workflow_server.mcp_surfaces import MCPSurfaceSnapshotControlPlane
from dar_workflow_server.package_sources import PackageSourceSelectionPolicy
from dar_workflow_server.policy import (
    PolicyCompilationError,
    compile_workflow_policy,
    resolve_capabilities,
)
from dar_workflow_server.preparation import (
    PreparedWorkflowInput,
    WorkflowInvocationPreparationService,
)
from dar_workflow_server.profiles import (
    InstallationIdentityProvider,
    LocalModelProfileControlPlane,
    LocalModelProfileError,
    create_local_adapter,
)
from dar_workflow_server.registration import (
    WorkflowRegistration,
    WorkflowRegistrationError,
    WorkflowRegistrationService,
)
from dar_workflow_server.runner import (
    DryRunDarWorkflowResult,
    RunDarWorkflowRequest,
    RunDarWorkflowResult,
    WorkflowRunner,
)
from dar_workflow_server.staging import PrivatePackageStager
from dar_workflow_server.state import PrivateStateStore
from dar_workflow_server.workspace_ingress import (
    WorkspaceIngressError,
    WorkspaceIngressPolicy,
    WorkspaceIngressService,
    WorkspaceInputArtifact,
)


_DEFAULT_WORKSPACE_INPUT_MAX_BYTES = 8 * 1024 * 1024


class LocalWorkflowHostError(ValueError):
    """Raised when required human-owned host configuration is unavailable."""


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
        runner: WorkflowRunner,
        workspace_ingress: WorkspaceIngressService | None,
        mcp_client: MCPConnectionClient | None = None,
    ) -> None:
        self._configuration = configuration
        self._sources = sources
        self._stager = stager
        self._catalog = catalog
        self._registrations = registrations
        self._preparation = preparation
        self._runner = runner
        self._workspace_ingress = workspace_ingress
        self._mcp_client = mcp_client

    @classmethod
    def open(cls, root: Path) -> LocalWorkflowHost:
        """Open a configured local host for the current OS user."""

        _validate_root(root)
        configuration = _read_configuration(root)
        store = PrivateStateStore(root)
        profiles = LocalModelProfileControlPlane(store=store)
        profile = profiles.load(configuration.profile_id)
        connections = MCPConnectionControlPlane(store=store, profiles=profiles)
        surfaces = MCPSurfaceSnapshotControlPlane(store=store, connections=connections)
        mcp_bindings = MCPWorkflowCapabilityBindingControlPlane(
            store=store, surfaces=surfaces
        )
        mcp_client = _mcp_client(configuration=configuration, connections=connections)
        catalog = PackageCatalog(root / "catalog")
        registrations = WorkflowRegistrationService(
            profiles=profiles,
            configured_profile_id=profile.profile_id,
            root=root / "registrations",
            mcp_bindings=mcp_bindings if mcp_client is not None else None,
            mcp_client=mcp_client,
            mcp_surfaces=surfaces if mcp_client is not None else None,
        )
        workspace_ingress = _workspace_ingress_service(
            root=root, configuration=configuration, store=store
        )
        preparation = WorkflowInvocationPreparationService(
            registrations=registrations,
            catalog=catalog,
            store=store,
            artifact_verifier=workspace_ingress,
        )
        return cls(
            configuration=configuration,
            sources=PackageSourceSelectionPolicy(
                allowed_root=configuration.package_root, store=store
            ),
            stager=PrivatePackageStager(store=store, private_root=root / "staging"),
            catalog=catalog,
            registrations=registrations,
            preparation=preparation,
            runner=WorkflowRunner(
                registrations=registrations,
                catalog=catalog,
                preparation=preparation,
                model_adapter=create_local_adapter(profile),
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
            ),
            workspace_ingress=workspace_ingress,
            mcp_client=mcp_client,
        )

    def select_package(self, path: Path, *, now: datetime) -> str:
        """Return an opaque handle for one human-selected package directory."""

        return self._sources.select_directory(path, now=now)

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
        policy = compile_workflow_policy(revision)
        self._ensure_mcp_client(policy_requires_mcp=bool(policy.declared_tools))
        return self._registrations.register(
            workflow_id=workflow_id,
            policy=policy,
            capability_resolution=resolve_capabilities(
                policy,
                available_capabilities={
                    "local_model",
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
            policy = compile_workflow_policy(revision)
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
    ) -> RunDarWorkflowResult:
        """Execute a sealed local no-tool workflow through the one runner."""

        self._ensure_mcp_client_for_workflow(workflow_id)
        return self._runner.run(
            _request(workflow_id, prepared_input_id),
            now=now,
            approval_broker=approval_broker,
        )

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


def _validate_package_root(path: Path) -> None:
    if not path.is_absolute() or "." in path.parts or ".." in path.parts:
        raise LocalWorkflowHostError("package root must be an absolute canonical path")


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
