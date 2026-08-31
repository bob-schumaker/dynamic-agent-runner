#!/usr/bin/env python3
"""Run the controlled model-interface matrix against one explicitly selected live target.

This is intentionally a manual acceptance runner.  It never runs under normal
pytest: the operator must set ``DAR_RUN_LIVE_MODEL_INTERFACE_MATRIX=1`` and
select a target and model explicitly.  Its tools are the shared in-memory
controlled tools, so a run performs no external mutation.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import inspect
import json
import os
import re
import sys
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

from dynamic_agent_runner.apple_foundation_models import (
    AppleFoundationModelConfig,
    create_apple_foundation_model_async_adapter,
)
from dynamic_agent_runner.errors import ModelExecutionError, WorkflowExecutionError
from dynamic_agent_runner.executor import execute_workflow, execute_workflow_async
from dynamic_agent_runner.litellm_client import (
    create_async_litellm_codex_adapter_from_codex_auth,
    create_litellm_codex_adapter_from_codex_auth,
)
from dynamic_agent_runner.local_models import (
    LlamaCppLocalModelConfig,
    LocalOpenAIEndpointConfig,
    create_llama_cpp_local_adapter,
    create_llama_cpp_local_async_adapter,
    create_local_async_openai_adapter,
    create_local_openai_adapter,
)
from dynamic_agent_runner.mlx_models import MLXLocalModelConfig

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))

from model_interface_matrix import (  # noqa: E402 - repository test corpus import.
    ControlledToolScenario,
    controlled_tool_definitions,
    controlled_tool_registry,
    controlled_tool_scenarios,
    controlled_tool_workflow,
)
from dynamic_agent_runner.openai_client import (
    OpenAIProviderConfig,
    create_async_openai_adapter_from_provider_config,
    create_openai_adapter_from_provider_config,
)
from dynamic_agent_runner.qwen3_mlx_tools import (
    PINNED_QWEN3_MLX_MODEL_ID,
    create_qwen3_mlx_local_adapter,
    create_qwen3_mlx_local_async_adapter,
)


LIVE_ENV = "DAR_RUN_LIVE_MODEL_INTERFACE_MATRIX"
_LIVE_SCENARIOS = ("S1", "S2", "S3", "S4", "S5")
_TARGETS = (
    "apple",
    "codex",
    "endpoint",
    "llama_cpp",
    "litellm",
    "mlx_qwen3",
    "openai",
)
_TARGET_MODES = dict.fromkeys(_TARGETS, ("sync", "async"))
_TARGET_MODES["apple"] = ("async",)
_AUTHORIZATION_REFERENCE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_SOURCE_REVISION = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_SECRET_KEY_MARKERS = (
    "authorization",
    "api_key",
    "token",
    "secret",
    "password",
    "cookie",
)
_ROW_STATUSES = (
    "passed",
    "behavioral_mismatch",
    "adapter_error",
    "unavailable",
    "skipped",
)


class LiveMatrixError(RuntimeError):
    """Raised when an operator's live-matrix request is incomplete or fails."""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=_TARGETS, required=True)
    parser.add_argument("--model")
    parser.add_argument("--mode", choices=("sync", "async", "both"), default="both")
    parser.add_argument("--scenario", action="append", dest="scenarios")
    parser.add_argument("--base-url")
    parser.add_argument("--model-path")
    parser.add_argument("--expected-model-id")
    parser.add_argument("--authorization-reference")
    parser.add_argument("--max-tokens", type=int, default=256)
    return parser


def _require_live_opt_in() -> None:
    if os.environ.get(LIVE_ENV) != "1":
        raise LiveMatrixError(f"set {LIVE_ENV}=1 to authorize a live matrix run")


