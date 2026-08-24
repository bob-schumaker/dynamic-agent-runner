"""Static, de-identified target-invocation fixture contract validation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


_SKILL_IDS = frozenset(
    {"agent-development", "agent-tool-contract-design", "agent-evaluation"}
)


class AuthoringFixtureError(ValueError):
    """Raised when a static authoring fixture is incomplete or unsafe."""


@dataclass(frozen=True)
class AuthoringFixture:
    """A normalized target invocation projection, not a production material set."""

    format_version: int
    skill_id: str
    request: str
    artifact_properties: tuple[str, ...]
    capability_result: str
    refusal_fields: tuple[str, ...]


def load_authoring_fixture(path: Path) -> AuthoringFixture:
    """Load one static fixture without accessing a model or source material."""

    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise AuthoringFixtureError("fixture is not valid JSON") from error
    if not isinstance(value, Mapping) or set(value) != {
        "format_version",
        "skill_id",
        "request",
        "materials",
        "expected",
        "private_material_exclusions",
    }:
        raise AuthoringFixtureError("fixture must contain exactly its v1 fields")
    if value["format_version"] != 1:
        raise AuthoringFixtureError("fixture format_version must be 1")
    skill_id = _nonempty(value["skill_id"], "skill_id")
    if skill_id not in _SKILL_IDS:
        raise AuthoringFixtureError("fixture skill_id is unsupported")
    request = _nonempty(value["request"], "request")
    if "@" in request:
        raise AuthoringFixtureError("fixture request must be de-identified")
    exclusions = _string_tuple(value["private_material_exclusions"], "exclusions")
    _materials(value["materials"], exclusions)
    expected = value["expected"]
    if not isinstance(expected, Mapping) or set(expected) != {
        "artifact_properties",
        "capability_result",
        "refusal_fields",
    }:
        raise AuthoringFixtureError("fixture expected result is invalid")
    return AuthoringFixture(
        format_version=1,
        skill_id=skill_id,
        request=request,
        artifact_properties=_string_tuple(
            expected["artifact_properties"], "artifact_properties"
        ),
        capability_result=_nonempty(expected["capability_result"], "capability_result"),
        refusal_fields=_string_tuple(expected["refusal_fields"], "refusal_fields"),
    )


def _materials(value: object, exclusions: tuple[str, ...]) -> None:
    if not isinstance(value, list) or not value:
        raise AuthoringFixtureError("fixture materials must be a non-empty list")
    for material in value:
        if not isinstance(material, Mapping) or set(material) != {
            "artifact_id",
            "version",
            "classification",
            "content_projection",
        }:
            raise AuthoringFixtureError("fixture material is invalid")
        _nonempty(material["artifact_id"], "artifact_id")
        _nonempty(material["version"], "version")
        if material["classification"] != "distributable":
            raise AuthoringFixtureError("fixture material must be distributable")
        projection = _nonempty(material["content_projection"], "content_projection")
        if any(exclusion in projection for exclusion in exclusions):
            raise AuthoringFixtureError("fixture material contains excluded content")


def _string_tuple(value: object, name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item for item in value
    ):
        raise AuthoringFixtureError(f"{name} must be a list of non-empty strings")
    return tuple(value)


def _nonempty(value: object, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise AuthoringFixtureError(f"{name} must be a non-empty string")
    return value
