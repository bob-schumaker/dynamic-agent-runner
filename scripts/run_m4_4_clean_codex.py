#!/usr/bin/env python3
"""Run the mandatory CLI-first M4.4 clean-Codex acceptance cases.

The controller owns fixture state, package registration, and the test-owned
``dar-package`` launcher. Codex sees only the installed successor skill,
opaque material IDs, and declared text inputs.
"""

from __future__ import annotations

import argparse
from contextlib import ExitStack, contextmanager
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from threading import Event, Thread
from typing import Any, Callable, Sequence
from urllib.parse import urlparse
from urllib.request import urlopen

from dynamic_agent_runner.workflow_host.authoring_evidence import (
    AuthorThenRunEvidence,
    write_author_then_run_evidence,
)
from dynamic_agent_runner.workflow_host.authoring_materials import (
    AuthoringMaterialInput,
)
from dynamic_agent_runner.workflow_host.host import (
    LocalWorkflowHost,
    LocalWorkflowHostError,
    attach_mcp_client,
    configure_local_host,
)
from dynamic_agent_runner.workflow_host.connections import MCPConnectionControlPlane
from dynamic_agent_runner.workflow_host.mcp_client import MCPClientConfiguration
from dynamic_agent_runner.workflow_host.mcp_surfaces import MCPDiscoveredTool
from dynamic_agent_runner.workflow_host.oauth import OAuthTokenBundle
from dynamic_agent_runner.workflow_host.authorized_tools import LocalApprovalDecision
from dynamic_agent_runner.workflow_host.package_controller import (
    serve_package_controller,
)
from dynamic_agent_runner.workflow_host.profiles import LocalModelProfileControlPlane
from dynamic_agent_runner.workflow_host.state import PrivateStateStore
from dynamic_agent_runner.guardrails import (
    GuardrailResult,
    InMemoryGuardrailRegistry,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))

from m4_4_clean_codex import (  # noqa: E402 - repository test corpus import.
    M44CleanCodexError,
    build_clean_codex_environment,
    create_marketplace,
    stage_dar_package,
)
from m4_4_deterministic import run_fixture_contract  # noqa: E402
from m4_4_scenarios import (  # noqa: E402 - repository test corpus import.
    M44Coverage,
    M44ExternalScenarioPlan,
    M44Scenario,
    M44ScenarioError,
    load_m44_coverage,
    load_m44_external_scenario_plan,
    load_m44_original_scenario_ids,
    load_m44_scenario,
    validate_m44_external_scenario_plan,
    validate_m44_original_scenario_admission,
    validate_m44_evidence,
)


class HarnessError(ValueError):
    """Raised when M4.4 cannot produce a valid redacted acceptance record."""


_ORIGINAL_SCENARIO_IDS = (
    Path(__file__).resolve().parents[1]
    / "tests"
    / "fixtures"
    / "m4-4-original-scenario-ids.json"
)


class _ApprovedActionBroker:
    """Deterministic controller-only approval for declared positive fixtures."""

    def decide(self, **_kwargs: object) -> LocalApprovalDecision:
        return LocalApprovalDecision.APPROVED


class _ControllerSecretStore:
    """Ephemeral controller credential storage for deterministic MCP setup."""

    def __init__(self) -> None:
        self._values: dict[str, str] = {}

    def store(self, secret: str) -> str:
        reference = f"m44-fixture-{len(self._values) + 1}"
        self._values[reference] = secret
        return reference

    def load(self, reference: str) -> str:
        return self._values[reference]

    def delete(self, reference: str) -> None:
        del self._values[reference]

    def replace(self, reference: str, secret: str) -> None:
        self._values[reference] = secret


class _ControllerMCPClient:
    """Fixed reviewed MCP surface with no transport or credential access."""

    def __init__(self, configuration: MCPClientConfiguration) -> None:
        self.connection_id = configuration.connection_id
        self.authentication_id = configuration.authentication_id
        self._generation = 0
        self.calls: list[tuple[str, dict[str, object]]] = []

    @property
    def current_generation(self) -> int:
        if self._generation == 0:
            raise ValueError("controller MCP client is not initialized")
        return self._generation

    def initialize(self) -> None:
        self._generation = 1

    def list_tools(self) -> tuple[MCPDiscoveredTool, ...]:
        return (
            MCPDiscoveredTool(
                name="list_unread",
                input_schema={"type": "object", "properties": {}},
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
                },
            ),
        )

    def call_tool(self, name: str, arguments: dict[str, object]) -> dict[str, object]:
        self.calls.append((name, arguments))
        return {"content": [{"type": "text", "text": "fixture result"}]}


class _ControllerFixtures:
    """The concrete collaborators available to one controller-run scenario."""

    def __init__(
        self,
        *,
        fixture_ids: tuple[str, ...],
        approval_broker_factory: Callable[[], object] | None = None,
        guardrail_registry: InMemoryGuardrailRegistry | None = None,
    ) -> None:
        self.fixture_ids = fixture_ids
        self.approval_broker_factory = approval_broker_factory
        self.guardrail_registry = guardrail_registry


