"""Tests for the deterministic external M4.4 model fixture."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE = REPO_ROOT / "scripts" / "serve_m4_4_fake_model.py"


def _fixture_module() -> object:
    spec = importlib.util.spec_from_file_location("m44_fake_model", FIXTURE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_fake_model_returns_text_without_a_declared_tool() -> None:
    module = _fixture_module()

    response = module._fake_response(json.dumps({"model": "local"}).encode())

    assert response["choices"][0]["message"]["content"] == "summary"


def test_fake_model_calls_the_first_declared_zero_argument_tool() -> None:
    module = _fixture_module()

    response = module._fake_response(
        json.dumps(
            {
                "tools": [
                    {
                        "type": "function",
                        "function": {
                            "name": "list_unread",
                            "parameters": {
                                "type": "object",
                                "properties": {},
                                "required": [],
                            },
                        },
                    }
                ]
            }
        ).encode()
    )

    assert response["choices"][0]["message"]["tool_calls"][0]["function"] == {
        "name": "list_unread",
        "arguments": "{}",
    }
    assert response["output"][0]["type"] == "function_call"


def test_fake_model_selects_only_a_declared_m44_fixture_tool() -> None:
    module = _fixture_module()

    response = module._fake_response(
        json.dumps(
            {
                "tools": [
                    {
                        "type": "function",
                        "function": {
                            "name": "erase_everything",
                            "parameters": {
                                "type": "object",
                                "properties": {},
                                "required": [],
                            },
                        },
                    },
                    {
                        "type": "function",
                        "function": {
                            "name": "list_unread",
                            "parameters": {
                                "type": "object",
                                "properties": {},
                                "required": [],
                            },
                        },
                    },
                ]
            }
        ).encode()
    )

    assert (
        response["choices"][0]["message"]["tool_calls"][0]["function"]["name"]
        == "list_unread"
    )


def test_fake_model_calls_declared_tool_with_deterministic_required_arguments() -> None:
    module = _fixture_module()

    response = module._fake_response(
        json.dumps(
            {
                "tools": [
                    {
                        "type": "function",
                        "function": {
                            "name": "mail_send",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "recipient": {"type": "string"},
                                    "body": {"type": "string"},
                                },
                                "required": ["recipient", "body"],
                            },
                        },
                    }
                ]
            }
        ).encode()
    )

    assert response["choices"][0]["message"]["tool_calls"][0]["function"] == {
        "name": "mail_send",
        "arguments": '{"body":"fixture body","recipient":"fixture@example.test"}',
    }


def test_fake_model_wraps_reviewed_tool_values_in_prompt_provenance() -> None:
    module = _fixture_module()
    prompt = "Send the email to fixture@example.test with body fixture body."

    response = module._fake_response(
        json.dumps(
            {
                "input": [{"role": "user", "content": prompt}],
                "tools": [
                    {
                        "type": "function",
                        "function": {
                            "name": "mail_send",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "provenance_envelope": {"type": "string"}
                                },
                                "required": ["provenance_envelope"],
                            },
                        },
                    }
                ],
            }
        ).encode()
    )

    arguments = json.loads(
        response["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"]
    )
    envelope = json.loads(arguments["provenance_envelope"])
    assert envelope["arguments"] == {
        "body": "fixture body",
        "recipient": "fixture@example.test",
    }
    for name, value in envelope["arguments"].items():
        proof = envelope["sources"][name]
        assert proof["kind"] == "prompt_span"
        assert (
            prompt.encode()[proof["start_byte"] : proof["end_byte"]].decode() == value
        )


def test_fake_model_uses_declared_email_body_artifact_provenance() -> None:
    module = _fixture_module()
    prompt = (
        "Send the email to fixture@example.test using the declared email_body artifact."
    )

    response = module._fake_response(
        json.dumps(
            {
                "input": [{"role": "user", "content": prompt}],
                "tools": [
                    {
                        "type": "function",
                        "function": {
                            "name": "mail_send",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "provenance_envelope": {"type": "string"}
                                },
                                "required": ["provenance_envelope"],
                            },
                        },
                    }
                ],
            }
        ).encode()
    )

    arguments = json.loads(
        response["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"]
    )
    envelope = json.loads(arguments["provenance_envelope"])
    assert envelope["arguments"]["body"] == "controller fixture input\n"
    assert envelope["sources"]["body"] == {"kind": "artifact", "ref": "email_body"}


def test_fake_model_uses_any_declared_artifact_role_for_body_provenance() -> None:
    module = _fixture_module()
    prompt = "Send the email to fixture@example.test using the declared vendor-ticket artifact."

    response = module._fake_response(
        json.dumps(
            {
                "input": [{"role": "user", "content": prompt}],
                "tools": [
                    {
                        "type": "function",
                        "function": {
                            "name": "mail_send",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "provenance_envelope": {"type": "string"}
                                },
                                "required": ["provenance_envelope"],
                            },
                        },
                    }
                ],
            }
        ).encode()
    )

    arguments = json.loads(
        response["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"]
    )
    envelope = json.loads(arguments["provenance_envelope"])
    assert envelope["sources"]["body"] == {"kind": "artifact", "ref": "vendor-ticket"}


def test_fake_model_streams_a_declared_tool_call() -> None:
    module = _fixture_module()
    response = module._fake_response(
        json.dumps(
            {
                "tools": [
                    {
                        "type": "function",
                        "function": {
                            "name": "list_unread",
                            "parameters": {"type": "object", "required": []},
                        },
                    }
                ]
            }
        ).encode()
    )

    events = [
        json.loads(line.removeprefix("data: "))
        for line in module._stream_response(response).decode().splitlines()
        if line.startswith("data: {")
    ]

    assert events[0]["type"] == "response.output_item.done"
    assert events[0]["item"]["type"] == "function_call"
    assert events[-1]["type"] == "response.completed"


def test_fake_model_finishes_after_a_tool_result() -> None:
    module = _fixture_module()

    response = module._fake_response(
        json.dumps(
            {
                "tools": [
                    {
                        "type": "function",
                        "name": "list_unread",
                        "parameters": {"type": "object", "required": []},
                    }
                ],
                "input": [
                    {
                        "type": "function_call_output",
                        "call_id": "m44-tool-call",
                        "output": "fixture result",
                    }
                ],
            }
        ).encode()
    )

    assert response["choices"][0]["message"]["content"] == "summary"


def test_fake_model_finishes_after_a_chat_completion_tool_result() -> None:
    module = _fixture_module()

    response = module._fake_response(
        json.dumps(
            {
                "messages": [
                    {
                        "role": "tool",
                        "tool_call_id": "m44-tool-call",
                        "content": "fixture result",
                    }
                ],
                "tools": [
                    {
                        "type": "function",
                        "function": {
                            "name": "mail_send",
                            "parameters": {"type": "object", "required": []},
                        },
                    }
                ],
            }
        ).encode()
    )

    assert response["choices"][0]["message"]["content"] == "summary"