def _selected_scenarios(
    identifiers: Sequence[str] | None,
) -> tuple[ControlledToolScenario, ...]:
    all_scenarios = controlled_tool_scenarios()
    if identifiers is None:
        return tuple(
            scenario for scenario in all_scenarios if scenario.id in _LIVE_SCENARIOS
        )
    if not identifiers or len(set(identifiers)) != len(identifiers):
        raise LiveMatrixError("live matrix scenarios must be non-empty and unique")
    by_id = {scenario.id: scenario for scenario in all_scenarios}
    try:
        selected = tuple(by_id[identifier] for identifier in identifiers)
    except KeyError as error:
        raise LiveMatrixError(f"unknown matrix scenario {error.args[0]!r}") from error
    if any(scenario.id not in _LIVE_SCENARIOS for scenario in selected):
        raise LiveMatrixError("live matrix accepts only S1, S2, S3, S4, and S5")
    return selected


def _require_model(arguments: argparse.Namespace) -> str:
    if not arguments.model:
        raise LiveMatrixError(f"--model is required for {arguments.target}")
    return str(arguments.model)


def _target_model(arguments: argparse.Namespace) -> str:
    if arguments.target == "apple":
        return "apple-system-language-model"
    return _require_model(arguments)


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _safe_value(value: object, *, depth: int = 0) -> object:
    """Return a bounded structural projection without raw free-form strings."""

    if depth >= 6:
        return {"type": type(value).__name__, "truncated": True}
    if isinstance(value, Mapping):
        return {
            str(key): "redacted"
            if any(marker in str(key).lower() for marker in _SECRET_KEY_MARKERS)
            else _safe_value(item, depth=depth + 1)
            for key, item in tuple(value.items())[:24]
        }
    if isinstance(value, (list, tuple)):
        return [_safe_value(item, depth=depth + 1) for item in value[:24]]
    if isinstance(value, str):
        return {"type": "string", "length": len(value), "digest": _digest(value)}
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(getattr(value, "name", None), str) and hasattr(value, "arguments"):
        return {
            "name": value.name,
            "arguments": _safe_value(value.arguments, depth=depth + 1),
        }
    return {"type": type(value).__name__}


def _safe_base_url(value: object) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    parsed = urlsplit(value)
    try:
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            return None
        return f"{parsed.scheme}://{parsed.hostname}{f':{parsed.port}' if parsed.port else ''}"
    except ValueError:
        return None


def _preflight(arguments: argparse.Namespace) -> str | None:
    """Validate local, non-secret inputs before adapter or executor activity."""

    try:
        _target_model(arguments)
    except LiveMatrixError:
        return "missing_model"
    authorization_reference = str(
        getattr(arguments, "authorization_reference", "") or ""
    )
    if not _AUTHORIZATION_REFERENCE.fullmatch(authorization_reference) or any(
        marker in authorization_reference.lower() for marker in _SECRET_KEY_MARKERS
    ):
        return "invalid_authorization_reference"
    if arguments.target == "endpoint" and not _safe_base_url(arguments.base_url):
        return "invalid_base_url"
    if arguments.target in {"llama_cpp", "mlx_qwen3"}:
        path_value = getattr(arguments, "model_path", None)
        if (
            not path_value
            or not Path(path_value).exists()
            or not os.access(path_value, os.R_OK)
        ):
            return "unavailable_model_path"
    return None


def _configuration(arguments: argparse.Namespace) -> dict[str, object]:
    model = (
        "apple-system-language-model"
        if arguments.target == "apple"
        else getattr(arguments, "model", None)
    )
    configuration: dict[str, object] = {"model": model or "unavailable"}
    if arguments.target == "endpoint":
        configuration["base_url_origin"] = (
            _safe_base_url(arguments.base_url) or "unavailable"
        )
    if arguments.target in {"llama_cpp", "mlx_qwen3"} and arguments.model_path:
        configuration["model_path"] = {
            "basename": Path(arguments.model_path).name,
            "digest": _digest(str(arguments.model_path)),
        }
    configuration["max_tokens"] = getattr(arguments, "max_tokens", 256)
    return configuration


def _generation_settings(arguments: argparse.Namespace) -> dict[str, object]:
    """Return only the generation controls supported by the selected target."""

    if arguments.target in {"endpoint", "llama_cpp", "mlx_qwen3"}:
        return {"max_tokens": getattr(arguments, "max_tokens", 256)}
    return {}


