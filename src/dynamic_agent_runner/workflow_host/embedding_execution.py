"""Host-owned validation for one exact embedding capability execution."""

from __future__ import annotations

import math
import re
from hashlib import sha256
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Protocol

from dynamic_agent_runner.local_models import EmbeddingInputItem
from dynamic_agent_runner.workflow_host.capabilities import (
    CapabilityContract,
    CapabilityRequirements,
)
from dynamic_agent_runner.workflow_host.model_execution_binding import (
    ModelExecutionBinding,
)
from dynamic_agent_runner.workflow_host.execution_descriptors import (
    ExecutionDescriptor,
    ExecutionDescriptorAbi,
)


_EMBEDDING_CAPABILITY_ID = "embedding.execute.v1"
_OPAQUE_ID = re.compile(r"[A-Za-z0-9_-]{1,128}")


class EmbeddingExecutionBindingError(ValueError):
    """Raised with a redacted embedding admission or result classification."""


@dataclass(frozen=True)
class EmbeddingBatchLimits:
    """Positive package or host bounds for one embedding batch."""

    max_items: int
    max_item_utf8_bytes: int
    max_total_utf8_bytes: int
    max_vector_dimension: int
    max_total_vectors: int

    def __post_init__(self) -> None:
        if any(
            not _positive(value)
            for value in (
                self.max_items,
                self.max_item_utf8_bytes,
                self.max_total_utf8_bytes,
                self.max_vector_dimension,
                self.max_total_vectors,
            )
        ):
            raise EmbeddingExecutionBindingError("embedding batch limits are invalid")


@dataclass(frozen=True)
class EmbeddingLimitProjectorBinding:
    """One exact receiver-owned ABI projection to private embedding limits."""

    identity: ExecutionDescriptorAbi
    projector: Callable[[ExecutionDescriptor], EmbeddingBatchLimits]

    def __post_init__(self) -> None:
        if not isinstance(self.identity, ExecutionDescriptorAbi) or not callable(
            self.projector
        ):
            raise EmbeddingExecutionBindingError(
                "embedding limit projector is unavailable"
            )


class EmbeddingLimitProjectorRegistry:
    """Resolve limits only through one exact receiver-installed embedding ABI."""

    def __init__(self, bindings: Sequence[EmbeddingLimitProjectorBinding]) -> None:
        resolved: dict[ExecutionDescriptorAbi, EmbeddingLimitProjectorBinding] = {}
        for binding in bindings:
            if (
                not isinstance(binding, EmbeddingLimitProjectorBinding)
                or binding.identity in resolved
            ):
                raise EmbeddingExecutionBindingError(
                    "embedding limit projector is unavailable"
                )
            resolved[binding.identity] = binding
        self._bindings = resolved

    def project(self, descriptor: ExecutionDescriptor) -> EmbeddingBatchLimits:
        """Project one already-admitted exact ABI descriptor without material work."""

        if not isinstance(descriptor, ExecutionDescriptor):
            raise EmbeddingExecutionBindingError("embedding limits are unavailable")
        binding = self._bindings.get(descriptor.architecture_abi)
        if binding is None:
            raise EmbeddingExecutionBindingError("embedding limits are unavailable")
        try:
            limits = binding.projector(descriptor)
        except Exception as error:  # noqa: BLE001 - receiver ABI boundary.
            raise EmbeddingExecutionBindingError(
                "embedding limits are unavailable"
            ) from error
        if not isinstance(limits, EmbeddingBatchLimits):
            raise EmbeddingExecutionBindingError("embedding limits are unavailable")
        return limits


@dataclass(frozen=True)
class EmbeddingTextItem:
    """One opaque caller ID and its private UTF-8 text."""

    item_id: str
    text: str


@dataclass(frozen=True)
class EmbeddingVector:
    """One opaque caller ID and its finite embedding vector."""

    item_id: str
    values: tuple[float, ...]


@dataclass(frozen=True)
class EmbeddingExecutionBinding:
    """Exact private material, runner, and embedding capability identity."""

    model_binding: ModelExecutionBinding
    capability_id: str
    capability_contract_version: str
    capability_contract_digest: str

    @property
    def material_lock_digest(self) -> str:
        """Return the locked material identity for result binding."""

        return self.model_binding.material_lock_digest

    @property
    def digest(self) -> str:
        """Return the sealed host-private embedding execution identity."""

        return sha256(
            (
                self.model_binding.digest
                + self.capability_id
                + self.capability_contract_version
                + self.capability_contract_digest
            ).encode("utf-8")
        ).hexdigest()


class EmbeddingProvider(Protocol):
    """Receiver-local provider; its identity is never package data."""

    provider_id: str
    contract: CapabilityContract
    deterministic: bool
    model_binding: ModelExecutionBinding

    def embed(
        self,
        *,
        binding: EmbeddingExecutionBinding,
        items: tuple[EmbeddingTextItem, ...],
    ) -> tuple[EmbeddingVector, ...]:
        """Embed exactly the supplied validated ordered batch."""


class LocalEmbeddingAdapter(Protocol):
    """Existing direct local adapter shape, supplied only by the receiver host."""

    def embed(self, items: Sequence[EmbeddingInputItem]) -> object:
        """Embed items through a receiver-configured local adapter."""


@dataclass(frozen=True)
class LocalEmbeddingAdapterProvider:
    """Adapt a receiver-owned direct embedding adapter to the generic seam."""

    provider_id: str
    contract: CapabilityContract
    adapter: LocalEmbeddingAdapter
    model_binding: ModelExecutionBinding
    deterministic: bool = True

    def embed(
        self,
        *,
        binding: EmbeddingExecutionBinding,
        items: tuple[EmbeddingTextItem, ...],
    ) -> tuple[EmbeddingVector, ...]:
        """Call the existing adapter without exposing its configuration to a package."""

        result = self.adapter.embed(
            tuple(EmbeddingInputItem(id=item.item_id, text=item.text) for item in items)
        )
        raw_items = getattr(result, "items", None)
        if not isinstance(raw_items, tuple):
            return ()
        vectors: list[EmbeddingVector] = []
        for item in raw_items:
            item_id = getattr(item, "id", None)
            values = getattr(item, "vector", None)
            if not isinstance(item_id, str) or not isinstance(values, tuple):
                return ()
            vectors.append(EmbeddingVector(item_id, values))
        return tuple(vectors)


class EmbeddingProviderCatalog:
    """Private receiver catalog for exact, deterministic embedding providers."""

    def __init__(self, providers: Sequence[EmbeddingProvider]) -> None:
        resolved: dict[str, EmbeddingProvider] = {}
        for provider in providers:
            try:
                provider_id = provider.provider_id
                model_binding = provider.model_binding
            except Exception as error:  # noqa: BLE001 - receiver provider boundary.
                raise EmbeddingExecutionBindingError(
                    "embedding provider is unavailable"
                ) from error
            if (
                not isinstance(provider_id, str)
                or not provider_id
                or provider_id in resolved
                or not isinstance(model_binding, ModelExecutionBinding)
            ):
                raise EmbeddingExecutionBindingError(
                    "embedding provider is unavailable"
                )
            resolved[provider_id] = provider
        self._providers = resolved

    def resolve(
        self,
        binding: EmbeddingExecutionBinding,
        *,
        selected_provider_ids: Sequence[str],
    ) -> EmbeddingProvider:
        """Return only the one provider selected by earlier capability admission."""

        if len(selected_provider_ids) != 1:
            raise EmbeddingExecutionBindingError("embedding provider is unavailable")
        provider = self._providers.get(selected_provider_ids[0])
        try:
            compatible = (
                provider is not None
                and provider.deterministic
                and provider.model_binding == binding.model_binding
                and provider.contract.capability_id == binding.capability_id
                and provider.contract.contract_version
                == binding.capability_contract_version
                and provider.contract.contract_digest
                == binding.capability_contract_digest
            )
        except Exception:  # noqa: BLE001 - receiver provider boundary.
            compatible = False
        if not compatible:
            raise EmbeddingExecutionBindingError("embedding provider is unavailable")
        return provider


class EmbeddingExecutionService:
    """Execute one bounded host-selected embedding batch with strict validation."""

    def __init__(
        self, *, providers: EmbeddingProviderCatalog, host_limits: EmbeddingBatchLimits
    ) -> None:
        self._providers = providers
        self._host_limits = host_limits

    def execute(
        self,
        *,
        binding: EmbeddingExecutionBinding,
        selected_provider_ids: Sequence[str],
        package_limits: EmbeddingBatchLimits,
        items: Sequence[EmbeddingTextItem],
    ) -> tuple[EmbeddingVector, ...]:
        """Validate, execute, and validate one exact deterministic batch."""

        _validate_limits(package_limits, self._host_limits)
        normalized = tuple(items)
        _validate_items(normalized, package_limits)
        provider = self._providers.resolve(
            binding, selected_provider_ids=selected_provider_ids
        )
        try:
            result = provider.embed(binding=binding, items=normalized)
        except Exception as error:  # noqa: BLE001 - providers have varied internals.
            raise EmbeddingExecutionBindingError(
                "embedding execution failed"
            ) from error
        _validate_result(result, normalized, package_limits)
        return result


def derive_embedding_execution_binding(
    *,
    model_binding: ModelExecutionBinding,
    requirements: CapabilityRequirements,
) -> EmbeddingExecutionBinding:
    """Derive an exact embedding binding from sealed generic contracts only."""

    requirement = next(
        (
            item
            for item in requirements.required_capabilities
            if item.capability_id == _EMBEDDING_CAPABILITY_ID
        ),
        None,
    )
    if requirement is None or "deterministic" not in requirement.required_features:
        raise EmbeddingExecutionBindingError("embedding capability is unavailable")
    return EmbeddingExecutionBinding(
        model_binding,
        requirement.capability_id,
        requirement.contract_version,
        requirement.contract_digest,
    )


def _validate_limits(
    package_limits: EmbeddingBatchLimits, host_limits: EmbeddingBatchLimits
) -> None:
    if any(
        package > host
        for package, host in zip(
            (
                package_limits.max_items,
                package_limits.max_item_utf8_bytes,
                package_limits.max_total_utf8_bytes,
                package_limits.max_vector_dimension,
                package_limits.max_total_vectors,
            ),
            (
                host_limits.max_items,
                host_limits.max_item_utf8_bytes,
                host_limits.max_total_utf8_bytes,
                host_limits.max_vector_dimension,
                host_limits.max_total_vectors,
            ),
            strict=True,
        )
    ):
        raise EmbeddingExecutionBindingError("embedding batch exceeds host limits")


def _validate_items(
    items: tuple[EmbeddingTextItem, ...], limits: EmbeddingBatchLimits
) -> None:
    if (
        not items
        or len(items) > limits.max_items
        or len(items) > limits.max_total_vectors
    ):
        raise EmbeddingExecutionBindingError("embedding batch is invalid")
    identifiers: list[str] = []
    total_bytes = 0
    for item in items:
        if (
            not isinstance(item, EmbeddingTextItem)
            or not _OPAQUE_ID.fullmatch(item.item_id)
            or not isinstance(item.text, str)
        ):
            raise EmbeddingExecutionBindingError("embedding batch is invalid")
        try:
            encoded = item.text.encode("utf-8")
        except UnicodeEncodeError as error:
            raise EmbeddingExecutionBindingError(
                "embedding batch is invalid"
            ) from error
        if len(encoded) > limits.max_item_utf8_bytes:
            raise EmbeddingExecutionBindingError("embedding batch is invalid")
        identifiers.append(item.item_id)
        total_bytes += len(encoded)
    if (
        len(set(identifiers)) != len(identifiers)
        or total_bytes > limits.max_total_utf8_bytes
    ):
        raise EmbeddingExecutionBindingError("embedding batch is invalid")


def _validate_result(
    result: object,
    items: tuple[EmbeddingTextItem, ...],
    limits: EmbeddingBatchLimits,
) -> None:
    if not isinstance(result, tuple) or len(result) != len(items):
        raise EmbeddingExecutionBindingError("embedding result is invalid")
    expected_ids = tuple(item.item_id for item in items)
    dimensions: set[int] = set()
    for expected_id, vector in zip(expected_ids, result, strict=True):
        if (
            not isinstance(vector, EmbeddingVector)
            or vector.item_id != expected_id
            or not vector.values
            or len(vector.values) > limits.max_vector_dimension
            or any(
                not isinstance(value, int | float)
                or isinstance(value, bool)
                or not math.isfinite(value)
                for value in vector.values
            )
        ):
            raise EmbeddingExecutionBindingError("embedding result is invalid")
        dimensions.add(len(vector.values))
    if len(dimensions) != 1:
        raise EmbeddingExecutionBindingError("embedding result is invalid")


def _positive(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0
