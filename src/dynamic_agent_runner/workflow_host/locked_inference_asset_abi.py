"""Versioned sealed-asset ABI for locked inference callbacks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from dynamic_agent_runner.workflow_host.sandbox_result_location import (
    DeclaredResultArtifact,
    ResultLocation,
    create_result_location,
)


class LockedInferenceAssetAbiError(ValueError):
    """Raised when a callback-enabled sealed asset ABI is invalid."""


@dataclass(frozen=True)
class LockedInferenceAssetAbi:
    asset_digest: str
    authorized_roles: tuple[str, ...]
    sealed_inputs: tuple[str, ...]
    result_declarations: tuple[DeclaredResultArtifact, ...]

    def create_result_location(self) -> ResultLocation:
        """Allocate only this ABI's ordered, bounded output slots."""

        return create_result_location(self.result_declarations)

    @classmethod
    def from_mapping(cls, value: object) -> "LockedInferenceAssetAbi":
        if (
            not isinstance(value, Mapping)
            or set(value)
            != {
                "format_version",
                "asset_digest",
                "authorized_roles",
                "sealed_inputs",
                "result_slots",
            }
            or value.get("format_version") != 1
        ):
            raise LockedInferenceAssetAbiError("locked inference asset ABI is invalid")
        digest = value["asset_digest"]
        roles = value["authorized_roles"]
        inputs = value["sealed_inputs"]
        slots = value["result_slots"]
        if (
            not _digest(digest)
            or not _ordered(roles)
            or not _ordered(inputs)
            or not isinstance(slots, list)
        ):
            raise LockedInferenceAssetAbiError("locked inference asset ABI is invalid")
        declarations = []
        for slot in slots:
            if (
                not isinstance(slot, Mapping)
                or set(slot) != {"name", "media_type", "schema_digest", "max_bytes"}
                or slot.get("media_type") != "application/json"
                or not _digest(slot.get("schema_digest"))
            ):
                raise LockedInferenceAssetAbiError(
                    "locked inference asset ABI is invalid"
                )
            try:
                declarations.append(
                    DeclaredResultArtifact(slot["name"], slot["max_bytes"])
                )
            except Exception as error:
                raise LockedInferenceAssetAbiError(
                    "locked inference asset ABI is invalid"
                ) from error
        if not declarations or tuple(item.name for item in declarations) != tuple(
            sorted(item.name for item in declarations)
        ):
            raise LockedInferenceAssetAbiError("locked inference asset ABI is invalid")
        return cls(digest, tuple(roles), tuple(inputs), tuple(declarations))


def _ordered(value: object) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(isinstance(item, str) and item for item in value)
        and value == sorted(value)
        and len(set(value)) == len(value)
    )


def _digest(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(item in "0123456789abcdef" for item in value)
    )
