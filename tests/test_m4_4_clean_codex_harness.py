"""Tests for the CLI-first M4.4 clean-Codex harness boundary."""

from __future__ import annotations

import importlib.util
import json
from dataclasses import replace
import os
from pathlib import Path
import socket
import subprocess
import sys
from contextlib import contextmanager
from uuid import uuid4

import pytest

from conftest import _ORIGINAL_SOCKET_CONNECT
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
                dar_runtime_version="0.1.17",
                dar_runtime_wheel_filename=(
                    "dynamic_agent_runner-0.1.17-py3-none-any.whl"
                ),
                dar_runtime_wheel_metadata_digest=digest,
                dar_runtime_release_descriptor_digest=digest,
                dar_runtime_payload_selector_list_digest=digest,
                actor_durations_ms=(100, 200) if positive else (100,),
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


def test_codex_actor_receives_prompt_on_closed_standard_input(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    module = _harness_module()
    observed: dict[str, object] = {}

    def completed(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        observed["command"] = args[0]
        observed.update(kwargs)
        return subprocess.CompletedProcess(args[0], 0, "", "")

    monkeypatch.setattr(module, "_command", completed)

    module._run_codex("codex", "author the workflow", tmp_path, {"PATH": "/bin"}, 30)

    assert observed["command"][-1] == "-"
    assert observed["input_text"] == "author the workflow"


def test_codex_commands_close_inherited_standard_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _harness_module()
    observed: dict[str, object] = {}

    def completed(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        observed.update(kwargs)
        return subprocess.CompletedProcess(args[0], 0, "", "")

    monkeypatch.setattr(module.subprocess, "run", completed)

    module._command(["codex", "exec", "prompt"], {"PATH": "/usr/bin:/bin"}, 30)

    assert observed["stdin"] is subprocess.DEVNULL


def test_plugin_identity_reads_the_staged_plugin_manifest(tmp_path: Path) -> None:
    module = _harness_module()
    plugin_root = tmp_path / "generated-plugin"
    manifest = plugin_root / ".codex-plugin" / "plugin.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        json.dumps({"name": "agent-engineering", "version": "0.1.0"}),
        encoding="utf-8",
    )

    assert module._plugin_identity(plugin_root) == "agent-engineering@0.1.0"


def test_generated_plugin_provenance_requires_every_packager_receipt(
    tmp_path: Path,
) -> None:
    module = _harness_module()
    plugin_root = tmp_path / "generated-plugin"
    manifest = plugin_root / ".codex-plugin" / "plugin.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        json.dumps({"name": "agent-engineering", "version": "0.1.0"}),
        encoding="utf-8",
    )

    with pytest.raises(module.HarnessError, match="generated plugin receipt"):
        module._generated_plugin_provenance(plugin_root)


def test_generated_plugin_provenance_binds_every_packager_receipt() -> None:
    module = _harness_module()

    provenance = module._generated_plugin_provenance(
        REPO_ROOT / ".codex-plugin" / "generated" / "agent-engineering"
    )

    assert set(provenance) == {
        "generated_manifest_digest",
        "router_authority_digest",
        "payload_manifest_digest",
        "source_map_digest",
        "release_metadata_digest",
    }
    assert all(len(digest) == 64 for digest in provenance.values())


def test_unavailable_evidence_uses_its_declared_terminal_boundary() -> None:
    module = _harness_module()
    contract = module.load_m44_scenario(
        REPO_ROOT
        / "tests"
        / "fixtures"
        / "dar-authoring"
        / "m4-4"
        / "portable-package-handoff.json"
    )

    evidence = module._unavailable_evidence(
        contract,
        subprocess.CompletedProcess(("codex",), 0, "capability_unavailable", ""),
        REPO_ROOT / "dist" / "dynamic_agent_runner-0.2.1-py3-none-any.whl",
        "materials",
        (100,),
        "agent-engineering@0.1.0",
        {},
    )

    assert evidence.terminal_phase == "source_selection"


def test_refusal_evidence_preserves_the_declared_refusal_status() -> None:
    module = _harness_module()
    contract = module.load_m44_scenario(
        REPO_ROOT
        / "tests"
        / "fixtures"
        / "dar-authoring"
        / "m4-4"
        / "authoring-boundary-attack.json"
    )

    evidence = module._unavailable_evidence(
        contract,
        subprocess.CompletedProcess(("codex",), 0, "capability_unavailable", ""),
        REPO_ROOT / "dist" / "dynamic_agent_runner-0.2.1-py3-none-any.whl",
        "materials",
        (100,),
        "agent-engineering@0.1.0",
        {},
    )

    assert evidence.observed_status == "expected_refusal"
    assert evidence.terminal_phase == contract.expected_terminal_phase


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
        set(record)
        == {
            "scenario_id",
            "observed_status",
            "record_digest",
            "actor_duration_ms",
        }
        for record in value["records"]
    )
    assert value["actor_duration_ms"] == sum(
        record["actor_duration_ms"] for record in value["records"]
    )
    assert str(tmp_path) not in aggregate.read_text(encoding="utf-8")
    record = json.loads(
        (
            evidence_directory
            / value["records"][0]["scenario_id"]
            / "author-then-run.json"
        ).read_text(encoding="utf-8")
    )
    assert record["dar_runtime_version"] == "0.1.17"
    assert record["dar_runtime_wheel_filename"].endswith(".whl")
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
    records = _manifest_records(module)
    with pytest.raises(module.HarnessError, match="runtime identities"):
        module.write_manifest_evidence(
            evidence_directory=(tmp_path / "mismatched-runtime-evidence").resolve(),
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
            records=(*records[:-1], replace(records[-1], dar_runtime_version="0.1.18")),
        )
    records = _manifest_records(module)
    with pytest.raises(module.HarnessError, match="actor durations"):
        module.write_manifest_evidence(
            evidence_directory=(tmp_path / "missing-duration-evidence").resolve(),
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
            records=(*records[:-1], replace(records[-1], actor_durations_ms=())),
        )


