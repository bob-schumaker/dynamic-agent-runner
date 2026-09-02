"""Tests for the CLI-first M4.4 clean-Codex harness boundary."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import socket
import sys
from contextlib import contextmanager
from uuid import uuid4

import pytest

from m4_4_clean_codex import (
    M44CleanCodexError,
    build_clean_codex_environment,
    create_marketplace,
    stage_dar_package,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
HARNESS = REPO_ROOT / "scripts" / "run_m4_4_clean_codex.py"


def _harness_module() -> object:
    spec = importlib.util.spec_from_file_location("m44_harness", HARNESS)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _manifest_records(module: object) -> tuple[object, ...]:
    coverage = json.loads(
        (REPO_ROOT / "tests" / "fixtures" / "m4-4-successor-coverage.json").read_text(
            encoding="utf-8"
        )
    )
    expected_statuses = {
        entry["scenario_id"]: entry["expected_status"] for entry in coverage["entries"]
    }
    digest = "a" * 64
    records = []
    for scenario_id, expected_status in expected_statuses.items():
        positive = expected_status == "pass"
        records.append(
            module.AuthorThenRunEvidence(
                scenario_id=scenario_id,
                scenario_contract_version="m4.4-v1",
                checker_version="m4.4-cli-first-v1",
                expected_status=expected_status,
                observed_status="pending_human_review" if positive else expected_status,
                terminal_phase="invocation" if positive else "capability_preflight",
                invocation_mode="mcp_prompt_only",
                plugin_identity="agent-engineering",
                skill_identity="agent-development@agent-engineering",
                wheel_digest=digest,
                harness_policy_digest=digest,
                executable_identity="codex@clean",
                module_identity="m4.4",
                authoring_material_set_id="materials" if positive else None,
                authoring_output_id="output" if positive else None,
                authoring_receipt_digest=digest if positive else None,
                final_package_digest=digest if positive else None,
                catalog_revision_digest=digest if positive else None,
                registration_digest=digest if positive else None,
                prepared_input_registration_digest=digest if positive else None,
                action_trace_digest=digest if positive else None,
                dispatch_count=0,
                reviewer_id=None,
                reviewer_decision="pending",
                marketplace_manifest_digest=digest if positive else None,
            )
        )
    return tuple(records)


def test_clean_codex_environment_exposes_successor_path_not_legacy_state(
    tmp_path: Path,
) -> None:
    environment = build_clean_codex_environment(
        codex_home=tmp_path / "codex-home",
        working_directory=tmp_path / "workspace",
        wheel=tmp_path / "dynamic_agent_runner.whl",
        state_root=tmp_path / "state",
        template_root=tmp_path / "templates",
        inherited={"PATH": "/usr/bin:/bin", "OPENAI_API_KEY": "secret"},
    )

    assert environment == {
        "CODEX_HOME": str(tmp_path / "codex-home"),
        "UV_CACHE_DIR": str(tmp_path / "workspace" / ".uv-cache"),
        "HOME": str(tmp_path / "workspace"),
        "LANG": "C.UTF-8",
        "PATH": "/usr/bin:/bin",
    }
    assert not {
        key
        for key in environment
        if "DAR_AUTHORING" in key or "BROKER" in key or "MCP_MODE" in key
    }


def test_scenario_codex_home_copies_only_test_authentication(tmp_path: Path) -> None:
    module = _harness_module()
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    source.mkdir()
    (source / "auth.json").write_text("test-auth", encoding="utf-8")
    (source / "config.toml").write_text("ignored", encoding="utf-8")

    module._scenario_codex_home(source, destination)

    assert (destination / "auth.json").read_text(encoding="utf-8") == "test-auth"
    assert not (destination / "config.toml").exists()


def test_actor_timeout_becomes_a_terminal_failure_record(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    module = _harness_module()

    def timed_out(*_args: object, **_kwargs: object) -> object:
        raise module.HarnessError("Codex command could not be run")

    monkeypatch.setattr(module, "_command", timed_out)

    result = module._run_codex(
        "codex",
        "author the workflow",
        tmp_path,
        {"PATH": "/usr/bin:/bin"},
        300,
    )

    assert result.returncode == 124
    assert result.stdout == ""
    assert result.stderr == ""


def test_stage_dar_package_rejects_non_absolute_state_root(
    tmp_path: Path,
) -> None:
    with pytest.raises(M44CleanCodexError):
        stage_dar_package(
            wheel=tmp_path / "dynamic_agent_runner.whl",
            controller_socket=Path("controller"),
            destination=tmp_path / "dar-bin",
            allowed_commands=("invoke",),
        )


def test_actor_launcher_hides_state_and_limits_its_dar_commands(tmp_path: Path) -> None:
    wheel = (tmp_path / "dynamic_agent_runner.whl").resolve()
    wheel.write_bytes(b"wheel")
    state_root = (tmp_path / "controller-state").resolve()
    controller_socket = Path("/private/tmp") / f"m44-controller-{uuid4().hex}.sock"
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as controller:
        controller.bind(str(controller_socket))
        launcher_directory = stage_dar_package(
            wheel=wheel,
            controller_socket=controller_socket,
            destination=(tmp_path / "actor-bin").resolve(),
            allowed_commands=("invoke",),
        )

        launcher = (launcher_directory / "dar-package").read_text(encoding="utf-8")
    assert str(state_root) not in launcher
    assert "DAR_AUTHORING_STATE_ROOT" not in launcher
    assert "--controller-proxy" in launcher
    assert "invoke" in launcher
    assert "create-authored-package" not in launcher


def test_manifest_evidence_requires_complete_fresh_redacted_record_set(
    tmp_path: Path,
) -> None:
    module = _harness_module()
    evidence_directory = (tmp_path / "evidence").resolve()

    aggregate = module.write_manifest_evidence(
        evidence_directory=evidence_directory,
        coverage_source=(
            REPO_ROOT / "tests" / "fixtures" / "m4-4-successor-coverage.json"
        ),
        scenario_plan_source=(
            REPO_ROOT / "tests" / "fixtures" / "m4-4-external-scenario-plan.json"
        ),
        scenario_roots=(
            REPO_ROOT / "tests" / "fixtures" / "dar-authoring" / "m4-4",
            REPO_ROOT / "tests" / "fixtures" / "m4-4-successor",
        ),
        records=_manifest_records(module),
    )

    value = json.loads(aggregate.read_text(encoding="utf-8"))
    assert value["format_version"] == "m4.4-external-evidence-v1"
    assert len(value["records"]) == 23
    assert all(
        set(record) == {"scenario_id", "observed_status", "record_digest"}
        for record in value["records"]
    )
    assert str(tmp_path) not in aggregate.read_text(encoding="utf-8")
    with pytest.raises(module.HarnessError):
        module.write_manifest_evidence(
            evidence_directory=evidence_directory,
            coverage_source=(
                REPO_ROOT / "tests" / "fixtures" / "m4-4-successor-coverage.json"
            ),
            scenario_plan_source=(
                REPO_ROOT / "tests" / "fixtures" / "m4-4-external-scenario-plan.json"
            ),
            scenario_roots=(
                REPO_ROOT / "tests" / "fixtures" / "dar-authoring" / "m4-4",
                REPO_ROOT / "tests" / "fixtures" / "m4-4-successor",
            ),
            records=_manifest_records(module)[:-1],
        )


def test_manifest_runner_replays_every_plan_entry_before_aggregating(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _harness_module()
    records = {record.scenario_id: record for record in _manifest_records(module)}
    calls: list[dict[str, object]] = []
    fixture_contracts: list[str] = []

    def run_case(**kwargs: object) -> object:
        calls.append(kwargs)
        return records[module.load_m44_scenario(kwargs["scenario"]).scenario_id]

    monkeypatch.setattr(module, "run_scenario", run_case)
    monkeypatch.setattr(
        module,
        "run_fixture_contract",
        lambda scenario: (
            fixture_contracts.append(scenario.scenario_id) or {"model_calls": 0}
        ),
    )

    aggregate = module.run_manifest(
        coverage=REPO_ROOT / "tests" / "fixtures" / "m4-4-successor-coverage.json",
        scenario_plan=REPO_ROOT
        / "tests"
        / "fixtures"
        / "m4-4-external-scenario-plan.json",
        scenario_roots=(
            REPO_ROOT / "tests" / "fixtures" / "dar-authoring" / "m4-4",
            REPO_ROOT / "tests" / "fixtures" / "m4-4-successor",
        ),
        evidence_directory=(tmp_path / "evidence").resolve(),
        codex_home=(tmp_path / "codex-home").resolve(),
        plugin_root=(tmp_path / "plugin").resolve(),
        wheel=(tmp_path / "dar.whl").resolve(),
        materials=(tmp_path / "materials.json").resolve(),
        model_id="openai/local-model",
        base_url="http://127.0.0.1:8080/v1",
        reviewer_id=None,
        reviewer_decision="pending",
        codex_executable="codex",
        timeout=1,
    )

    assert len(calls) == 23
    assert set(fixture_contracts) == set(records)
    assert {call["evidence"] for call in calls} == {None}
    assert len(json.loads(aggregate.read_text(encoding="utf-8"))["records"]) == 23


def test_external_command_rejects_a_scenario_only_override(tmp_path: Path) -> None:
    module = _harness_module()
    root = tmp_path.resolve()

    with pytest.raises(SystemExit):
        module._arguments(
            (
                "--coverage",
                str(root / "coverage.json"),
                "--scenario-plan",
                str(root / "plan.json"),
                "--scenario-root",
                str(root / "scenarios"),
                "--evidence-directory",
                str(root / "evidence"),
                "--codex-home",
                str(root / "codex"),
                "--plugin-root",
                str(root / "plugin"),
                "--wheel",
                str(root / "dar.whl"),
                "--materials",
                str(root / "materials.json"),
                "--scenario",
                str(root / "selected.json"),
            )
        )


def test_external_command_owns_its_deterministic_fake_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _harness_module()
    aggregate = tmp_path / "aggregate.json"
    aggregate.write_text("{}", encoding="utf-8")
    observed: dict[str, object] = {}

    @contextmanager
    def fake_server():
        yield "http://127.0.0.1:18080/v1"

    def run_manifest(**kwargs: object) -> Path:
        observed.update(kwargs)
        return aggregate

    monkeypatch.setattr(module, "_fake_model_server", fake_server)
    monkeypatch.setattr(module, "run_manifest", run_manifest)

    assert (
        module.main(
            (
                "--coverage",
                str(tmp_path / "coverage.json"),
                "--scenario-plan",
                str(tmp_path / "plan.json"),
                "--scenario-root",
                str(tmp_path / "scenarios"),
                "--evidence-directory",
                str(tmp_path / "evidence"),
                "--codex-home",
                str(tmp_path / "codex"),
                "--plugin-root",
                str(tmp_path / "plugin"),
                "--wheel",
                str(tmp_path / "dar.whl"),
                "--materials",
                str(tmp_path / "materials.json"),
            )
        )
        == 0
    )
    assert observed["model_id"] == "openai/local-model"
    assert observed["base_url"] == "http://127.0.0.1:18080/v1"


def test_controller_waits_for_fake_model_before_actor_launch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _harness_module()

    class Process:
        def poll(self) -> None:
            return None

    class Response:
        status = 200

        def __enter__(self) -> "Response":
            return self

        def __exit__(self, *_arguments: object) -> None:
            return None

    observed: list[str] = []

    def open_url(url: str, *, timeout: float) -> Response:
        observed.append(url)
        assert timeout == 0.1
        return Response()

    monkeypatch.setattr(module, "urlopen", open_url)

    module._wait_for_fake_model("http://127.0.0.1:18080/v1", Process())

    assert observed == ["http://127.0.0.1:18080/v1/models"]


def test_controller_provisions_only_declared_positive_collaborators() -> None:
    module = _harness_module()
    input_guardrail = module.load_m44_scenario(
        REPO_ROOT / "tests" / "fixtures" / "m4-4-successor" / "guardrail-input.json"
    )
    missing_guardrail = module.load_m44_scenario(
        REPO_ROOT
        / "tests"
        / "fixtures"
        / "m4-4-successor"
        / "guardrail-input-missing.json"
    )
    mcp_workflow = module.load_m44_scenario(
        REPO_ROOT
        / "tests"
        / "fixtures"
        / "dar-authoring"
        / "m4-4"
        / "generic-email-send.json"
    )

    provisioned = module._controller_fixtures(input_guardrail)
    unavailable = module._controller_fixtures(missing_guardrail)
    mcp = module._controller_fixtures(mcp_workflow)

    assert "input-guardrail-registry" in provisioned.fixture_ids
    assert provisioned.guardrail_registry is not None
    assert provisioned.guardrail_registry.has_guardrail("require_input")
    assert unavailable.approval_broker_factory is None
    assert unavailable.guardrail_registry is None
    assert "input-guardrail-registry" not in unavailable.fixture_ids
    assert "reviewed-mcp-connection" in mcp.fixture_ids


def test_controller_fixture_inventory_covers_every_positive_scenario() -> None:
    module = _harness_module()
    roots = (
        REPO_ROOT / "tests" / "fixtures" / "dar-authoring" / "m4-4",
        REPO_ROOT / "tests" / "fixtures" / "m4-4-successor",
    )
    contracts = {
        contract.scenario_id: contract
        for root in roots
        for source in root.glob("*.json")
        if (contract := module.load_m44_scenario(source)).expected_status == "pass"
    }

    for contract in contracts.values():
        fixtures = module._controller_fixtures(contract)
        assert set(contract.required_host_fixtures).issubset(fixtures.fixture_ids)


def test_controller_mcp_fixture_reviews_without_a_network_transport(
    tmp_path: Path,
) -> None:
    module = _harness_module()
    state_root = (tmp_path / "state").resolve()
    package_root = (tmp_path / "packages").resolve()
    package_root.mkdir()
    configuration = module.configure_local_host(
        root=state_root,
        package_root=package_root,
        model_id="openai/local-model",
        base_url="http://127.0.0.1:8080/v1",
    )
    client, connections = module._configure_controller_mcp(
        state_root=state_root, profile_id=configuration.profile_id
    )
    host = module.LocalWorkflowHost.open(
        state_root,
        mcp_client_factory=lambda _configuration: client,
        mcp_connections=connections,
    )

    reviewed = host.review_mcp_surface(
        approved_read_only_tool_names=("list_unread",),
        approved_tool_side_effects={"send_email": "write"},
    )

    assert reviewed.read_only_tool_names == frozenset({"list_unread"})
    assert client.calls == []


def test_controller_oauth_fixture_reviews_without_a_network_transport(
    tmp_path: Path,
) -> None:
    module = _harness_module()
    state_root = (tmp_path / "state").resolve()
    package_root = (tmp_path / "packages").resolve()
    package_root.mkdir()
    configuration = module.configure_local_host(
        root=state_root,
        package_root=package_root,
        model_id="openai/local-model",
        base_url="http://127.0.0.1:8080/v1",
    )
    client, connections = module._configure_controller_mcp(
        state_root=state_root, profile_id=configuration.profile_id, use_oauth=True
    )
    host = module.LocalWorkflowHost.open(
        state_root,
        mcp_client_factory=lambda _configuration: client,
        mcp_connections=connections,
    )

    reviewed = host.review_mcp_surface(approved_read_only_tool_names=("list_unread",))

    assert reviewed.read_only_tool_names == frozenset({"list_unread"})
    assert client.calls == []


@pytest.mark.parametrize(
    ("model_id", "base_url"),
    (
        ("gpt-5", "http://127.0.0.1:8080/v1"),
        ("openai/local-model", "https://example.invalid/v1"),
        ("openai/local-model", "http://127.0.0.1:8080/not-v1"),
    ),
)
def test_manifest_runner_rejects_non_deterministic_model_configuration(
    model_id: str, base_url: str
) -> None:
    module = _harness_module()

    with pytest.raises(module.HarnessError):
        module._validate_deterministic_model(model_id, base_url)


def test_marketplace_contains_only_the_copied_plugin(tmp_path: Path) -> None:
    plugin = tmp_path / "plugin"
    (plugin / ".codex-plugin").mkdir(parents=True)
    (plugin / "skills" / "agent-development").mkdir(parents=True)
    (plugin / "references").mkdir(parents=True)
    (plugin / ".codex-plugin" / "plugin.json").write_text("{}", encoding="utf-8")
    (plugin / "skills" / "agent-development" / "SKILL.md").write_text(
        "# Agent development\n", encoding="utf-8"
    )
    (plugin / "references" / "dar-runtime-profile.md").write_text(
        "# DAR runtime profile\n", encoding="utf-8"
    )

    marketplace = create_marketplace(
        plugin_root=plugin, destination=tmp_path / "marketplace"
    )

    assert marketplace.is_file()
    copied_plugin = tmp_path / "marketplace" / "plugins" / "agent-engineering"
    assert copied_plugin.is_dir()
    assert (copied_plugin / "skills" / "agent-development" / "SKILL.md").is_file()
    assert (copied_plugin / "references" / "dar-runtime-profile.md").is_file()
    manifest_value = json.loads(marketplace.read_text(encoding="utf-8"))
    assert manifest_value["plugins"][0]["name"] == "agent-engineering"
    assert "dar-authoring" not in marketplace.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "manifest,extra_path",
    (
        ('{"mcpServers":{"test":{}}}', None),
        ('{"metadata":{"mcpServers":{"test":{}}}}', None),
        ("{}", "mcp.json"),
        ("{}", "scripts/session-broker"),
        ("{}", "skills/dar-authoring/SKILL.md"),
    ),
)
def test_marketplace_rejects_legacy_or_plugin_control_plane_surface(
    tmp_path: Path, manifest: str, extra_path: str | None
) -> None:
    plugin = tmp_path / "plugin"
    (plugin / ".codex-plugin").mkdir(parents=True)
    (plugin / "skills" / "agent-development").mkdir(parents=True)
    (plugin / "references").mkdir(parents=True)
    (plugin / ".codex-plugin" / "plugin.json").write_text(manifest, encoding="utf-8")
    (plugin / "skills" / "agent-development" / "SKILL.md").write_text(
        "# Agent development\n", encoding="utf-8"
    )
    (plugin / "references" / "dar-runtime-profile.md").write_text(
        "# DAR runtime profile\n", encoding="utf-8"
    )
    if extra_path is not None:
        extra = plugin / extra_path
        extra.parent.mkdir(parents=True, exist_ok=True)
        extra.write_text("legacy", encoding="utf-8")

    with pytest.raises(M44CleanCodexError):
        create_marketplace(plugin_root=plugin, destination=tmp_path / "marketplace")


def test_receipt_reader_finds_nested_redacted_cli_receipts() -> None:
    module = _harness_module()
    transcript = "\n".join(
        (
            json.dumps(
                {
                    "item": {
                        "aggregated_output": 'command output\n{"format_version":1,"status":"created","authoring_output_id":"output-id"}'
                    }
                }
            ),
            json.dumps(
                {
                    "item": {
                        "aggregated_output": '{"format_version":1,"status":"finalized","package_digest":"'
                        + "a" * 64
                        + '"}'
                    }
                }
            ),
        )
    )

    assert module._receipt(transcript, "created") == {
        "format_version": 1,
        "status": "created",
        "authoring_output_id": "output-id",
    }
    assert module._receipt(transcript, "finalized")["package_digest"] == "a" * 64


def test_successor_author_prompt_uses_no_legacy_identity_or_cli_recipe() -> None:
    module = _harness_module()

    prompt = module._author_request(
        "Design a summary workflow.",
        "material-id",
        "summary",
        "pass",
    )

    assert "agent-engineering" in prompt
    assert "DAR" in prompt
    assert "material-id" in prompt
    assert "dar-authoring" not in prompt
    assert "dar-package" not in prompt
    assert "/tmp" not in prompt
    assert "broker" not in prompt
    assert "MCP" not in prompt


def test_successor_run_prompt_names_only_the_saved_package_and_request() -> None:
    module = _harness_module()

    prompt = module._run_request("summary", "Summarize this text.")

    assert "dar-package invoke" in prompt
    assert "summary" in prompt
    assert "Summarize this text." in prompt
    assert "uv run" not in prompt
    assert "/" not in prompt