def _uses_tool_choice_policy(arguments: argparse.Namespace) -> bool:
    """Return whether the target supports DAR's explicit tool-choice policy."""

    return arguments.target not in {"apple", "mlx_qwen3"}


def _source_revision() -> str:
    value = os.environ.get("DAR_LIVE_MATRIX_SOURCE_REVISION")
    return value if value and _SOURCE_REVISION.fullmatch(value) else "unavailable"


def _row_base(
    arguments: argparse.Namespace, *, mode: str, scenario: ControlledToolScenario
) -> dict[str, object]:
    return {
        "mode": mode,
        "scenario": scenario.id,
        "model_identifier": _configuration(arguments)["model"],
        "artifact_identity": _configuration(arguments).get(
            "model_path", "not_applicable"
        ),
        "adapter_backend_parser": "unavailable",
        "generation_settings": _generation_settings(arguments),
        "actual_rendered_tools_digest": "unavailable",
        "tool_choice": "unavailable",
        "normalized_calls": [],
        "invocations": [],
        "completion_class": "unavailable",
        "diagnostic_references": [],
    }


class _RecordingAdapter:
    """Delegate unchanged while recording DAR's normalized adapter boundary."""

    def __init__(
        self,
        delegate: object,
        observations: list[dict[str, object]],
        facts: list[dict[str, object]],
    ) -> None:
        self._delegate = delegate
        self._observations = observations
        self._facts = facts

    @property
    def models(self) -> object:
        return self._delegate.models  # type: ignore[attr-defined]

    def create_response(self, request: object) -> object:
        observation: dict[str, object] = {
            "tools": _safe_value(getattr(request, "tools", ())),
            "tool_choice": _safe_value(getattr(request, "tool_choice", None)),
            "messages": _safe_value(getattr(request, "messages", ())),
        }
        fact = {
            "tools": tuple(getattr(request, "tools", ())),
            "tool_choice": getattr(request, "tool_choice", None),
            "messages": tuple(getattr(request, "messages", ())),
            "calls": [],
        }
        self._observations.append(observation)
        self._facts.append(fact)
        response = self._delegate.create_response(request)  # type: ignore[attr-defined]
        if inspect.isawaitable(response):

            async def record_response() -> object:
                completed = await response
                observation["normalized_calls"] = _safe_value(
                    getattr(completed, "tool_calls", ())
                )
                fact["calls"] = tuple(getattr(completed, "tool_calls", ()))
                return completed

            return record_response()
        observation["normalized_calls"] = _safe_value(
            getattr(response, "tool_calls", ())
        )
        fact["calls"] = tuple(getattr(response, "tool_calls", ()))
        return response


def _tool_names(tools: Sequence[object]) -> set[str]:
    names: set[str] = set()
    for tool in tools:
        if not isinstance(tool, Mapping):
            continue
        if isinstance(tool.get("name"), str):
            names.add(str(tool["name"]))
        function = tool.get("function")
        if isinstance(function, Mapping) and isinstance(function.get("name"), str):
            names.add(str(function["name"]))
    return names


def _tool_schemas(tools: Sequence[object]) -> dict[str, object]:
    schemas: dict[str, object] = {}
    for tool in tools:
        if not isinstance(tool, Mapping):
            continue
        function = tool.get("function")
        container = function if isinstance(function, Mapping) else tool
        name = container.get("name")
        schema = container.get("parameters", container.get("input_schema"))
        if isinstance(name, str) and isinstance(schema, Mapping):
            schemas[name] = dict(schema)
    return schemas


