#!/usr/bin/env python3
"""Run one no-tool M4.4 author-then-run scenario with a clean Codex profile.

This is external acceptance evidence. It deliberately does not run in pytest,
does not copy authentication, and does not claim operating-system containment.
The supplied Codex home must be a separately authenticated test profile.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
from typing import Sequence

from dynamic_agent_runner.workflow_host.authoring_materials import (
    AuthoringMaterialInput,
)
from dynamic_agent_runner.workflow_host.authoring_evidence import (
    AuthorThenRunEvidence,
    write_author_then_run_evidence,
)
from dynamic_agent_runner.workflow_host.host import (
    LocalWorkflowHost,
    attach_mcp_client,
    configure_mcp_api_token,
    configure_local_host,
    create_mcp_connection,
)
from dynamic_agent_runner.workflow_host.mcp_client import MCPClientConfiguration
from dynamic_agent_runner.workflow_host.mcp_surfaces import MCPDiscoveredTool
from dynamic_agent_runner.workflow_host.m4_4_clean_codex import (
    M44CleanCodexError,
    build_clean_codex_environment,
    build_clean_codex_run_environment,
    create_marketplace,
)
from dynamic_agent_runner.workflow_host.m4_4_scenarios import (
    M44ScenarioError,
    load_m44_scenario,
    validate_m44_evidence,
)
from dynamic_agent_runner.workflow_host.server import (
    serve_authoring_broker,
    serve_workflow_broker,
)


class HarnessError(ValueError):
    """Raised when an external M4.4 run cannot produce valid evidence."""


class _HarnessSecretStore:
    values: dict[str, str] = {}

    def __init__(self, **_: object) -> None:
        return None

    def store(self, secret: str) -> str:
        reference = f"secret-{len(self.values) + 1}"
        self.values[reference] = secret
        return reference

    def load(self, reference: str) -> str:
        return self.values[reference]

    def delete(self, reference: str) -> None:
        self.values.pop(reference, None)


class _HarnessReadOnlyMCPClient:
    """Hermetic controller-owned G2 surface; never visible to a Codex child."""

    def __init__(self, *, configuration: MCPClientConfiguration, **_: object) -> None:
        self.connection_id = configuration.connection_id
        self.authentication_id = configuration.authentication_id
        self.current_generation = 1
        self.calls: list[tuple[str, dict[str, object]]] = []

    def initialize(self) -> None:
        return None

    def list_tools(self) -> tuple[MCPDiscoveredTool, ...]:
        return (
            MCPDiscoveredTool(
                name="list_unread", input_schema={"type": "object", "properties": {}}
            ),
            MCPDiscoveredTool(
                name="send_email", input_schema={"type": "object", "properties": {}}
            ),
        )

    def call_tool(self, name: str, arguments: dict[str, object]) -> dict[str, object]:
        self.calls.append((name, arguments))
        return {"content": [{"type": "text", "text": "three unread messages"}]}


@dataclass
class _ControllerFixture:
    fixture_id: str
    gates: tuple[str, ...]
    host_fixtures: tuple[str, ...]
    mcp_client: _HarnessReadOnlyMCPClient | None = None
    snapshot_id: str | None = None
    binding_id: str | None = None

    def configure(
        self, *, root: Path, package_root: Path, model_id: str, base_url: str
    ) -> LocalWorkflowHost:
        if self.fixture_id == "g3-local-model":
            configure_local_host(
                root=root,
                package_root=package_root,
                model_id=model_id,
                base_url=base_url,
            )
            return LocalWorkflowHost.open(root)
        return self._configure_read_only_mcp(
            root=root,
            package_root=package_root,
            model_id=model_id,
            base_url=base_url,
        )

    def _configure_read_only_mcp(
        self, *, root: Path, package_root: Path, model_id: str, base_url: str
    ) -> LocalWorkflowHost:
        import dynamic_agent_runner.workflow_host.connections as connections_module
        import dynamic_agent_runner.workflow_host.host as host_module

        original_store = connections_module.KeyringSecretStore
        original_client = host_module.MCPConnectionClient
        _HarnessSecretStore.values.clear()
        connections_module.KeyringSecretStore = _HarnessSecretStore
        host_module.MCPConnectionClient = _HarnessReadOnlyMCPClient
        try:
            configure_local_host(
                root=root,
                package_root=package_root,
                model_id=model_id,
                base_url=base_url,
            )
            connection = create_mcp_connection(
                root=root,
                endpoint="https://mcp.example.test/v1",
                scopes={"mail.read"},
                authentication_method="api_token",
            )
            authentication = configure_mcp_api_token(
                root=root, connection_id=connection.connection_id, token="test-token"
            )
            attach_mcp_client(
                root=root,
                connection_id=connection.connection_id,
                authentication_id=authentication.authentication_id,
                peer_certificate_sha256="a" * 64,
                timeout_seconds=10,
                max_response_bytes=32_768,
            )
            host = LocalWorkflowHost.open(root)
            if not isinstance(host._mcp_client, _HarnessReadOnlyMCPClient):
                raise HarnessError("read-only MCP fixture is unavailable")
            self.mcp_client = host._mcp_client
            return host
        finally:
            connections_module.KeyringSecretStore = original_store
            host_module.MCPConnectionClient = original_client

    def register(
        self,
        *,
        host: LocalWorkflowHost,
        workflow_id: str,
        source_handle: str,
        now: datetime,
    ) -> object:
        if self.fixture_id == "g3-local-model":
            registration = host.register(
                workflow_id=workflow_id, package_source_handle=source_handle, now=now
            )
            self.validate_registration(registration)
            return registration
        snapshot = host.review_mcp_surface(
            approved_read_only_tool_names={"list_unread"}
        )
        binding = host.bind_mcp_package(
            package_source_handle=source_handle,
            snapshot_id=snapshot.snapshot_id,
            now=now,
        )
        self.snapshot_id = snapshot.snapshot_id
        self.binding_id = binding.binding_id
        registration = host.register(
            workflow_id=workflow_id,
            package_source_handle=source_handle,
            mcp_binding_id=binding.binding_id,
            now=now,
        )
        self.validate_registration(registration)
        return registration

    def validate_registration(self, registration: object) -> None:
        from dynamic_agent_runner.workflow_host.registration import WorkflowRegistration

        if not isinstance(registration, WorkflowRegistration):
            raise HarnessError("workflow registration is invalid")
        expected_binding_id = (
            None if self.fixture_id == "g3-local-model" else self.binding_id
        )
        if registration.mcp_binding_id != expected_binding_id:
            raise HarnessError(
                "workflow registration does not match controller fixture"
            )

    def digest(self) -> str:
        return _digest_json(
            {
                "fixture_id": self.fixture_id,
                "gates": self.gates,
                "host_fixtures": self.host_fixtures,
                "read_only_tools": ["list_unread"] if self.mcp_client else [],
            }
        )

    def read_call_summary(self) -> tuple[tuple[str, ...], int, int]:
        calls = () if self.mcp_client is None else tuple(self.mcp_client.calls)
        names = tuple(sorted({name for name, _ in calls}))
        return names, len(calls), sum(name == "send_email" for name, _ in calls)


def _controller_fixture(scenario: object) -> _ControllerFixture:
    from dynamic_agent_runner.workflow_host.m4_4_scenarios import M44Scenario

    if not isinstance(scenario, M44Scenario):
        raise HarnessError("scenario is invalid")
    if set(scenario.required_gates) == {"G3"}:
        return _ControllerFixture("g3-local-model", ("G3",), ("local-model-profile",))
    if set(scenario.required_gates) == {"G2"}:
        return _ControllerFixture(
            "g2-read-only-mcp",
            ("G2",),
            ("local-model-profile", "reviewed-mcp-connection"),
        )
    raise HarnessError("scenario controller fixture is unavailable")


def main(argv: Sequence[str] | None = None) -> int:
    """Run the one currently executable M4.4 no-tool vertical slice."""

    arguments = _arguments(argv)
    try:
        evidence = run_no_tool_scenario(
            scenario_path=arguments.scenario,
            codex_home=arguments.codex_home,
            plugin_root=arguments.plugin_root,
            wheel=arguments.wheel,
            package_name=arguments.package_name,
            workflow_id=arguments.workflow_id,
            author_prompt=arguments.author_prompt,
            run_prompt=arguments.run_prompt,
            materials_path=arguments.materials,
            model_id=arguments.model_id,
            base_url=arguments.base_url,
            reviewer_id=arguments.reviewer_id,
            reviewer_decision=arguments.reviewer_decision,
            evidence_path=arguments.evidence,
            codex_executable=arguments.codex_executable,
            timeout=arguments.timeout,
        )
    except (HarnessError, M44CleanCodexError, M44ScenarioError) as error:
        print(f"M4.4 clean-Codex harness failed: {error}")
        return 2
    print(json.dumps(evidence.to_mapping(), sort_keys=True, separators=(",", ":")))
    return 0


def run_no_tool_scenario(
    *,
    scenario_path: Path,
    codex_home: Path,
    plugin_root: Path,
    wheel: Path,
    package_name: str,
    workflow_id: str,
    author_prompt: str,
    run_prompt: str,
    materials_path: Path,
    model_id: str,
    base_url: str,
    reviewer_id: str | None,
    reviewer_decision: str,
    evidence_path: Path,
    codex_executable: str,
    timeout: int,
) -> AuthorThenRunEvidence:
    """Create, author, register, and run one controller-fixtured prompt-only package."""

    scenario = load_m44_scenario(scenario_path)
    fixture = _controller_fixture(scenario)
    _validate_prompt_only_scenario(
        scenario=scenario,
        reviewer_decision=reviewer_decision,
        fixture=fixture,
    )
    _validate_paths(
        codex_home=codex_home,
        plugin_root=plugin_root,
        wheel=wheel,
        materials_path=materials_path,
        evidence_path=evidence_path,
    )
    if not isinstance(timeout, int) or isinstance(timeout, bool) or timeout <= 0:
        raise HarnessError("timeout is invalid")
    materials = _load_materials(materials_path)
    with tempfile.TemporaryDirectory(
        dir="/private/tmp", prefix="m44-clean-codex-"
    ) as temporary:
        root = Path(temporary)
        workspace = root / "workspace"
        package_root = root / "packages"
        state_root = root / "state"
        workspace.mkdir(mode=0o700)
        package_root.mkdir(mode=0o700)
        host = fixture.configure(
            root=state_root,
            package_root=package_root,
            model_id=model_id,
            base_url=base_url,
        )
        now = datetime.now(UTC)
        material_receipt = host.issue_authoring_materials(materials=materials, now=now)
        output_receipt = host.create_authored_package(
            package_name=package_name, now=now
        )
        socket_directory = root / "broker"
        socket_directory.mkdir(mode=0o700)
        broker_socket = socket_directory / "authoring.sock"
        broker_stop = threading.Event()
        authoring_receipts: list[tuple[object, str]] = []
        broker = threading.Thread(
            target=serve_authoring_broker,
            kwargs={
                "socket_path": broker_socket,
                "host": host,
                "material_set_id": material_receipt.material_set_id,
                "package_name": package_name,
                "authoring_output_id": output_receipt.output_id,
                "stop_event": broker_stop,
                "finalized_sink": lambda validation, source_handle: (
                    authoring_receipts.append((validation, source_handle))
                ),
            },
            daemon=True,
        )
        broker.start()
        _wait_for_socket(broker_socket)
        marketplace_root = root / "marketplace"
        marketplace = create_marketplace(
            plugin_root=plugin_root, destination=marketplace_root
        )
        management_environment = _management_environment(
            codex_home=codex_home, working_directory=workspace
        )
        installed = False
        try:
            _install_plugin(
                codex=codex_executable,
                marketplace=marketplace,
                environment=management_environment,
                timeout=timeout,
            )
            installed = True
            author_result = _run_codex(
                codex=codex_executable,
                prompt=author_prompt,
                working_directory=workspace,
                environment=build_clean_codex_environment(
                    codex_home=codex_home,
                    working_directory=workspace,
                    wheel=wheel,
                    broker_socket=broker_socket,
                    inherited=os.environ,
                ),
                timeout=timeout,
            )
            broker_stop.set()
            broker.join(timeout=5)
            if broker.is_alive():
                raise HarnessError("authoring broker did not stop")
            if len(authoring_receipts) != 1:
                evidence = _failure_evidence(
                    scenario=scenario,
                    terminal_phase="authoring_validation",
                    wheel=wheel,
                    material_set_id=material_receipt.material_set_id,
                    output_id=output_receipt.output_id,
                )
            else:
                evidence = _finish_positive_scenario(
                    host=host,
                    workflow_id=workflow_id,
                    run_prompt=run_prompt,
                    scenario=scenario,
                    author_result=author_result,
                    codex_home=codex_home,
                    workspace=workspace,
                    wheel=wheel,
                    socket_directory=socket_directory,
                    reviewer_id=reviewer_id,
                    reviewer_decision=reviewer_decision,
                    codex_executable=codex_executable,
                    timeout=timeout,
                    material_set_id=material_receipt.material_set_id,
                    output_id=output_receipt.output_id,
                    final_validation=authoring_receipts[0][0],
                    source_handle=authoring_receipts[0][1],
                    fixture=fixture,
                )
        finally:
            _stop_broker(stop_event=broker_stop, broker=broker)
            if installed:
                _remove_plugin(
                    codex=codex_executable,
                    environment=management_environment,
                    timeout=timeout,
                )
    write_author_then_run_evidence(evidence_path, evidence)
    return evidence


def _finish_positive_scenario(
    *,
    host: LocalWorkflowHost,
    workflow_id: str,
    run_prompt: str,
    scenario: object,
    author_result: subprocess.CompletedProcess[str],
    codex_home: Path,
    workspace: Path,
    wheel: Path,
    socket_directory: Path,
    reviewer_id: str | None,
    reviewer_decision: str,
    codex_executable: str,
    timeout: int,
    material_set_id: str,
    output_id: str,
    final_validation: object,
    source_handle: str,
    fixture: _ControllerFixture,
) -> AuthorThenRunEvidence:
    if author_result.returncode != 0:
        return _failure_evidence(
            scenario=scenario,
            terminal_phase="authoring_validation",
            wheel=wheel,
            material_set_id=material_set_id,
            output_id=output_id,
        )
    now = datetime.now(UTC)
    try:
        from dynamic_agent_runner.workflow_host.authoring_output import (
            AuthoredPackageValidation,
        )

        if not isinstance(final_validation, AuthoredPackageValidation):
            raise ValueError("authoring finalization is invalid")
        registration = fixture.register(
            host=host, workflow_id=workflow_id, source_handle=source_handle, now=now
        )
        if final_validation.package_digest != registration.revision_digest:
            raise ValueError("staged revision does not match authoring receipt")
    except ValueError:
        return _failure_evidence(
            scenario=scenario,
            terminal_phase="registration",
            wheel=wheel,
            material_set_id=material_set_id,
            output_id=output_id,
        )
    broker_socket = socket_directory / "workflow.sock"
    broker_stop = threading.Event()
    prepared_inputs: list[object] = []
    broker = threading.Thread(
        target=serve_workflow_broker,
        kwargs={
            "socket_path": broker_socket,
            "host": host,
            "workflow_id": workflow_id,
            "stop_event": broker_stop,
            "prepared_input_sink": prepared_inputs.append,
        },
        daemon=True,
    )
    broker.start()
    _wait_for_socket(broker_socket)
    try:
        run_result = _run_codex(
            codex=codex_executable,
            prompt=(
                f"Use the saved workflow `{workflow_id}` to perform this request: {run_prompt}"
            ),
            working_directory=workspace,
            environment=build_clean_codex_run_environment(
                codex_home=codex_home,
                working_directory=workspace,
                wheel=wheel,
                broker_socket=broker_socket,
                inherited=os.environ,
            ),
            timeout=timeout,
        )
    finally:
        _stop_broker(stop_event=broker_stop, broker=broker)
    if run_result.returncode != 0:
        return _failure_evidence(
            scenario=scenario,
            terminal_phase="invocation",
            wheel=wheel,
            material_set_id=material_set_id,
            output_id=output_id,
        )
    traces = tuple(
        trace
        for trace in host.run_traces()
        if trace.workflow_id == workflow_id and trace.status == "completed"
    )
    if len(traces) != 1:
        return _failure_evidence(
            scenario=scenario,
            terminal_phase="invocation",
            wheel=wheel,
            material_set_id=material_set_id,
            output_id=output_id,
        )
    trace = traces[0]
    if len(prepared_inputs) != 1:
        return _failure_evidence(
            scenario=scenario,
            terminal_phase="invocation",
            wheel=wheel,
            material_set_id=material_set_id,
            output_id=output_id,
        )
    prepared_input = prepared_inputs[0]
    prepared_input_registration_digest = getattr(
        prepared_input, "registration_digest", None
    )
    if prepared_input_registration_digest != registration.registration_digest:
        return _failure_evidence(
            scenario=scenario,
            terminal_phase="invocation",
            wheel=wheel,
            material_set_id=material_set_id,
            output_id=output_id,
        )
    return _completed_evidence(
        scenario=scenario,
        fixture=fixture,
        reviewer_id=reviewer_id,
        reviewer_decision=reviewer_decision,
        wheel=wheel,
        codex_executable=codex_executable,
        material_set_id=material_set_id,
        output_id=output_id,
        final_validation=final_validation,
        registration=registration,
        prepared_input_registration_digest=prepared_input_registration_digest,
        trace=trace,
    )


def _completed_evidence(
    *,
    scenario: object,
    fixture: _ControllerFixture,
    reviewer_id: str | None,
    reviewer_decision: str,
    wheel: Path,
    codex_executable: str,
    material_set_id: str,
    output_id: str,
    final_validation: object,
    registration: object,
    prepared_input_registration_digest: object,
    trace: object,
) -> AuthorThenRunEvidence:
    from dynamic_agent_runner.workflow_host.authoring_output import (
        AuthoredPackageValidation,
    )
    from dynamic_agent_runner.workflow_host.m4_4_scenarios import M44Scenario

    if (
        not isinstance(scenario, M44Scenario)
        or not isinstance(final_validation, AuthoredPackageValidation)
        or not isinstance(prepared_input_registration_digest, str)
        or not hasattr(registration, "revision_digest")
        or not hasattr(registration, "registration_digest")
        or not hasattr(trace, "output_byte_count")
        or not hasattr(trace, "run_id")
        or not hasattr(trace, "status")
        or not hasattr(trace, "workflow_id")
    ):
        raise HarnessError("completed scenario evidence is invalid")
    read_tool_names, read_call_count, forbidden_send_dispatch_count = (
        fixture.read_call_summary()
    )
    evidence = AuthorThenRunEvidence(
        scenario_id=scenario.scenario_id,
        scenario_contract_version="m4.4-v1",
        checker_version="m4.4-checker-v1",
        expected_status=scenario.expected_status,
        observed_status=(
            "pass" if reviewer_decision == "approved" else "pending_human_review"
        ),
        terminal_phase="invocation",
        invocation_mode=scenario.invocation_mode,
        plugin_identity=_plugin_identity(),
        skill_identity="agent-development@dar-authoring",
        wheel_digest=_digest_file(wheel),
        harness_policy_digest=_harness_policy_digest(),
        executable_identity=_codex_identity(codex_executable),
        module_identity=_module_identity(),
        authoring_material_set_id=material_set_id,
        authoring_output_id=output_id,
        authoring_receipt_digest=_digest_json(
            {
                "material_set_id": material_set_id,
                "output_id": output_id,
                "package_digest": final_validation.package_digest,
            }
        ),
        final_package_digest=final_validation.package_digest,
        catalog_revision_digest=registration.revision_digest,
        registration_digest=registration.registration_digest,
        prepared_input_registration_digest=prepared_input_registration_digest,
        action_trace_digest=_digest_json(
            {
                "output_byte_count": trace.output_byte_count,
                "run_id": trace.run_id,
                "status": trace.status,
                "workflow_id": trace.workflow_id,
            }
        ),
        dispatch_count=0,
        reviewer_id=reviewer_id,
        reviewer_decision=reviewer_decision,
        controller_fixture_digest=fixture.digest(),
        mcp_snapshot_id=fixture.snapshot_id,
        mcp_binding_id=fixture.binding_id,
        mcp_read_tool_names=read_tool_names,
        mcp_read_call_count=read_call_count,
        forbidden_send_dispatch_count=forbidden_send_dispatch_count,
    )
    validate_m44_evidence(
        scenario,
        evidence,
        available_gates=fixture.gates,
        available_host_fixtures=fixture.host_fixtures,
    )
    return evidence


def _failure_evidence(
    *,
    scenario: object,
    terminal_phase: str,
    wheel: Path,
    material_set_id: str,
    output_id: str,
) -> AuthorThenRunEvidence:
    from dynamic_agent_runner.workflow_host.m4_4_scenarios import M44Scenario

    if not isinstance(scenario, M44Scenario):
        raise HarnessError("scenario is invalid")
    return AuthorThenRunEvidence(
        scenario_id=scenario.scenario_id,
        scenario_contract_version="m4.4-v1",
        checker_version="m4.4-checker-v1",
        expected_status=scenario.expected_status,
        observed_status="harness_failure",
        terminal_phase=terminal_phase,
        invocation_mode=scenario.invocation_mode,
        plugin_identity=_plugin_identity(),
        skill_identity="agent-development@dar-authoring",
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
    )


def _arguments(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", type=Path, required=True)
    parser.add_argument("--codex-home", type=Path, required=True)
    parser.add_argument("--plugin-root", type=Path, required=True)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--materials", type=Path, required=True)
    parser.add_argument("--package-name", required=True)
    parser.add_argument("--workflow-id", required=True)
    parser.add_argument("--author-prompt", required=True)
    parser.add_argument("--run-prompt", required=True)
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--reviewer-id")
    parser.add_argument(
        "--reviewer-decision", choices=("pending", "approved"), default="pending"
    )
    parser.add_argument("--codex-executable", default="codex")
    parser.add_argument("--timeout", type=int, default=300)
    return parser.parse_args(argv)


def _validate_prompt_only_scenario(
    *,
    scenario: object,
    reviewer_decision: str,
    fixture: _ControllerFixture,
) -> None:
    from dynamic_agent_runner.workflow_host.m4_4_scenarios import M44Scenario

    if not isinstance(scenario, M44Scenario):
        raise HarnessError("scenario is invalid")
    if (
        scenario.expected_status != "pass"
        or scenario.invocation_mode != "mcp_prompt_only"
        or scenario.required_artifact_roles
        or set(scenario.required_gates) != set(fixture.gates)
        or set(scenario.required_host_fixtures) != set(fixture.host_fixtures)
    ):
        raise HarnessError("scenario does not match its controller fixture")
    if reviewer_decision not in {"pending", "approved"}:
        raise HarnessError("reviewer decision is invalid")


def _validate_paths(**paths: Path) -> None:
    for label, path in paths.items():
        if not path.is_absolute() or path.is_symlink():
            raise HarnessError(f"{label} is invalid")
    if (
        not paths["codex_home"].is_dir()
        or not (paths["codex_home"] / "auth.json").is_file()
    ):
        raise HarnessError("codex_home must be a pre-authenticated test profile")
    if not paths["plugin_root"].is_dir() or not paths["wheel"].is_file():
        raise HarnessError("plugin root or wheel is unavailable")
    if not paths["materials_path"].is_file():
        raise HarnessError("materials are unavailable")


def _load_materials(path: Path) -> tuple[AuthoringMaterialInput, ...]:
    try:
        values = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise HarnessError("materials are invalid") from error
    if not isinstance(values, list) or not values:
        raise HarnessError("materials are invalid")
    try:
        materials = tuple(
            AuthoringMaterialInput(
                role=value["role"],
                content=value["content"],
                disposition=value["disposition"],
            )
            for value in values
            if isinstance(value, dict)
            and set(value) == {"role", "content", "disposition"}
        )
    except (KeyError, TypeError, ValueError) as error:
        raise HarnessError("materials are invalid") from error
    if len(materials) != len(values):
        raise HarnessError("materials are invalid")
    return materials


def _management_environment(
    *, codex_home: Path, working_directory: Path
) -> dict[str, str]:
    path = os.environ.get("PATH")
    if not path:
        raise HarnessError("PATH is unavailable")
    return {
        "CODEX_HOME": str(codex_home),
        "HOME": str(working_directory),
        "LANG": "C.UTF-8",
        "PATH": path,
    }


def _install_plugin(
    *, codex: str, marketplace: Path, environment: dict[str, str], timeout: int
) -> None:
    _command(
        [codex, "plugin", "marketplace", "add", str(marketplace.parent.parent.parent)],
        environment=environment,
        timeout=timeout,
    )
    _command(
        [codex, "plugin", "add", "dar-authoring@m44-clean-codex"],
        environment=environment,
        timeout=timeout,
    )


def _remove_plugin(*, codex: str, environment: dict[str, str], timeout: int) -> None:
    for command in (
        [codex, "plugin", "remove", "dar-authoring@m44-clean-codex"],
        [codex, "plugin", "marketplace", "remove", "m44-clean-codex"],
    ):
        try:
            subprocess.run(
                command,
                env=environment,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass


def _run_codex(
    *,
    codex: str,
    prompt: str,
    working_directory: Path,
    environment: dict[str, str],
    timeout: int,
) -> subprocess.CompletedProcess[str]:
    return _command(
        [
            codex,
            "exec",
            "--ephemeral",
            "--ignore-rules",
            "--skip-git-repo-check",
            "--json",
            "--cd",
            str(working_directory),
            prompt,
        ],
        environment=environment,
        timeout=timeout,
        check=False,
    )


def _command(
    command: Sequence[str],
    *,
    environment: dict[str, str],
    timeout: int,
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


def _wait_for_socket(path: Path) -> None:
    for _ in range(100):
        if path.exists():
            return
        threading.Event().wait(0.01)
    raise HarnessError("authoring broker did not start")


def _stop_broker(*, stop_event: threading.Event, broker: threading.Thread) -> None:
    stop_event.set()
    broker.join(timeout=5)


def _digest_file(path: Path) -> str:
    return _digest_bytes(path.read_bytes())


def _digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _digest_json(value: object) -> str:
    return _digest_bytes(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    )


def _harness_policy_digest() -> str:
    return _digest_json(
        {
            "format_version": 1,
            "mode": "clean_process",
            "network_isolation": False,
            "filesystem_isolation": False,
        }
    )


def _plugin_identity() -> str:
    root = (
        Path(__file__).resolve().parents[1]
        / "dar-authoring"
        / ".codex-plugin"
        / "plugin.json"
    )
    value = json.loads(root.read_text(encoding="utf-8"))
    return f"{value['name']}@{value['version']}"


def _codex_identity(codex: str) -> str:
    result = _command(
        [codex, "--version"],
        environment=_management_environment(
            codex_home=Path("/tmp"), working_directory=Path("/tmp")
        ),
        timeout=10,
        check=False,
    )
    return result.stdout.strip() or "codex@unknown"


def _module_identity() -> str:
    from importlib.metadata import version

    return f"dynamic-agent-runner@{version('dynamic-agent-runner')}"


if __name__ == "__main__":  # pragma: no cover - external acceptance entry point.
    raise SystemExit(main())
