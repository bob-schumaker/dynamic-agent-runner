"""PyInstaller integration for dynamic-agent-runner."""

from __future__ import annotations

from pathlib import Path


def get_hook_dirs() -> list[str]:
    """Return package-owned PyInstaller hook directories."""

    return [str(Path(__file__).with_name("_pyinstaller_hooks"))]