def _configure_controller_mcp(
    *, state_root: Path, profile_id: str, use_oauth: bool = False
) -> tuple[_ControllerMCPClient, MCPConnectionControlPlane]:
    """Persist a fixture-only reviewed connection without touching a network."""

    store = PrivateStateStore(state_root)
    connections = MCPConnectionControlPlane(
        store=store,
        profiles=LocalModelProfileControlPlane(store=store),
        secret_store=_ControllerSecretStore(),
    )
    connection = connections.create(
        profile_id=profile_id,
        endpoint="https://m44-controller.invalid/mcp",
        scopes=("mail.read",),
        authentication_method=(
            "oauth_authorization_code_pkce_loopback" if use_oauth else "api_token"
        ),
    )
    authentication = (
        connections.configure_oauth_token(
            connection.connection_id,
            OAuthTokenBundle(access_token="fixture-access").secret_value(),
            token_endpoint="https://m44-controller.invalid/token",
            client_id="m44-controller",
        )
        if use_oauth
        else connections.configure_api_token(connection.connection_id, "fixture-token")
    )
    attached = attach_mcp_client(
        root=state_root,
        connection_id=connection.connection_id,
        authentication_id=authentication.authentication_id,
        peer_certificate_sha256="a" * 64,
        timeout_seconds=1,
        max_response_bytes=32768,
    )
    if attached.mcp_client_configuration is None:
        raise HarnessError("controller MCP fixture is unavailable")
    client = _ControllerMCPClient(attached.mcp_client_configuration)
    client.initialize()
    return client, connections


def _controller_fixtures(contract: M44Scenario) -> _ControllerFixtures:
    """Provision only the collaborators this controller really owns."""

    fixture_ids = {"local-model-profile", "authoring-broker", "workflow-registration"}
    approval_broker_factory: Callable[[], object] | None = None
    handlers = {}
    if contract.expected_status == "pass":
        if "reviewed-mcp-connection" in contract.required_host_fixtures:
            fixture_ids.add("reviewed-mcp-connection")
        if "oauth-connection" in contract.required_host_fixtures:
            fixture_ids.update(
                {
                    "fake-oauth-provider",
                    "oauth-connection",
                    "reviewed-mcp-connection",
                }
            )
        if "trusted-workspace-ingress" in contract.required_host_fixtures:
            fixture_ids.add("trusted-workspace-ingress")
        if "approval-broker" in contract.required_host_fixtures:
            fixture_ids.add("approval-broker")
            approval_broker_factory = _ApprovedActionBroker
        if "input-guardrail-registry" in contract.required_host_fixtures:
            fixture_ids.add("input-guardrail-registry")
            handlers["require_input"] = lambda _subject: GuardrailResult(
                guardrail_id="require_input"
            )
        if "tool-input-guardrail-registry" in contract.required_host_fixtures:
            fixture_ids.add("tool-input-guardrail-registry")
            handlers["require_tool_input"] = lambda _subject: GuardrailResult(
                guardrail_id="require_tool_input", phase="tool_input"
            )
    return _ControllerFixtures(
        fixture_ids=tuple(sorted(fixture_ids)),
        approval_broker_factory=approval_broker_factory,
        guardrail_registry=InMemoryGuardrailRegistry(handlers) if handlers else None,
    )


def write_manifest_evidence(
    *,
    evidence_directory: Path,
    coverage_source: Path,
    scenario_plan_source: Path,
    scenario_roots: tuple[Path, ...],
    records: tuple[AuthorThenRunEvidence, ...],
) -> Path:
    """Write one complete redacted evidence set for the closed external replay."""

    coverage = load_m44_coverage(coverage_source)
    plan = load_m44_external_scenario_plan(scenario_plan_source)
    validate_m44_external_scenario_plan(
        plan, coverage=coverage, scenario_roots=scenario_roots
    )
    validate_m44_original_scenario_admission(
        load_m44_original_scenario_ids(_ORIGINAL_SCENARIO_IDS),
        plan=plan,
        coverage=coverage,
        scenario_roots=scenario_roots,
    )
    _validate_manifest_records(records, coverage=coverage, plan=plan)
    if evidence_directory.exists() or not evidence_directory.is_absolute():
        raise HarnessError("external evidence directory must be fresh and absolute")
    evidence_directory.mkdir(mode=0o700, parents=True)
    aggregate_records: list[dict[str, str]] = []
    for record in sorted(records, key=lambda value: value.scenario_id):
        destination = evidence_directory / record.scenario_id / "author-then-run.json"
        write_author_then_run_evidence(destination, record)
        aggregate_records.append(
            {
                "scenario_id": record.scenario_id,
                "observed_status": record.observed_status,
                "record_digest": _digest_file(destination),
                "actor_duration_ms": sum(record.actor_durations_ms),
            }
        )
    aggregate = {
        "format_version": "m4.4-external-evidence-v1",
        "coverage_digest": _digest_file(coverage_source),
        "scenario_plan_digest": _digest_file(scenario_plan_source),
        "records": aggregate_records,
        "actor_duration_ms": sum(
            record["actor_duration_ms"] for record in aggregate_records
        ),
    }
    destination = evidence_directory / "aggregate.json"
    destination.write_text(
        json.dumps(aggregate, sort_keys=True, separators=(",", ":")), encoding="utf-8"
    )
    os.chmod(destination, 0o600)
    return destination


