#!/usr/bin/env python3
"""Verify DAR runtime selectors without coupling them to plugin versions."""

from __future__ import annotations

import hashlib
import json
import re
import tomllib
from pathlib import Path
from typing import NamedTuple, Sequence
from zipfile import ZipFile


class RuntimeReleaseContractError(ValueError):
    """Raised when a declared DAR runtime selector is inconsistent."""


class RuntimeReleaseReceipt(NamedTuple):
    """Redacted identities verified for one runtime-selector contract."""

    runtime_version: str
    wheel_filename: str
    wheel_sha256: str
    wheel_metadata_sha256: str
    descriptor_sha256: str
    payload_sha256: str
    selector_list_sha256: str
    plugin_versions: tuple[str, ...]


_REQUIRED_FIELDS = frozenset({"distribution", "format_version", "runtime_version"})
_RUNTIME_SELECTOR = re.compile(r"dynamic-agent-runner==([^\s`]+)")
_WORKFLOW_SELECTOR = re.compile(r"required_version:\s*([^\s#`]+)")


def validate_runtime_release_contract(
    *,
    project_file: Path,
    descriptor_file: Path,
    wheel_file: Path,
    payload_roots: Sequence[Path],
    plugin_manifest_files: Sequence[Path],
) -> RuntimeReleaseReceipt:
    """Verify one DAR version across only runtime-version-bearing artifacts."""

    runtime_version = _descriptor_version(descriptor_file)
    if _project_version(project_file) != runtime_version:
        raise RuntimeReleaseContractError("DAR project version mismatch")
    wheel_metadata = _wheel_metadata(wheel_file)
    if _metadata_value(wheel_metadata.decode("utf-8"), "Version") != runtime_version:
        raise RuntimeReleaseContractError("DAR wheel version mismatch")
    selectors = _validate_payload_selectors(payload_roots, runtime_version)
    return RuntimeReleaseReceipt(
        runtime_version=runtime_version,
        wheel_filename=wheel_file.name,
        wheel_sha256=hashlib.sha256(wheel_file.read_bytes()).hexdigest(),
        wheel_metadata_sha256=hashlib.sha256(wheel_metadata).hexdigest(),
        descriptor_sha256=hashlib.sha256(descriptor_file.read_bytes()).hexdigest(),
        payload_sha256=_payload_digest(payload_roots),
        selector_list_sha256=_selector_list_digest(selectors),
        plugin_versions=tuple(_plugin_version(path) for path in plugin_manifest_files),
    )


def prepare_runtime_release_payload(
    *, descriptor_file: Path, payload_roots: Sequence[Path]
) -> tuple[Path, ...]:
    """Apply a declared DAR runtime selector to payload files only."""

    runtime_version = _descriptor_version(descriptor_file)
    changed_files: list[Path] = []
    for root in payload_roots:
        selector_count = 0
        for path in sorted(
            candidate for candidate in root.rglob("*") if candidate.is_file()
        ):
            text = path.read_text(encoding="utf-8")
            selector_count += len(_RUNTIME_SELECTOR.findall(text))
            selector_count += len(_WORKFLOW_SELECTOR.findall(text))
            prepared = _RUNTIME_SELECTOR.sub(
                f"dynamic-agent-runner=={runtime_version}", text
            )
            prepared = _WORKFLOW_SELECTOR.sub(
                f"required_version: {runtime_version}", prepared
            )
            if prepared != text:
                path.write_text(prepared, encoding="utf-8")
                changed_files.append(path)
        if selector_count == 0:
            raise RuntimeReleaseContractError("DAR payload has no runtime selector")
    return tuple(changed_files)


def _descriptor_version(path: Path) -> str:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeReleaseContractError(
            "DAR runtime release descriptor is invalid"
        ) from error
    if (
        not isinstance(value, dict)
        or set(value) != _REQUIRED_FIELDS
        or value.get("format_version") != 1
        or value.get("distribution") != "dynamic-agent-runner"
        or not isinstance(value.get("runtime_version"), str)
        or not value["runtime_version"]
    ):
        raise RuntimeReleaseContractError("DAR runtime release descriptor is invalid")
    return value["runtime_version"]


def _project_version(path: Path) -> str:
    try:
        project = tomllib.loads(path.read_text(encoding="utf-8"))
        version = project["project"]["version"]
    except (KeyError, OSError, tomllib.TOMLDecodeError) as error:
        raise RuntimeReleaseContractError("DAR project metadata is invalid") from error
    if not isinstance(version, str) or not version:
        raise RuntimeReleaseContractError("DAR project metadata is invalid")
    return version


def _wheel_metadata(path: Path) -> bytes:
    try:
        with ZipFile(path) as wheel:
            metadata_paths = [
                name
                for name in wheel.namelist()
                if name.endswith(".dist-info/METADATA")
            ]
            if len(metadata_paths) != 1:
                raise RuntimeReleaseContractError("DAR wheel metadata is invalid")
            metadata = wheel.read(metadata_paths[0])
    except OSError as error:
        raise RuntimeReleaseContractError("DAR wheel metadata is invalid") from error
    try:
        text = metadata.decode("utf-8")
    except UnicodeDecodeError as error:
        raise RuntimeReleaseContractError("DAR wheel metadata is invalid") from error
    name = _metadata_value(text, "Name")
    version = _metadata_value(text, "Version")
    if name != "dynamic-agent-runner" or version is None:
        raise RuntimeReleaseContractError("DAR wheel metadata is invalid")
    return metadata


def _metadata_value(metadata: str, field: str) -> str | None:
    prefix = f"{field}: "
    return next(
        (
            line.removeprefix(prefix)
            for line in metadata.splitlines()
            if line.startswith(prefix)
        ),
        None,
    )


def _validate_payload_selectors(
    roots: Sequence[Path], expected: str
) -> tuple[str, ...]:
    all_selectors: list[str] = []
    for root in roots:
        selectors: list[str] = []
        for path in sorted(
            candidate for candidate in root.rglob("*") if candidate.is_file()
        ):
            text = path.read_text(encoding="utf-8")
            selectors.extend(_RUNTIME_SELECTOR.findall(text))
            selectors.extend(_WORKFLOW_SELECTOR.findall(text))
        if not selectors:
            raise RuntimeReleaseContractError("DAR payload has no runtime selector")
        if any(selector != expected for selector in selectors):
            raise RuntimeReleaseContractError("DAR payload version mismatch")
        all_selectors.extend(selectors)
    return tuple(sorted(all_selectors))


def _payload_digest(roots: Sequence[Path]) -> str:
    digest = hashlib.sha256()
    for index, root in enumerate(roots):
        for path in sorted(
            candidate for candidate in root.rglob("*") if candidate.is_file()
        ):
            digest.update(str(index).encode("ascii"))
            digest.update(b"\0")
            digest.update(str(path.relative_to(root)).encode("utf-8"))
            digest.update(b"\0")
            digest.update(path.read_bytes())
            digest.update(b"\0")
    return digest.hexdigest()


def _selector_list_digest(selectors: Sequence[str]) -> str:
    encoded = json.dumps(list(selectors), separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _plugin_version(path: Path) -> str:
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeReleaseContractError("plugin manifest is invalid") from error
    version = manifest.get("version") if isinstance(manifest, dict) else None
    if not isinstance(version, str) or not version:
        raise RuntimeReleaseContractError("plugin manifest is invalid")
    return version
