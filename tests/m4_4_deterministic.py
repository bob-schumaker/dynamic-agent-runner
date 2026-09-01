"""Deterministic successor-lifecycle adapter registry."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import tempfile
from collections.abc import Callable
import json
from unittest.mock import patch

import yaml

from dynamic_agent_runner.openai_client import (
    ModelResponse,
    ModelToolCall,
    OpenAIClientAdapter,
)
from dynamic_agent_runner.guardrails import GuardrailResult, InMemoryGuardrailRegistry
from dynamic_agent_runner.workflow_host.authoring_materials import (
    AuthoringMaterialInput,
)
from dynamic_agent_runner.workflow_host.authorized_tools import (
    LocalApprovalDecision,
)
from dynamic_agent_runner.workflow_host.host import (
    LocalWorkflowHost,
    LocalWorkflowHostError,
    attach_mcp_client,
    configure_local_host,
    configure_mcp_api_token,
    create_mcp_connection,
)
from dynamic_agent_runner.workflow_host import host as host_module
from dynamic_agent_runner.workflow_host.mcp_client import (
    MCPClientConfiguration,
    MCPConnectionClient,
    MCPTransportResponse,
)
from dynamic_agent_runner.workflow_host.mcp_surfaces import MCPDiscoveredTool
from dynamic_agent_runner.workflow_host.oauth import OAuthTokenBundle
from dynamic_agent_runner.workflow_host.package_sources import (
    PackageSourceSelectionError,
)
from dynamic_agent_runner.workflow_host.runner import (
    RunDarWorkflowError,
    RunDarWorkflowRequest,
)


_SUPPORTED_SCENARIO_ADAPTER_IDS = frozenset(
    {
        "document-summary-v1",
        "email-file-body-v1",
        "generic-email-send-v1",
        "guardrail-input-v1",
        "guardrail-tool-input-v1",
        "hybrid-brief-v1",
        "mailbox-triage-v1",
        "no-tool-graph-and-skill-v1",
        "oauth-reconnect-v1",
        "side-effect-recovery-v1",
        "structured-single-model-review-v1",
    }
)


def supported_scenario_adapter_ids() -> frozenset[str]:
    """Return the positive scenarios with an explicit lifecycle adapter."""

    return _SUPPORTED_SCENARIO_ADAPTER_IDS


_TEMPLATE_ROOT = (
    Path(__file__).resolve().parents[1]
    / "specs"
    / "agent-engineering-plugin-migration"
    / "legacy-dar-authoring"
    / "templates"
)
_EVALUATION_TEMPLATE_ROOT = _TEMPLATE_ROOT.parent / "evaluation-templates"


class _Responses:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> ModelResponse:
        self.calls.append(kwargs)
        return ModelResponse(content="completed locally")


class _Client:
    def __init__(self) -> None:
        self.responses = _Responses()


class _StructuredResponses:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> ModelResponse:
        self.calls.append(kwargs)
        return ModelResponse(content="review complete")


class _StructuredClient:
    def __init__(self) -> None:
        self.responses = _StructuredResponses()


class _Guardrail:
    def __init__(self) -> None:
        self.calls = 0

    def check_input(self, subject: object) -> GuardrailResult:
        if subject != "Review the submitted answer.":
            raise ValueError("input guardrail received an unexpected subject")
        self.calls += 1
        return GuardrailResult(guardrail_id="require_input")

    def check_tool_input(self, subject: object) -> GuardrailResult:
        expected = {
            "phase": "tool_input",
            "tool_id": "mail_list_unread",
            "node_id": "answer_request",
            "arguments": {},
            "tool_call_id": "call-1",
        }
        if subject != expected:
            raise ValueError("tool-input guardrail received an unexpected subject")
        self.calls += 1
        return GuardrailResult(guardrail_id="require_tool_input", phase="tool_input")


class _GraphSkillResponses:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.responses = iter(
            (
                ModelResponse(content="proceed"),
                ModelResponse(content="completed locally"),
            )
        )

    def create(self, **kwargs: object) -> ModelResponse:
        self.calls.append(kwargs)
        return next(self.responses)


class _GraphSkillClient:
    def __init__(self) -> None:
        self.responses = _GraphSkillResponses()


class _ToolResponses:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.responses = iter(
            (
                ModelResponse(
                    content=None,
                    tool_calls=(
                        ModelToolCall(
                            id="call-1", name="mail_list_unread", arguments="{}"
                        ),
                    ),
                ),
                ModelResponse(content="three unread messages"),
            )
        )

    def create(self, **kwargs: object) -> ModelResponse:
        self.calls.append(kwargs)
        return next(self.responses)


class _ToolClient:
    def __init__(self) -> None:
        self.responses = _ToolResponses()


class _WriteResponses:
    def __init__(self, *, artifact_role: str | None) -> None:
        self.calls: list[dict[str, object]] = []
        body = "Body from artifact" if artifact_role else "Welcome!"
        envelope = {
            "format_version": 1,
            "arguments": {"recipient": "ada@example.test", "body": body},
            "sources": {
                "recipient": {
                    "kind": "prompt_span",
                    "start_byte": 0,
                    "end_byte": 16,
                    "normalization": "identity",
                },
                "body": (
                    {"kind": "artifact", "ref": artifact_role}
                    if artifact_role
                    else {
                        "kind": "prompt_span",
                        "start_byte": 17,
                        "end_byte": 25,
                        "normalization": "identity",
                    }
                ),
            },
        }
        self.responses = iter(
            (
                ModelResponse(
                    content=None,
                    tool_calls=(
                        ModelToolCall(
                            id="call-1",
                            name="mail_send",
                            arguments=json.dumps(
                                {
                                    "provenance_envelope": json.dumps(
                                        envelope, sort_keys=True, separators=(",", ":")
                                    )
                                },
                                sort_keys=True,
                                separators=(",", ":"),
                            ),
                        ),
                    ),
                ),
                ModelResponse(content="message sent"),
            )
        )

    def create(self, **kwargs: object) -> ModelResponse:
        self.calls.append(kwargs)
        return next(self.responses)


class _WriteClient:
    def __init__(self, *, artifact_role: str | None) -> None:
        self.responses = _WriteResponses(artifact_role=artifact_role)


class _ApprovedBroker:
    def __init__(self) -> None:
        self.calls = 0

    def decide(self, **_kwargs: object) -> LocalApprovalDecision:
        self.calls += 1
        return LocalApprovalDecision.APPROVED


class _Secrets:
    values: dict[str, str] = {}

    def __init__(self, **_kwargs: object) -> None:
        return None

    def store(self, secret: str) -> str:
        reference = f"secret-{len(self.values) + 1}"
        self.values[reference] = secret
        return reference

    def load(self, reference: str) -> str:
        return self.values[reference]

    def delete(self, reference: str) -> None:
        self.values.pop(reference, None)

    def replace(self, reference: str, secret: str) -> None:
        self.values[reference] = secret


class _ReadOnlyMCP:
    calls: list[tuple[str, dict[str, object]]] = []

    def __init__(
        self, *, configuration: MCPClientConfiguration, **_kwargs: object
    ) -> None:
        self.connection_id = configuration.connection_id
        self.authentication_id = configuration.authentication_id
        self.current_generation = 1

    def initialize(self) -> None:
        return None

    def list_tools(self) -> tuple[MCPDiscoveredTool, ...]:
        return (
            MCPDiscoveredTool(
                name="list_unread",
                input_schema={
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
            ),
            MCPDiscoveredTool(
                name="send_email",
                input_schema={
                    "type": "object",
                    "properties": {
                        "recipient": {"type": "string"},
                        "body": {"type": "string"},
                    },
                    "required": ["recipient", "body"],
                    "additionalProperties": False,
                },
            ),
        )

    def call_tool(self, name: str, arguments: dict[str, object]) -> dict[str, object]:
        self.calls.append((name, arguments))
        return {"content": [{"type": "text", "text": "three unread messages"}]}


class _OAuthSession:
    def __init__(self) -> None:
        self.closed = False

    def initialize(self, **_kwargs: object) -> MCPTransportResponse:
        return MCPTransportResponse("a" * 64, 1, "2025-06-18", "mail")

    def close(self) -> None:
        self.closed = True

    def list_tools(self, **_kwargs: object) -> tuple[MCPDiscoveredTool, ...]:
        return (
            MCPDiscoveredTool(
                name="list_unread",
                input_schema={"type": "object", "properties": {}},
            ),
        )

    def call_tool(self, **kwargs: object) -> dict[str, object]:
        name = kwargs["name"]
        arguments = kwargs["arguments"]
        assert isinstance(name, str) and isinstance(arguments, dict)
        _ReadOnlyMCP.calls.append((name, arguments))
        return {"content": [{"type": "text", "text": "three unread messages"}]}


class _OAuthFactory:
    def __init__(self) -> None:
        self.sessions: list[_OAuthSession] = []

    def open(self, **_kwargs: object) -> _OAuthSession:
        session = _OAuthSession()
        self.sessions.append(session)
        return session


class _OAuthRefresher:
    def __init__(self) -> None:
        self.calls = 0

    def refresh(self, **_kwargs: object) -> OAuthTokenBundle:
        self.calls += 1
        return OAuthTokenBundle(access_token="refreshed-access")


def run_oauth_reconnect(scenario) -> dict[str, object]:
    """Refresh OAuth, re-review the new generation, then invoke its binding."""

    if scenario.scenario_id != "oauth-reconnect-v1":
        raise ValueError("OAuth reconnect adapter received the wrong scenario")
    with tempfile.TemporaryDirectory(
        dir="/private/tmp", prefix="m44-acceptance-"
    ) as temporary:
        root = Path(temporary)
        state_root = root / "state"
        package_root = root / "packages"
        package_root.mkdir(mode=0o700)
        _Secrets.values.clear()
        _ReadOnlyMCP.calls.clear()
        client = _ToolClient()
        factory = _OAuthFactory()
        refresher = _OAuthRefresher()
        with (
            patch(
                "dynamic_agent_runner.workflow_host.connections.KeyringSecretStore",
                _Secrets,
            ),
            patch(
                "dynamic_agent_runner.workflow_host.host.create_local_adapter",
                lambda profile: OpenAIClientAdapter(
                    client,
                    models=[profile.execution_model_id],
                    is_local=True,
                    model_id_mapping={profile.execution_model_id: profile.model_id},
                    execution_profile_adapter_id=profile.adapter_id,
                ),
            ),
        ):
            configure_local_host(
                root=state_root,
                package_root=package_root,
                model_id="local-model",
                base_url="http://127.0.0.1:11434/v1",
            )
            connection = create_mcp_connection(
                root=state_root,
                endpoint="https://mcp.example.test/v1",
                scopes={"mail.read"},
                authentication_method="oauth_authorization_code_pkce_loopback",
            )
            configuration, connections = host_module._connection_control(state_root)
            authentication = connections.configure_oauth_token(
                connection.connection_id,
                OAuthTokenBundle(
                    access_token="initial-access",
                    refresh_token="refresh-token",
                    expires_at=datetime(2026, 8, 24, 13, tzinfo=UTC),
                ).secret_value(),
                token_endpoint="https://login.example.test/token",
                client_id="public-client-id",
            )
            attached = attach_mcp_client(
                root=state_root,
                connection_id=connection.connection_id,
                authentication_id=authentication.authentication_id,
                peer_certificate_sha256="a" * 64,
                timeout_seconds=10,
                max_response_bytes=32768,
            )
            mcp = MCPConnectionClient(
                connections=connections,
                configuration=attached.mcp_client_configuration,
                transport_factory=factory,
                oauth_refresher=refresher,
                now=lambda: datetime(2026, 8, 24, 12, 30, tzinfo=UTC),
            )
            host = LocalWorkflowHost.open(state_root)
            host._mcp_client = mcp
            host._registrations._mcp_client = mcp
            host._runner._mcp_client = mcp
            mcp.initialize()
            first = host.review_mcp_surface(
                approved_read_only_tool_names={"list_unread"}
            )
            reference = next(iter(_Secrets.values))
            _Secrets.values[reference] = OAuthTokenBundle(
                access_token="expired-access",
                refresh_token="refresh-token",
                expires_at=datetime(2026, 8, 24, 12, tzinfo=UTC),
            ).secret_value()
            mcp.reconnect()
            second = host.review_mcp_surface(
                approved_read_only_tool_names={"list_unread"}
            )
            now = datetime.now(UTC)
            source_handle = _author_package(
                host, scenario.scenario_id, now, rewrite=_read_only_package
            )
            binding = host.bind_mcp_package(
                package_source_handle=source_handle,
                snapshot_id=second.snapshot_id,
                now=now,
            )
            registration = host.register(
                workflow_id=scenario.scenario_id,
                package_source_handle=source_handle,
                mcp_binding_id=binding.binding_id,
                now=now,
            )
            prepared = host.prepare(
                workflow_id=registration.workflow_id,
                prompt="List unread email.",
                now=now,
            )
            host.run(
                workflow_id=registration.workflow_id,
                prepared_input_id=prepared.prepared_input_id,
                now=now,
            )
    return {
        "lifecycle": ("authored", "finalized", "registered", "prepared", "invoked"),
        "model_calls": len(client.responses.calls),
        "tool_dispatches": len(_ReadOnlyMCP.calls),
        "oauth_refreshes": refresher.calls,
        "review_generations": (
            first.connection_generation,
            second.connection_generation,
        ),
    }


def run_document_summary(scenario) -> dict[str, object]:
    """Execute the basic-reasoning contract through the real local host."""

    if scenario.scenario_id != "document-summary-v1":
        raise ValueError("document-summary adapter received the wrong scenario")
    with tempfile.TemporaryDirectory(
        dir="/private/tmp", prefix="m44-acceptance-"
    ) as temporary:
        root = Path(temporary)
        package_root = root / "packages"
        state_root = root / "state"
        package_root.mkdir(mode=0o700)
        client = _Client()
        configure_local_host(
            root=state_root,
            package_root=package_root,
            model_id="local-model",
            base_url="http://127.0.0.1:11434/v1",
        )
        with patch(
            "dynamic_agent_runner.workflow_host.host.create_local_adapter",
            lambda profile: OpenAIClientAdapter(
                client,
                models=[profile.execution_model_id],
                is_local=True,
                model_id_mapping={profile.execution_model_id: profile.model_id},
                execution_profile_adapter_id=profile.adapter_id,
            ),
        ):
            host = LocalWorkflowHost.open(state_root)
            now = datetime.now(UTC)
            source_handle = _author_package(host, scenario.scenario_id, now)
            registration = host.register(
                workflow_id=scenario.scenario_id,
                package_source_handle=source_handle,
                now=now,
            )
            prepared = host.prepare(
                workflow_id=registration.workflow_id,
                prompt="Summarize the approved document.",
                now=now,
            )
            host.run(
                workflow_id=registration.workflow_id,
                prepared_input_id=prepared.prepared_input_id,
                now=now,
            )
    return {
        "lifecycle": ("authored", "finalized", "registered", "prepared", "invoked"),
        "model_calls": len(client.responses.calls),
        "tool_dispatches": 0,
    }


def run_authoring_boundary_attack(scenario) -> dict[str, object]:
    """Reject an authoring output that attempts an undeclared host tool path."""

    if scenario.scenario_id != "authoring-boundary-attack-v1":
        raise ValueError("authoring-boundary adapter received the wrong scenario")
    with tempfile.TemporaryDirectory(
        dir="/private/tmp", prefix="m44-acceptance-"
    ) as temporary:
        root = Path(temporary)
        package_root = root / "packages"
        state_root = root / "state"
        package_root.mkdir(mode=0o700)
        configure_local_host(
            root=state_root,
            package_root=package_root,
            model_id="local-model",
            base_url="http://127.0.0.1:11434/v1",
        )
        host = LocalWorkflowHost.open(state_root)
        now = datetime.now(UTC)
        materials = host.issue_authoring_materials(
            materials=(
                AuthoringMaterialInput(
                    role="example", content="approved", disposition="reference_only"
                ),
            ),
            now=now,
        )
        output = host.create_authored_package(
            package_name=scenario.scenario_id, now=now
        )
        for source in _TEMPLATE_ROOT.iterdir():
            content = source.read_text(encoding="utf-8")
            if source.name == "agent-runtime.yaml":
                runtime = yaml.safe_load(content)
                runtime["tools"] = [{"id": "escape", "adapter": "host.shell"}]
                content = yaml.safe_dump(runtime)
            host.write_authored_package_file(
                output_id=output.output_id,
                relative_path=source.name,
                content=content,
                now=now,
            )
        try:
            host.finalize_authored_output(
                output_id=output.output_id,
                material_set_id=materials.material_set_id,
                now=now,
            )
        except Exception:
            pass
        else:
            raise ValueError("unreviewed host tool was finalized")
    return {
        "terminal_phase": "authoring_validation",
        "finalized": False,
        "model_calls": 0,
        "tool_dispatches": 0,
    }


def run_invocation_schema_boundary_attack(scenario) -> dict[str, object]:
    """Reject a host-tool field outside the sealed invocation request shape."""

    if scenario.scenario_id != "invocation-schema-boundary-attack-v1":
        raise ValueError("invocation-boundary adapter received the wrong scenario")
    with tempfile.TemporaryDirectory(
        dir="/private/tmp", prefix="m44-acceptance-"
    ) as temporary:
        root = Path(temporary)
        package_root = root / "packages"
        state_root = root / "state"
        package_root.mkdir(mode=0o700)
        client = _Client()
        configure_local_host(
            root=state_root,
            package_root=package_root,
            model_id="local-model",
            base_url="http://127.0.0.1:11434/v1",
        )
        with patch(
            "dynamic_agent_runner.workflow_host.host.create_local_adapter",
            lambda profile: OpenAIClientAdapter(
                client,
                models=[profile.execution_model_id],
                is_local=True,
                model_id_mapping={profile.execution_model_id: profile.model_id},
                execution_profile_adapter_id=profile.adapter_id,
            ),
        ):
            host = LocalWorkflowHost.open(state_root)
            now = datetime.now(UTC)
            source_handle = _author_package(host, scenario.scenario_id, now)
            registration = host.register(
                workflow_id=scenario.scenario_id,
                package_source_handle=source_handle,
                now=now,
            )
            prepared = host.prepare(
                workflow_id=registration.workflow_id,
                prompt="Answer the request.",
                now=now,
            )
            try:
                RunDarWorkflowRequest.from_mapping(
                    {
                        "format_version": 1,
                        "workflow_id": registration.workflow_id,
                        "prepared_input_id": prepared.prepared_input_id,
                        "host_tool_input": {"adapter": "host.shell"},
                    }
                )
            except RunDarWorkflowError:
                pass
            else:
                raise ValueError("model-facing host tool input was accepted")
            if client.responses.calls or host.run_traces():
                raise ValueError(
                    "invocation schema boundary reached workflow execution"
                )
    return {
        "terminal_phase": "invocation",
        "model_calls": 0,
        "tool_dispatches": 0,
    }


def run_portable_package_handoff(scenario) -> dict[str, object]:
    """Refuse a recipient host's direct access to an unpublished package."""

    if scenario.scenario_id != "portable-package-handoff-v1":
        raise ValueError("portable-handoff adapter received the wrong scenario")
    with tempfile.TemporaryDirectory(
        dir="/private/tmp", prefix="m44-acceptance-"
    ) as temporary:
        root = Path(temporary)
        author_packages = root / "author-packages"
        author_state = root / "author-state"
        recipient_packages = root / "recipient-packages"
        recipient_state = root / "recipient-state"
        author_packages.mkdir(mode=0o700)
        recipient_packages.mkdir(mode=0o700)
        configure_local_host(
            root=author_state,
            package_root=author_packages,
            model_id="local-model",
            base_url="http://127.0.0.1:11434/v1",
        )
        configure_local_host(
            root=recipient_state,
            package_root=recipient_packages,
            model_id="local-model",
            base_url="http://127.0.0.1:11434/v1",
        )
        author = LocalWorkflowHost.open(author_state)
        recipient = LocalWorkflowHost.open(recipient_state)
        now = datetime.now(UTC)
        _author_package(author, scenario.scenario_id, now)
        try:
            recipient.select_package(author_packages / scenario.scenario_id, now=now)
        except PackageSourceSelectionError:
            pass
        else:
            raise ValueError("recipient selected an unpublished package")
        if recipient.run_traces():
            raise ValueError("recipient dispatched an unpublished package")
    return {
        "terminal_phase": "source_selection",
        "recipient_registered": False,
        "model_calls": 0,
        "tool_dispatches": 0,
    }


