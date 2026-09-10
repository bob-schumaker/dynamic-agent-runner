"""Host-private admission of sealed workflow model materials."""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType

from dynamic_agent_runner.workflow_host.capabilities import CapabilityRequirements
from dynamic_agent_runner.workflow_host.model_materials import (
    MaterialContract,
    ModelDependencyLock,
    ModelMaterialSource,
    PreparationOperation,
)


class ModelMaterialAdmissionError(ValueError):
    """Raised with a stable redacted model-material admission classification."""


class ModelMaterialCache:
    """Host-private verified artifact-cache boundary."""

    def load(
        self, *, lock_digest: str, role: str, transformation_digest: str | None
    ) -> bytes | None:
        """Return a previously promoted artifact, if one exists."""

        raise NotImplementedError

    def promote(
        self,
        *,
        lock_digest: str,
        role: str,
        transformation_digest: str | None,
        content: bytes,
    ) -> None:
        """Atomically promote one verified artifact into the private cache."""

        raise NotImplementedError


class ModelMaterialTransport:
    """DAR-owned source transport boundary for one sealed source artifact."""

    def fetch(self, source: ModelMaterialSource) -> bytes:
        """Fetch exactly one host-authorized locked source."""

        raise NotImplementedError


@dataclass(frozen=True)
class HostMaterialPolicy:
    """Receiver-local authorization for sealed material cache misses."""

    allow_download: bool
    allow_preparation: bool


@dataclass(frozen=True)
class ModelPreparationProvider:
    """One receiver-installed deterministic preparation capability."""

    provider_id: str
    contract: MaterialContract
    contract_digest: str
    prepare: Callable[[PreparationOperation, Mapping[str, bytes]], bytes]


@dataclass(frozen=True)
class VerifiedModelMaterials:
    """Private verified byte artifacts for one exact lock identity."""

    lock_digest: str
    artifacts: Mapping[str, bytes]

    def __post_init__(self) -> None:
        object.__setattr__(self, "artifacts", MappingProxyType(dict(self.artifacts)))


class ModelMaterialAdmission:
    """Materialize only a sealed lock through receiver-owned collaborators."""

    def __init__(
        self,
        *,
        cache: ModelMaterialCache,
        transport: ModelMaterialTransport,
        providers: Sequence[ModelPreparationProvider],
        selected_provider_ids: Sequence[str],
        revalidate_selected: Callable[[Sequence[str]], bool],
        policy: HostMaterialPolicy,
    ) -> None:
        self._cache = cache
        self._transport = transport
        self._providers = tuple(providers)
        self._selected_provider_ids = tuple(selected_provider_ids)
        self._revalidate_selected = revalidate_selected
        self._policy = policy

    def materialize(
        self,
        *,
        lock: ModelDependencyLock,
        requirements: CapabilityRequirements,
    ) -> VerifiedModelMaterials:
        """Revalidate, then cache, download, and prepare exact locked artifacts."""

        providers = self._validate(lock, requirements)
        if not self._revalidate_selected(self._selected_provider_ids):
            raise ModelMaterialAdmissionError("material_unavailable")
        artifacts = {source.role: self._source(lock, source) for source in lock.sources}
        for operation, provider in zip(lock.preparation, providers, strict=True):
            artifacts[operation.output.role] = self._prepared(
                lock, operation, provider, artifacts
            )
        return VerifiedModelMaterials(lock.digest, artifacts)

    def _validate(
        self,
        lock: ModelDependencyLock,
        requirements: CapabilityRequirements,
    ) -> tuple[ModelPreparationProvider, ...]:
        if "runner" not in requirements.bindings:
            raise ModelMaterialAdmissionError("material_unavailable")
        requirements_by_id = {
            requirement.capability_id: requirement
            for requirement in requirements.required_capabilities
        }
        providers: list[ModelPreparationProvider] = []
        for operation in lock.preparation:
            requirement = requirements_by_id.get(operation.capability_id)
            provider = next(
                (
                    item
                    for item in self._providers
                    if item.provider_id in self._selected_provider_ids
                    and item.contract.contract_id == operation.capability_id
                    and item.contract.version == operation.contract_version
                    and item.contract_digest == operation.contract_digest
                ),
                None,
            )
            if (
                requirement is None
                or requirement.contract_version != operation.contract_version
                or requirement.contract_digest != operation.contract_digest
                or provider is None
            ):
                raise ModelMaterialAdmissionError("material_unavailable")
            providers.append(provider)
        return tuple(providers)

    def _source(self, lock: ModelDependencyLock, source: ModelMaterialSource) -> bytes:
        cached = self._cache.load(
            lock_digest=lock.digest, role=source.role, transformation_digest=None
        )
        if cached is not None and _matches(cached, source.sha256):
            return cached
        if not self._policy.allow_download:
            raise ModelMaterialAdmissionError("host_policy_denied")
        try:
            content = self._transport.fetch(source)
        except Exception as error:  # noqa: BLE001 - transport errors stay redacted.
            raise ModelMaterialAdmissionError("material_unavailable") from error
        if not _matches(content, source.sha256):
            raise ModelMaterialAdmissionError("material_integrity_failed")
        self._cache.promote(
            lock_digest=lock.digest,
            role=source.role,
            transformation_digest=None,
            content=content,
        )
        return content

    def _prepared(
        self,
        lock: ModelDependencyLock,
        operation: PreparationOperation,
        provider: ModelPreparationProvider,
        artifacts: Mapping[str, bytes],
    ) -> bytes:
        cached = self._cache.load(
            lock_digest=lock.digest,
            role=operation.output.role,
            transformation_digest=operation.transformation_digest,
        )
        if cached is not None and _matches(cached, operation.output.sha256):
            return cached
        if not self._policy.allow_preparation:
            raise ModelMaterialAdmissionError("host_policy_denied")
        try:
            inputs = {role: artifacts[role] for role in operation.inputs}
            content = provider.prepare(operation, inputs)
        except Exception as error:  # noqa: BLE001 - provider errors stay redacted.
            raise ModelMaterialAdmissionError("material_preparation_failed") from error
        if not _matches(content, operation.output.sha256):
            raise ModelMaterialAdmissionError("material_integrity_failed")
        self._cache.promote(
            lock_digest=lock.digest,
            role=operation.output.role,
            transformation_digest=operation.transformation_digest,
            content=content,
        )
        return content


def _matches(content: bytes, expected_digest: str) -> bool:
    return hashlib.sha256(content).hexdigest() == expected_digest
