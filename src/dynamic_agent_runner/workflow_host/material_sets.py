"""Canonical named sets of sealed model-material locks."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Mapping

from dynamic_agent_runner.workflow_host.model_materials import (
    ModelDependencyLock,
    ModelMaterialsError,
    parse_model_dependency_lock,
)


_ROLE = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")


class MaterialSetsError(ValueError):
    """Raised when a sealed named material-set declaration is invalid."""


@dataclass(frozen=True)
class MaterialSet:
    """One named sealed material lock used by a package role."""

    role: str
    model_materials: ModelDependencyLock

    def to_mapping(self) -> dict[str, object]:
        return {
            "role": self.role,
            "model_materials": json.loads(self.model_materials.canonical_bytes),
        }


@dataclass(frozen=True)
class ModelMaterialSets:
    """Canonical v1 ordered material-set declaration."""

    material_sets: tuple[MaterialSet, ...]
    format_version: int = 1

    def __post_init__(self) -> None:
        if self.format_version != 1:
            raise MaterialSetsError("material-set format_version must be 1")
        roles = tuple(item.role for item in self.material_sets)
        if not roles or roles != tuple(sorted(roles)) or len(set(roles)) != len(roles):
            raise MaterialSetsError("material-set roles are invalid")
        if any(not _ROLE.fullmatch(role) for role in roles):
            raise MaterialSetsError("material-set roles are invalid")
        object.__setattr__(self, "material_sets", tuple(self.material_sets))

    @property
    def roles(self) -> tuple[str, ...]:
        return tuple(item.role for item in self.material_sets)

    @property
    def canonical_bytes(self) -> bytes:
        return _canonical_json(
            {
                "format_version": self.format_version,
                "material_sets": [item.to_mapping() for item in self.material_sets],
            }
        )

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.canonical_bytes).hexdigest()

    def for_role(self, role: str) -> ModelDependencyLock:
        for item in self.material_sets:
            if item.role == role:
                return item.model_materials
        raise MaterialSetsError("material-set role is unavailable")


def parse_model_material_sets(value: object) -> ModelMaterialSets:
    """Parse strict v1 named locks and verify an optional declared digest."""

    mapping = _mapping(value)
    allowed = {"format_version", "material_sets", "material_sets_digest"}
    if set(mapping) - allowed or not {"format_version", "material_sets"} <= set(
        mapping
    ):
        raise MaterialSetsError("material-set fields are invalid")
    raw_sets = mapping["material_sets"]
    if not isinstance(raw_sets, list):
        raise MaterialSetsError("material_sets must be a list")
    entries: list[MaterialSet] = []
    for item in raw_sets:
        if not isinstance(item, Mapping) or set(item) != {"role", "model_materials"}:
            raise MaterialSetsError("material-set entry is invalid")
        role = item["role"]
        if not isinstance(role, str) or not _ROLE.fullmatch(role):
            raise MaterialSetsError("material-set role is invalid")
        try:
            lock = parse_model_dependency_lock(item["model_materials"])
        except ModelMaterialsError as error:
            raise MaterialSetsError("material-set lock is invalid") from error
        entries.append(MaterialSet(role, lock))
    result = ModelMaterialSets(tuple(entries), mapping["format_version"])
    declared_digest = mapping.get("material_sets_digest")
    if declared_digest is not None:
        if not _digest(declared_digest) or declared_digest != result.digest:
            raise MaterialSetsError("material-set digest does not match")
    return result


def _mapping(value: object) -> Mapping[str, object]:
    if isinstance(value, bytes):
        try:
            value = json.loads(value.decode("utf-8"), object_pairs_hook=_unique_object)
        except (UnicodeDecodeError, json.JSONDecodeError, MaterialSetsError) as error:
            raise MaterialSetsError("material-set JSON is invalid") from error
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        raise MaterialSetsError("material-set declaration is invalid")
    return value


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, item in pairs:
        if key in result:
            raise MaterialSetsError("material-set JSON contains duplicate keys")
        result[key] = item
    return result


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _digest(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )
