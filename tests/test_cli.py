"""Tests for the dynamic-agent-runner CLI."""

from __future__ import annotations

from io import StringIO
from pathlib import Path

from dynamic_agent_runner.cli import main
from dynamic_agent_runner.openai_client import OpenAIClientAdapter


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "agent-patterns"


class FakeResponses:
    def __init__(self, responses: list[object]):
        self.responses = list(responses)
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        return self.responses.pop(0)


class FakeClient:
    def __init__(self, responses: list[object]):
        self.responses = FakeResponses(responses)


def make_adapter(responses: list[object]) -> OpenAIClientAdapter:
    return OpenAIClientAdapter(FakeClient(responses))


def basic_reasoning_fixture() -> Path:
    return FIXTURE_ROOT / "basic-reasoning-agent"


def test_cli_runs_workflow_from_artifact_paths_and_prompt() -> None:
    fixture = basic_reasoning_fixture()
    stdout = StringIO()
    stderr = StringIO()
    adapter = make_adapter([{"id": "resp", "output_text": "hello from cli"}])

    exit_code = main(
        [
            "--runtime-manifest",
            str(fixture / "agent-runtime.yaml"),
            "--agent-design",
            str(fixture / "agent-design.md"),
            "--prompt",
            "Say hello.",
            "--workspace-root",
            str(fixture),
        ],
        model_adapter=adapter,
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 0
    assert stdout.getvalue() == "hello from cli\n"
    assert stderr.getvalue() == ""
    assert adapter.client.responses.calls[0]["model"] == "gpt-test"


def test_cli_reads_prompt_from_file(tmp_path: Path) -> None:
    fixture = basic_reasoning_fixture()
    stdout = StringIO()
    prompt_file = tmp_path / "prompt.txt"
    adapter = make_adapter([{"id": "resp", "output_text": "file prompt result"}])

    prompt_file.write_text("Prompt from file", encoding="utf-8")
    exit_code = main(
        [
            "--runtime-manifest",
            str(fixture / "agent-runtime.yaml"),
            "--prompt-file",
            str(prompt_file),
        ],
        model_adapter=adapter,
        stdout=stdout,
    )

    assert exit_code == 0
    assert stdout.getvalue() == "file prompt result\n"


def test_cli_reads_prompt_from_stdin() -> None:
    fixture = basic_reasoning_fixture()
    stdout = StringIO()
    adapter = make_adapter([{"id": "resp", "output_text": "stdin result"}])

    exit_code = main(
        ["--runtime-manifest", str(fixture / "agent-runtime.yaml")],
        model_adapter=adapter,
        stdin=StringIO("Prompt from stdin"),
        stdout=stdout,
    )

    assert exit_code == 0
    assert stdout.getvalue() == "stdin result\n"


def test_cli_returns_error_for_missing_prompt() -> None:
    fixture = basic_reasoning_fixture()
    stderr = StringIO()

    exit_code = main(
        ["--runtime-manifest", str(fixture / "agent-runtime.yaml")],
        model_adapter=make_adapter([]),
        stdin=StringIO(""),
        stderr=stderr,
    )

    assert exit_code == 1
    assert "workflow prompt is required" in stderr.getvalue()


def test_cli_returns_error_for_execution_failure() -> None:
    fixture = basic_reasoning_fixture()
    stderr = StringIO()

    exit_code = main(
        [
            "--runtime-manifest",
            str(fixture / "agent-runtime.yaml"),
            "--prompt",
            "Hello",
        ],
        model_adapter=make_adapter([]),
        stderr=stderr,
    )

    assert exit_code == 1
    assert "OpenAI model request failed" in stderr.getvalue()