def run_mcp_missing_connection(scenario, *, rewrite: str) -> dict[str, object]:
    """Stop a tool-bearing package before registration without an MCP client."""

    expected = {
        "mcp-tooling-missing-connection-v1": lambda name, content: _write_package(
            name, content, artifact_role=None
        ),
        "read-only-mcp-missing-connection-v1": _read_only_package,
        "file-provenance-missing-ingress-v1": lambda name, content: _write_package(
            name, content, artifact_role="vendor-ticket"
        ),
        "oauth-missing-connection-v1": _read_only_package,
    }
    if expected.get(scenario.scenario_id) is None:
        raise ValueError("missing-connection adapter received the wrong scenario")
    if rewrite not in {"file", "read", "write"}:
        raise ValueError("missing-connection rewrite is invalid")
    with tempfile.TemporaryDirectory(
        dir="/private/tmp", prefix="m44-acceptance-"
    ) as temporary:
        root = Path(temporary)
        package_root = root / "packages"
        state_root = root / "state"
        package_root.mkdir(mode=0o700)
        configure_local_host(
            root=state_root,
            package_root=package_root,
            model_id="local-model",
            base_url="http://127.0.0.1:11434/v1",
        )
        host = LocalWorkflowHost.open(state_root)
        now = datetime.now(UTC)
        source_handle = _author_package(
            host, scenario.scenario_id, now, rewrite=expected[scenario.scenario_id]
        )
        try:
            host.register(
                workflow_id=scenario.scenario_id,
                package_source_handle=source_handle,
                now=now,
            )
        except LocalWorkflowHostError:
            pass
        else:
            raise ValueError("tool-bearing package registered without an MCP client")
        if host.run_traces():
            raise ValueError("missing MCP connection reached workflow execution")
    return {
        "terminal_phase": "capability_preflight",
        "registered": False,
        "model_calls": 0,
        "tool_dispatches": 0,
    }


