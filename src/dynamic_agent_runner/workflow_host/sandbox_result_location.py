"""Host-only bounded in-memory result collection for future sandbox adapters."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from hashlib import sha256
from typing import Sequence


_RESULT_NAME = re.compile(r"[a-z][a-z0-9_]{0,63}")


class ResultLocationError(ValueError):
    """Raised when a result collector escapes its declared host boundary."""


@dataclass(frozen=True)
class DeclaredResultArtifact:
    """One package-declared bounded result slot with no storage location."""

    name: str
    max_bytes: int

    def __post_init__(self) -> None:
        if not _RESULT_NAME.fullmatch(self.name) or not _positive(self.max_bytes):
            raise ResultLocationError("result artifact declaration is invalid")


@dataclass(frozen=True)
class SealedResultArtifact:
    """One host-private result value and its content-free identity."""

    name: str
    sha256: str
    byte_count: int
    _content: bytes = field(repr=False)


class ResultLocation:
    """Collect exactly one bounded byte value for each declared result slot."""

    def __init__(self, declarations: tuple[DeclaredResultArtifact, ...]) -> None:
        self._declarations = {item.name: item for item in declarations}
        self._written: dict[str, SealedResultArtifact] = {}
        self._sealed = False

    def write(self, name: str, content: bytes) -> None:
        """Accept one declared result byte sequence before sealing."""

        if self._sealed:
            raise ResultLocationError("result location is sealed")
        declaration = self._declarations.get(name)
        if declaration is None or not isinstance(content, bytes):
            raise ResultLocationError("result artifact is invalid")
        if name in self._written:
            raise ResultLocationError("result artifact is already written")
        if len(content) > declaration.max_bytes:
            raise ResultLocationError("result artifact exceeds its limit")
        self._written[name] = SealedResultArtifact(
            name=name,
            sha256=sha256(content).hexdigest(),
            byte_count=len(content),
            _content=content,
        )

    def seal(self) -> tuple[SealedResultArtifact, ...]:
        """Close the collector and return the complete declared artifact set."""

        if len(self._written) != len(self._declarations):
            raise ResultLocationError("result location is incomplete")
        self._sealed = True
        return tuple(self._written[name] for name in self._declarations)

    def read(self, artifact: SealedResultArtifact) -> bytes:
        """Return bytes only for an artifact sealed by this exact collector."""

        if not self._sealed or self._written.get(artifact.name) != artifact:
            raise ResultLocationError("result artifact is unavailable")
        return artifact._content


def create_result_location(
    declarations: Sequence[DeclaredResultArtifact],
) -> ResultLocation:
    """Create one canonical declared-result collector with no path capability."""

    normalized = tuple(declarations)
    if any(not isinstance(item, DeclaredResultArtifact) for item in normalized):
        raise ResultLocationError("result artifact declarations are invalid")
    names = tuple(item.name for item in normalized)
    if not normalized or names != tuple(sorted(names)) or len(set(names)) != len(names):
        raise ResultLocationError("result artifact declarations are invalid")
    return ResultLocation(normalized)


def _positive(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0
