"""Tests for the dynamic-agent-runner CLI."""

from __future__ import annotations

from io import StringIO
from pathlib import Path

import pytest
import yaml

from dynamic_agent_runner.cli import main
from dynamic_agent_runner.models import SUPPORTED_AGENT_PATTERNS, ToolDefinition
from dynamic_agent_runner.openai_client import OpenAIClientAdapter
from dynamic_agent_runner.registry import InMemoryToolRegistry, RegisteredTool


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "agent-patterns"
EXECUTABLE_PATTERN_IDS = tuple(
    pattern_id
    for pattern_id in SUPPORTED_AGENT_PATTERNS
    if pattern_id != "multi-agent-collaboration"
)
UNSUPPORTED_PATTERN_IDS = ("multi-agent-collaboration",)


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


def make_fixture_registry(fixture: Path) -> InMemoryToolRegistry:
    manifest = yaml.safe_load((fixture / "agent-runtime.yaml").read_text())
    return InMemoryToolRegistry(
        RegisteredTool(
            ToolDefinition.from_mapping(tool),
            lambda args, tool_id=tool["id"]: {
                "message": f"hello from {tool_id}",
                "query": args.get("query"),
                "route": "proceed",
            },
        )
        for tool in manifest.get("tools", [])
    )


def basic_reasoning_fixture() -> Path:
    return FIXTURE_ROOT / "basic-reasoning-agent"


def fixture_path(pattern_id: str) -> Path:
    return FIXTURE_ROOT / pattern_id


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


def test_cli_accepts_runtime_overrides_path(tmp_path: Path) -> None:
    """The CLI passes runtime behavior overrides into workflow execution."""

    fixture = basic_reasoning_fixture()
    stdout = StringIO()
    overrides_path = tmp_path / "agent-runtime-overrides.yaml"
    overrides_path.write_text(
        "\n".join(
            [
                "format_version: 1",
                "override_type: dynamic_agent_runtime_overrides",
                "nodes:",
                "  reason_about_request:",
                "    prompt:",
                "      replace:",
                "        user_template: 'CLI override {prompt}'",
            ]
        ),
        encoding="utf-8",
    )
    adapter = make_adapter([{"id": "resp", "output_text": "override result"}])

    exit_code = main(
        [
            "--runtime-manifest",
            str(fixture / "agent-runtime.yaml"),
            "--runtime-overrides",
            str(overrides_path),
            "--prompt",
            "Hello",
        ],
        model_adapter=adapter,
        stdout=stdout,
    )

    assert exit_code == 0
    assert stdout.getvalue() == "override result\n"
    assert adapter.client.responses.calls[0]["input"][-1] == {
        "role": "user",
        "content": "CLI override Hello",
    }


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


@pytest.mark.parametrize("pattern_id", EXECUTABLE_PATTERN_IDS)
def test_cli_runs_all_currently_executable_pattern_fixtures(pattern_id: str) -> None:
    fixture = fixture_path(pattern_id)
    stdout = StringIO()
    stderr = StringIO()
    adapter = make_adapter(
        [
            {
                "id": f"{pattern_id}-response-1",
                "output_text": '{"message":"hello","route":"proceed"}',
            },
            {
                "id": f"{pattern_id}-response-2",
                "output_text": f'{{"message":"final {pattern_id}"}}',
            },
            {
                "id": f"{pattern_id}-response-3",
                "output_text": f'{{"message":"final {pattern_id}"}}',
            },
        ]
    )

    exit_code = main(
        [
            "--runtime-manifest",
            str(fixture / "agent-runtime.yaml"),
            "--agent-design",
            str(fixture / "agent-design.md"),
            "--prompt",
            f"Run hello-world fixture for {pattern_id}.",
        ],
        model_adapter=adapter,
        tool_registry=make_fixture_registry(fixture),
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 0, stderr.getvalue()
    assert stdout.getvalue().strip()
    assert stderr.getvalue() == ""


@pytest.mark.parametrize("pattern_id", UNSUPPORTED_PATTERN_IDS)
def test_cli_fails_clearly_for_unsupported_pattern_fixture_features(
    pattern_id: str,
) -> None:
    fixture = fixture_path(pattern_id)
    stdout = StringIO()
    stderr = StringIO()

    exit_code = main(
        [
            "--runtime-manifest",
            str(fixture / "agent-runtime.yaml"),
            "--agent-design",
            str(fixture / "agent-design.md"),
            "--prompt",
            f"Run hello-world fixture for {pattern_id}.",
        ],
        model_adapter=make_adapter(
            [
                {
                    "id": f"{pattern_id}-response",
                    "output_text": '{"message":"architect says hello"}',
                }
            ]
        ),
        tool_registry=make_fixture_registry(fixture),
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 1
    assert stdout.getvalue() == ""
    assert "unsupported outgoing edge kind(s): parallel_join" in stderr.getvalue()


def test_cli_fails_clearly_for_tool_fixture_without_registry() -> None:
    fixture = fixture_path("tool-based-function-calling-agent")
    stderr = StringIO()

    exit_code = main(
        [
            "--runtime-manifest",
            str(fixture / "agent-runtime.yaml"),
            "--prompt",
            "Run without a callable registry.",
        ],
        model_adapter=make_adapter([]),
        stderr=stderr,
    )

    assert exit_code == 1
    assert "exposes tools but no registry was provided" in stderr.getvalue()