def run_hybrid_brief(scenario) -> dict[str, object]:
    """Execute the no-tool workflow after sealing two trusted workspace inputs."""

    if scenario.scenario_id != "hybrid-brief-v1":
        raise ValueError("hybrid-brief adapter received the wrong scenario")
    with tempfile.TemporaryDirectory(
        dir="/private/tmp", prefix="m44-acceptance-"
    ) as temporary:
        root = Path(temporary)
        package_root = root / "packages"
        state_root = root / "state"
        input_root = root / "input"
        package_root.mkdir(mode=0o700)
        input_root.mkdir(mode=0o700)
        paths = []
        for role in ("brief", "risk-artifact"):
            path = input_root / f"{role}.txt"
            path.write_text(f"{role} body", encoding="utf-8")
            paths.append((role, path))
        client = _Client()
        configure_local_host(
            root=state_root,
            package_root=package_root,
            workspace_input_root=input_root,
            model_id="local-model",
            base_url="http://127.0.0.1:11434/v1",
        )
        with patch(
            "dynamic_agent_runner.workflow_host.host.create_local_adapter",
            lambda profile: OpenAIClientAdapter(
                client,
                models=[profile.execution_model_id],
                is_local=True,
                model_id_mapping={profile.execution_model_id: profile.model_id},
                execution_profile_adapter_id=profile.adapter_id,
            ),
        ):
            host = LocalWorkflowHost.open(state_root)
            now = datetime.now(UTC)
            source_handle = _author_package(
                host, scenario.scenario_id, now, rewrite=_hybrid_package
            )
            registration = host.register(
                workflow_id=scenario.scenario_id,
                package_source_handle=source_handle,
                now=now,
            )
            artifact_ids = tuple(
                host.ingress_file(
                    workflow_id=registration.workflow_id,
                    path=path,
                    role=role,
                    media_type="text/plain",
                    now=now,
                ).artifact_id
                for role, path in paths
            )
            prepared = host.prepare(
                workflow_id=registration.workflow_id,
                prompt="Summarize the approved brief.",
                workspace_artifact_ids=artifact_ids,
                now=now,
            )
            host.run(
                workflow_id=registration.workflow_id,
                prepared_input_id=prepared.prepared_input_id,
                now=now,
            )
    return {
        "lifecycle": ("authored", "finalized", "registered", "prepared", "invoked"),
        "model_calls": len(client.responses.calls),
        "tool_dispatches": 0,
        "artifact_count": len(artifact_ids),
    }


