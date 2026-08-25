"""Tests for the non-mutating DAR package CLI discovery command."""

from __future__ import annotations

import json
from io import StringIO
from pathlib import Path
import tomllib

import pytest

from dynamic_agent_runner import dar_package_cli


def test_project_declares_the_console_entry_point() -> None:
    project = tomllib.loads(
        (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text(
            encoding="utf-8"
        )
    )

    assert project["project"]["scripts"]["dar-package"] == (
        "dynamic_agent_runner.dar_package_cli:console_main"
    )


def test_console_entry_point_emits_the_discovery_receipt(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        dar_package_cli.sys, "argv", ["dar-package", "version", "--json"]
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(dar_package_cli, "_distribution_version", lambda: "0.1.16")

    with pytest.raises(SystemExit) as raised:
        dar_package_cli.console_main()

    captured = capsys.readouterr()
    assert raised.value.code == 0
    assert json.loads(captured.out) == {
        "distribution": "dynamic-agent-runner",
        "format_version": 1,
        "status": "ok",
        "version": "0.1.16",
    }
    assert captured.err == ""
    assert str(tmp_path) not in captured.out
    assert str(tmp_path) not in captured.err


def test_version_json_emits_the_exact_discovery_receipt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stdout = StringIO()
    stderr = StringIO()
    monkeypatch.setattr(dar_package_cli, "_distribution_version", lambda: "0.1.16")

    assert (
        dar_package_cli.main(["version", "--json"], stdout=stdout, stderr=stderr) == 0
    )
    assert json.loads(stdout.getvalue()) == {
        "distribution": "dynamic-agent-runner",
        "format_version": 1,
        "status": "ok",
        "version": "0.1.16",
    }
    assert stderr.getvalue() == ""


@pytest.mark.parametrize(
    "argv",
    [[], ["version"], ["version", "--text"], ["unknown", "--json"]],
)
def test_version_json_rejects_invalid_usage(argv: list[str]) -> None:
    stdout = StringIO()
    stderr = StringIO()

    assert dar_package_cli.main(argv, stdout=stdout, stderr=stderr) == 2
    assert stdout.getvalue() == ""
    assert json.loads(stderr.getvalue()) == {
        "error_code": "usage",
        "format_version": 1,
        "status": "error",
    }


def test_version_json_redacts_an_internal_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stdout = StringIO()
    stderr = StringIO()

    def fail() -> str:
        raise RuntimeError("/private/state must not escape")

    monkeypatch.setattr(dar_package_cli, "_distribution_version", fail)

    assert (
        dar_package_cli.main(["version", "--json"], stdout=stdout, stderr=stderr) == 1
    )
    assert stdout.getvalue() == ""
    assert json.loads(stderr.getvalue()) == {
        "error_code": "internal",
        "format_version": 1,
        "status": "error",
    }
    assert "/private/state" not in stderr.getvalue()