def test_manifest_evidence_retains_an_actor_failure_with_its_actual_phase(
    tmp_path: Path,
) -> None:
    module = _harness_module()
    records = list(_manifest_records(module))
    index = next(
        index
        for index, record in enumerate(records)
        if record.scenario_id == "document-summary-v1"
    )
    records[index] = replace(
        records[index],
        observed_status="harness_failure",
        terminal_phase="authoring_validation",
        authoring_material_set_id=None,
        authoring_output_id=None,
        authoring_receipt_digest=None,
        final_package_digest=None,
        catalog_revision_digest=None,
        registration_digest=None,
        prepared_input_registration_digest=None,
        action_trace_digest=None,
        marketplace_manifest_digest=None,
        failure_reason="author_process_or_receipt_validation",
    )

    aggregate = module.write_manifest_evidence(
        evidence_directory=(tmp_path / "evidence").resolve(),
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
        records=tuple(records),
    )

    aggregate_value = json.loads(aggregate.read_text(encoding="utf-8"))
    assert len(aggregate_value["records"]) == 23
    failure = json.loads(
        (
            tmp_path / "evidence" / "document-summary-v1" / "author-then-run.json"
        ).read_text(encoding="utf-8")
    )
    assert failure["observed_status"] == "harness_failure"
    assert failure["terminal_phase"] == "authoring_validation"