def run_no_tool_graph_and_skill(scenario) -> dict[str, object]:
    """Run a package-local skill through an LLM route and final LLM step."""

    if scenario.scenario_id != "no-tool-graph-and-skill-v1":
        raise ValueError("no-tool graph adapter received the wrong scenario")
    with tempfile.TemporaryDirectory(
        dir="/private/tmp", prefix="m44-acceptance-"
    ) as temporary:
        root = Path(temporary)
        package_root = root / "packages"
        state_root = root / "state"
        package_root.mkdir(mode=0o700)
        client = _GraphSkillClient()
        configure_local_host(
            root=state_root,
            package_root=package_root,
            model_id="local-model",
            base_url="http://127.0.0.1:11434/v1",
        )
        with patch(
            "dynamic_agent_runner.workflow_host.host.create_local_adapter",
            lambda profile: OpenAIClientAdapter(
                client,
                models=[profile.execution_model_id],
                is_local=True,
                model_id_mapping={profile.execution_model_id: profile.model_id},
                execution_profile_adapter_id=profile.adapter_id,
            ),
        ):
            host = LocalWorkflowHost.open(state_root)
            now = datetime.now(UTC)
            source_handle = _author_package(
                host,
                scenario.scenario_id,
                now,
                rewrite=_graph_skill_package,
                extra_files={
                    "skill-bundle/skills/review-guide/SKILL.md": "Use the supplied request only.",
                    **{
                        source.name: source.read_text(encoding="utf-8")
                        for source in _EVALUATION_TEMPLATE_ROOT.iterdir()
                    },
                },
            )
            registration = host.register(
                workflow_id=scenario.scenario_id,
                package_source_handle=source_handle,
                now=now,
            )
            prepared = host.prepare(
                workflow_id=registration.workflow_id,
                prompt="Review this request.",
                now=now,
            )
            host.run(
                workflow_id=registration.workflow_id,
                prepared_input_id=prepared.prepared_input_id,
                now=now,
            )
    return {
        "lifecycle": ("authored", "finalized", "registered", "prepared", "invoked"),
        "model_calls": len(client.responses.calls),
        "tool_dispatches": 0,
        "skill_count": 1,
        "evaluation_artifact_count": len(tuple(_EVALUATION_TEMPLATE_ROOT.iterdir())),
    }


def run_structured_single_model_review(scenario) -> dict[str, object]:
    """Run a no-tool review and preserve its registered terminal output shape."""

    if scenario.scenario_id != "structured-single-model-review-v1":
        raise ValueError("structured review adapter received the wrong scenario")
    with tempfile.TemporaryDirectory(
        dir="/private/tmp", prefix="m44-acceptance-"
    ) as temporary:
        root = Path(temporary)
        package_root = root / "packages"
        state_root = root / "state"
        package_root.mkdir(mode=0o700)
        client = _StructuredClient()
        configure_local_host(
            root=state_root,
            package_root=package_root,
            model_id="local-model",
            base_url="http://127.0.0.1:11434/v1",
        )
        with patch(
            "dynamic_agent_runner.workflow_host.host.create_local_adapter",
            lambda profile: OpenAIClientAdapter(
                client,
                models=[profile.execution_model_id],
                is_local=True,
                model_id_mapping={profile.execution_model_id: profile.model_id},
                execution_profile_adapter_id=profile.adapter_id,
            ),
        ):
            host = LocalWorkflowHost.open(state_root)
            now = datetime.now(UTC)
            source_handle = _author_package(
                host, scenario.scenario_id, now, rewrite=_structured_review_package
            )
            registration = host.register(
                workflow_id=scenario.scenario_id,
                package_source_handle=source_handle,
                now=now,
            )
            prepared = host.prepare(
                workflow_id=registration.workflow_id,
                prompt="Review the submitted answer.",
                now=now,
            )
            run = host.run(
                workflow_id=registration.workflow_id,
                prepared_input_id=prepared.prepared_input_id,
                now=now,
            )
    return {
        "lifecycle": ("authored", "finalized", "registered", "prepared", "invoked"),
        "model_calls": len(client.responses.calls),
        "tool_dispatches": 0,
        "terminal_output": run.output,
    }


