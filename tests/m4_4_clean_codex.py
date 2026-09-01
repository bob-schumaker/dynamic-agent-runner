"""Clean-process launch primitives for the external M4.4 Codex harness."""

from __future__ import annotations

import json
from collections.abc import Mapping
import shlex
from pathlib import Path
import shutil


class M44CleanCodexError(ValueError):
    """Raised when a clean Codex acceptance actor cannot be prepared."""


def stage_dar_package(
    *,
    wheel: Path,
    controller_launcher: Path,
    destination: Path,
    allowed_commands: tuple[str, ...],
) -> Path:
    """Stage a command-limited actor launcher without controller state."""

    for path, label in (
        (wheel, "wheel"),
        (controller_launcher, "controller launcher"),
        (destination, "DAR launcher destination"),
    ):
        _absolute_not_symlink(path, label)
    if (
        not wheel.is_file()
        or not controller_launcher.is_file()
        or destination.exists()
        or destination.is_symlink()
        or not allowed_commands
        or set(allowed_commands) - _DAR_PACKAGE_COMMANDS
    ):
        raise M44CleanCodexError("DAR launcher inputs are invalid")
    destination.mkdir(mode=0o700)
    launcher = destination / "dar-package"
    commands = "|".join(allowed_commands)
    launcher.write_text(
        "#!/bin/sh\n"
        f'case "$1" in {commands}) ;; *) exit 2 ;; esac\n'
        f'exec {shlex.quote(str(controller_launcher))} "$@"\n',
        encoding="utf-8",
    )
    launcher.chmod(0o700)
    return destination


_DAR_PACKAGE_COMMANDS = frozenset(
    {
        "project-authoring-materials",
        "create-authored-package",
        "write-authored-package-file",
        "finalize-authored-package",
        "invoke",
    }
)


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
        extra={},
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
        "UV_CACHE_DIR": str(working_directory / ".uv-cache"),
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
    _validate_successor_plugin_surface(plugin_root)
    if not (
        (plugin_root / "skills" / "agent-development" / "SKILL.md").is_file()
        and (plugin_root / "references" / "dar-runtime-profile.md").is_file()
    ):
        raise M44CleanCodexError("successor plugin surface is invalid")
    plugin_destination = destination / "plugins" / "agent-engineering"
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
                        "name": "agent-engineering",
                        "policy": {
                            "authentication": "ON_INSTALL",
                            "installation": "AVAILABLE",
                        },
                        "source": {
                            "path": "./plugins/agent-engineering",
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


def _validate_successor_plugin_surface(plugin_root: Path) -> None:
    """Reject legacy or plugin-owned control-plane surfaces before copying."""

    try:
        manifest = json.loads(
            (plugin_root / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise M44CleanCodexError("plugin manifest is invalid") from error
    if not isinstance(manifest, dict) or _contains_control_plane_key(manifest):
        raise M44CleanCodexError("plugin control-plane surface is invalid")
    for path in plugin_root.rglob("*"):
        relative_parts = path.relative_to(plugin_root).parts
        if any(part in {"dar-authoring", "broker"} for part in relative_parts):
            raise M44CleanCodexError("plugin legacy surface is invalid")
        if path.name in {".mcp.json", "mcp.json", "session-broker", "dar-mcp"}:
            raise M44CleanCodexError("plugin control-plane surface is invalid")


def _contains_control_plane_key(value: object) -> bool:
    if isinstance(value, dict):
        return any(
            key in {"mcpServers", "mcp"} or _contains_control_plane_key(child)
            for key, child in value.items()
        )
    if isinstance(value, list):
        return any(_contains_control_plane_key(item) for item in value)
    return False


def _absolute_not_symlink(path: object, label: str) -> None:
    if not isinstance(path, Path) or not path.is_absolute() or path.is_symlink():
        raise M44CleanCodexError(f"{label} is invalid")
