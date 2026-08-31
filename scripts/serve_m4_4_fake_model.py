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
            response = _fake_response()
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


def _fake_response() -> dict[str, object]:
    return {
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
