"""Artifact loading helpers for generated dynamic-agent runtime packages."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml

from dynamic_agent_runner.errors import ArtifactLoadError
from dynamic_agent_runner.models import (
    AgentDesign,
    LoadedAgentWorkflow,
    RuntimeBehaviorOverrides,
    RuntimeManifest,
    ToolIndex,
)

ParsedInput = Mapping[str, Any]
TextInput = str | Path
ArtifactInput = TextInput | ParsedInput

PACKAGE_RUNTIME_MANIFEST = "agent-runtime.yaml"
PACKAGE_AGENT_DESIGN = "agent-design.md"
PACKAGE_MERMAID_GRAPH = "agent-graph.mmd"
DEFAULT_SKILL_BUNDLE_DIR = "skill-bundle"


def load_runtime_manifest(value: ArtifactInput) -> RuntimeManifest:
    """Load an `agent-runtime.yaml` artifact from a path, raw YAML, or mapping."""

    mapping = _load_yaml_mapping(value, artifact_name="runtime manifest")
    return RuntimeManifest.from_mapping(mapping)


def load_runtime_behavior_overrides(
    value: ArtifactInput | None,
) -> RuntimeBehaviorOverrides | None:
    """Load optional runtime behavior overrides."""

    if value is None:
        return None
    mapping = _load_yaml_mapping(value, artifact_name="runtime behavior overrides")
    return RuntimeBehaviorOverrides.from_mapping(mapping)


def load_tool_index(value: ArtifactInput | None) -> ToolIndex | None:
    """Load an optional `tool-index.yaml` artifact."""

    if value is None:
        return None
    mapping = _load_yaml_mapping(value, artifact_name="tool index")
    return ToolIndex.from_mapping(mapping)


def load_agent_design(value: TextInput | None) -> AgentDesign | None:
    """Load an optional `agent-design.md` artifact from a path or raw markdown."""

    if value is None:
        return None
    return AgentDesign.from_text(_load_text(value, artifact_name="agent design"))


def load_mermaid_graph(value: TextInput | None) -> str | None:
    """Load an optional Mermaid graph artifact from a path or raw string."""

    if value is None:
        return None
    return _load_text(value, artifact_name="Mermaid graph")


def load_agent_workflow_artifacts(
    *,
    runtime_manifest: ArtifactInput,
    mermaid_graph: TextInput | None = None,
    agent_design: TextInput | None = None,
    tool_index: ArtifactInput | None = None,
    runtime_overrides: ArtifactInput | None = None,
) -> LoadedAgentWorkflow:
    """Load generated agent workflow artifacts without executing them."""

    loaded_runtime = load_runtime_manifest(runtime_manifest)
    loaded_graph = _load_manifest_graph_reference(
        runtime_manifest_input=runtime_manifest,
        runtime_manifest=loaded_runtime,
        explicit_graph=mermaid_graph,
    )
    return LoadedAgentWorkflow(
        runtime_manifest=loaded_runtime,
        mermaid_graph=loaded_graph,
        agent_design=load_agent_design(agent_design),
        tool_index=load_tool_index(tool_index),
        runtime_overrides=load_runtime_behavior_overrides(runtime_overrides),
    )


def load_agent_package(package_directory: TextInput) -> LoadedAgentWorkflow:
    """Load a canonical agent package directory rooted at a design bundle path."""

    package_root = _require_directory(package_directory, artifact_name="agent package")
    runtime_path = package_root / PACKAGE_RUNTIME_MANIFEST
    if not runtime_path.exists():
        raise ArtifactLoadError(
            f"Agent package is missing required {PACKAGE_RUNTIME_MANIFEST}: {runtime_path}"
        )

    loaded_runtime = load_runtime_manifest(runtime_path)
    agent_design_path = _require_package_file(
        package_root / PACKAGE_AGENT_DESIGN,
        artifact_name=PACKAGE_AGENT_DESIGN,
    )
    mermaid_graph_path = _require_package_file(
        package_root / PACKAGE_MERMAID_GRAPH,
        artifact_name=PACKAGE_MERMAID_GRAPH,
    )
    skill_bundle_root = _skill_bundle_root(package_root, loaded_runtime)

    return LoadedAgentWorkflow(
        runtime_manifest=loaded_runtime,
        package_root=str(package_root),
        skill_bundle_root=str(skill_bundle_root)
        if skill_bundle_root is not None
        else None,
        mermaid_graph=load_mermaid_graph(mermaid_graph_path),
        agent_design=load_agent_design(agent_design_path),
    )


def _load_manifest_graph_reference(
    *,
    runtime_manifest_input: ArtifactInput,
    runtime_manifest: RuntimeManifest,
    explicit_graph: TextInput | None,
) -> str | None:
    if explicit_graph is not None:
        return load_mermaid_graph(explicit_graph)

    if not runtime_manifest.mermaid_diagram:
        return None

    base_path = _existing_path(runtime_manifest_input)
    if base_path is None:
        return None

    graph_path = base_path.parent / runtime_manifest.mermaid_diagram
    if not graph_path.exists():
        raise ArtifactLoadError(f"Mermaid graph not found: {graph_path}")
    return graph_path.read_text(encoding="utf-8")


def _load_yaml_mapping(value: ArtifactInput, *, artifact_name: str) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)

    text = _load_text(value, artifact_name=artifact_name)
    try:
        parsed = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ArtifactLoadError(f"Could not parse {artifact_name} YAML: {exc}") from exc

    if not isinstance(parsed, Mapping):
        raise ArtifactLoadError(f"Expected {artifact_name} YAML to parse to a mapping")
    return dict(parsed)


def _load_text(value: TextInput, *, artifact_name: str) -> str:
    if isinstance(value, Path):
        return _read_existing_path(value, artifact_name=artifact_name)

    path = _existing_path(value)
    if path is not None:
        return _read_existing_path(path, artifact_name=artifact_name)

    return str(value)


def _read_existing_path(path: Path, *, artifact_name: str) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ArtifactLoadError(
            f"Could not read {artifact_name} at {path}: {exc}"
        ) from exc


def _existing_path(value: object) -> Path | None:
    if not isinstance(value, (str, Path)):
        return None
    path = Path(value)
    try:
        return path if path.exists() else None
    except OSError:
        return None


def _require_directory(value: TextInput, *, artifact_name: str) -> Path:
    path = Path(value)
    if not path.exists():
        raise ArtifactLoadError(f"Could not find {artifact_name} at {path}")
    if not path.is_dir():
        raise ArtifactLoadError(f"Expected {artifact_name} to be a directory: {path}")
    return path


def _require_package_file(path: Path, *, artifact_name: str) -> Path:
    if not path.exists():
        raise ArtifactLoadError(
            f"Agent package is missing required {artifact_name}: {path}"
        )
    if not path.is_file():
        raise ArtifactLoadError(
            f"Expected package artifact {artifact_name} to be a file: {path}"
        )
    return path


def _skill_bundle_root(
    package_root: Path, runtime_manifest: RuntimeManifest
) -> Path | None:
    raw_dir = runtime_manifest.packaging.get("skill_bundle_dir")
    if raw_dir is None:
        return None
    skill_bundle_dir = str(raw_dir).strip() or DEFAULT_SKILL_BUNDLE_DIR
    return package_root / skill_bundle_dir
