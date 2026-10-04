from __future__ import annotations

import os
import subprocess
import sys

import pytest


@pytest.mark.parametrize(
    ("module_name", "runtime_modules"),
    [
        (
            "dynamic_agent_runner.workflow_host.julia1_decision_adapter",
            ("torch", "transformers", "safetensors", "numpy"),
        ),
        (
            "dynamic_agent_runner.workflow_host.von_decision_adapter",
            ("torch", "transformers", "accelerate", "von"),
        ),
        (
            "dynamic_agent_runner.workflow_host.laya_mlx_decision_adapter",
            ("mlx", "laya_mlx"),
        ),
        (
            "dynamic_agent_runner.workflow_host.kev_decision_adapter",
            ("torch", "transformers", "peft", "kev"),
        ),
        (
            "dynamic_agent_runner.workflow_host.jevstyle_decision_adapter",
            ("torch", "transformers", "mlx", "mlx_lm", "llama_cpp"),
        ),
    ],
)
def test_importing_adapter_does_not_import_its_optional_runtime(
    module_name: str, runtime_modules: tuple[str, ...]
) -> None:
    source_root = os.path.abspath("src")
    env = dict(os.environ, PYTHONPATH=source_root)
    script = (
        "import importlib, sys; "
        f"importlib.import_module({module_name!r}); "
        f"assert not (set({runtime_modules!r}) & sys.modules.keys())"
    )

    subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