def run_guardrail_input(scenario) -> dict[str, object]:
    """Run an input guardrail through the saved-package host boundary."""

    if scenario.scenario_id != "guardrail-input-v1":
        raise ValueError("input guardrail adapter received the wrong scenario")
    with tempfile.TemporaryDirectory(
        dir="/private/tmp", prefix="m44-acceptance-"
    ) as temporary:
        root = Path(temporary)
        package_root = root / "packages"
        state_root = root / "state"
        package_root.mkdir(mode=0o700)
        client = _StructuredClient()
        guardrail = _Guardrail()
        configure_local_host(
            root=state_root,
            package_root=package_root,
            model_id="local-model",
            base_url="http://127.0.0.1:11434/v1",
        )
        with patch(
            "dynamic_agent_runner.workflow_host.host.create_local_adapter",
            lambda profile: OpenAIClientAdapter(
                client,
                models=[profile.execution_model_id],
                is_local=True,
                model_id_mapping={profile.execution_model_id: profile.model_id},
                execution_profile_adapter_id=profile.adapter_id,
            ),
        ):
            host = LocalWorkflowHost.open(state_root)
            now = datetime.now(UTC)
            source_handle = _author_package(
                host, scenario.scenario_id, now, rewrite=_input_guardrail_package
            )
            registration = host.register(
                workflow_id=scenario.scenario_id,
                package_source_handle=source_handle,
                now=now,
            )
            prepared = host.prepare(
                workflow_id=registration.workflow_id,
                prompt="Review the submitted answer.",
                now=now,
            )
            host.run(
                workflow_id=registration.workflow_id,
                prepared_input_id=prepared.prepared_input_id,
                now=now,
                guardrail_registry=InMemoryGuardrailRegistry(
                    {"require_input": guardrail.check_input}
                ),
            )
    return {
        "lifecycle": ("authored", "finalized", "registered", "prepared", "invoked"),
        "model_calls": len(client.responses.calls),
        "tool_dispatches": 0,
        "guardrail_calls": guardrail.calls,
    }


def run_guardrail_missing_registry(scenario) -> dict[str, object]:
    """Reject a declared input guardrail before consuming its prepared input."""

    if scenario.scenario_id != "guardrail-input-missing-v1":
        raise ValueError("missing input guardrail adapter received the wrong scenario")
    with tempfile.TemporaryDirectory(
        dir="/private/tmp", prefix="m44-acceptance-"
    ) as temporary:
        root = Path(temporary)
        package_root = root / "packages"
        state_root = root / "state"
        package_root.mkdir(mode=0o700)
        client = _StructuredClient()
        guardrail = _Guardrail()
        configure_local_host(
            root=state_root,
            package_root=package_root,
            model_id="local-model",
            base_url="http://127.0.0.1:11434/v1",
        )
        with patch(
            "dynamic_agent_runner.workflow_host.host.create_local_adapter",
            lambda profile: OpenAIClientAdapter(
                client,
                models=[profile.execution_model_id],
                is_local=True,
                model_id_mapping={profile.execution_model_id: profile.model_id},
                execution_profile_adapter_id=profile.adapter_id,
            ),
        ):
            host = LocalWorkflowHost.open(state_root)
            now = datetime.now(UTC)
            source_handle = _author_package(
                host, scenario.scenario_id, now, rewrite=_input_guardrail_package
            )
            registration = host.register(
                workflow_id=scenario.scenario_id,
                package_source_handle=source_handle,
                now=now,
            )
            prepared = host.prepare(
                workflow_id=registration.workflow_id,
                prompt="Review the submitted answer.",
                now=now,
            )
            try:
                host.run(
                    workflow_id=registration.workflow_id,
                    prepared_input_id=prepared.prepared_input_id,
                    now=now,
                )
            except RunDarWorkflowError:
                pass
            else:
                raise ValueError("missing input guardrail reached workflow execution")
            if client.responses.calls:
                raise ValueError("missing input guardrail reached model execution")
            host.run(
                workflow_id=registration.workflow_id,
                prepared_input_id=prepared.prepared_input_id,
                now=now,
                guardrail_registry=InMemoryGuardrailRegistry(
                    {"require_input": guardrail.check_input}
                ),
            )
    return {
        "terminal_phase": "capability_preflight",
        "model_calls": 0,
        "tool_dispatches": 0,
        "retry_model_calls": len(client.responses.calls),
    }


def run_tool_input_guardrail_missing_registry(scenario) -> dict[str, object]:
    """Reject a declared tool-input guardrail before consuming its input."""

    if scenario.scenario_id != "guardrail-tool-input-missing-v1":
        raise ValueError(
            "missing tool-input guardrail adapter received the wrong scenario"
        )
    with tempfile.TemporaryDirectory(
        dir="/private/tmp", prefix="m44-acceptance-"
    ) as temporary:
        root = Path(temporary)
        package_root = root / "packages"
        state_root = root / "state"
        package_root.mkdir(mode=0o700)
        _Secrets.values.clear()
        _ReadOnlyMCP.calls.clear()
        client = _ToolClient()
        guardrail = _Guardrail()
        with (
            patch(
                "dynamic_agent_runner.workflow_host.connections.KeyringSecretStore",
                _Secrets,
            ),
            patch(
                "dynamic_agent_runner.workflow_host.host.MCPConnectionClient",
                _ReadOnlyMCP,
            ),
            patch(
                "dynamic_agent_runner.workflow_host.host.create_local_adapter",
                lambda profile: OpenAIClientAdapter(
                    client,
                    models=[profile.execution_model_id],
                    is_local=True,
                    model_id_mapping={profile.execution_model_id: profile.model_id},
                    execution_profile_adapter_id=profile.adapter_id,
                ),
            ),
        ):
            configure_local_host(
                root=state_root,
                package_root=package_root,
                model_id="local-model",
                base_url="http://127.0.0.1:11434/v1",
            )
            connection = create_mcp_connection(
                root=state_root,
                endpoint="https://mcp.example.test/v1",
                scopes={"mail.read"},
                authentication_method="api_token",
            )
            authentication = configure_mcp_api_token(
                root=state_root,
                connection_id=connection.connection_id,
                token="secret-token",
            )
            attach_mcp_client(
                root=state_root,
                connection_id=connection.connection_id,
                authentication_id=authentication.authentication_id,
                peer_certificate_sha256="a" * 64,
                timeout_seconds=10,
                max_response_bytes=32768,
            )
            host = LocalWorkflowHost.open(state_root)
            now = datetime.now(UTC)
            source_handle = _author_package(
                host, scenario.scenario_id, now, rewrite=_tool_input_guardrail_package
            )
            snapshot = host.review_mcp_surface(
                approved_read_only_tool_names={"list_unread"}
            )
            binding = host.bind_mcp_package(
                package_source_handle=source_handle,
                snapshot_id=snapshot.snapshot_id,
                now=now,
            )
            registration = host.register(
                workflow_id=scenario.scenario_id,
                package_source_handle=source_handle,
                mcp_binding_id=binding.binding_id,
                now=now,
            )
            prepared = host.prepare(
                workflow_id=registration.workflow_id,
                prompt="List unread email.",
                now=now,
            )
            try:
                host.run(
                    workflow_id=registration.workflow_id,
                    prepared_input_id=prepared.prepared_input_id,
                    now=now,
                )
            except RunDarWorkflowError:
                pass
            else:
                raise ValueError("missing tool-input guardrail reached execution")
            if client.responses.calls or _ReadOnlyMCP.calls:
                raise ValueError("missing tool-input guardrail reached dispatch")
            host.run(
                workflow_id=registration.workflow_id,
                prepared_input_id=prepared.prepared_input_id,
                now=now,
                guardrail_registry=InMemoryGuardrailRegistry(
                    {"require_tool_input": guardrail.check_tool_input}
                ),
            )
    return {
        "terminal_phase": "capability_preflight",
        "model_calls": 0,
        "tool_dispatches": 0,
        "retry_model_calls": len(client.responses.calls),
        "retry_tool_dispatches": len(_ReadOnlyMCP.calls),
    }