def test_manifest_runner_replays_every_plan_entry_before_aggregating(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _harness_module()
    records = {record.scenario_id: record for record in _manifest_records(module)}
    calls: list[dict[str, object]] = []
    fixture_contracts: list[str] = []
    original_admission_calls: list[tuple[object, object]] = []

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
    monkeypatch.setattr(
        module,
        "validate_m44_original_scenario_admission",
        lambda original_ids, **kwargs: original_admission_calls.append(
            (original_ids, kwargs["plan"])
        ),
    )
    runtime_release = module.RuntimeReleaseReceipt(
        "0.1.17",
        "dynamic_agent_runner-0.1.17-py3-none-any.whl",
        "a" * 64,
        "b" * 64,
        "c" * 64,
        "d" * 64,
        "e" * 64,
        ("0.1.3", "0.1.3"),
    )
    monkeypatch.setattr(
        module, "_runtime_release_receipt", lambda **_kwargs: runtime_release
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
        runtime_release_descriptor=(tmp_path / "release.json").resolve(),
        model_id="openai/local-model",
        base_url="http://127.0.0.1:8080/v1",
        reviewer_id=None,
        reviewer_decision="pending",
        codex_executable="codex",
        timeout=1,
        progress_file=(tmp_path / "progress.jsonl").resolve(),
    )

    assert len(calls) == 23
    assert len(original_admission_calls) == 2
    assert set(fixture_contracts) == set(records)
    assert {call["evidence"] for call in calls} == {None}
    assert {call["runtime_release"] for call in calls} == {runtime_release}
    aggregate_data = json.loads(aggregate.read_text(encoding="utf-8"))
    assert len(aggregate_data["records"]) == 23
    emitted = json.loads(
        (
            (tmp_path / "evidence")
            / aggregate_data["records"][0]["scenario_id"]
            / "author-then-run.json"
        ).read_text(encoding="utf-8")
    )
    assert emitted["dar_runtime_wheel_metadata_digest"] == "b" * 64
    progress = [
        json.loads(line)
        for line in (tmp_path / "progress.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert progress[0] == {"event": "run_started", "scenario_count": 23}
    assert sum(event["event"] == "scenario_started" for event in progress) == 23
    assert sum(event["event"] == "scenario_completed" for event in progress) == 23
    assert progress[-1] == {"event": "run_completed", "scenario_count": 23}


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
                "--runtime-release-descriptor",
                str(tmp_path / "dar-runtime-release.json"),
            )
        )
        == 0
    )
    assert observed["model_id"] == "openai/local-model"
    assert observed["base_url"] == "http://127.0.0.1:18080/v1"
    assert observed["progress_file"] == (tmp_path / "evidence.progress.jsonl").resolve()


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


