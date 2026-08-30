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
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from dynamic_agent_runner.apple_foundation_models import (
    AppleFoundationModelConfig,
    create_apple_foundation_model_async_adapter,
)
from dynamic_agent_runner.errors import ModelExecutionError, WorkflowExecutionError
from dynamic_agent_runner.executor import execute_workflow, execute_workflow_async
from dynamic_agent_runner.litellm_client import (
    create_async_litellm_adapter,
    create_litellm_adapter,
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
_TARGETS = (
    "apple",
    "codex",
    "endpoint",
    "llama_cpp",
    "litellm",
    "mlx_qwen3",
    "openai",
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
    parser.add_argument("--api-key")
    parser.add_argument("--model-path")
    parser.add_argument("--expected-model-id")
    return parser


def _require_live_opt_in() -> None:
    if os.environ.get(LIVE_ENV) != "1":
        raise LiveMatrixError(f"set {LIVE_ENV}=1 to authorize a live matrix run")


def _selected_scenarios(
    identifiers: Sequence[str] | None,
) -> tuple[ControlledToolScenario, ...]:
    all_scenarios = controlled_tool_scenarios()
    if not identifiers:
        return all_scenarios
    by_id = {scenario.id: scenario for scenario in all_scenarios}
    try:
        return tuple(by_id[identifier] for identifier in identifiers)
    except KeyError as error:
        raise LiveMatrixError(f"unknown matrix scenario {error.args[0]!r}") from error


def _require_model(arguments: argparse.Namespace) -> str:
    if not arguments.model:
        raise LiveMatrixError(f"--model is required for {arguments.target}")
    return str(arguments.model)


def _target_model(arguments: argparse.Namespace) -> str:
    if arguments.target == "apple":
        return "apple-system-language-model"
    return _require_model(arguments)


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
            api_key=arguments.api_key,
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
        api_key=arguments.api_key,
        codex_auth_preference=(
            "chatgpt_first" if arguments.target == "codex" else "api_key_first"
        ),
    )
    if arguments.target == "litellm":
        return (
            create_async_litellm_adapter(model=model, config=config)
            if asynchronous
            else create_litellm_adapter(model=model, config=config)
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
    adapter = _adapter(arguments, asynchronous=asynchronous)
    registry, invocations, _results = controlled_tool_registry()
    workflow = controlled_tool_workflow(
        scenario,
        model=_target_model(arguments),
        include_tool_choice_policy=arguments.target != "mlx_qwen3",
    )
    error: Exception | None = None
    try:
        if asynchronous:
            asyncio.run(
                execute_workflow_async(
                    workflow,
                    prompt=scenario.prompt,
                    tool_registry=registry,
                    model_adapter=adapter,
                    model_adapter_coverage="strict",
                )
            )
        else:
            execute_workflow(
                workflow,
                prompt=scenario.prompt,
                tool_registry=registry,
                model_adapter=adapter,
                model_adapter_coverage="strict",
            )
    except (ModelExecutionError, WorkflowExecutionError) as exc:
        error = exc
    observed_calls = tuple(
        (tool_id, dict(arguments)) for tool_id, arguments in invocations
    )
    expected_calls = tuple(
        (tool_id, dict(arguments)) for tool_id, arguments in scenario.expected_calls
    )
    if scenario.expected_error is None:
        if error is not None or observed_calls != expected_calls:
            raise LiveMatrixError(
                f"{scenario.id} did not produce the expected successful tool path"
            )
    elif error is None or observed_calls:
        raise LiveMatrixError(
            f"{scenario.id} did not produce the expected {scenario.expected_error}"
        )
    return {
        "mode": "async" if asynchronous else "sync",
        "scenario": scenario.id,
        "status": "passed",
    }


def run_live_matrix(arguments: argparse.Namespace) -> dict[str, object]:
    """Run selected scenarios and return a receipt without secrets or prompts."""

    _require_live_opt_in()
    modes = (False, True) if arguments.mode == "both" else (arguments.mode == "async",)
    rows = [
        _run_scenario(arguments, scenario, asynchronous=asynchronous)
        for asynchronous in modes
        for scenario in _selected_scenarios(arguments.scenarios)
    ]
    return {
        "format_version": 1,
        "rows": rows,
        "status": "passed",
        "target": arguments.target,
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