def run_guardrail_tool_input(scenario) -> dict[str, object]:
    """Run a tool-input guardrail before one reviewed MCP read dispatch."""

    if scenario.scenario_id != "guardrail-tool-input-v1":
        raise ValueError("tool-input guardrail adapter received the wrong scenario")
    with tempfile.TemporaryDirectory(
        dir="/private/tmp", prefix="m44-acceptance-"
    ) as temporary:
        root = Path(temporary)
        package_root = root / "packages"
        state_root = root / "state"
        package_root.mkdir(mode=0o700)
        _Secrets.values.clear()
        _ReadOnlyMCP.calls.clear()
        client = _ToolClient()
        guardrail = _Guardrail()
        with (
            patch(
                "dynamic_agent_runner.workflow_host.connections.KeyringSecretStore",
                _Secrets,
            ),
            patch(
                "dynamic_agent_runner.workflow_host.host.MCPConnectionClient",
                _ReadOnlyMCP,
            ),
            patch(
                "dynamic_agent_runner.workflow_host.host.create_local_adapter",
                lambda profile: OpenAIClientAdapter(
                    client,
                    models=[profile.execution_model_id],
                    is_local=True,
                    model_id_mapping={profile.execution_model_id: profile.model_id},
                    execution_profile_adapter_id=profile.adapter_id,
                ),
            ),
        ):
            configure_local_host(
                root=state_root,
                package_root=package_root,
                model_id="local-model",
                base_url="http://127.0.0.1:11434/v1",
            )
            connection = create_mcp_connection(
                root=state_root,
                endpoint="https://mcp.example.test/v1",
                scopes={"mail.read"},
                authentication_method="api_token",
            )
            authentication = configure_mcp_api_token(
                root=state_root,
                connection_id=connection.connection_id,
                token="secret-token",
            )
            attach_mcp_client(
                root=state_root,
                connection_id=connection.connection_id,
                authentication_id=authentication.authentication_id,
                peer_certificate_sha256="a" * 64,
                timeout_seconds=10,
                max_response_bytes=32768,
            )
            host = LocalWorkflowHost.open(state_root)
            now = datetime.now(UTC)
            source_handle = _author_package(
                host, scenario.scenario_id, now, rewrite=_tool_input_guardrail_package
            )
            snapshot = host.review_mcp_surface(
                approved_read_only_tool_names={"list_unread"}
            )
            binding = host.bind_mcp_package(
                package_source_handle=source_handle,
                snapshot_id=snapshot.snapshot_id,
                now=now,
            )
            registration = host.register(
                workflow_id=scenario.scenario_id,
                package_source_handle=source_handle,
                mcp_binding_id=binding.binding_id,
                now=now,
            )
            prepared = host.prepare(
                workflow_id=registration.workflow_id,
                prompt="List unread email.",
                now=now,
            )
            host.run(
                workflow_id=registration.workflow_id,
                prepared_input_id=prepared.prepared_input_id,
                now=now,
                guardrail_registry=InMemoryGuardrailRegistry(
                    {"require_tool_input": guardrail.check_tool_input}
                ),
            )
    if _ReadOnlyMCP.calls != [("list_unread", {})]:
        raise ValueError("tool-input guardrail did not permit the reviewed dispatch")
    return {
        "lifecycle": ("authored", "finalized", "registered", "prepared", "invoked"),
        "model_calls": len(client.responses.calls),
        "tool_dispatches": len(_ReadOnlyMCP.calls),
        "guardrail_calls": guardrail.calls,
    }


def run_mailbox_triage(scenario) -> dict[str, object]:
    """Execute the reviewed read-only MCP contract through the local host."""

    if scenario.scenario_id != "mailbox-triage-v1":
        raise ValueError("mailbox-triage adapter received the wrong scenario")
    with tempfile.TemporaryDirectory(
        dir="/private/tmp", prefix="m44-acceptance-"
    ) as temporary:
        root = Path(temporary)
        package_root = root / "packages"
        state_root = root / "state"
        package_root.mkdir(mode=0o700)
        _Secrets.values.clear()
        _ReadOnlyMCP.calls.clear()
        client = _ToolClient()
        with (
            patch(
                "dynamic_agent_runner.workflow_host.connections.KeyringSecretStore",
                _Secrets,
            ),
            patch(
                "dynamic_agent_runner.workflow_host.host.MCPConnectionClient",
                _ReadOnlyMCP,
            ),
            patch(
                "dynamic_agent_runner.workflow_host.host.create_local_adapter",
                lambda profile: OpenAIClientAdapter(
                    client,
                    models=[profile.execution_model_id],
                    is_local=True,
                    model_id_mapping={profile.execution_model_id: profile.model_id},
                    execution_profile_adapter_id=profile.adapter_id,
                ),
            ),
        ):
            configure_local_host(
                root=state_root,
                package_root=package_root,
                model_id="local-model",
                base_url="http://127.0.0.1:11434/v1",
            )
            connection = create_mcp_connection(
                root=state_root,
                endpoint="https://mcp.example.test/v1",
                scopes={"mail.read"},
                authentication_method="api_token",
            )
            authentication = configure_mcp_api_token(
                root=state_root,
                connection_id=connection.connection_id,
                token="secret-token",
            )
            attach_mcp_client(
                root=state_root,
                connection_id=connection.connection_id,
                authentication_id=authentication.authentication_id,
                peer_certificate_sha256="a" * 64,
                timeout_seconds=10,
                max_response_bytes=32768,
            )
            host = LocalWorkflowHost.open(state_root)
            now = datetime.now(UTC)
            source_handle = _author_package(
                host, scenario.scenario_id, now, rewrite=_read_only_package
            )
            snapshot = host.review_mcp_surface(
                approved_read_only_tool_names={"list_unread"}
            )
            binding = host.bind_mcp_package(
                package_source_handle=source_handle,
                snapshot_id=snapshot.snapshot_id,
                now=now,
            )
            registration = host.register(
                workflow_id=scenario.scenario_id,
                package_source_handle=source_handle,
                mcp_binding_id=binding.binding_id,
                now=now,
            )
            prepared = host.prepare(
                workflow_id=registration.workflow_id,
                prompt="List unread email.",
                now=now,
            )
            host.run(
                workflow_id=registration.workflow_id,
                prepared_input_id=prepared.prepared_input_id,
                now=now,
            )
    if _ReadOnlyMCP.calls != [("list_unread", {})]:
        raise ValueError("mailbox-triage did not make its reviewed read dispatch")
    return {
        "lifecycle": ("authored", "finalized", "registered", "prepared", "invoked"),
        "model_calls": len(client.responses.calls),
        "tool_dispatches": len(_ReadOnlyMCP.calls),
    }


