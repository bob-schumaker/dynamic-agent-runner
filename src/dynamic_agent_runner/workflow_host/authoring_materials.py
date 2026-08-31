"""Private, bounded authoring-material sets for DAR package design."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import stat
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from dynamic_agent_runner.workflow_host.state import (
    OpaqueRecordError,
    PrivateStateStore,
)


class AuthoringMaterialError(ValueError):
    """Raised when authoring material cannot be issued or projected safely."""


@dataclass(frozen=True)
class AuthoringMaterialInput:
    """Human-selected textual material before it enters private state."""

    role: str
    content: str
    disposition: str


@dataclass(frozen=True)
class AuthoringMaterialReference:
    """Content-free public reference for one selected material version."""

    artifact_id: str
    digest: str
    role: str
    disposition: str


@dataclass(frozen=True)
class AuthoringMaterialSetReceipt:
    """Opaque, content-free receipt for a human-issued material set."""

    material_set_id: str
    members: tuple[AuthoringMaterialReference, ...]
    expires_at: datetime


@dataclass(frozen=True)
class AuthoringMaterialProjectionMember:
    """Approved content projection available to an authoring skill only."""

    artifact_id: str
    digest: str
    role: str
    disposition: str
    content: str


@dataclass(frozen=True)
class AuthoringMaterialSetProjection:
    """Selected content and metadata for one bounded authoring request."""

    material_set_id: str
    members: tuple[AuthoringMaterialProjectionMember, ...]
    expires_at: datetime


class AuthoringMaterialService:
    """Issue opaque selected-material sets and project only their contents."""

    def __init__(
        self,
        *,
        store: PrivateStateStore,
        owner: str,
        max_material_bytes: int,
        max_materials: int,
        material_ttl: timedelta,
    ) -> None:
        if not isinstance(owner, str) or not owner:
            raise AuthoringMaterialError("authoring material owner is invalid")
        if (
            not isinstance(max_material_bytes, int)
            or isinstance(max_material_bytes, bool)
            or max_material_bytes <= 0
        ):
            raise AuthoringMaterialError("authoring material byte limit is invalid")
        if (
            not isinstance(max_materials, int)
            or isinstance(max_materials, bool)
            or max_materials <= 0
        ):
            raise AuthoringMaterialError("authoring material count limit is invalid")
        if material_ttl <= timedelta():
            raise AuthoringMaterialError("authoring material lifetime is invalid")
        self._store = store
        self._owner = owner
        self._max_material_bytes = max_material_bytes
        self._max_materials = max_materials
        self._material_ttl = material_ttl

    def issue(
        self,
        *,
        materials: tuple[AuthoringMaterialInput, ...],
        now: datetime,
    ) -> AuthoringMaterialSetReceipt:
        """Persist one human-selected bounded material set behind an opaque ID."""

        issued_at = _as_utc(now)
        members = _members(
            materials,
            max_material_bytes=self._max_material_bytes,
            max_materials=self._max_materials,
        )
        expires_at = issued_at + self._material_ttl
        try:
            material_set_id = self._store.issue(
                kind="authoring_material_set",
                owner=self._owner,
                payload={
                    "format_version": 1,
                    "members": [
                        {
                            "artifact_id": member.artifact_id,
                            "digest": member.digest,
                            "role": member.role,
                            "disposition": member.disposition,
                            "content": member.content,
                        }
                        for member in members
                    ],
                },
                expires_at=expires_at,
                now=issued_at,
            )
        except OpaqueRecordError as error:
            raise AuthoringMaterialError("authoring material is unavailable") from error
        return AuthoringMaterialSetReceipt(
            material_set_id,
            tuple(_reference(member) for member in members),
            expires_at,
        )

    def issue_human_manifest(
        self, *, manifest_path: Path, now: datetime
    ) -> AuthoringMaterialSetReceipt:
        """Issue one material set from a human-selected manifest of text files."""

        return self.issue(
            materials=_manifest_materials(
                manifest_path,
                max_material_bytes=self._max_material_bytes,
                max_materials=self._max_materials,
            ),
            now=now,
        )

    def project(
        self, material_set_id: str, *, now: datetime
    ) -> AuthoringMaterialSetProjection:
        """Return content only from the exact selected set owned by this host."""

        try:
            record = self._store.load(
                material_set_id,
                expected_kind="authoring_material_set",
                owner=self._owner,
                now=_as_utc(now),
            )
            members = _stored_members(
                record.payload.get("members"),
                max_material_bytes=self._max_material_bytes,
                max_materials=self._max_materials,
            )
        except (OpaqueRecordError, AuthoringMaterialError) as error:
            raise AuthoringMaterialError("authoring material is unavailable") from error
        return AuthoringMaterialSetProjection(
            material_set_id, members, record.expires_at
        )


def _members(
    materials: tuple[AuthoringMaterialInput, ...],
    *,
    max_material_bytes: int,
    max_materials: int,
) -> tuple[AuthoringMaterialProjectionMember, ...]:
    if not materials:
        raise AuthoringMaterialError("at least one authoring material is required")
    if len(materials) > max_materials:
        raise AuthoringMaterialError("authoring material count exceeds the limit")
    members: list[AuthoringMaterialProjectionMember] = []
    roles: set[str] = set()
    for material in materials:
        if not isinstance(material, AuthoringMaterialInput):
            raise AuthoringMaterialError("authoring material is invalid")
        _validate_member(
            role=material.role,
            content=material.content,
            disposition=material.disposition,
            max_material_bytes=max_material_bytes,
        )
        if material.role in roles:
            raise AuthoringMaterialError("authoring material roles must be unique")
        roles.add(material.role)
        encoded = material.content.encode("utf-8")
        members.append(
            AuthoringMaterialProjectionMember(
                artifact_id=f"v1.material.{secrets.token_urlsafe(24)}",
                digest=hashlib.sha256(encoded).hexdigest(),
                role=material.role,
                disposition=material.disposition,
                content=material.content,
            )
        )
    return tuple(members)


def _manifest_materials(
    manifest_path: Path,
    *,
    max_material_bytes: int,
    max_materials: int,
) -> tuple[AuthoringMaterialInput, ...]:
    try:
        parsed = json.loads(
            _read_regular_utf8(manifest_path, max_bytes=max_materials * 8192)
        )
        if (
            not isinstance(parsed, dict)
            or set(parsed) != {"format_version", "members"}
            or parsed["format_version"] != 1
            or not isinstance(parsed["members"], list)
            or not parsed["members"]
            or len(parsed["members"]) > max_materials
        ):
            raise ValueError
        materials = tuple(
            AuthoringMaterialInput(
                role=member["role"],
                content=_read_regular_utf8(
                    _absolute_path(member["path"]), max_bytes=max_material_bytes
                ),
                disposition=member["disposition"],
            )
            for member in parsed["members"]
            if isinstance(member, dict)
            and set(member) == {"disposition", "path", "role"}
        )
        if len(materials) != len(parsed["members"]):
            raise ValueError
        return materials
    except (
        KeyError,
        OSError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
        UnicodeDecodeError,
    ) as error:
        raise AuthoringMaterialError(
            "authoring material manifest is invalid"
        ) from error


def _absolute_path(value: object) -> Path:
    if not isinstance(value, str) or not value:
        raise ValueError
    path = Path(value)
    if not path.is_absolute():
        raise ValueError
    return path


def _read_regular_utf8(path: Path, *, max_bytes: int) -> str:
    if not isinstance(path, Path) or max_bytes <= 0:
        raise ValueError
    nofollow = getattr(os, "O_NOFOLLOW", None)
    if nofollow is None:
        raise ValueError
    flags = os.O_RDONLY | nofollow
    descriptor = os.open(path, flags)
    try:
        details = os.fstat(descriptor)
        if not stat.S_ISREG(details.st_mode) or details.st_size > max_bytes:
            raise ValueError
        with os.fdopen(descriptor, "rb", closefd=False) as source:
            content = source.read(max_bytes + 1)
    finally:
        os.close(descriptor)
    if len(content) > max_bytes:
        raise ValueError
    return content.decode("utf-8")


def _stored_members(
    value: object, *, max_material_bytes: int, max_materials: int
) -> tuple[AuthoringMaterialProjectionMember, ...]:
    if not isinstance(value, list) or not value:
        raise AuthoringMaterialError("stored authoring material is invalid")
    if len(value) > max_materials:
        raise AuthoringMaterialError("stored authoring material is invalid")
    result: list[AuthoringMaterialProjectionMember] = []
    roles: set[str] = set()
    for raw_member in value:
        if not isinstance(raw_member, dict):
            raise AuthoringMaterialError("stored authoring material is invalid")
        artifact_id = raw_member.get("artifact_id")
        digest = raw_member.get("digest")
        role = raw_member.get("role")
        content = raw_member.get("content")
        disposition = raw_member.get("disposition")
        _validate_member(
            role=role,
            content=content,
            disposition=disposition,
            max_material_bytes=max_material_bytes,
        )
        assert isinstance(role, str)
        assert isinstance(content, str)
        assert isinstance(disposition, str)
        if role in roles:
            raise AuthoringMaterialError("stored authoring material is invalid")
        roles.add(role)
        if (
            not isinstance(artifact_id, str)
            or not artifact_id.startswith("v1.material.")
            or not isinstance(digest, str)
            or digest != hashlib.sha256(content.encode("utf-8")).hexdigest()
        ):
            raise AuthoringMaterialError("stored authoring material is invalid")
        result.append(
            AuthoringMaterialProjectionMember(
                artifact_id,
                digest,
                role,
                disposition,
                content,
            )
        )
    return tuple(result)


def _reference(
    member: AuthoringMaterialProjectionMember,
) -> AuthoringMaterialReference:
    return AuthoringMaterialReference(
        member.artifact_id, member.digest, member.role, member.disposition
    )


def _validate_member(
    *, role: object, content: object, disposition: object, max_material_bytes: int
) -> None:
    if not isinstance(role, str) or not role:
        raise AuthoringMaterialError("authoring material role is invalid")
    if not isinstance(content, str) or not content:
        raise AuthoringMaterialError("authoring material content is invalid")
    if disposition not in {"reference_only", "distributable"}:
        raise AuthoringMaterialError("authoring material disposition is invalid")
    if len(content.encode("utf-8")) > max_material_bytes:
        raise AuthoringMaterialError("authoring material exceeds the byte limit")


def _as_utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise AuthoringMaterialError("authoring material time is invalid")
    return value.astimezone(UTC)
