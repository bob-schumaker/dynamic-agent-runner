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
    """Return text unless the request declares one no-argument tool."""

    try:
        request = json.loads(request_body)
    except (TypeError, json.JSONDecodeError):
        request = {}
    tool_name = (
        None
        if _has_tool_result(request)
        else _zero_argument_tool_name(request.get("tools"))
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
    if tool_name is not None:
        response["choices"] = [
            {
                "message": {
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "m44-tool-call",
                            "type": "function",
                            "function": {"name": tool_name, "arguments": "{}"},
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
                "arguments": "{}",
            }
        ]
    return response


def _zero_argument_tool_name(value: object) -> str | None:
    if not isinstance(value, list):
        return None
    for tool in value:
        if not isinstance(tool, dict):
            continue
        function = tool.get("function")
        candidate = function if isinstance(function, dict) else tool
        name, parameters = candidate.get("name"), candidate.get("parameters")
        if (
            isinstance(name, str)
            and isinstance(parameters, dict)
            and parameters.get("required", []) == []
        ):
            return name
    return None


def _has_tool_result(value: object) -> bool:
    if isinstance(value, dict):
        if value.get("type") == "function_call_output":
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
    content = response["output"][0]["content"][0]["text"]
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
