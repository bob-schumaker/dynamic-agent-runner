#!/usr/bin/env python3
"""Build and validate the agent-engineering routed-input classification manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import NamedTuple, Sequence


class ClassificationManifestError(ValueError):
    """Raised when routed plugin inputs lack declared ownership."""


class ClassificationReceipt(NamedTuple):
    """The bounded result of validating one classified plugin source tree."""

    source_file_count: int
    mapped_output_count: int
    excluded_paths: tuple[str, ...]


_FORMAT_VERSION = 1
_SELF_MANIFEST = ".codex-plugin/classification-manifest.json"
_RELEASE_DESCRIPTOR = ".codex-plugin/dar-runtime-release.json"


def build_classification_manifest(plugin_root: Path) -> dict[str, object]:
    """Return the deterministic ownership classification for routed inputs."""

    entries = []
    for path in _source_files(plugin_root):
        relative = path.relative_to(plugin_root).as_posix()
        disposition, output_path = _classify(relative)
        entries.append(
            {
                "disposition": disposition,
                "output_path": output_path,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "source_path": relative,
            }
        )
    return {
        "entries": entries,
        "format_version": _FORMAT_VERSION,
        "source_root": "plugins/agent-engineering",
    }


def write_classification_manifest(*, plugin_root: Path, manifest_file: Path) -> None:
    """Write the deterministic checked-in classification manifest."""

    manifest_file.write_text(
        json.dumps(build_classification_manifest(plugin_root), indent=2) + "\n",
        encoding="utf-8",
    )


def validate_classification_manifest(
    *, plugin_root: Path, manifest_file: Path, source_map_file: Path
) -> ClassificationReceipt:
    """Verify source coverage and routed-output provenance against the source map."""

    expected = build_classification_manifest(plugin_root)
    actual = _load_json(manifest_file, "classification manifest")
    if actual != expected:
        raise ClassificationManifestError("classification manifest is stale or invalid")
    source_map = _load_json(source_map_file, "router source map")
    source_entries = source_map.get("entries") if isinstance(source_map, dict) else None
    if not isinstance(source_entries, list):
        raise ClassificationManifestError("router source map is invalid")
    mapped_outputs = {
        entry.get("path"): entry
        for entry in source_entries
        if isinstance(entry, dict) and isinstance(entry.get("path"), str)
    }
    entries = expected["entries"]
    if not isinstance(entries, list):
        raise ClassificationManifestError("classification manifest is invalid")
    excluded: list[str] = []
    mapped_count = 0
    for entry in entries:
        source_path, output_path = _classified_paths(entry)
        if output_path is None:
            excluded.append(source_path)
            continue
        _validate_mapped_output(
            source_path=source_path,
            output_path=output_path,
            mapped_outputs=mapped_outputs,
        )
        mapped_count += 1
    return ClassificationReceipt(
        source_file_count=len(entries),
        mapped_output_count=mapped_count,
        excluded_paths=tuple(sorted(excluded)),
    )


def _classified_paths(entry: object) -> tuple[str, str | None]:
    if not isinstance(entry, dict):
        raise ClassificationManifestError("classification manifest is invalid")
    source_path = entry.get("source_path")
    output_path = entry.get("output_path")
    disposition = entry.get("disposition")
    if (
        not isinstance(source_path, str)
        or not isinstance(disposition, str)
        or output_path is not None
        and not isinstance(output_path, str)
    ):
        raise ClassificationManifestError("classification manifest is invalid")
    return source_path, output_path


def _validate_mapped_output(
    *, source_path: str, output_path: str, mapped_outputs: dict[object, object]
) -> None:
    mapped = mapped_outputs.get(output_path)
    if not isinstance(mapped, dict):
        raise ClassificationManifestError("classified output is absent from source map")
    if source_path == ".codex-plugin/plugin.json":
        if mapped.get("acquisition_mode") != "generated":
            raise ClassificationManifestError("generated plugin manifest is invalid")
    elif mapped.get("source_reference") != f"plugins/agent-engineering/{source_path}":
        raise ClassificationManifestError("classified output source map mismatch")


def _source_files(plugin_root: Path) -> tuple[Path, ...]:
    if not plugin_root.is_dir():
        raise ClassificationManifestError("plugin source root is invalid")
    return tuple(
        sorted(
            path
            for path in plugin_root.rglob("*")
            if path.is_file()
            and path.relative_to(plugin_root).as_posix() != _SELF_MANIFEST
        )
    )


def _classify(relative: str) -> tuple[str, str | None]:
    if relative == ".codex-plugin/plugin.json":
        return "generated_public_manifest", ".codex-plugin/plugin.json"
    if relative == _RELEASE_DESCRIPTOR:
        return "release_preparation_input", None
    if relative.startswith("assets/"):
        return "copied_asset", relative
    if relative.startswith("skills/") and relative.endswith("/SKILL.md"):
        skill_id = Path(relative).parent.name
        return (
            "module_instruction",
            f"skills/agent-development/references/modules/{skill_id}/instructions.md",
        )
    if relative.startswith("payload/general-agent-development/"):
        suffix = relative.removeprefix("payload/general-agent-development/")
        return (
            "private_module_support",
            f"references/modules/general-agent-development/{suffix}",
        )
    if relative.startswith("payload/dar-workflow-authoring/"):
        suffix = relative.removeprefix("payload/dar-workflow-authoring/")
        return (
            "private_module_support",
            f"references/modules/dar-workflow-authoring/{suffix}",
        )
    raise ClassificationManifestError("plugin source input is unclassified")


def _load_json(path: Path, label: str) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ClassificationManifestError(f"{label} is invalid") from error


def main(argv: Sequence[str] | None = None) -> int:
    """Write or validate the manifest for the caller-provided plugin root."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plugin-root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--source-map", type=Path)
    parser.add_argument("--write", action="store_true")
    arguments = parser.parse_args(argv)
    if arguments.write:
        write_classification_manifest(
            plugin_root=arguments.plugin_root, manifest_file=arguments.manifest
        )
        return 0
    if arguments.source_map is None:
        parser.error("--source-map is required without --write")
    validate_classification_manifest(
        plugin_root=arguments.plugin_root,
        manifest_file=arguments.manifest,
        source_map_file=arguments.source_map,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
