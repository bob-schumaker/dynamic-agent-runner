"""Tests for the external DAR authoring release-harness script."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
HARNESS = REPO_ROOT / "scripts" / "run_dar_authoring_harness.py"
FIXTURE = (
    REPO_ROOT
    / "tests"
    / "fixtures"
    / "dar-authoring"
    / "invocations"
    / "agent-development.json"
)
EVALUATION_FIXTURE = (
    REPO_ROOT
    / "tests"
    / "fixtures"
    / "dar-authoring"
    / "invocations"
    / "agent-evaluation.json"
)
TOOL_CONTRACT_FIXTURE = (
    REPO_ROOT
    / "tests"
    / "fixtures"
    / "dar-authoring"
    / "invocations"
    / "agent-tool-contract-design.json"
)
TEMPLATE = (
    REPO_ROOT
    / "specs"
    / "agent-engineering-plugin-migration"
    / "legacy-dar-authoring"
    / "templates"
)
EVALUATION_TEMPLATE = (
    REPO_ROOT
    / "specs"
    / "agent-engineering-plugin-migration"
    / "legacy-dar-authoring"
    / "evaluation-templates"
)
READ_ONLY_MCP_TEMPLATE = (
    REPO_ROOT
    / "specs"
    / "agent-engineering-plugin-migration"
    / "legacy-dar-authoring"
    / "read-only-mcp-template"
)


def _materials(tmp_path: Path) -> Path:
    path = tmp_path / "materials.json"
    path.write_text(
        json.dumps(
            {
                "expires_at": "2026-08-25T00:00:00+00:00",
                "material_set_id": "v1.material-set.signature",
                "members": [
                    {
                        "artifact_id": "authoring-material-text-sample-v1",
                        "content": "private selected example",
                        "digest": "1" * 64,
                        "disposition": "reference_only",
                        "role": "example_text",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def _evaluation_materials(tmp_path: Path) -> Path:
    path = tmp_path / "evaluation-materials.json"
    path.write_text(
        json.dumps(
            {
                "expires_at": "2026-08-25T00:00:00+00:00",
                "material_set_id": "v1.evaluation-material-set.signature",
                "members": [
                    {
                        "artifact_id": "authoring-material-package-contract-v1",
                        "content": "private selected package contract",
                        "digest": "3" * 64,
                        "disposition": "reference_only",
                        "role": "package_contract",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def _tool_contract_materials(tmp_path: Path) -> Path:
    path = tmp_path / "tool-contract-materials.json"
    path.write_text(
        json.dumps(
            {
                "expires_at": "2026-08-25T00:00:00+00:00",
                "material_set_id": "v1.tool-contract-material-set.signature",
                "members": [
                    {
                        "artifact_id": "authoring-material-reviewed-tool-surface-v1",
                        "content": "private selected reviewed tool surface",
                        "digest": "2" * 64,
                        "disposition": "reference_only",
                        "role": "reviewed_tool_surface",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def _generator(leak: bool, violates_no_tool_contract: bool = False) -> str:
    purpose_adaptation = (
        "(output / 'workflow-descriptor.yaml').write_text("
        "(output / 'workflow-descriptor.yaml').read_text().replace("
        "'purpose: Answer one bounded user request with a local model and no tools.', "
        "'purpose: Answer one bounded question using only supplied text with gpt-5.6-terra and no tools.'), "
        "encoding='utf-8');"
    )
    leak_statement = (
        "(output / 'agent-design.md').write_text("
        "(output / 'agent-design.md').read_text() + 'private selected example', "
        "encoding='utf-8');"
        if leak
        else ""
    )
    no_tool_violation = (
        "(output / 'workflow-descriptor.yaml').write_text("
        "(output / 'workflow-descriptor.yaml').read_text().replace("
        "'max_total_tool_calls: 0', 'max_total_tool_calls: 1'), "
        "encoding='utf-8');"
        if violates_no_tool_contract
        else ""
    )
    return (
        "from pathlib import Path; "
        "import shutil, sys; "
        "from dynamic_agent_runner.workflow_host.authoring_output "
        "import write_authored_package_manifest; "
        f"template = Path({str(TEMPLATE)!r}); "
        "output = Path(sys.argv[sys.argv.index('--output') + 1]); "
        "shutil.copytree(template, output, dirs_exist_ok=True); "
        "[path.write_text(path.read_text().replace('profile_requirement: local-general-model', 'profile_requirement: gpt-5.6-terra').replace('model: local-model', 'model: gpt-5.6-terra')) for path in output.iterdir()]; "
        f"{purpose_adaptation}"
        f"{leak_statement}"
        f"{no_tool_violation}"
        "write_authored_package_manifest(output)"
    )


def _run(
    tmp_path: Path,
    *,
    leak: bool,
    decision: str,
    violates_no_tool_contract: bool = False,
) -> subprocess.CompletedProcess[str]:
    evidence = tmp_path / "evidence" / "evidence.json"
    return subprocess.run(
        [
            sys.executable,
            str(HARNESS),
            "--fixture",
            str(FIXTURE),
            "--materials",
            str(_materials(tmp_path)),
            "--provider",
            "test-provider",
            "--model-id",
            "test-model",
            "--reviewer-id",
            "test-reviewer",
            "--reviewer-decision",
            decision,
            "--evidence",
            str(evidence),
            "--pass-criterion",
            "package_validation",
            "--generator",
            sys.executable,
            "-c",
            _generator(leak, violates_no_tool_contract),
        ],
        capture_output=True,
        check=False,
        encoding="utf-8",
        timeout=10,
    )


def test_harness_records_redacted_evidence_for_a_valid_generated_package(
    tmp_path: Path,
) -> None:
    completed = _run(tmp_path, leak=False, decision="approved")
    evidence = tmp_path / "evidence" / "evidence.json"

    assert completed.returncode == 0, completed.stderr
    recorded = json.loads(evidence.read_text(encoding="utf-8"))
    assert recorded["validator_result"] == "passed"
    assert recorded["reviewer_decision"] == "approved"
    assert len(recorded["generated_package_digests"]) == 1
    assert "private selected example" not in completed.stdout
    assert "private selected example" not in evidence.read_text(encoding="utf-8")
    assert evidence.stat().st_mode & 0o777 == 0o600


def test_harness_records_a_rejected_redacted_failure_for_private_material_leak(
    tmp_path: Path,
) -> None:
    completed = _run(tmp_path, leak=True, decision="rejected")
    evidence = tmp_path / "evidence" / "evidence.json"

    assert completed.returncode == 0, completed.stderr
    recorded = json.loads(evidence.read_text(encoding="utf-8"))
    assert recorded["validator_result"] == "failed"
    assert recorded["reviewer_decision"] == "rejected"
    assert recorded["generated_package_digests"] == []
    assert "private selected example" not in completed.stdout
    assert "private selected example" not in evidence.read_text(encoding="utf-8")


def test_harness_rejects_a_package_that_violates_the_no_tool_contract(
    tmp_path: Path,
) -> None:
    completed = _run(
        tmp_path,
        leak=False,
        decision="rejected",
        violates_no_tool_contract=True,
    )
    evidence = tmp_path / "evidence" / "evidence.json"

    assert completed.returncode == 0, completed.stderr
    recorded = json.loads(evidence.read_text(encoding="utf-8"))
    assert recorded["validator_result"] == "failed"
    assert recorded["generated_package_digests"] == []


def test_harness_accepts_a_package_finalized_by_the_host_control_plane(
    tmp_path: Path,
) -> None:
    from dynamic_agent_runner.workflow_host.host import configure_local_host

    state_root = tmp_path / "state"
    package_root = tmp_path / "packages"
    package_root.mkdir()
    configure_local_host(
        root=state_root,
        package_root=package_root,
        model_id="local-test-model",
        base_url="http://127.0.0.1:11434/v1",
    )
    generator = tmp_path / "control_plane_generator.py"
    generator.write_text(
        "\n".join(
            [
                "from __future__ import annotations",
                "import json",
                "from pathlib import Path",
                "import sys",
                "from dynamic_agent_runner.workflow_host.cli import main",
                f"state_root = {str(state_root)!r}",
                f"template_root = Path({str(TEMPLATE)!r})",
                f"package_root = Path({str(package_root)!r})",
                "request_path = Path(sys.argv[sys.argv.index('--request') + 1])",
                "output_path = Path(sys.argv[sys.argv.index('--output') + 1])",
                "request = json.loads(request_path.read_text(encoding='utf-8'))",
                "def call(arguments, content=None):",
                "    output = []",
                "    status = main(['--state-root', state_root, *arguments],",
                "                  write=output.append,",
                "                  read_stdin=(lambda: content) if content is not None else None)",
                "    assert status == 0",
                "    return json.loads(output[0])",
                "material_root = output_path.parent / 'human-materials'",
                "material_root.mkdir()",
                "manifest_members = []",
                "for index, member in enumerate(request['materials']['members']):",
                "    path = material_root / f'material-{index}.txt'",
                "    path.write_text(member['content'], encoding='utf-8')",
                "    manifest_members.append({'role': member['role'], 'path': str(path), 'disposition': member['disposition']})",
                "manifest_path = material_root / 'manifest.json'",
                "manifest_path.write_text(json.dumps({'format_version': 1, 'members': manifest_members}), encoding='utf-8')",
                "issued = call(['issue-authoring-materials', '--materials-manifest', str(manifest_path)])",
                "call(['project-authoring-materials', '--material-set-id', issued['material_set_id']])",
                "created = call(['create-authored-package', '--package-name', 'document-helper'])",
                "for source in template_root.iterdir():",
                "    content = source.read_text(encoding='utf-8').replace(",
                "        'purpose: Answer one bounded user request with a local model and no tools.',",
                "        'purpose: Answer one bounded question using only supplied text with gpt-5.6-terra and no tools.').replace(",
                "        'profile_requirement: local-general-model', 'profile_requirement: gpt-5.6-terra').replace(",
                "        'model: local-model', 'model: gpt-5.6-terra')",
                "    call(['write-authored-package-file', '--authoring-output-id', created['authoring_output_id'],",
                "          '--relative-path', source.name, '--content-stdin'],",
                "         content)",
                "call(['finalize-authored-package', '--authoring-output-id', created['authoring_output_id'],",
                "      '--material-set-id', issued['material_set_id']])",
                "assert output_path == package_root / 'document-helper'",
            ]
        ),
        encoding="utf-8",
    )
    evidence = tmp_path / "evidence" / "evidence.json"

    completed = subprocess.run(
        [
            sys.executable,
            str(HARNESS),
            "--fixture",
            str(FIXTURE),
            "--materials",
            str(_materials(tmp_path)),
            "--provider",
            "test-provider",
            "--model-id",
            "test-model",
            "--reviewer-id",
            "test-reviewer",
            "--reviewer-decision",
            "approved",
            "--evidence",
            str(evidence),
            "--pass-criterion",
            "host_control_plane",
            "--host-package-root",
            str(package_root),
            "--host-package-name",
            "document-helper",
            "--generator",
            sys.executable,
            str(generator),
        ],
        capture_output=True,
        check=False,
        encoding="utf-8",
        timeout=10,
    )

    assert completed.returncode == 0, completed.stderr
    assert (package_root / "document-helper" / "package-manifest.json").is_file()
    assert (
        json.loads(evidence.read_text(encoding="utf-8"))["validator_result"] == "passed"
    )


def test_harness_validates_companion_artifacts_in_the_entry_skill_package(
    tmp_path: Path,
) -> None:
    from dynamic_agent_runner.workflow_host.host import configure_local_host

    state_root = tmp_path / "state"
    package_root = tmp_path / "packages"
    package_root.mkdir()
    configure_local_host(
        root=state_root,
        package_root=package_root,
        model_id="local-test-model",
        base_url="http://127.0.0.1:11434/v1",
    )
    generator = tmp_path / "companion_generator.py"
    generator.write_text(
        "\n".join(
            [
                "from __future__ import annotations",
                "import json",
                "from pathlib import Path",
                "import sys",
                "from dynamic_agent_runner.workflow_host.cli import main",
                f"state_root = {str(state_root)!r}",
                f"template_root = Path({str(TEMPLATE)!r})",
                f"evaluation_root = Path({str(EVALUATION_TEMPLATE)!r})",
                "request_path = Path(sys.argv[sys.argv.index('--request') + 1])",
                "output_path = Path(sys.argv[sys.argv.index('--output') + 1])",
                "request = json.loads(request_path.read_text(encoding='utf-8'))",
                "assert request['companions'][0]['skill'] == 'agent-evaluation'",
                "def call(arguments, content=None):",
                "    output = []",
                "    status = main(['--state-root', state_root, *arguments],",
                "                  write=output.append,",
                "                  read_stdin=(lambda: content) if content is not None else None)",
                "    assert status == 0",
                "    return json.loads(output[0])",
                "material_root = output_path.parent / 'human-materials'",
                "material_root.mkdir()",
                "manifest_members = []",
                "for index, member in enumerate(request['materials']['members']):",
                "    path = material_root / f'material-{index}.txt'",
                "    path.write_text(member['content'], encoding='utf-8')",
                "    manifest_members.append({'role': member['role'], 'path': str(path), 'disposition': member['disposition']})",
                "manifest_path = material_root / 'manifest.json'",
                "manifest_path.write_text(json.dumps({'format_version': 1, 'members': manifest_members}), encoding='utf-8')",
                "issued = call(['issue-authoring-materials', '--materials-manifest', str(manifest_path)])",
                "call(['project-authoring-materials', '--material-set-id', issued['material_set_id']])",
                "created = call(['create-authored-package', '--package-name', 'document-helper'])",
                "for source_root in (template_root, evaluation_root):",
                "    for source in source_root.iterdir():",
                "        content = source.read_text(encoding='utf-8').replace(",
                "            'purpose: Answer one bounded user request with a local model and no tools.',",
                "            'purpose: Answer one bounded question using only supplied text with gpt-5.6-terra and no tools.').replace(",
                "            'profile_requirement: local-general-model', 'profile_requirement: gpt-5.6-terra').replace(",
                "            'model: local-model', 'model: gpt-5.6-terra')",
                "        call(['write-authored-package-file', '--authoring-output-id', created['authoring_output_id'],",
                "              '--relative-path', source.name, '--content-stdin'],",
                "             content)",
                "call(['finalize-authored-package', '--authoring-output-id', created['authoring_output_id'],",
                "      '--material-set-id', issued['material_set_id']])",
                "assert output_path.name == 'document-helper'",
            ]
        ),
        encoding="utf-8",
    )
    evidence = tmp_path / "evidence" / "evidence.json"

    completed = subprocess.run(
        [
            sys.executable,
            str(HARNESS),
            "--fixture",
            str(FIXTURE),
            "--materials",
            str(_materials(tmp_path)),
            "--companion-fixture",
            str(EVALUATION_FIXTURE),
            "--companion-materials",
            str(_evaluation_materials(tmp_path)),
            "--provider",
            "test-provider",
            "--model-id",
            "test-model",
            "--reviewer-id",
            "test-reviewer",
            "--reviewer-decision",
            "approved",
            "--evidence",
            str(evidence),
            "--pass-criterion",
            "companion_artifacts",
            "--host-package-root",
            str(package_root),
            "--host-package-name",
            "document-helper",
            "--generator",
            sys.executable,
            str(generator),
        ],
        capture_output=True,
        check=False,
        encoding="utf-8",
        timeout=10,
    )

    assert completed.returncode == 0, completed.stderr
    generated = package_root / "document-helper"
    assert (generated / "eval-plan.md").is_file()
    assert (generated / "evaluation-fixtures.json").is_file()
    assert (generated / "regression-gate.yaml").is_file()
    assert (
        json.loads(evidence.read_text(encoding="utf-8"))["validator_result"] == "passed"
    )


def test_harness_allows_a_tool_companion_to_replace_the_entry_descriptor(
    tmp_path: Path,
) -> None:
    from dynamic_agent_runner.workflow_host.host import configure_local_host

    state_root = tmp_path / "state"
    package_root = tmp_path / "packages"
    package_root.mkdir()
    configure_local_host(
        root=state_root,
        package_root=package_root,
        model_id="local-test-model",
        base_url="http://127.0.0.1:11434/v1",
    )
    generator = tmp_path / "tool_generator.py"
    generator.write_text(
        "\n".join(
            [
                "from __future__ import annotations",
                "import json",
                "from pathlib import Path",
                "import sys",
                "from dynamic_agent_runner.workflow_host.cli import main",
                f"state_root = {str(state_root)!r}",
                f"template_root = Path({str(READ_ONLY_MCP_TEMPLATE)!r})",
                "request_path = Path(sys.argv[sys.argv.index('--request') + 1])",
                "output_path = Path(sys.argv[sys.argv.index('--output') + 1])",
                "request = json.loads(request_path.read_text(encoding='utf-8'))",
                "assert request['companions'][0]['skill'] == 'agent-tool-contract-design'",
                "def call(arguments, content=None):",
                "    output = []",
                "    status = main(['--state-root', state_root, *arguments],",
                "                  write=output.append,",
                "                  read_stdin=(lambda: content) if content is not None else None)",
                "    assert status == 0",
                "    return json.loads(output[0])",
                "material_root = output_path.parent / 'human-materials'",
                "material_root.mkdir()",
                "manifest_members = []",
                "for index, member in enumerate(request['materials']['members']):",
                "    path = material_root / f'material-{index}.txt'",
                "    path.write_text(member['content'], encoding='utf-8')",
                "    manifest_members.append({'role': member['role'], 'path': str(path), 'disposition': member['disposition']})",
                "manifest_path = material_root / 'manifest.json'",
                "manifest_path.write_text(json.dumps({'format_version': 1, 'members': manifest_members}), encoding='utf-8')",
                "issued = call(['issue-authoring-materials', '--materials-manifest', str(manifest_path)])",
                "call(['project-authoring-materials', '--material-set-id', issued['material_set_id']])",
                "created = call(['create-authored-package', '--package-name', 'tool-helper'])",
                "for source in template_root.iterdir():",
                "    content = source.read_text(encoding='utf-8').replace('dar-authoring-read-only-mcp-template', 'tool-helper').replace(",
                "        'profile_requirement: local-general-model', 'profile_requirement: gpt-5.6-terra').replace(",
                "        'model: local-model', 'model: gpt-5.6-terra')",
                "    call(['write-authored-package-file', '--authoring-output-id', created['authoring_output_id'],",
                "          '--relative-path', source.name, '--content-stdin'], content)",
                "tool_index = 'format_version: 1\\nindex_type: agent_runtime_tool_index\\nindex_id: tool-helper-index\\ntools:\\n  - id: lookup_records\\n    adapter: host.mcp\\n'",
                "call(['write-authored-package-file', '--authoring-output-id', created['authoring_output_id'],",
                "      '--relative-path', 'tool-index.yaml', '--content-stdin'], tool_index)",
                "call(['finalize-authored-package', '--authoring-output-id', created['authoring_output_id'],",
                "      '--material-set-id', issued['material_set_id']])",
                "assert output_path.name == 'tool-helper'",
            ]
        ),
        encoding="utf-8",
    )
    evidence = tmp_path / "evidence" / "evidence.json"

    completed = subprocess.run(
        [
            sys.executable,
            str(HARNESS),
            "--fixture",
            str(FIXTURE),
            "--materials",
            str(_materials(tmp_path)),
            "--companion-fixture",
            str(TOOL_CONTRACT_FIXTURE),
            "--companion-materials",
            str(_tool_contract_materials(tmp_path)),
            "--provider",
            "test-provider",
            "--model-id",
            "test-model",
            "--reviewer-id",
            "test-reviewer",
            "--reviewer-decision",
            "approved",
            "--evidence",
            str(evidence),
            "--pass-criterion",
            "tool_companion_artifacts",
            "--host-package-root",
            str(package_root),
            "--host-package-name",
            "tool-helper",
            "--generator",
            sys.executable,
            str(generator),
        ],
        capture_output=True,
        check=False,
        encoding="utf-8",
        timeout=10,
    )

    assert completed.returncode == 0, completed.stderr
    assert (package_root / "tool-helper" / "tool-index.yaml").is_file()
