"""Clean-process launch primitives for the external M4.4 Codex harness."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
import shutil


class M44CleanCodexError(ValueError):
    """Raised when a clean Codex acceptance actor cannot be prepared."""


def build_clean_codex_environment(
    *,
    codex_home: Path,
    working_directory: Path,
    wheel: Path,
    state_root: Path,
    template_root: Path,
    inherited: Mapping[str, str],
) -> dict[str, str]:
    """Return the allowlisted environment for one clean Codex process."""

    for path, label in (
        (codex_home, "codex home"),
        (working_directory, "working directory"),
        (wheel, "wheel"),
        (state_root, "state root"),
        (template_root, "template root"),
    ):
        _absolute_not_symlink(path, label)
    return _base_environment(
        codex_home=codex_home,
        working_directory=working_directory,
        wheel=wheel,
        template_root=template_root,
        inherited=inherited,
        extra={"DAR_AUTHORING_STATE_ROOT": str(state_root)},
    )


def _base_environment(
    *,
    codex_home: Path,
    working_directory: Path,
    wheel: Path,
    template_root: Path,
    inherited: Mapping[str, str],
    extra: Mapping[str, str],
) -> dict[str, str]:
    path = inherited.get("PATH")
    if not isinstance(path, str) or not path:
        raise M44CleanCodexError("clean Codex PATH is invalid")
    return {
        "CODEX_HOME": str(codex_home),
        "DAR_AUTHORING_DAR_WHEEL": str(wheel),
        "UV_CACHE_DIR": str(working_directory / ".uv-cache"),
        "DAR_AUTHORING_TEMPLATE_ROOT": str(template_root),
        "HOME": str(working_directory),
        "LANG": "C.UTF-8",
        "PATH": path,
        **dict(extra),
    }


def create_marketplace(*, plugin_root: Path, destination: Path) -> Path:
    """Copy one plugin into an isolated marketplace and return its manifest."""

    _absolute_not_symlink(plugin_root, "plugin root")
    _absolute_not_symlink(destination, "marketplace destination")
    if (
        not plugin_root.is_dir()
        or not (plugin_root / ".codex-plugin" / "plugin.json").is_file()
    ):
        raise M44CleanCodexError("plugin root is invalid")
    if destination.exists() or destination.is_symlink():
        raise M44CleanCodexError("marketplace destination is unavailable")
    if any(path.is_symlink() for path in plugin_root.rglob("*")):
        raise M44CleanCodexError("plugin root contains a symbolic link")
    plugin_destination = destination / "plugins" / "dar-authoring"
    shutil.copytree(plugin_root, plugin_destination)
    manifest = destination / ".agents" / "plugins" / "marketplace.json"
    manifest.parent.mkdir(mode=0o700, parents=True)
    manifest.write_text(
        json.dumps(
            {
                "name": "m44-clean-codex",
                "plugins": [
                    {
                        "category": "Productivity",
                        "name": "dar-authoring",
                        "policy": {
                            "authentication": "ON_INSTALL",
                            "installation": "AVAILABLE",
                        },
                        "source": {
                            "path": "./plugins/dar-authoring",
                            "source": "local",
                        },
                    }
                ],
            },
            sort_keys=True,
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )
    return manifest


def _absolute_not_symlink(path: object, label: str) -> None:
    if not isinstance(path, Path) or not path.is_absolute() or path.is_symlink():
        raise M44CleanCodexError(f"{label} is invalid")