def main(argv: Sequence[str] | None = None) -> int:
    """Run the complete manifest-defined clean-Codex M4.4 acceptance replay."""

    arguments = _arguments(argv)
    try:
        with _fake_model_server() as base_url:
            aggregate = run_manifest(
                **vars(arguments), model_id="openai/local-model", base_url=base_url
            )
    except (
        HarnessError,
        LocalWorkflowHostError,
        M44CleanCodexError,
        M44ScenarioError,
    ) as error:
        print(f"M4.4 clean-Codex harness failed: {error}")
        return 2
    print(aggregate.read_text(encoding="utf-8"))
    return 0


@contextmanager
def _fake_model_server():
    """Run the controller-owned deterministic model fixture for one replay."""

    port = _available_loopback_port()
    fixture = Path(__file__).with_name("serve_m4_4_fake_model.py")
    process = subprocess.Popen(
        [sys.executable, str(fixture), "--port", str(port)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    try:
        base_url = f"http://127.0.0.1:{port}/v1"
        _wait_for_fake_model(base_url, process)
        yield base_url
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def _wait_for_fake_model(base_url: str, process: subprocess.Popen[str]) -> None:
    for _ in range(20):
        if process.poll() is not None:
            raise HarnessError("deterministic fake model did not start")
        try:
            with urlopen(f"{base_url}/models", timeout=0.1) as response:  # noqa: S310
                if response.status == 200:
                    return
        except OSError:
            time.sleep(0.05)
    raise HarnessError("deterministic fake model did not start")


def _available_loopback_port() -> int:
    import socket

    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


@contextmanager
def _package_controller(
    *,
    host: LocalWorkflowHost,
    socket_path: Path,
    allowed_commands: tuple[str, ...],
    approval_broker_factory: Callable[[], object] | None = None,
    guardrail_registry: InMemoryGuardrailRegistry | None = None,
    workspace_artifact_ids: list[str] | None = None,
):
    stop_event = Event()
    thread = Thread(
        target=serve_package_controller,
        kwargs={
            "socket_path": socket_path,
            "host": host,
            "allowed_commands": allowed_commands,
            "stop_event": stop_event,
            "approval_broker_factory": approval_broker_factory,
            "guardrail_registry": guardrail_registry,
            "workspace_artifact_ids": (
                workspace_artifact_ids if workspace_artifact_ids is not None else ()
            ),
        },
        daemon=True,
    )
    thread.start()
    for _ in range(20):
        if socket_path.exists():
            break
        time.sleep(0.01)
    if not socket_path.is_socket():
        stop_event.set()
        thread.join(timeout=1)
        raise HarnessError("package controller did not start")
    try:
        yield socket_path
    finally:
        stop_event.set()
        thread.join(timeout=1)
        if thread.is_alive():
            raise HarnessError("package controller did not stop")


def run_manifest(
    *,
    coverage: Path,
    scenario_plan: Path,
    scenario_roots: tuple[Path, ...],
    evidence_directory: Path,
    codex_home: Path,
    plugin_root: Path,
    wheel: Path,
    materials: Path,
    model_id: str,
    base_url: str,
    reviewer_id: str | None,
    reviewer_decision: str,
    codex_executable: str,
    timeout: int,
    plugin_surface: str = "generated-root",
) -> Path:
    """Replay every closed-plan scenario and write its one aggregate evidence set."""

    _validate_deterministic_model(model_id, base_url)
    coverage_contract = load_m44_coverage(coverage)
    plan = load_m44_external_scenario_plan(scenario_plan)
    validate_m44_external_scenario_plan(
        plan, coverage=coverage_contract, scenario_roots=scenario_roots
    )
    validate_m44_original_scenario_admission(
        load_m44_original_scenario_ids(_ORIGINAL_SCENARIO_IDS),
        plan=plan,
        coverage=coverage_contract,
        scenario_roots=scenario_roots,
    )
    sources = _scenario_sources(scenario_roots)
    _verify_fixture_contracts(plan, sources)
    records = tuple(
        run_scenario(
            scenario=sources[entry.scenario_id],
            codex_home=codex_home,
            plugin_root=plugin_root,
            wheel=wheel,
            package_name=entry.package_name,
            workflow_id=entry.workflow_id,
            author_prompt=entry.author_request,
            run_prompt=entry.run_request,
            materials=materials,
            model_id=model_id,
            base_url=base_url,
            evidence=None,
            reviewer_id=reviewer_id,
            reviewer_decision=reviewer_decision,
            codex_executable=codex_executable,
            timeout=timeout,
            plugin_surface=plugin_surface,
        )
        for entry in plan.entries
    )
    return write_manifest_evidence(
        evidence_directory=evidence_directory,
        coverage_source=coverage,
        scenario_plan_source=scenario_plan,
        scenario_roots=scenario_roots,
        records=records,
    )


def run_scenario(
    *,
    scenario: Path,
    codex_home: Path,
    plugin_root: Path,
    wheel: Path,
    package_name: str,
    workflow_id: str,
    author_prompt: str,
    run_prompt: str,
    materials: Path,
    model_id: str,
    base_url: str,
    evidence: Path | None,
    reviewer_id: str | None,
    reviewer_decision: str,
    codex_executable: str,
    timeout: int,
    plugin_surface: str = "generated-root",
) -> AuthorThenRunEvidence:
    """Run one author turn and, for the positive case, one independent run turn."""

    contract = load_m44_scenario(scenario)
    fixtures = _controller_fixtures(contract)
    _validate_inputs(
        contract,
        codex_home,
        plugin_root,
        wheel,
        materials,
        evidence,
        reviewer_decision,
        timeout,
    )
    with tempfile.TemporaryDirectory(
        dir="/private/tmp", prefix="m44-clean-codex-"
    ) as temporary:
        root = Path(temporary)
        author_workspace = root / "author-workspace"
        invocation_workspace = root / "invocation-workspace"
        scenario_codex_home = root / "codex-home"
        package_root, state_root = (
            author_workspace / ".packages",
            author_workspace / ".state",
        )
        author_workspace.mkdir(mode=0o700)
        invocation_workspace.mkdir(mode=0o700)
        package_root.mkdir(mode=0o700)
        controller_input_root = root / "controller-inputs"
        controller_input_root.mkdir(mode=0o700)
        configuration = configure_local_host(
            root=state_root,
            package_root=package_root,
            model_id=model_id,
            base_url=base_url,
            workspace_input_root=controller_input_root,
        )
        mcp_fixture = (
            _configure_controller_mcp(
                state_root=state_root,
                profile_id=configuration.profile_id,
                use_oauth="oauth-connection" in fixtures.fixture_ids,
            )
            if "reviewed-mcp-connection" in fixtures.fixture_ids
            else None
        )
        mcp_client, mcp_connections = mcp_fixture or (None, None)
        host = LocalWorkflowHost.open(
            state_root,
            mcp_client_factory=(lambda _configuration: mcp_client)
            if mcp_client is not None
            else None,
            mcp_connections=mcp_connections,
        )
        with ExitStack() as controllers:
            workspace_artifact_ids: list[str] = []
            author_socket = controllers.enter_context(
                _package_controller(
                    host=host,
                    socket_path=root / "author-controller.sock",
                    allowed_commands=(
                        "project-authoring-materials",
                        "create-authored-package",
                        "write-authored-package-file",
                        "finalize-authored-package",
                    ),
                    approval_broker_factory=fixtures.approval_broker_factory,
                    guardrail_registry=fixtures.guardrail_registry,
                )
            )
            invocation_socket = controllers.enter_context(
                _package_controller(
                    host=host,
                    socket_path=root / "invocation-controller.sock",
                    allowed_commands=("invoke",),
                    approval_broker_factory=fixtures.approval_broker_factory,
                    guardrail_registry=fixtures.guardrail_registry,
                    workspace_artifact_ids=workspace_artifact_ids,
                )
            )
            author_dar_bin = stage_dar_package(
                wheel=wheel,
                controller_socket=author_socket,
                destination=root / "author-dar-bin",
                allowed_commands=(
                    "project-authoring-materials",
                    "create-authored-package",
                    "write-authored-package-file",
                    "finalize-authored-package",
                ),
            )
            invocation_dar_bin = stage_dar_package(
                wheel=wheel,
                controller_socket=invocation_socket,
                destination=root / "invocation-dar-bin",
                allowed_commands=("invoke",),
            )
            material_receipt = host.issue_authoring_materials(
                materials=_load_materials(materials), now=datetime.now(UTC)
            )
            marketplace = create_marketplace(
                plugin_root=plugin_root,
                destination=root / "marketplace",
                plugin_surface=plugin_surface,
            )
            management_environment = _management_environment(
                _scenario_codex_home(codex_home, scenario_codex_home), author_workspace
            )
            installed = False
            try:
                _install_plugin(
                    codex_executable, marketplace, management_environment, timeout
                )
                installed = True
                author_started = time.monotonic()
                author_result = _run_codex(
                    codex_executable,
                    _author_request(
                        author_prompt,
                        material_receipt.material_set_id,
                        package_name,
                        contract.expected_status,
                    ),
                    author_workspace,
                    build_clean_codex_environment(
                        codex_home=scenario_codex_home,
                        working_directory=author_workspace,
                        wheel=wheel,
                        state_root=state_root,
                        template_root=root
                        / "marketplace"
                        / "plugins"
                        / "agent-engineering",
                        inherited={
                            **os.environ,
                            "PATH": f"{author_dar_bin}{os.pathsep}{os.environ.get('PATH', '')}",
                        },
                    ),
                    timeout,
                )
                author_duration_ms = _actor_duration_ms(author_started)
                if contract.expected_status == "expected_capability_unavailable":
                    result = _unavailable_evidence(
                        contract,
                        author_result,
                        wheel,
                        material_receipt.material_set_id,
                        (author_duration_ms,),
                    )
                else:
                    result = _pass_evidence(
                        contract,
                        host,
                        author_result,
                        package_name,
                        workflow_id,
                        run_prompt,
                        scenario_codex_home,
                        invocation_workspace,
                        state_root,
                        invocation_dar_bin,
                        root / "marketplace" / "plugins" / "agent-engineering",
                        wheel,
                        reviewer_id,
                        reviewer_decision,
                        codex_executable,
                        timeout,
                        material_receipt.material_set_id,
                        _digest_file(marketplace),
                        fixtures.fixture_ids,
                        mcp_client,
                        controller_input_root,
                        workspace_artifact_ids,
                        author_duration_ms,
                    )
            finally:
                if installed:
                    _remove_plugin(codex_executable, management_environment, timeout)
    if evidence is not None:
        write_author_then_run_evidence(evidence, result)
    return result


def _pass_evidence(
    contract: M44Scenario,
    host: LocalWorkflowHost,
    author_result: subprocess.CompletedProcess[str],
    package_name: str,
    workflow_id: str,
    run_prompt: str,
    codex_home: Path,
    invocation_workspace: Path,
    state_root: Path,
    dar_bin: Path,
    template_root: Path,
    wheel: Path,
    reviewer_id: str | None,
    reviewer_decision: str,
    codex: str,
    timeout: int,
    material_set_id: str,
    marketplace_manifest_digest: str,
    available_host_fixtures: tuple[str, ...],
    mcp_client: _ControllerMCPClient | None,
    controller_input_root: Path,
    workspace_artifact_ids: list[str],
    author_duration_ms: int,
) -> AuthorThenRunEvidence:
    created, finalized = (
        _receipt(author_result.stdout, "created"),
        _receipt(author_result.stdout, "finalized"),
    )
    if author_result.returncode or created is None or finalized is None:
        return _failure(
            contract,
            "authoring_validation",
            wheel,
            material_set_id,
            (author_duration_ms,),
        )
    output_id, package_digest = (
        created.get("authoring_output_id"),
        finalized.get("package_digest"),
    )
    if not isinstance(output_id, str) or not isinstance(package_digest, str):
        return _failure(
            contract,
            "authoring_validation",
            wheel,
            material_set_id,
            (author_duration_ms,),
        )
    try:
        source_handle = host.select_authored_package(
            package_name, now=datetime.now(UTC)
        )
        snapshot = (
            host.review_mcp_surface(
                approved_read_only_tool_names=("list_unread",),
                approved_tool_side_effects={"send_email": "write"},
            )
            if mcp_client is not None
            else None
        )
        binding = (
            host.bind_mcp_package(
                package_source_handle=source_handle,
                snapshot_id=snapshot.snapshot_id,
                now=datetime.now(UTC),
            )
            if snapshot is not None
            else None
        )
        registration = host.register(
            workflow_id=workflow_id,
            package_source_handle=source_handle,
            now=datetime.now(UTC),
            mcp_binding_id=binding.binding_id if binding is not None else None,
        )
        if "trusted-workspace-ingress" in available_host_fixtures:
            fixture_input = controller_input_root / "fixture-input.txt"
            fixture_input.write_text("controller fixture input\n", encoding="utf-8")
            workspace_artifact_ids.append(
                host.ingress_default_file(
                    workflow_id=registration.workflow_id,
                    path=fixture_input,
                    now=datetime.now(UTC),
                ).artifact_id
            )
        if registration.revision_digest != package_digest:
            raise ValueError
    except (LocalWorkflowHostError, ValueError):
        return _failure(
            contract,
            "registration",
            wheel,
            material_set_id,
            (author_duration_ms,),
            output_id,
        )
    invocation_started = time.monotonic()
    run_result = _run_codex(
        codex,
        _run_request(package_name, run_prompt),
        invocation_workspace,
        build_clean_codex_environment(
            codex_home=codex_home,
            working_directory=invocation_workspace,
            wheel=wheel,
            state_root=state_root,
            template_root=template_root,
            inherited={
                **os.environ,
                "PATH": f"{dar_bin}{os.pathsep}{os.environ.get('PATH', '')}",
            },
        ),
        timeout,
    )
    invocation_duration_ms = _actor_duration_ms(invocation_started)
    invoked = _receipt(run_result.stdout, "completed")
    if (
        run_result.returncode
        or invoked is None
        or invoked.get("workflow_id") != package_name
    ):
        return _failure(
            contract,
            "invocation",
            wheel,
            material_set_id,
            (author_duration_ms, invocation_duration_ms),
            output_id,
        )
    result = AuthorThenRunEvidence(
        scenario_id=contract.scenario_id,
        scenario_contract_version="m4.4-v1",
        checker_version="m4.4-cli-first-v1",
        expected_status="pass",
        observed_status="pass"
        if reviewer_decision == "approved"
        else "pending_human_review",
        terminal_phase="invocation",
        invocation_mode=contract.invocation_mode,
        plugin_identity=_plugin_identity(),
        skill_identity="agent-development@agent-engineering",
        wheel_digest=_digest_file(wheel),
        harness_policy_digest=_harness_policy_digest(),
        executable_identity=_codex_identity(codex),
        module_identity=_module_identity(),
        authoring_material_set_id=material_set_id,
        authoring_output_id=output_id,
        authoring_receipt_digest=_digest_json(finalized),
        final_package_digest=package_digest,
        catalog_revision_digest=registration.revision_digest,
        registration_digest=registration.registration_digest,
        prepared_input_registration_digest=registration.registration_digest,
        action_trace_digest=_digest_json(invoked),
        dispatch_count=0,
        reviewer_id=reviewer_id,
        reviewer_decision=reviewer_decision,
        controller_fixture_digest=_digest_json(
            {"gates": ["G3"], "fixtures": available_host_fixtures}
        ),
        marketplace_manifest_digest=marketplace_manifest_digest,
        mcp_snapshot_id=snapshot.snapshot_id if snapshot is not None else None,
        mcp_binding_id=binding.binding_id if binding is not None else None,
        mcp_read_tool_names=("list_unread",) if snapshot is not None else (),
        mcp_read_call_count=(
            sum(name == "list_unread" for name, _arguments in mcp_client.calls)
            if mcp_client is not None
            else 0
        ),
        forbidden_send_dispatch_count=(
            sum(name == "send_email" for name, _arguments in mcp_client.calls)
            if mcp_client is not None
            else 0
        ),
        actor_durations_ms=(author_duration_ms, invocation_duration_ms),
    )
    validate_m44_evidence(
        contract,
        result,
        available_gates=("G3",),
        available_host_fixtures=available_host_fixtures,
    )
    return result


def _unavailable_evidence(
    contract: M44Scenario,
    author_result: subprocess.CompletedProcess[str],
    wheel: Path,
    material_set_id: str,
    actor_durations_ms: tuple[int, ...],
) -> AuthorThenRunEvidence:
    if (
        author_result.returncode
        or _receipt(author_result.stdout, "created") is not None
    ):
        return _failure(
            contract,
            "capability_preflight",
            wheel,
            material_set_id,
            actor_durations_ms,
        )
    result = AuthorThenRunEvidence(
        scenario_id=contract.scenario_id,
        scenario_contract_version="m4.4-v1",
        checker_version="m4.4-cli-first-v1",
        expected_status=contract.expected_status,
        observed_status="expected_capability_unavailable",
        terminal_phase="capability_preflight",
        invocation_mode=contract.invocation_mode,
        plugin_identity=_plugin_identity(),
        skill_identity="agent-development@agent-engineering",
        wheel_digest=_digest_file(wheel),
        harness_policy_digest=_harness_policy_digest(),
        executable_identity="codex@clean",
        module_identity=_module_identity(),
        authoring_material_set_id=material_set_id,
        authoring_output_id=None,
        authoring_receipt_digest=None,
        final_package_digest=None,
        catalog_revision_digest=None,
        registration_digest=None,
        prepared_input_registration_digest=None,
        action_trace_digest=None,
        dispatch_count=0,
        reviewer_id=None,
        reviewer_decision="pending",
        controller_fixture_digest=_digest_json(
            {"gates": ["G3"], "fixture": "local-model-profile"}
        ),
        actor_durations_ms=actor_durations_ms,
    )
    validate_m44_evidence(
        contract,
        result,
        available_gates=("G3",),
        available_host_fixtures=("local-model-profile",),
    )
    return result


def _failure(
    contract: M44Scenario,
    phase: str,
    wheel: Path,
    material_set_id: str,
    actor_durations_ms: tuple[int, ...],
    output_id: str | None = None,
) -> AuthorThenRunEvidence:
    return AuthorThenRunEvidence(
        scenario_id=contract.scenario_id,
        scenario_contract_version="m4.4-v1",
        checker_version="m4.4-cli-first-v1",
        expected_status=contract.expected_status,
        observed_status="harness_failure",
        terminal_phase=phase,
        invocation_mode=contract.invocation_mode,
        plugin_identity=_plugin_identity(),
        skill_identity="agent-development@agent-engineering",
        wheel_digest=_digest_file(wheel),
        harness_policy_digest=_harness_policy_digest(),
        executable_identity="codex@unavailable",
        module_identity=_module_identity(),
        authoring_material_set_id=material_set_id,
        authoring_output_id=output_id,
        authoring_receipt_digest=None,
        final_package_digest=None,
        catalog_revision_digest=None,
        registration_digest=None,
        prepared_input_registration_digest=None,
        action_trace_digest=None,
        dispatch_count=0,
        reviewer_id=None,
        reviewer_decision="pending",
        actor_durations_ms=actor_durations_ms,
    )


def _actor_duration_ms(started: float) -> int:
    return max(0, int((time.monotonic() - started) * 1000))


def _validate_manifest_records(
    records: tuple[AuthorThenRunEvidence, ...],
    *,
    coverage: M44Coverage,
    plan: M44ExternalScenarioPlan,
) -> None:
    if not isinstance(records, tuple) or not records:
        raise HarnessError("external evidence records are invalid")
    expected_statuses = {
        entry.scenario_id: entry.expected_status for entry in coverage.entries
    }
    record_ids = [record.scenario_id for record in records]
    if len(set(record_ids)) != len(record_ids) or set(record_ids) != set(
        expected_statuses
    ):
        raise HarnessError("external evidence records are incomplete")
    if set(record_ids) != {entry.scenario_id for entry in plan.entries}:
        raise HarnessError("external evidence records do not match the scenario plan")
    if any(
        not isinstance(record, AuthorThenRunEvidence)
        or record.expected_status != expected_statuses[record.scenario_id]
        for record in records
    ):
        raise HarnessError("external evidence records are invalid")


def _scenario_sources(scenario_roots: tuple[Path, ...]) -> dict[str, Path]:
    sources: dict[str, Path] = {}
    for root in scenario_roots:
        if not isinstance(root, Path) or not root.is_absolute() or not root.is_dir():
            raise HarnessError("scenario root is invalid")
        for source in root.glob("*.json"):
            scenario_id = load_m44_scenario(source).scenario_id
            if scenario_id in sources:
                raise HarnessError("scenario sources are duplicated")
            sources[scenario_id] = source
    if not sources:
        raise HarnessError("scenario roots are empty")
    return sources


def _verify_fixture_contracts(
    plan: M44ExternalScenarioPlan, sources: dict[str, Path]
) -> None:
    for entry in plan.entries:
        try:
            run_fixture_contract(load_m44_scenario(sources[entry.scenario_id]))
        except (KeyError, ValueError) as error:
            raise HarnessError(
                "deterministic fixture contract is unavailable"
            ) from error


def _validate_deterministic_model(model_id: str, base_url: str) -> None:
    if model_id != "openai/local-model":
        raise HarnessError("M4.4 requires the deterministic fake model")
    parsed = urlparse(base_url)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"127.0.0.1", "::1", "localhost"}
        or parsed.path.rstrip("/") != "/v1"
    ):
        raise HarnessError("M4.4 fake model endpoint must be loopback /v1")