def _normalized_calls_outcome(
    scenario: ControlledToolScenario, facts: Sequence[Mapping[str, object]]
) -> str:
    expected_calls = tuple(
        (name, dict(arguments)) for name, arguments in scenario.expected_calls
    )
    all_calls = tuple(
        call
        for fact in facts
        for call in fact["calls"]  # type: ignore[union-attr]
    )
    if any(not isinstance(getattr(call, "name", None), str) for call in all_calls):
        return "malformed"
    observed_calls: list[tuple[str, dict[str, object]]] = []
    for call in all_calls:
        arguments = call.arguments
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                return "malformed"
        if not isinstance(arguments, Mapping):
            return "malformed"
        observed_calls.append((call.name, dict(arguments)))
    return "matches" if tuple(observed_calls) == expected_calls else "mismatch"


def _adapter_contract_matches(
    scenario: ControlledToolScenario,
    facts: Sequence[Mapping[str, object]],
    *,
    includes_tool_choice_policy: bool,
) -> bool:
    """Check provider-neutral request facts at DAR's adapter boundary."""

    if not facts:
        return True  # Focused executor fakes do not cross the adapter boundary.
    controlled_ids = {
        "lookup_record",
        "create_record",
        "transform_record",
        "fail_controlled",
    }
    if _tool_names(facts[0]["tools"]) != controlled_ids:  # type: ignore[arg-type]
        return False
    expected_schemas = {
        str(tool["id"]): dict(tool["input_schema"])
        for tool in controlled_tool_definitions()
    }
    if _tool_schemas(facts[0]["tools"]) != expected_schemas:  # type: ignore[arg-type]
        return False
    if (
        scenario.id != "S5"
        and includes_tool_choice_policy
        and facts[0]["tool_choice"] != "required"
    ):
        return False
    if scenario.id == "S3" and len(facts) >= 2:
        if not any(
            isinstance(message, Mapping) and message.get("role") == "tool"
            for message in facts[1]["messages"]  # type: ignore[union-attr]
        ):
            return False
        expected_after_tool_choice = scenario.after_tool_result_tool_choice
        if includes_tool_choice_policy and (
            facts[1]["tool_choice"] != expected_after_tool_choice
            if expected_after_tool_choice != "auto"
            else facts[1]["tool_choice"] not in {None, "auto"}
        ):
            return False
    return True


def _adapter(arguments: argparse.Namespace, *, asynchronous: bool) -> object:
    model = _target_model(arguments)
    if arguments.target == "apple":
        return create_apple_foundation_model_async_adapter(
            AppleFoundationModelConfig(model_aliases=(model,))
        )
    if arguments.target == "endpoint":
        if not arguments.base_url:
            raise LiveMatrixError("--base-url is required for endpoint")
        config = LocalOpenAIEndpointConfig(
            base_url=arguments.base_url,
            model_aliases=(model,),
            api_key=None,
            expected_model_id=arguments.expected_model_id,
        )
        return (
            create_local_async_openai_adapter(config)
            if asynchronous
            else create_local_openai_adapter(config)
        )
    if arguments.target == "llama_cpp":
        if not arguments.model_path:
            raise LiveMatrixError("--model-path is required for llama_cpp")
        config = LlamaCppLocalModelConfig(
            model_aliases=(model,),
            model_path=Path(arguments.model_path),
            expected_model_id=arguments.expected_model_id,
            model_kwargs={"chat_format": "chatml-function-calling", "verbose": False},
        )
        return (
            create_llama_cpp_local_async_adapter(config)
            if asynchronous
            else create_llama_cpp_local_adapter(config)
        )
    if arguments.target == "mlx_qwen3":
        if not arguments.model_path:
            raise LiveMatrixError("--model-path is required for mlx_qwen3")
        from mlx_lm import load

        loaded_model, tokenizer = load(arguments.model_path)
        config = MLXLocalModelConfig(
            model_aliases=(model,),
            model_path=arguments.model_path,
            expected_model_id=PINNED_QWEN3_MLX_MODEL_ID,
        )
        factory = (
            create_qwen3_mlx_local_async_adapter
            if asynchronous
            else create_qwen3_mlx_local_adapter
        )
        return factory(config, model=loaded_model, tokenizer=tokenizer)
    config = OpenAIProviderConfig(
        base_url=arguments.base_url,
        api_key=None,
        codex_auth_preference=(
            "chatgpt_first"
            if arguments.target in {"codex", "litellm"}
            else "api_key_first"
        ),
    )
    if arguments.target == "litellm":

        def model_list(**_kwargs: object) -> dict[str, list[dict[str, str]]]:
            return {"data": [{"id": model}]}

        return (
            create_async_litellm_codex_adapter_from_codex_auth(
                model=model,
                models=(model,),
                config=config,
                model_list=model_list,
            )
            if asynchronous
            else create_litellm_codex_adapter_from_codex_auth(
                model=model,
                models=(model,),
                config=config,
                model_list=model_list,
            )
        )
    return (
        create_async_openai_adapter_from_provider_config(config, models=(model,))
        if asynchronous
        else create_openai_adapter_from_provider_config(config, models=(model,))
    )


