"""Tests for host-only bounded sandbox result collection."""

from __future__ import annotations

from hashlib import sha256

import pytest

from dynamic_agent_runner.workflow_host.sandbox_result_location import (
    DeclaredResultArtifact,
    ResultLocationError,
    create_result_location,
)


def _location():
    return create_result_location(
        (
            DeclaredResultArtifact("coverage_report", 64),
            DeclaredResultArtifact("index_bundle", 128),
        )
    )


def test_result_location_seals_only_declared_bounded_memory_artifacts() -> None:
    location = _location()

    location.write("coverage_report", b'{"status":"ok"}')
    location.write("index_bundle", b"opaque vector index")
    sealed = location.seal()

    assert tuple(artifact.name for artifact in sealed) == (
        "coverage_report",
        "index_bundle",
    )
    assert sealed[1].sha256 == sha256(b"opaque vector index").hexdigest()
    assert sealed[1].byte_count == len(b"opaque vector index")
    assert "opaque vector index" not in repr(sealed[1])
    assert not hasattr(location, "path")
    assert location.read(sealed[1]) == b"opaque vector index"


@pytest.mark.parametrize(
    "name,content",
    [
        ("unexpected", b"data"),
        ("index_bundle", b"x" * 129),
        ("index_bundle", "not bytes"),
    ],
)
def test_result_location_rejects_undeclared_or_invalid_writes(
    name: str, content: object
) -> None:
    location = _location()

    with pytest.raises(ResultLocationError):
        location.write(name, content)
    with pytest.raises(ResultLocationError, match="incomplete"):
        location.seal()


def test_result_location_rejects_duplicate_or_late_writes() -> None:
    location = _location()
    location.write("coverage_report", b"report")

    with pytest.raises(ResultLocationError, match="already"):
        location.write("coverage_report", b"replacement")
    location.write("index_bundle", b"bundle")
    sealed = location.seal()

    with pytest.raises(ResultLocationError, match="sealed"):
        location.write("index_bundle", b"late")
    with pytest.raises(ResultLocationError, match="artifact"):
        location.read(type(sealed[0])("unknown", "a" * 64, 0, b""))


def test_result_location_rejects_noncanonical_declarations() -> None:
    with pytest.raises(ResultLocationError):
        create_result_location(
            (
                DeclaredResultArtifact("index_bundle", 1),
                DeclaredResultArtifact("coverage_report", 1),
            )
        )
    with pytest.raises(ResultLocationError):
        DeclaredResultArtifact("result/path", 1)
