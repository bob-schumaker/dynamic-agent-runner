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