def _validate_inputs(
    contract: M44Scenario,
    codex_home: Path,
    plugin_root: Path,
    wheel: Path,
    materials: Path,
    evidence: Path | None,
    reviewer_decision: str,
    timeout: int,
) -> None:
    for path in (codex_home, plugin_root, wheel, materials):
        if not path.is_absolute() or path.is_symlink():
            raise HarnessError("harness path is invalid")
    if evidence is not None and (not evidence.is_absolute() or evidence.is_symlink()):
        raise HarnessError("harness path is invalid")
    if not codex_home.is_dir() or not (codex_home / "auth.json").is_file():
        raise HarnessError("codex_home must be a pre-authenticated test profile")
    if (
        not plugin_root.is_dir()
        or not wheel.is_file()
        or not materials.is_file()
        or reviewer_decision not in {"pending", "approved"}
        or timeout <= 0
    ):
        raise HarnessError("harness input is invalid")


def _load_materials(path: Path) -> tuple[AuthoringMaterialInput, ...]:
    try:
        values = json.loads(path.read_text(encoding="utf-8"))
        result = tuple(
            AuthoringMaterialInput(
                role=value["role"],
                content=value["content"],
                disposition=value["disposition"],
            )
            for value in values
        )
    except (
        KeyError,
        TypeError,
        ValueError,
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as error:
        raise HarnessError("materials are invalid") from error
    if not result:
        raise HarnessError("materials are invalid")
    return result


def _author_request(
    author_prompt: str,
    material_set_id: str,
    package_name: str,
    expected_status: str,
) -> str:
    suffix = (
        "This requires unavailable multi-agent/subagent capability; report capability_unavailable and do not create a package."
        if expected_status != "pass"
        else "Create, write, and finalize the package, then report the redacted finalization receipt."
    )
    return (
        f"{author_prompt}\n\nUse the installed agent-engineering agent-development "
        f"skill to author a DAR workflow. The declared material_set_id is "
        f"`{material_set_id}` and the requested package name is `{package_name}`. "
        f"{suffix}"
    )


def _run_request(package_name: str, run_prompt: str) -> str:
    return (
        f"Use the saved workflow `{package_name}` for this request: {run_prompt}\n\n"
        "Use `dar-package invoke`, then report the JSON receipt. Do not select, "
        "register, or modify the package."
    )


def _receipt(output: str, status: str) -> dict[str, object] | None:
    candidates: list[dict[str, object]] = []
    for line in output.splitlines():
        try:
            _collect(json.loads(line), candidates)
        except json.JSONDecodeError:
            continue
    return next(
        (
            item
            for item in reversed(candidates)
            if item.get("format_version") == 1 and item.get("status") == status
        ),
        None,
    )


def _collect(value: Any, destination: list[dict[str, object]]) -> None:
    if isinstance(value, dict):
        destination.append(value)
        for nested in value.values():
            _collect(nested, destination)
    elif isinstance(value, list):
        for nested in value:
            _collect(nested, destination)
    elif isinstance(value, str):
        for line in value.splitlines():
            try:
                _collect(json.loads(line), destination)
            except json.JSONDecodeError:
                continue


def _arguments(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    for name in (
        "coverage",
        "scenario_plan",
        "codex_home",
        "plugin_root",
        "wheel",
        "materials",
        "evidence_directory",
    ):
        parser.add_argument(f"--{name.replace('_', '-')}", type=Path, required=True)
    parser.add_argument("--scenario-root", type=Path, action="append", required=True)
    parser.add_argument("--reviewer-id")
    parser.add_argument(
        "--reviewer-decision", choices=("pending", "approved"), default="pending"
    )
    parser.add_argument("--codex-executable", default="codex")
    parser.add_argument(
        "--plugin-surface",
        choices=("generated-root", "direct-baseline"),
        default="generated-root",
    )
    parser.add_argument("--timeout", type=int, default=300)
    arguments = parser.parse_args(argv)
    arguments.scenario_roots = tuple(arguments.scenario_root)
    del arguments.scenario_root
    return arguments


def _management_environment(codex_home: Path, workspace: Path) -> dict[str, str]:
    path = os.environ.get("PATH")
    if not path:
        raise HarnessError("PATH is unavailable")
    return {
        "CODEX_HOME": str(codex_home),
        "HOME": str(workspace),
        "LANG": "C.UTF-8",
        "PATH": path,
    }


def _scenario_codex_home(source: Path, destination: Path) -> Path:
    """Seed one scenario-local Codex profile with only test authentication."""

    destination.mkdir(mode=0o700)
    shutil.copy2(source / "auth.json", destination / "auth.json")
    os.chmod(destination / "auth.json", 0o600)
    return destination


def _install_plugin(
    codex: str, marketplace: Path, environment: dict[str, str], timeout: int
) -> None:
    _command(
        [codex, "plugin", "marketplace", "add", str(marketplace.parent.parent.parent)],
        environment,
        timeout,
    )
    _command(
        [codex, "plugin", "add", "agent-engineering@m44-clean-codex"],
        environment,
        timeout,
    )


def _remove_plugin(codex: str, environment: dict[str, str], timeout: int) -> None:
    for command in (
        [codex, "plugin", "remove", "agent-engineering@m44-clean-codex"],
        [codex, "plugin", "marketplace", "remove", "m44-clean-codex"],
    ):
        try:
            _command(command, environment, timeout, check=False)
        except HarnessError:
            pass


def _run_codex(
    codex: str, prompt: str, workspace: Path, environment: dict[str, str], timeout: int
) -> subprocess.CompletedProcess[str]:
    command = [
        codex,
        "exec",
        "--ephemeral",
        "--ignore-rules",
        "--skip-git-repo-check",
        "--approve-for-me",
        "--json",
        "--cd",
        str(workspace),
        prompt,
    ]
    try:
        return _command(command, environment, timeout, check=False)
    except HarnessError:
        return subprocess.CompletedProcess(command, 124, "", "")


def _command(
    command: Sequence[str],
    environment: dict[str, str],
    timeout: int,
    *,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            command,
            env=environment,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise HarnessError("Codex command could not be run") from error
    if check and result.returncode:
        raise HarnessError("Codex plugin setup failed")
    return result


def _digest_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _digest_json(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _harness_policy_digest() -> str:
    return _digest_json(
        {
            "format_version": 1,
            "mode": "clean_process_cli_first",
            "network_isolation": False,
            "filesystem_isolation": False,
        }
    )


def _plugin_identity() -> str:
    value = json.loads(
        (
            Path(__file__).resolve().parents[1]
            / "plugins"
            / "agent-engineering"
            / ".codex-plugin"
            / "plugin.json"
        ).read_text(encoding="utf-8")
    )
    return f"{value['name']}@{value['version']}"


def _codex_identity(codex: str) -> str:
    try:
        result = subprocess.run(
            [codex, "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "codex@unknown"
    return result.stdout.strip() or "codex@unknown"


def _module_identity() -> str:
    from importlib.metadata import version

    return f"dynamic-agent-runner@{version('dynamic-agent-runner')}"


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
