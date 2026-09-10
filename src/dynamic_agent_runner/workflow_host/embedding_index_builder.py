"""Owner-authorized experimental bridge for sealed embedding index builders."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from hashlib import sha256
from typing import Protocol

from dynamic_agent_runner.workflow_host.embedding_execution import (
    EmbeddingTextItem,
    EmbeddingVector,
)
from dynamic_agent_runner.workflow_host.embedding_index_artifacts import (
    DocumentSnapshot,
)
from dynamic_agent_runner.workflow_host.sandbox_result_location import (
    DeclaredResultArtifact,
    ResultLocation,
    ResultLocationError,
    SealedResultArtifact,
    create_result_location,
)


_DIGEST = re.compile(r"[0-9a-f]{64}")


class IndexBuilderError(ValueError):
    """Raised when a builder cannot use the experimental host bridge."""


class ExperimentalIndexBuilder(Protocol):
    """The narrow data-only ABI for an owner-authorized experimental builder."""

    def run(
        self,
        *,
        snapshot: DocumentSnapshot,
        prior_bundle: bytes | None,
        embed: Callable[[tuple[EmbeddingTextItem, ...]], tuple[EmbeddingVector, ...]],
        results: ResultLocation,
    ) -> None:
        """Write exactly the declared result artifacts through ``results``."""


@dataclass(frozen=True)
class IndexBuilderDescriptor:
    """Exact package and asset identity plus bounded result declarations."""

    package_digest: str
    asset_digest: str
    result_artifacts: tuple[DeclaredResultArtifact, ...]
    max_prior_bundle_bytes: int

    def __post_init__(self) -> None:
        artifacts = tuple(self.result_artifacts)
        names = tuple(item.name for item in artifacts)
        if (
            not _DIGEST.fullmatch(self.package_digest)
            or not _DIGEST.fullmatch(self.asset_digest)
            or not artifacts
            or names != tuple(sorted(names))
            or len(set(names)) != len(names)
            or any(not isinstance(item, DeclaredResultArtifact) for item in artifacts)
            or not _positive(self.max_prior_bundle_bytes)
        ):
            raise IndexBuilderError("index builder descriptor is invalid")
        object.__setattr__(self, "result_artifacts", artifacts)

    @property
    def digest(self) -> str:
        """Return the immutable builder identity bound into index artifacts."""

        return sha256(
            json.dumps(
                {
                    "format_version": 1,
                    "package_digest": self.package_digest,
                    "asset_digest": self.asset_digest,
                    "result_artifacts": [
                        {"name": item.name, "max_bytes": item.max_bytes}
                        for item in self.result_artifacts
                    ],
                    "max_prior_bundle_bytes": self.max_prior_bundle_bytes,
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()


@dataclass(frozen=True)
class OwnerAuthorizedBuilderProfile:
    """One local host owner's opt-in for exact experimental package bytes."""

    package_digest: str
    asset_digest: str

    def __post_init__(self) -> None:
        if not _DIGEST.fullmatch(self.package_digest) or not _DIGEST.fullmatch(
            self.asset_digest
        ):
            raise IndexBuilderError("owner authorization is invalid")


@dataclass(frozen=True)
class ExperimentalBuilderBinding:
    """One receiver-owned builder object selected by an exact asset digest."""

    asset_digest: str
    builder: ExperimentalIndexBuilder = field(repr=False)

    def __post_init__(self) -> None:
        if not _DIGEST.fullmatch(self.asset_digest) or not callable(
            getattr(self.builder, "run", None)
        ):
            raise IndexBuilderError("experimental builder binding is invalid")


class ExperimentalBuilderCatalog:
    """Private host catalog; package data cannot select an arbitrary callback."""

    def __init__(self, bindings: Sequence[ExperimentalBuilderBinding]) -> None:
        resolved: dict[str, ExperimentalIndexBuilder] = {}
        for binding in bindings:
            if not isinstance(binding, ExperimentalBuilderBinding):
                raise IndexBuilderError("experimental builder catalog is invalid")
            if binding.asset_digest in resolved:
                raise IndexBuilderError("experimental builder catalog is invalid")
            resolved[binding.asset_digest] = binding.builder
        self._builders = resolved

    def resolve(self, asset_digest: str) -> ExperimentalIndexBuilder:
        """Return only a host-installed builder with the exact sealed digest."""

        try:
            return self._builders[asset_digest]
        except KeyError as error:
            raise IndexBuilderError("experimental builder is unavailable") from error


@dataclass(frozen=True)
class BuilderRunResult:
    """Host-private completed result set for one owner-authorized builder run."""

    builder_digest: str
    artifacts: tuple[SealedResultArtifact, ...]
    _results: ResultLocation = field(repr=False, compare=False)

    def read(self, name: str) -> bytes:
        """Read one exact sealed result through the owning host collector."""

        artifact = next((item for item in self.artifacts if item.name == name), None)
        if artifact is None:
            raise IndexBuilderError("index builder result is unavailable")
        try:
            return self._results.read(artifact)
        except ResultLocationError as error:
            raise IndexBuilderError("index builder result is unavailable") from error


def run_owner_authorized_builder(
    *,
    profile: OwnerAuthorizedBuilderProfile,
    descriptor: IndexBuilderDescriptor,
    catalog: ExperimentalBuilderCatalog,
    snapshot: DocumentSnapshot,
    prior_bundle: bytes | None,
    embed: Callable[[tuple[EmbeddingTextItem, ...]], tuple[EmbeddingVector, ...]],
) -> BuilderRunResult:
    """Run one exact host-installed builder under the experimental profile.

    This is intentionally not an isolation boundary. Callers use it only after
    explicit local owner authorization of the exact sealed package and asset.
    """

    _validate_run_inputs(profile, descriptor, catalog, snapshot, prior_bundle, embed)
    builder = catalog.resolve(descriptor.asset_digest)
    results = create_result_location(descriptor.result_artifacts)
    try:
        builder.run(
            snapshot=snapshot,
            prior_bundle=prior_bundle,
            embed=embed,
            results=results,
        )
        artifacts = results.seal()
    except Exception as error:  # noqa: BLE001 - builder internals are untrusted here.
        raise IndexBuilderError("experimental builder execution failed") from error
    return BuilderRunResult(descriptor.digest, artifacts, results)


def _validate_run_inputs(
    profile: OwnerAuthorizedBuilderProfile,
    descriptor: IndexBuilderDescriptor,
    catalog: ExperimentalBuilderCatalog,
    snapshot: DocumentSnapshot,
    prior_bundle: bytes | None,
    embed: object,
) -> None:
    if (
        not isinstance(profile, OwnerAuthorizedBuilderProfile)
        or not isinstance(descriptor, IndexBuilderDescriptor)
        or not isinstance(catalog, ExperimentalBuilderCatalog)
        or not isinstance(snapshot, DocumentSnapshot)
        or not callable(embed)
        or profile.package_digest != descriptor.package_digest
        or profile.asset_digest != descriptor.asset_digest
        or prior_bundle is not None
        and (
            not isinstance(prior_bundle, bytes)
            or len(prior_bundle) > descriptor.max_prior_bundle_bytes
        )
    ):
        raise IndexBuilderError("experimental builder admission is invalid")


def _positive(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0
