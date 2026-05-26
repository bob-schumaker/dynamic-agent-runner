"""Effective prompt and skill behavior for runtime LLM nodes."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from dynamic_agent_runner.models import (
    LoadedAgentWorkflow,
    ManifestObject,
    NodeBehaviorOverride,
    PromptOverride,
    RuntimeBehaviorOverrides,
    RuntimeNode,
    SkillReferenceOverride,
)


@dataclass(frozen=True)
class EffectiveNodeBehavior:
    """Derived behavior for an `llm_step` after overrides are layered."""

    prompt: Mapping[str, Any]
    skill_refs: tuple[str, ...] = ()
    skills: tuple[ManifestObject, ...] = ()


def effective_node_behavior(
    node: RuntimeNode,
    workflow: LoadedAgentWorkflow,
) -> EffectiveNodeBehavior:
    """Return derived prompt and skill behavior without mutating artifacts."""

    override = _node_override(node, workflow.runtime_overrides)
    prompt = _effective_prompt(node, override.prompt if override else None)
    skill_refs = _effective_skill_refs(node, override.skill_refs if override else None)
    catalog = skill_catalog(workflow)
    skills = tuple(catalog[skill_id] for skill_id in skill_refs if skill_id in catalog)
    return EffectiveNodeBehavior(prompt=prompt, skill_refs=skill_refs, skills=skills)


def skill_catalog(workflow: LoadedAgentWorkflow) -> dict[str, ManifestObject]:
    """Return the effective skill catalog after override skill overlays."""

    catalog: dict[str, ManifestObject] = {}
    _add_skills(catalog, workflow.runtime_manifest.skills)
    if workflow.tool_index is not None:
        _add_skills(catalog, workflow.tool_index.skills, replace=False)
    overrides = workflow.runtime_overrides
    if overrides is not None:
        _add_skills(catalog, overrides.added_skills)
        _add_skills(catalog, overrides.replacement_skills)
    return catalog


def _add_skills(
    catalog: dict[str, ManifestObject],
    skills: tuple[ManifestObject, ...],
    *,
    replace: bool = True,
) -> None:
    for skill in skills:
        if not skill.id:
            continue
        if replace or skill.id not in catalog:
            catalog[skill.id] = skill


def _node_override(
    node: RuntimeNode,
    overrides: RuntimeBehaviorOverrides | None,
) -> NodeBehaviorOverride | None:
    if overrides is None or node.id is None:
        return None
    return overrides.node_overrides.get(node.id)


def _effective_prompt(
    node: RuntimeNode,
    override: PromptOverride | None,
) -> dict[str, Any]:
    prompt_data = node.raw.get("prompt")
    if isinstance(prompt_data, Mapping):
        prompt = dict(prompt_data)
    else:
        prompt = {"user_template": str(node.raw.get("prompt_source") or "{prompt}")}
    if override is None:
        return prompt
    for field, value in override.replace.items():
        prompt[str(field)] = value
    for field, value in override.prepend.items():
        current = prompt.get(field, "")
        prompt[field] = f"{value}{current}"
    for field, value in override.append.items():
        current = prompt.get(field, "")
        prompt[field] = f"{current}{value}"
    return prompt


def _effective_skill_refs(
    node: RuntimeNode,
    override: SkillReferenceOverride | None,
) -> tuple[str, ...]:
    skill_refs = list(node.skill_refs)
    if override is not None:
        skill_refs = list(override.only) if override.only is not None else skill_refs
        skill_refs.extend(override.add)
        remove = set(override.remove)
        skill_refs = [skill_id for skill_id in skill_refs if skill_id not in remove]
    return _dedupe(skill_refs)


def _dedupe(values: list[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return tuple(deduped)
