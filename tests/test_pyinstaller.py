"""Tests for PyInstaller package integration."""

from pathlib import Path

from dynamic_agent_runner.__pyinstaller import get_hook_dirs


def test_pyinstaller_hook_dirs_advertise_openai_model_registry_hook() -> None:
    hook_dirs = [Path(path) for path in get_hook_dirs()]

    assert len(hook_dirs) == 1
    assert hook_dirs[0].is_dir()
    assert (hook_dirs[0] / "hook-openai-model-registry.py").is_file()
