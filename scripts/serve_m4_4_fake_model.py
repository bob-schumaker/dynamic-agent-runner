#!/usr/bin/env python3
"""Serve deterministic OpenAI-compatible output for local M4.4 acceptance."""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class _Handler(BaseHTTPRequestHandler):
    live_model_id: str | None = None

    def do_GET(self) -> None:  # noqa: N802 - standard-library handler API.
        body = json.dumps(
            {
                "data": [
                    {
                        "id": self.live_model_id or "openai/local-model",
                        "object": "model",
                    }
                ],
                "object": "list",
            }
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:  # noqa: N802 - standard-library handler API.
        request_body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        if self.live_model_id is not None:
            response = _live_response(request_body, self.live_model_id)
        else:
            response = _fake_response(request_body)
        streamed = bool(json.loads(request_body).get("stream"))
        body = _stream_response(response) if streamed else _json_response(response)
        self.send_response(200)
        self.send_header(
            "Content-Type", "text/event-stream" if streamed else "application/json"
        )
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format: str, *_arguments: object) -> None:
        return


def _fake_response(request_body: bytes) -> dict[str, object]:
    """Return one deterministic declared-tool call, then a final response."""

    try:
        request = json.loads(request_body)
    except (TypeError, json.JSONDecodeError):
        request = {}
    tool_call = (
        None
        if _has_tool_result(request)
        else _first_declared_tool_call(request.get("tools"), request)
    )
    response: dict[str, object] = {
        "id": "m44-fake-response",
        "model": "openai/local-model",
        "object": "response",
        "output_text": "summary",
        "status": "completed",
        "choices": [{"message": {"content": "summary"}}],
        "output": [
            {
                "type": "message",
                "content": [
                    {
                        "type": "output_text",
                        "text": "summary",
                    }
                ],
            }
        ],
    }
    if tool_call is not None:
        tool_name, arguments = tool_call
        response["choices"] = [
            {
                "message": {
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "m44-tool-call",
                            "type": "function",
                            "function": {"name": tool_name, "arguments": arguments},
                        }
                    ],
                }
            }
        ]
        response["output"] = [
            {
                "type": "function_call",
                "call_id": "m44-tool-call",
                "name": tool_name,
                "arguments": arguments,
            }
        ]
    return response


def _first_declared_tool_call(
    value: object, request: dict[str, object]
) -> tuple[str, str] | None:
    if not isinstance(value, list):
        return None
    for tool in value:
        if not isinstance(tool, dict):
            continue
        function = tool.get("function")
        candidate = function if isinstance(function, dict) else tool
        name, parameters = candidate.get("name"), candidate.get("parameters")
        if not isinstance(name, str) or not isinstance(parameters, dict):
            continue
        arguments = _deterministic_arguments(parameters, request)
        if arguments is not None:
            return name, json.dumps(arguments, separators=(",", ":"), sort_keys=True)
    return None


def _deterministic_arguments(
    parameters: dict[str, object], request: dict[str, object]
) -> dict[str, object] | None:
    """Build valid fixture data solely for a declared JSON-object tool schema."""

    required = parameters.get("required", [])
    properties = parameters.get("properties", {})
    if not isinstance(required, list) or not isinstance(properties, dict):
        return None
    if required == ["provenance_envelope"]:
        envelope = _prompt_provenance_envelope(_request_text(request))
        return {"provenance_envelope": envelope} if envelope is not None else None
    arguments: dict[str, object] = {}
    for name in required:
        schema = properties.get(name)
        if not isinstance(name, str) or not isinstance(schema, dict):
            return None
        value = _fixture_value(name, schema)
        if value is None:
            return None
        arguments[name] = value
    return arguments


def _request_text(request: dict[str, object]) -> str:
    """Return the user text supplied to the deterministic fixture."""

    inputs = request.get("input", request.get("messages"))
    if not isinstance(inputs, list):
        return ""
    for item in reversed(inputs):
        if not isinstance(item, dict) or item.get("role") != "user":
            continue
        content = item.get("content")
        if isinstance(content, str):
            return content
    return ""


def _prompt_provenance_envelope(prompt: str) -> str | None:
    """Encode the fixed reviewed-email arguments as prompt-span proofs."""

    values = {"recipient": "fixture@example.test", "body": "fixture body"}
    encoded_prompt = prompt.encode("utf-8")
    sources: dict[str, dict[str, object]] = {}
    for name, value in values.items():
        if name == "body" and "declared email_body artifact" in prompt:
            values[name] = "controller fixture input\n"
            sources[name] = {"kind": "artifact", "ref": "email_body"}
            continue
        start = encoded_prompt.find(value.encode("utf-8"))
        if start < 0:
            return None
        sources[name] = {
            "kind": "prompt_span",
            "start_byte": start,
            "end_byte": start + len(value.encode("utf-8")),
            "normalization": "identity",
        }
    return json.dumps(
        {"format_version": 1, "arguments": values, "sources": sources},
        separators=(",", ":"),
        sort_keys=True,
    )


def _fixture_value(name: str, schema: dict[str, object]) -> object | None:
    """Return the smallest deterministic value supported by the fixture schema."""

    if name == "recipient" and schema.get("type") == "string":
        return "fixture@example.test"
    if name == "body" and schema.get("type") == "string":
        return "fixture body"
    if schema.get("type") == "string":
        return "fixture"
    if schema.get("type") == "integer":
        return 1
    if schema.get("type") == "number":
        return 1.0
    if schema.get("type") == "boolean":
        return True
    return None


def _has_tool_result(value: object) -> bool:
    if isinstance(value, dict):
        if value.get("type") == "function_call_output" or value.get("role") == "tool":
            return True
        return any(_has_tool_result(item) for item in value.values())
    if isinstance(value, list):
        return any(_has_tool_result(item) for item in value)
    return False


def _live_response(request_body: bytes, model_id: str) -> dict[str, object]:
    """Use DAR's native pre-authenticated Codex/ChatGPT adapter path."""

    request = json.loads(request_body)
    messages = request.get("input", request.get("messages"))
    if not isinstance(messages, list):
        raise ValueError("model request is invalid")
    from dynamic_agent_runner.openai_client import (
        OpenAIClientAdapter,
        OpenAIModelRequest,
    )

    result = OpenAIClientAdapter().create_response(
        OpenAIModelRequest(model=model_id, messages=tuple(messages))
    )
    return {
        "id": "m44-live-response",
        "model": request.get("model", model_id),
        "object": "response",
        "output": [
            {
                "type": "message",
                "content": [{"type": "output_text", "text": result.content}],
            }
        ],
    }


def _json_response(response: dict[str, object]) -> bytes:
    return json.dumps(response).encode("utf-8")


def _stream_response(response: dict[str, object]) -> bytes:
    output = response["output"]
    first = output[0]
    if first["type"] == "function_call":
        events = (
            {"type": "response.output_item.done", "item": first},
            {"type": "response.completed", "response": response},
        )
    else:
        content = first["content"][0]["text"]
        events = (
            {"type": "response.output_text.delta", "delta": content},
            {"type": "response.completed", "response": response},
        )
    return (
        b"".join(f"data: {json.dumps(event)}\n\n".encode("utf-8") for event in events)
        + b"data: [DONE]\n\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=18080)
    parser.add_argument("--live-model")
    arguments = parser.parse_args()
    _Handler.live_model_id = arguments.live_model
    ThreadingHTTPServer(("127.0.0.1", arguments.port), _Handler).serve_forever()


if __name__ == "__main__":  # pragma: no cover - test-fixture entry point.
    main()