def _run_scenario(
    arguments: argparse.Namespace,
    scenario: ControlledToolScenario,
    *,
    asynchronous: bool,
) -> dict[str, object]:
    observations: list[dict[str, object]] = []
    facts: list[dict[str, object]] = []
    registry, invocations, _results = controlled_tool_registry()
    workflow = controlled_tool_workflow(
        scenario,
        model=_target_model(arguments),
        include_tool_choice_policy=_uses_tool_choice_policy(arguments),
        model_parameters=_generation_settings(arguments) or None,
    )
    error: Exception | None = None
    result: object | None = None
    try:
        adapter = _RecordingAdapter(
            _adapter(arguments, asynchronous=asynchronous), observations, facts
        )
        if asynchronous:
            result = asyncio.run(
                execute_workflow_async(
                    workflow,
                    prompt=scenario.prompt,
                    tool_registry=registry,
                    model_adapter=adapter,
                    model_adapter_coverage="strict",
                )
            )
        else:
            result = execute_workflow(
                workflow,
                prompt=scenario.prompt,
                tool_registry=registry,
                model_adapter=adapter,
                model_adapter_coverage="strict",
            )
    except (ModelExecutionError, WorkflowExecutionError) as exc:
        error = exc
    except (KeyboardInterrupt, SystemExit):
        raise
    except Exception as exc:  # noqa: BLE001 - live target errors vary.
        error = exc
    observed_calls = tuple(
        (tool_id, dict(arguments)) for tool_id, arguments in invocations
    )
    expected_calls = tuple(
        (tool_id, dict(arguments)) for tool_id, arguments in scenario.expected_calls
    )
    expected_failure = scenario.id == "S4"
    final_result = getattr(result, "final_result", result)
    normal_text = isinstance(final_result, str) and bool(final_result.strip())
    controlled_failure = (
        isinstance(error, WorkflowExecutionError)
        and len(_results) == 1
        and _results[0][0] == "fail_controlled"
        and getattr(_results[0][1], "success", None) is False
        and getattr(_results[0][1], "error", None) == "planned controlled failure"
    )
    contract_matches = _adapter_contract_matches(
        scenario,
        facts,
        includes_tool_choice_policy=_uses_tool_choice_policy(arguments),
    )
    normalized_calls_outcome = _normalized_calls_outcome(scenario, facts)
    completed = error is None and normal_text
    missing_required_tool_call = isinstance(
        error, WorkflowExecutionError
    ) and "completed without a required tool call" in str(error)
    passed = (
        controlled_failure
        and observed_calls == expected_calls
        and len(facts) == 1
        and contract_matches
        and normalized_calls_outcome == "matches"
        if expected_failure
        else (
            completed
            and observed_calls == expected_calls
            and contract_matches
            and normalized_calls_outcome == "matches"
        )
    )
    adapter_error = not contract_matches or normalized_calls_outcome == "malformed"
    status = (
        "passed"
        if passed
        else (
            "adapter_error"
            if adapter_error or (error and not missing_required_tool_call)
            else "behavioral_mismatch"
        )
    )
    row = _row_base(
        arguments,
        mode="async" if asynchronous else "sync",
        scenario=scenario,
    )
    row.update(
        {
            "status": status,
            "reason": "completed"
            if passed
            else (
                "required_tool_call_missing"
                if missing_required_tool_call
                else "operational_error"
                if error
                else "positive_invariant_failed"
            ),
            "failure_locus": "not_applicable"
            if passed
            else (
                "adapter_interface"
                if adapter_error
                else "model_behavior"
                if missing_required_tool_call
                else "indeterminate"
                if error
                else "model_behavior"
            ),
            "stage": "completion_assessment" if not error else "executor_tool_loop",
            "normalized_calls": observations,
            "invocations": _safe_value(observed_calls),
            "completion_class": "controlled_tool_failure"
            if expected_failure and passed
            else "normal_text"
            if passed
            else "unavailable",
            "actual_rendered_tools_digest": _digest(
                [observation["tools"] for observation in observations]
            )
            if observations
            else "unavailable",
            "tool_choice": observations[0]["tool_choice"]
            if observations
            else "unavailable",
            "prompt_digest": _digest(scenario.prompt),
        }
    )
    return row


