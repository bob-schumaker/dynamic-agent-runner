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
TEMPLATE = REPO_ROOT / "dar-authoring" / "templates"


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


def _generator(leak: bool) -> str:
    leak_statement = (
        "(output / 'agent-design.md').write_text("
        "(output / 'agent-design.md').read_text() + 'private selected example', "
        "encoding='utf-8');"
        if leak
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
        f"{leak_statement}"
        "write_authored_package_manifest(output)"
    )


def _run(
    tmp_path: Path, *, leak: bool, decision: str
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
            "--reviewer-decision",
            decision,
            "--evidence",
            str(evidence),
            "--pass-criterion",
            "package_validation",
            "--generator",
            sys.executable,
            "-c",
            _generator(leak),
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