def _run_write(
    scenario, *, artifact_role: str | None, verify_replay: bool = False
) -> dict[str, object]:
    """Execute one approved MCP write, optionally from trusted ingress."""
    with tempfile.TemporaryDirectory(
        dir="/private/tmp", prefix="m44-acceptance-"
    ) as temporary:
        root = Path(temporary)
        package_root = root / "packages"
        state_root = root / "state"
        package_root.mkdir(mode=0o700)
        _Secrets.values.clear()
        _ReadOnlyMCP.calls.clear()
        client = _WriteClient(artifact_role=artifact_role)
        with (
            patch(
                "dynamic_agent_runner.workflow_host.connections.KeyringSecretStore",
                _Secrets,
            ),
            patch(
                "dynamic_agent_runner.workflow_host.host.MCPConnectionClient",
                _ReadOnlyMCP,
            ),
            patch(
                "dynamic_agent_runner.workflow_host.host.create_local_adapter",
                lambda profile: OpenAIClientAdapter(
                    client,
                    models=[profile.execution_model_id],
                    is_local=True,
                    model_id_mapping={profile.execution_model_id: profile.model_id},
                    execution_profile_adapter_id=profile.adapter_id,
                ),
            ),
        ):
            input_root = root / "input"
            if artifact_role:
                input_root.mkdir(mode=0o700)
                (input_root / "body.txt").write_text(
                    "Body from artifact", encoding="utf-8"
                )
                configure_local_host(
                    root=state_root,
                    package_root=package_root,
                    workspace_input_root=input_root,
                    model_id="local-model",
                    base_url="http://127.0.0.1:11434/v1",
                )
            else:
                configure_local_host(
                    root=state_root,
                    package_root=package_root,
                    model_id="local-model",
                    base_url="http://127.0.0.1:11434/v1",
                )
            connection = create_mcp_connection(
                root=state_root,
                endpoint="https://mcp.example.test/v1",
                scopes={"mail.send"},
                authentication_method="api_token",
            )
            authentication = configure_mcp_api_token(
                root=state_root,
                connection_id=connection.connection_id,
                token="secret-token",
            )
            attach_mcp_client(
                root=state_root,
                connection_id=connection.connection_id,
                authentication_id=authentication.authentication_id,
                peer_certificate_sha256="a" * 64,
                timeout_seconds=10,
                max_response_bytes=32768,
            )
            host = LocalWorkflowHost.open(state_root)
            now = datetime.now(UTC)
            source_handle = _author_package(
                host,
                scenario.scenario_id,
                now,
                rewrite=lambda name, content: _write_package(
                    name, content, artifact_role=artifact_role
                ),
            )
            snapshot = host.review_mcp_surface(
                approved_read_only_tool_names=(),
                approved_tool_side_effects={"send_email": "write"},
            )
            binding = host.bind_mcp_package(
                package_source_handle=source_handle,
                snapshot_id=snapshot.snapshot_id,
                now=now,
            )
            registration = host.register(
                workflow_id=scenario.scenario_id,
                package_source_handle=source_handle,
                mcp_binding_id=binding.binding_id,
                now=now,
            )
            artifact_ids = ()
            if artifact_role:
                artifact_ids = (
                    host.ingress_file(
                        workflow_id=registration.workflow_id,
                        path=input_root / "body.txt",
                        role=artifact_role,
                        media_type="text/plain",
                        now=now,
                    ).artifact_id,
                )
            prepared = host.prepare(
                workflow_id=registration.workflow_id,
                prompt=(
                    "ada@example.test" if artifact_role else "ada@example.test Welcome!"
                ),
                workspace_artifact_ids=artifact_ids,
                now=now,
            )
            broker = _ApprovedBroker()
            host.run(
                workflow_id=registration.workflow_id,
                prepared_input_id=prepared.prepared_input_id,
                now=now,
                approval_broker=broker,
            )
            if verify_replay:
                try:
                    host.run(
                        workflow_id=registration.workflow_id,
                        prepared_input_id=prepared.prepared_input_id,
                        now=now,
                        approval_broker=broker,
                    )
                except Exception:
                    pass
                else:
                    raise ValueError("side-effecting prepared input was replayed")
    body = "Body from artifact" if artifact_role else "Welcome!"
    if _ReadOnlyMCP.calls != [
        ("send_email", {"recipient": "ada@example.test", "body": body})
    ]:
        raise ValueError("approved write did not make its expected dispatch")
    return {
        "lifecycle": ("authored", "finalized", "registered", "prepared", "invoked"),
        "model_calls": len(client.responses.calls),
        "tool_dispatches": len(_ReadOnlyMCP.calls),
        "approval_requests": broker.calls,
    }


def run_generic_email_send(scenario) -> dict[str, object]:
    """Execute the prompt-provenance MCP write contract."""

    if scenario.scenario_id != "generic-email-send-v1":
        raise ValueError("generic-email-send adapter received the wrong scenario")
    return _run_write(scenario, artifact_role=None)


def run_email_file_body(scenario) -> dict[str, object]:
    """Execute the trusted-ingress MCP write contract."""

    if scenario.scenario_id != "email-file-body-v1":
        raise ValueError("email-file-body adapter received the wrong scenario")
    return _run_write(scenario, artifact_role="email_body")


def run_side_effect_recovery(scenario) -> dict[str, object]:
    """Execute one file-backed write and reject a replay of its prepared input."""

    if scenario.scenario_id != "side-effect-recovery-v1":
        raise ValueError("side-effect-recovery adapter received the wrong scenario")
    return _run_write(scenario, artifact_role="vendor-ticket", verify_replay=True)


def _author_package(
    host: LocalWorkflowHost,
    package_name: str,
    now: datetime,
    rewrite: Callable[[str, str], str] | None = None,
    extra_files: dict[str, str] | None = None,
) -> str:
    materials = host.issue_authoring_materials(
        materials=(
            AuthoringMaterialInput(
                role="example", content="approved", disposition="reference_only"
            ),
        ),
        now=now,
    )
    output = host.create_authored_package(package_name=package_name, now=now)
    for source in _TEMPLATE_ROOT.iterdir():
        content = source.read_text(encoding="utf-8")
        if rewrite is not None:
            content = rewrite(source.name, content)
        host.write_authored_package_file(
            output_id=output.output_id,
            relative_path=source.name,
            content=content,
            now=now,
        )
    for relative_path, content in (extra_files or {}).items():
        host.write_authored_package_file(
            output_id=output.output_id,
            relative_path=relative_path,
            content=content,
            now=now,
        )
    _, source_handle = host.finalize_and_select_authored_output(
        output_id=output.output_id,
        material_set_id=materials.material_set_id,
        now=now,
    )
    return source_handle


