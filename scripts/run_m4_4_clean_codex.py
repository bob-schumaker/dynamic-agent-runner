#!/usr/bin/env python3
"""Run the mandatory CLI-first M4.4 clean-Codex acceptance cases.

The controller owns fixture state, package registration, and the test-owned
``dar-package`` launcher. Codex sees only the installed successor skill,
opaque material IDs, and declared text inputs.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any, Sequence

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
    configure_local_host,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))

from m4_4_clean_codex import (  # noqa: E402 - repository test corpus import.
    M44CleanCodexError,
    build_clean_codex_environment,
    create_marketplace,
    stage_dar_package,
)
from m4_4_scenarios import (  # noqa: E402 - repository test corpus import.
    M44Scenario,
    M44ScenarioError,
    load_m44_scenario,
    validate_m44_evidence,
)


class HarnessError(ValueError):
    """Raised when M4.4 cannot produce a valid redacted acceptance record."""


def main(argv: Sequence[str] | None = None) -> int:
    """Run one mandatory clean-Codex M4.4 scenario."""

    arguments = _arguments(argv)
    try:
        evidence = run_scenario(**vars(arguments))
    except (
        HarnessError,
        LocalWorkflowHostError,
        M44CleanCodexError,
        M44ScenarioError,
    ) as error:
        print(f"M4.4 clean-Codex harness failed: {error}")
        return 2
    print(json.dumps(evidence.to_mapping(), sort_keys=True, separators=(",", ":")))
    return 0


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
    evidence: Path,
    reviewer_id: str | None,
    reviewer_decision: str,
    codex_executable: str,
    timeout: int,
) -> AuthorThenRunEvidence:
    """Run one author turn and, for the positive case, one independent run turn."""

    contract = load_m44_scenario(scenario)
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
        package_root, state_root = (
            author_workspace / ".packages",
            author_workspace / ".state",
        )
        author_workspace.mkdir(mode=0o700)
        invocation_workspace.mkdir(mode=0o700)
        package_root.mkdir(mode=0o700)
        configure_local_host(
            root=state_root,
            package_root=package_root,
            model_id=model_id,
            base_url=base_url,
        )
        host = LocalWorkflowHost.open(state_root)
        dar_bin = stage_dar_package(
            wheel=wheel,
            state_root=state_root,
            destination=root / "dar-bin",
        )
        material_receipt = host.issue_authoring_materials(
            materials=_load_materials(materials), now=datetime.now(UTC)
        )
        marketplace = create_marketplace(
            plugin_root=plugin_root, destination=root / "marketplace"
        )
        management_environment = _management_environment(codex_home, author_workspace)
        installed = False
        try:
            _install_plugin(
                codex_executable, marketplace, management_environment, timeout
            )
            installed = True
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
                    codex_home=codex_home,
                    working_directory=author_workspace,
                    wheel=wheel,
                    state_root=state_root,
                    template_root=root
                    / "marketplace"
                    / "plugins"
                    / "agent-engineering",
                    inherited={
                        **os.environ,
                        "PATH": f"{dar_bin}{os.pathsep}{os.environ.get('PATH', '')}",
                    },
                ),
                timeout,
            )
            if contract.expected_status == "expected_capability_unavailable":
                result = _unavailable_evidence(
                    contract, author_result, wheel, material_receipt.material_set_id
                )
            else:
                result = _pass_evidence(
                    contract,
                    host,
                    author_result,
                    package_name,
                    workflow_id,
                    run_prompt,
                    codex_home,
                    invocation_workspace,
                    state_root,
                    dar_bin,
                    root / "marketplace" / "plugins" / "agent-engineering",
                    wheel,
                    reviewer_id,
                    reviewer_decision,
                    codex_executable,
                    timeout,
                    material_receipt.material_set_id,
                )
        finally:
            if installed:
                _remove_plugin(codex_executable, management_environment, timeout)
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
) -> AuthorThenRunEvidence:
    created, finalized = (
        _receipt(author_result.stdout, "created"),
        _receipt(author_result.stdout, "finalized"),
    )
    if author_result.returncode or created is None or finalized is None:
        return _failure(contract, "authoring_validation", wheel, material_set_id)
    output_id, package_digest = (
        created.get("authoring_output_id"),
        finalized.get("package_digest"),
    )
    if not isinstance(output_id, str) or not isinstance(package_digest, str):
        return _failure(contract, "authoring_validation", wheel, material_set_id)
    try:
        source_handle = host.select_authored_package(
            package_name, now=datetime.now(UTC)
        )
        registration = host.register(
            workflow_id=workflow_id,
            package_source_handle=source_handle,
            now=datetime.now(UTC),
        )
        if registration.revision_digest != package_digest:
            raise ValueError
    except (LocalWorkflowHostError, ValueError):
        return _failure(contract, "registration", wheel, material_set_id, output_id)
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
    invoked = _receipt(run_result.stdout, "completed")
    if (
        run_result.returncode
        or invoked is None
        or invoked.get("workflow_id") != package_name
    ):
        return _failure(contract, "invocation", wheel, material_set_id, output_id)
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
            {"gates": ["G3"], "fixture": "local-model-profile"}
        ),
    )
    validate_m44_evidence(
        contract,
        result,
        available_gates=("G3",),
        available_host_fixtures=("local-model-profile",),
    )
    return result


def _unavailable_evidence(
    contract: M44Scenario,
    author_result: subprocess.CompletedProcess[str],
    wheel: Path,
    material_set_id: str,
) -> AuthorThenRunEvidence:
    if (
        author_result.returncode
        or _receipt(author_result.stdout, "created") is not None
    ):
        return _failure(contract, "capability_preflight", wheel, material_set_id)
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
    )


def _validate_inputs(
    contract: M44Scenario,
    codex_home: Path,
    plugin_root: Path,
    wheel: Path,
    materials: Path,
    evidence: Path,
    reviewer_decision: str,
    timeout: int,
) -> None:
    if contract.scenario_id not in {"document-summary-v1", "council-request-v1"}:
        raise HarnessError("scenario is not an M4.4 mandatory case")
    for path in (codex_home, plugin_root, wheel, materials, evidence):
        if not path.is_absolute() or path.is_symlink():
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
        "scenario",
        "codex_home",
        "plugin_root",
        "wheel",
        "materials",
        "evidence",
    ):
        parser.add_argument(f"--{name.replace('_', '-')}", type=Path, required=True)
    for name in (
        "package_name",
        "workflow_id",
        "author_prompt",
        "run_prompt",
        "model_id",
        "base_url",
    ):
        parser.add_argument(f"--{name.replace('_', '-')}", required=True)
    parser.add_argument("--reviewer-id")
    parser.add_argument(
        "--reviewer-decision", choices=("pending", "approved"), default="pending"
    )
    parser.add_argument("--codex-executable", default="codex")
    parser.add_argument("--timeout", type=int, default=300)
    return parser.parse_args(argv)


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
    return _command(
        [
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
        ],
        environment,
        timeout,
        check=False,
    )


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
            / ".agents"
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
