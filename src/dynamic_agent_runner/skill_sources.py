"""Skill source resolution policy and provenance models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


DEFAULT_MAX_SKILL_BYTES = 65_536
DEFAULT_MAX_NODE_SKILL_BYTES = 262_144
SUPPORTED_SKILL_SOURCE_KINDS = frozenset({"package_bundle"})
SUPPORTED_SKILL_SOURCE_PROMPT_ROLES = frozenset({"system", "developer"})


@dataclass(frozen=True)
class SkillSourceResolutionPolicy:
    """Execution policy for opt-in `SKILL.md` source loading."""

    enabled: bool = False
    allowed_sources: tuple[str, ...] = ("package_bundle",)
    max_skill_bytes: int = DEFAULT_MAX_SKILL_BYTES
    max_node_skill_bytes: int = DEFAULT_MAX_NODE_SKILL_BYTES
    load_support_files: bool = False
    prompt_role: str = "developer"
    raw: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def disabled(cls) -> SkillSourceResolutionPolicy:
        """Return the default disabled policy."""

        return cls(enabled=False)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> SkillSourceResolutionPolicy:
        """Build a skill-source policy from runtime execution policy metadata."""

        raw = dict(value)
        return cls(
            enabled=bool(raw.get("enabled", False)),
            allowed_sources=_string_tuple(
                raw.get("allowed_sources"), default=("package_bundle",)
            ),
            max_skill_bytes=_positive_int(
                raw.get("max_skill_bytes"),
                default=DEFAULT_MAX_SKILL_BYTES,
            ),
            max_node_skill_bytes=_positive_int(
                raw.get("max_node_skill_bytes"),
                default=DEFAULT_MAX_NODE_SKILL_BYTES,
            ),
            load_support_files=bool(raw.get("load_support_files", False)),
            prompt_role=str(raw.get("prompt_role") or "developer"),
            raw=raw,
        )


@dataclass(frozen=True)
class ResolvedSkillSource:
    """Resolved skill body plus redaction-safe provenance metadata."""

    skill_id: str
    body: str
    source_kind: str
    trust: str
    package_id: str | None = None
    bundled_path: str | None = None
    content_hash: str | None = None
    byte_count: int = 0

    def redacted_metadata(self) -> dict[str, Any]:
        """Return provenance metadata without raw skill content."""

        metadata: dict[str, Any] = {
            "skill_id": self.skill_id,
            "source_kind": self.source_kind,
            "trust": self.trust,
            "byte_count": self.byte_count,
        }
        if self.package_id is not None:
            metadata["package_id"] = self.package_id
        if self.bundled_path is not None:
            metadata["bundled_path"] = self.bundled_path
        if self.content_hash is not None:
            metadata["content_hash"] = self.content_hash
        return metadata


@dataclass(frozen=True)
class RejectedSkillSource:
    """Redaction-safe diagnostic for a rejected skill source."""

    skill_id: str
    reason: str
    source_kind: str | None = None
    bundled_path: str | None = None

    def redacted_metadata(self) -> dict[str, Any]:
        """Return rejection metadata without raw skill content."""

        metadata: dict[str, Any] = {"skill_id": self.skill_id, "reason": self.reason}
        if self.source_kind is not None:
            metadata["source_kind"] = self.source_kind
        if self.bundled_path is not None:
            metadata["bundled_path"] = self.bundled_path
        return metadata


def _string_tuple(value: object, *, default: tuple[str, ...]) -> tuple[str, ...]:
    if value is None:
        return default
    if isinstance(value, list):
        return tuple(str(item) for item in value)
    return (str(value),)


def _positive_int(value: object, *, default: int) -> int:
    if value is None:
        return default
    if isinstance(value, bool):
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default