def _read_only_package(name: str, content: str) -> str:
    if name == "workflow-descriptor.yaml":
        descriptor = yaml.safe_load(content)
        descriptor["package_id"] = "mail-reader"
        descriptor["tools"] = [
            {
                "id": "mail_list_unread",
                "kind": "mcp",
                "remote_tool_name": "list_unread",
                "side_effect": "read",
            }
        ]
        descriptor["task_invocation"].update(
            {"allowed_tool_ids": ["mail_list_unread"], "max_total_tool_calls": 3}
        )
        descriptor["limits"]["max_steps"] = 4
        return yaml.safe_dump(descriptor)
    if name == "agent-runtime.yaml":
        runtime = yaml.safe_load(content)
        runtime["package_id"] = "mail-reader"
        runtime["runtime"]["execution_policy"].update(
            {
                "max_steps": 3,
                "tool_use_completion": {
                    "run_again": "required",
                    "stop_on_tool": "disabled",
                    "final_output": "default",
                },
            }
        )
        runtime["tools"] = [
            {
                "id": "mail_list_unread",
                "label": "List unread mail",
                "tool_type": "external_api",
                "description_for_llm": "List unread mail.",
                "adapter": "host.mcp",
                "input_schema": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
                "side_effect": "read",
                "approval_required": False,
                "timeout": "runtime_default",
                "retry_policy": "none",
                "failure_behavior": "error",
            }
        ]
        runtime["nodes"][0]["available_tools"] = ["mail_list_unread"]
        return yaml.safe_dump(runtime)
    return content


def _hybrid_package(name: str, content: str) -> str:
    if name == "workflow-descriptor.yaml":
        descriptor = yaml.safe_load(content)
        descriptor["package_id"] = "hybrid-brief"
        descriptor["task_invocation"]["allowed_artifact_roles"] = [
            "brief",
            "risk-artifact",
        ]
        return yaml.safe_dump(descriptor)
    if name == "agent-runtime.yaml":
        runtime = yaml.safe_load(content)
        runtime["package_id"] = "hybrid-brief"
        return yaml.safe_dump(runtime)
    return content


def _graph_skill_package(name: str, content: str) -> str:
    if name == "workflow-descriptor.yaml":
        descriptor = yaml.safe_load(content)
        descriptor["package_id"] = "graph-skill-review"
        descriptor["skills"] = ["review-guide"]
        descriptor["task_invocation"]["entrypoint"] = "route_request"
        descriptor["limits"]["max_steps"] = 4
        return yaml.safe_dump(descriptor)
    if name == "agent-runtime.yaml":
        runtime = yaml.safe_load(content)
        runtime["package_id"] = "graph-skill-review"
        runtime["entrypoint"] = "route_request"
        runtime["packaging"]["skill_bundle_dir"] = "skill-bundle"
        runtime["runtime"]["execution_policy"]["max_steps"] = 4
        runtime["runtime"]["execution_policy"]["skill_source_resolution"] = {
            "enabled": True,
            "allowed_sources": ["package_bundle"],
            "prompt_role": "developer",
        }
        runtime["skills"] = [
            {"id": "review-guide", "bundled_path": "skills/review-guide/SKILL.md"}
        ]
        runtime["nodes"] = [
            {
                "id": "route_request",
                "kind": "llm_step",
                "model": "local-model",
                "skill_refs": ["review-guide"],
                "prompt": {"user_template": "Route {prompt}", "input_vars": ["prompt"]},
            },
            {
                "id": "choose_path",
                "kind": "decision_step",
                "decision_subtype": "llm_route",
                "route_from": "route_request",
                "decision_contract": {
                    "allowed_paths": [{"id": "proceed", "target": "finish_review"}],
                    "default_path": "proceed",
                },
            },
            {
                "id": "finish_review",
                "kind": "llm_step",
                "model": "local-model",
                "prompt": {
                    "user_template": "Finish {prompt}",
                    "input_vars": ["prompt"],
                },
            },
        ]
        runtime["edges"] = [
            {"from": "route_request", "to": "choose_path", "edge_kind": "sequential"},
            {
                "from": "choose_path",
                "to": "finish_review",
                "edge_kind": "branch",
                "condition": "proceed",
            },
        ]
        return yaml.safe_dump(runtime)
    return content


def _structured_review_package(name: str, content: str) -> str:
    if name == "workflow-descriptor.yaml":
        descriptor = yaml.safe_load(content)
        descriptor["package_id"] = "structured-review"
        descriptor["output"] = {"schema_ref": "review_result"}
        descriptor["task_invocation"]["terminal_output_schema_ref"] = "review_result"
        return yaml.safe_dump(descriptor)
    if name == "agent-runtime.yaml":
        runtime = yaml.safe_load(content)
        runtime["package_id"] = "structured-review"
        runtime["output_contracts"] = [
            {"id": "review_result", "required_fields": ["message"]}
        ]
        return yaml.safe_dump(runtime)
    return content


def _input_guardrail_package(name: str, content: str) -> str:
    if name == "workflow-descriptor.yaml":
        descriptor = yaml.safe_load(content)
        descriptor["package_id"] = "input-guardrail-review"
        return yaml.safe_dump(descriptor)
    if name == "agent-runtime.yaml":
        runtime = yaml.safe_load(content)
        runtime["package_id"] = "input-guardrail-review"
        runtime["extensions"] = {
            "guardrails": {
                "declarations": [
                    {
                        "id": "require_input",
                        "phase": "input",
                        "behavior_on_tripwire": "abort",
                    }
                ]
            }
        }
        return yaml.safe_dump(runtime)
    return content


def _tool_input_guardrail_package(name: str, content: str) -> str:
    content = _read_only_package(name, content)
    if name != "agent-runtime.yaml":
        return content
    runtime = yaml.safe_load(content)
    runtime["extensions"] = {
        "guardrails": {
            "declarations": [
                {
                    "id": "require_tool_input",
                    "phase": "tool_input",
                    "behavior_on_tripwire": "abort",
                }
            ]
        }
    }
    return yaml.safe_dump(runtime)


def _write_package(name: str, content: str, *, artifact_role: str | None) -> str:
    if name == "workflow-descriptor.yaml":
        descriptor = yaml.safe_load(content)
        descriptor["package_id"] = "mail-writer"
        descriptor["tools"] = [
            {
                "id": "mail_send",
                "kind": "mcp",
                "remote_tool_name": "send_email",
                "side_effect": "write",
                "approval_required": True,
            }
        ]
        descriptor["task_invocation"].update(
            {
                "allowed_tool_ids": ["mail_send"],
                "max_total_tool_calls": 1,
                "allowed_artifact_roles": ([artifact_role] if artifact_role else []),
                "argument_sources": {
                    "mail_send": {
                        "recipient": {
                            "sources": ["cited_original_prompt_span"],
                            "authority": True,
                        },
                        "body": {
                            "sources": (
                                [f"artifact_role:{artifact_role}"]
                                if artifact_role
                                else ["cited_original_prompt_span"]
                            ),
                            "authority": False,
                        },
                    }
                },
            }
        )
        return yaml.safe_dump(descriptor)
    if name == "agent-runtime.yaml":
        runtime = yaml.safe_load(content)
        runtime["package_id"] = "mail-writer"
        runtime["runtime"]["execution_policy"]["tool_use_completion"] = {
            "run_again": "required",
            "stop_on_tool": "disabled",
            "final_output": "default",
        }
        runtime["tools"] = [
            {
                "id": "mail_send",
                "label": "Send email",
                "tool_type": "external_api",
                "description_for_llm": "Send email.",
                "adapter": "host.mcp",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "recipient": {"type": "string"},
                        "body": {"type": "string"},
                    },
                    "required": ["recipient", "body"],
                    "additionalProperties": False,
                },
                "side_effect": "write",
                "approval_required": True,
                "timeout": "runtime_default",
                "retry_policy": "none",
                "failure_behavior": "error",
            }
        ]
        runtime["nodes"][0]["available_tools"] = ["mail_send"]
        return yaml.safe_dump(runtime)
    return content
