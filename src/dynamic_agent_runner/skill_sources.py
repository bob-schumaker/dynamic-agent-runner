"""Skill source resolution policy and provenance models."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping


DEFAULT_MAX_SKILL_BYTES = 65_536
DEFAULT_MAX_NODE_SKILL_BYTES = 262_144
SUPPORTED_SKILL_SOURCE_KINDS = frozenset({"package_bundle"})
SUPPORTED_SKILL_SOURCE_PROMPT_ROLES = frozenset({"system", "developer"})
PACKAGE_LOCAL_TRUST = "package_local"
PACKAGE_BUNDLE_SOURCE_KIND = "package_bundle"


class SkillSourceResolutionError(ValueError):
    """Raised when a declared skill source cannot be loaded safely."""


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


def resolve_package_bundled_skill_source(
    *,
    skill_id: str,
    raw_skill: Mapping[str, Any],
    package_id: str | None,
    skill_bundle_root: str | Path,
    policy: SkillSourceResolutionPolicy,
) -> ResolvedSkillSource:
    """Resolve one package-local bundled `SKILL.md` source."""

    bundled_path = raw_skill.get("bundled_path")
    if bundled_path is None:
        raise SkillSourceResolutionError(
            f"skill {skill_id!r} requires bundled_path for source loading"
        )
    relative_path = Path(str(bundled_path))
    if relative_path.name != "SKILL.md":
        raise SkillSourceResolutionError(
            f"skill {skill_id!r} bundled_path must point to SKILL.md"
        )
    root = Path(skill_bundle_root)
    candidate = _safe_package_relative_file(
        root,
        relative_path,
        label=f"skill {skill_id!r}",
    )
    body_bytes = _bounded_read_bytes(
        candidate,
        max_bytes=policy.max_skill_bytes,
        label=f"skill {skill_id!r}",
    )
    body = _decode_skill_body(body_bytes, label=f"skill {skill_id!r}")
    return ResolvedSkillSource(
        skill_id=skill_id,
        body=body,
        source_kind=PACKAGE_BUNDLE_SOURCE_KIND,
        trust=PACKAGE_LOCAL_TRUST,
        package_id=package_id,
        bundled_path=str(relative_path),
        content_hash=f"sha256:{hashlib.sha256(body_bytes).hexdigest()}",
        byte_count=len(body_bytes),
    )


def enforce_node_skill_source_budget(
    sources: tuple[ResolvedSkillSource, ...],
    *,
    policy: SkillSourceResolutionPolicy,
    node_id: str,
) -> None:
    """Fail when resolved source bodies exceed the per-node budget."""

    total_bytes = sum(source.byte_count for source in sources)
    if total_bytes > policy.max_node_skill_bytes:
        raise SkillSourceResolutionError(
            f"llm_step node {node_id!r} skill sources exceed max_node_skill_bytes"
        )


def _safe_package_relative_file(
    root: Path,
    relative_path: Path,
    *,
    label: str,
) -> Path:
    if relative_path.is_absolute():
        raise SkillSourceResolutionError(
            f"{label} bundled_path must be package-relative"
        )
    if ".." in relative_path.parts:
        raise SkillSourceResolutionError(
            f"{label} bundled_path must not escape package skill-bundle"
        )
    try:
        root_resolved = root.resolve(strict=True)
    except FileNotFoundError as exc:
        raise SkillSourceResolutionError(
            "package skill-bundle directory does not exist"
        ) from exc
    candidate = root / relative_path
    try:
        candidate_resolved = candidate.resolve(strict=True)
    except FileNotFoundError as exc:
        raise SkillSourceResolutionError(f"{label} bundled_path not found") from exc
    try:
        candidate_resolved.relative_to(root_resolved)
    except ValueError as exc:
        raise SkillSourceResolutionError(
            f"{label} bundled_path escapes package skill-bundle"
        ) from exc
    if not candidate_resolved.is_file():
        raise SkillSourceResolutionError(f"{label} bundled_path is not a file")
    return candidate_resolved


def _bounded_read_bytes(
    path: Path,
    *,
    max_bytes: int,
    label: str,
) -> bytes:
    size = path.stat().st_size
    if size > max_bytes:
        raise SkillSourceResolutionError(f"{label} exceeds max_skill_bytes")
    return path.read_bytes()


def _decode_skill_body(body: bytes, *, label: str) -> str:
    if b"\x00" in body:
        raise SkillSourceResolutionError(f"{label} appears to be binary")
    try:
        return body.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SkillSourceResolutionError(f"{label} must be UTF-8 text") from exc


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