def test_generated_root_launches_isolated_author_and_invocation_actors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The author is the only actor allowed to construct the package."""

    module = _harness_module()
    actor_log = tmp_path / "actors.jsonl"
    fake_codex = tmp_path / "fake-codex"
    template = (
        REPO_ROOT
        / "plugins"
        / "agent-engineering"
        / "payload"
        / "dar-workflow-authoring"
        / "references"
        / "dar-authoring-templates"
    )
    files = {
        path.name: path.read_text(encoding="utf-8")
        for path in sorted(template.iterdir())
        if path.is_file()
    }
    files["agent-runtime.yaml"] = files["agent-runtime.yaml"].replace(
        "package_id: dar-authoring-no-tool-template",
        "package_id: m44-isolated-actors",
    )
    files["workflow-descriptor.yaml"] = files["workflow-descriptor.yaml"].replace(
        "package_id: dar-authoring-no-tool-template",
        "package_id: m44-isolated-actors",
    )
    fake_codex.write_text(
        "#!/usr/bin/env python3\n"
        "import json\n"
        "import os\n"
        "import re\n"
        "import subprocess\n"
        "import sys\n"
        f"LOG = {str(actor_log)!r}\n"
        f"FILES = {files!r}\n"
        "args = sys.argv[1:]\n"
        "if args[:1] == ['plugin']:\n"
        "    raise SystemExit(0)\n"
        "if args[:1] != ['exec']:\n"
        "    raise SystemExit(2)\n"
        "os.chdir(args[args.index('--cd') + 1])\n"
        "prompt = sys.stdin.read()\n"
        "mode = 'author' if 'Create, write, and finalize' in prompt else 'invoke'\n"
        "with open(LOG, 'a', encoding='utf-8') as stream:\n"
        "    stream.write(json.dumps({'mode': mode, 'cwd': os.getcwd(), 'prompt': prompt, 'state_env': [key for key in os.environ if 'STATE_ROOT' in key or 'CONTROLLER_SOCKET' in key]}) + '\\n')\n"
        "if mode == 'author':\n"
        "    material = re.search(r'material_set_id is `([^`]+)`', prompt).group(1)\n"
        "    package = re.search(r'package name is `([^`]+)`', prompt).group(1)\n"
        "    def call(arguments, content=None):\n"
        "        result = subprocess.run(['dar-package', *arguments], input=content, text=True, capture_output=True, check=True)\n"
        "        print(result.stdout, end='')\n"
        "        return json.loads(result.stdout)\n"
        "    call(['project-authoring-materials', '--material-set-id', material])\n"
        "    created = call(['create-authored-package', '--package-name', package])\n"
        "    for name, content in FILES.items():\n"
        "        call(['write-authored-package-file', '--authoring-output-id', created['authoring_output_id'], '--relative-path', name, '--content-stdin'], content)\n"
        "    call(['finalize-authored-package', '--authoring-output-id', created['authoring_output_id'], '--material-set-id', material])\n"
        "else:\n"
        "    package = re.search(r'saved workflow `([^`]+)`', prompt).group(1)\n"
        "    result = subprocess.run(['dar-package', 'invoke', '--package-name', package, '--prompt-stdin'], input='Summarize the supplied document.', text=True, capture_output=True, check=True)\n"
        "    print(result.stdout, end='')\n",
        encoding="utf-8",
    )
    os.chmod(fake_codex, 0o700)
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir(mode=0o700)
    (codex_home / "auth.json").write_text("{}", encoding="utf-8")

    def connect_loopback(
        address: tuple[str, int], timeout: object = None, source_address: object = None
    ) -> socket.socket:
        assert address[0] == "127.0.0.1"
        connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if timeout is not None:
            connection.settimeout(timeout)
        _ORIGINAL_SOCKET_CONNECT(connection, address)
        return connection

    monkeypatch.setattr(socket, "create_connection", connect_loopback)
    monkeypatch.setenv("LITELLM_LOCAL_MODEL_COST_MAP", "true")
    monkeypatch.setenv("UV_CACHE_DIR", str(tmp_path / "uv-cache"))

    with module._fake_model_server() as base_url:
        evidence = module.run_scenario(
            scenario=(
                REPO_ROOT
                / "tests"
                / "fixtures"
                / "dar-authoring"
                / "m4-4"
                / "document-summary.json"
            ),
            codex_home=codex_home,
            plugin_root=REPO_ROOT / ".codex-plugin" / "generated" / "agent-engineering",
            wheel=REPO_ROOT / "dist" / "dynamic_agent_runner-0.1.17-py3-none-any.whl",
            package_name="m44-isolated-actors",
            workflow_id="m44-isolated-actors",
            author_prompt="Author the declared DAR document-summary workflow.",
            run_prompt="Summarize the supplied document.",
            materials=REPO_ROOT / "tests" / "fixtures" / "m4-4-external-materials.json",
            model_id="openai/local-model",
            base_url=base_url,
            evidence=None,
            reviewer_id=None,
            reviewer_decision="pending",
            codex_executable=str(fake_codex),
            timeout=20,
        )

    actors = [
        json.loads(line) for line in actor_log.read_text(encoding="utf-8").splitlines()
    ]
    assert evidence.observed_status == "pending_human_review"
    assert [actor["mode"] for actor in actors] == ["author", "invoke"]
    assert actors[0]["cwd"] != actors[1]["cwd"]
    assert actors[0]["state_env"] == []
    assert actors[1]["state_env"] == []
    assert "create-authored-package" not in actors[1]["prompt"]
    assert "finalize-authored-package" not in actors[1]["prompt"]
    assert "m44-isolated-actors" in actors[1]["prompt"]


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


def test_controller_mcp_fixture_exposes_the_read_only_authoring_template_tool(
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
        approved_read_only_tool_names=("lookup_records",),
    )

    assert reviewed.read_only_tool_names == frozenset({"lookup_records"})


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
    (plugin / "references" / "modules" / "dar-workflow-authoring" / "references").mkdir(
        parents=True
    )
    (plugin / ".codex-plugin" / "plugin.json").write_text("{}", encoding="utf-8")
    (plugin / "skills" / "agent-development" / "SKILL.md").write_text(
        "# Agent development\n", encoding="utf-8"
    )
    (
        plugin
        / "references"
        / "modules"
        / "dar-workflow-authoring"
        / "references"
        / "dar-runtime-profile.md"
    ).write_text("# DAR runtime profile\n", encoding="utf-8")

    marketplace = create_marketplace(
        plugin_root=plugin, destination=tmp_path / "marketplace"
    )

    assert marketplace.is_file()
    copied_plugin = tmp_path / "marketplace" / "plugins" / "agent-engineering"
    assert copied_plugin.is_dir()
    assert (copied_plugin / "skills" / "agent-development" / "SKILL.md").is_file()
    assert (
        copied_plugin
        / "references"
        / "modules"
        / "dar-workflow-authoring"
        / "references"
        / "dar-runtime-profile.md"
    ).is_file()


def test_marketplace_allows_the_frozen_direct_baseline_only_when_explicit(
    tmp_path: Path,
) -> None:
    with pytest.raises(M44CleanCodexError, match="successor plugin surface is invalid"):
        create_marketplace(
            plugin_root=REPO_ROOT
            / "tests"
            / "fixtures"
            / "m4-4-direct-plugin-baseline",
            destination=tmp_path / "generated-only-marketplace",
        )

    marketplace = create_marketplace(
        plugin_root=REPO_ROOT / "tests" / "fixtures" / "m4-4-direct-plugin-baseline",
        destination=tmp_path / "direct-baseline-marketplace",
        plugin_surface="direct-baseline",
    )

    assert marketplace.is_file()
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


def test_decision_summary_keeps_normalized_actor_choices_without_transcript_text() -> (
    None
):
    module = _harness_module()
    transcript = "\n".join(
        (
            json.dumps(
                {
                    "item": {
                        "type": "agent_message",
                        "text": "private prompt content",
                    }
                }
            ),
            json.dumps(
                {
                    "item": {
                        "type": "command_execution",
                        "command": "dar-package finalize-authored-package",
                    }
                }
            ),
            json.dumps({"item": {"type": "file_change"}}),
        )
    )

    decisions = module._decision_summary(transcript, prefix="author")

    assert decisions == (
        "author:agent_message",
        "author:command:dar-package",
        "author:file_change",
    )
    assert "private prompt content" not in decisions


def test_event_trace_preserves_actor_order_and_command_exit_without_content() -> None:
    module = _harness_module()
    transcript = "\n".join(
        (
            json.dumps({"item": {"type": "agent_message"}}),
            json.dumps(
                {
                    "item": {
                        "type": "command_execution",
                        "command": "/bin/zsh -lc 'dar-package invoke'",
                        "exit_code": 1,
                    }
                }
            ),
        )
    )

    assert module._event_trace(transcript, prefix="invocation") == (
        "invocation:1:agent_message",
        "invocation:2:command_execution:zsh:exit=1",
    )


def test_successor_author_prompt_declares_exact_artifact_roles() -> None:
    module = _harness_module()

    prompt = module._author_request(
        "Author the declared DAR workflow using the supplied email_body artifact.",
        "material-id",
        "email-file-body",
        "pass",
        artifact_roles=("email_body",),
    )

    assert "Declared artifact roles: email_body" in prompt
    assert "copy each role exactly" in prompt


def test_email_artifact_author_prompt_requires_reviewed_write_template() -> None:
    module = _harness_module()

    prompt = module._author_request(
        "Author the declared DAR approved email-send workflow.",
        "material-id",
        "email-file-body",
        "pass",
        artifact_roles=("email_body",),
    )

    assert "approved email-send operation" in prompt
    assert "reviewed write-MCP template" in prompt
    assert "do not choose the no-tool starter" in prompt


def test_email_author_prompt_requires_reviewed_write_template_without_artifact() -> (
    None
):
    module = _harness_module()

    prompt = module._author_request(
        "Author the declared DAR approved email-send workflow.",
        "material-id",
        "generic-email-send",
        "pass",
    )

    assert "approved email-send operation" in prompt
    assert "reviewed write-MCP template" in prompt
    assert "do not choose the no-tool starter" in prompt


def test_document_summary_author_prompt_requires_the_no_tool_template() -> None:
    module = _harness_module()

    prompt = module._author_request(
        "Author the declared DAR document-summary workflow.",
        "material-id",
        "document-summary",
        "pass",
    )

    assert "bounded no-tool workflow" in prompt
    assert "canonical no-tool template" in prompt
    assert "references/dar-authoring-templates/" in prompt
    assert "do not construct its graph from scratch" in prompt


def test_mailbox_triage_author_prompt_requires_the_read_only_template() -> None:
    module = _harness_module()

    prompt = module._author_request(
        "Author the declared DAR mailbox-triage workflow.",
        "material-id",
        "mailbox-triage",
        "pass",
    )

    assert "read-only MCP workflow" in prompt
    assert "reviewed read-only MCP template" in prompt
    assert "do not construct its graph from scratch" in prompt


def test_oauth_reconnect_author_prompt_requires_the_read_only_template() -> None:
    module = _harness_module()

    prompt = module._author_request(
        "Author the declared DAR OAuth reconnect workflow.",
        "material-id",
        "oauth-reconnect",
        "pass",
    )

    assert "read-only MCP workflow" in prompt
    assert "reviewed read-only MCP template" in prompt
    assert "do not construct its graph from scratch" in prompt


def test_structured_review_author_prompt_requires_its_terminal_contract() -> None:
    module = _harness_module()

    prompt = module._author_request(
        "Author the declared DAR structured single-model review workflow.",
        "material-id",
        "structured-review",
        "pass",
    )

    assert "canonical no-tool template" in prompt
    assert "review_result" in prompt
    assert "required message field" in prompt


def test_skill_bundle_author_prompt_requires_the_review_template() -> None:
    module = _harness_module()

    prompt = module._author_request(
        "Author the declared DAR no-tool graph with package-local skill `review-guide`.",
        "material-id",
        "no-tool-graph",
        "pass",
    )

    assert "package-local skill workflow" in prompt
    assert "skill-bundle template" in prompt
    assert "references/dar-authoring-skill-bundle-template/" in prompt
    assert "do not construct its graph from scratch" in prompt


def test_successor_author_prompt_declares_caller_owned_guardrail_contract() -> None:
    module = _harness_module()

    prompt = module._author_request(
        "Author the declared DAR input-guardrail workflow.",
        "material-id",
        "guardrail-input",
        "pass",
        guardrails=(("require_input", "input"),),
    )

    assert "Declared caller-owned guardrails: require_input (input)" in prompt
    assert "do not implement a handler" in prompt


def test_successor_run_prompt_names_only_the_saved_package_and_request() -> None:
    module = _harness_module()

    prompt = module._run_request(
        "summary", "Summarize this text.", requires_approval=False
    )

    assert "dar-package invoke --package-name summary --prompt-stdin" in prompt
    assert "printf '%s' 'Summarize this text.'" in prompt
    assert "summary" in prompt
    assert "Summarize this text." in prompt
    assert "exactly one command" in prompt
    assert "Immediately return" in prompt
    assert "uv run" not in prompt
    assert "/" not in prompt


def test_successor_approval_run_prompt_requires_the_declared_ask_mode() -> None:
    module = _harness_module()

    prompt = module._run_request(
        "email", "Send the declared email.", requires_approval=True
    )

    assert "dar-package invoke --package-name email --prompt-stdin --ask" in prompt


def test_successor_controller_advertises_supported_execution_gates() -> None:
    module = _harness_module()

    assert set(module._controller_available_gates()) == {"G2", "G3", "G4", "G5"}