def _summary(rows: Sequence[Mapping[str, object]]) -> tuple[str, dict[str, int]]:
    counts = dict.fromkeys(_ROW_STATUSES, 0)
    for row in rows:
        counts[str(row["status"])] += 1
    eligible = len(rows) - counts["skipped"]
    if eligible == 0 or counts["unavailable"]:
        return "unavailable", counts
    if counts["adapter_error"]:
        return "adapter_error", counts
    if counts["behavioral_mismatch"]:
        return "behavioral_mismatch", counts
    return "passed", counts


def run_live_matrix(arguments: argparse.Namespace) -> dict[str, object]:
    """Run selected scenarios and return a receipt without secrets or prompts."""

    _require_live_opt_in()
    scenarios = _selected_scenarios(arguments.scenarios)
    selected_modes = (
        ("sync", "async") if arguments.mode == "both" else (arguments.mode,)
    )
    rows: list[dict[str, object]] = []
    preflight_reason = _preflight(arguments)
    for mode in selected_modes:
        if mode not in _TARGET_MODES[arguments.target]:
            rows.extend(
                _row_base(arguments, mode=mode, scenario=scenario)
                | {
                    "status": "skipped",
                    "reason": "unsupported_mode",
                    "failure_locus": "not_applicable",
                    "stage": "preflight",
                }
                for scenario in scenarios
            )
        elif preflight_reason:
            rows.extend(
                _row_base(arguments, mode=mode, scenario=scenario)
                | {
                    "status": "unavailable",
                    "reason": preflight_reason,
                    "failure_locus": "indeterminate",
                    "stage": "preflight",
                }
                for scenario in scenarios
            )
        else:
            rows.extend(
                _run_scenario(arguments, scenario, asynchronous=mode == "async")
                for scenario in scenarios
            )
    status, counts = _summary(rows)
    authorization = getattr(arguments, "authorization_reference", None)
    return {
        "format_version": 2,
        "run_id": uuid4().hex,
        "timestamp": datetime.now(UTC).isoformat(),
        "rows": rows,
        "status": status,
        "target": arguments.target,
        "configuration": _configuration(arguments),
        "source_revision": _source_revision(),
        "status_counts": counts,
        "manual_authorization": {
            "reference_digest": _digest(authorization),
            "scope_digest": _digest(
                {
                    "target": arguments.target,
                    "configuration": _configuration(arguments),
                    "modes": selected_modes,
                    "scenarios": [scenario.id for scenario in scenarios],
                    "lifecycle": "operator_managed",
                }
            ),
        }
        if authorization
        else "not_applicable",
    }


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        print(
            json.dumps(
                run_live_matrix(arguments), sort_keys=True, separators=(",", ":")
            )
        )
    except LiveMatrixError as error:
        print(
            json.dumps(
                {"format_version": 1, "reason": str(error), "status": "failed"},
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
