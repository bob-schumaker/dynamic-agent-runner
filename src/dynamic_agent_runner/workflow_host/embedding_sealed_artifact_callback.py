"""Receiver-owned JSON bridge for one sealed embedding callback."""

from __future__ import annotations

import json
from hashlib import sha256
from collections.abc import Mapping, Sequence
from typing import Protocol

from jsonschema import Draft202012Validator, SchemaError, ValidationError

from dynamic_agent_runner.workflow_host.embedding_execution import (
    EmbeddingBatchLimits,
    EmbeddingExecutionBinding,
    EmbeddingTextItem,
    EmbeddingLimitProjectorRegistry,
)
from dynamic_agent_runner.workflow_host.capabilities import (
    selected_provider_id_for_requirement,
)
from dynamic_agent_runner.workflow_host.sealed_artifact_runner import (
    SealedArtifactCallback,
    SealedArtifactRunnerDescriptor,
)


class EmbeddingSealedArtifactCallbackError(ValueError):
    """Raised without exposing embedding requests, vectors, or provider detail."""


class _EmbeddingExecution(Protocol):
    def execute(
        self,
        *,
        binding: EmbeddingExecutionBinding,
        selected_provider_ids: Sequence[str],
        package_limits: EmbeddingBatchLimits,
        items: Sequence[EmbeddingTextItem],
    ) -> tuple[object, ...]: ...


class EmbeddingSealedArtifactCallbackProvider:
    """Translate one fixed sealed JSON callback to host-owned embedding execution."""

    def __init__(
        self,
        *,
        callback: SealedArtifactCallback,
        execution: _EmbeddingExecution,
        binding: EmbeddingExecutionBinding,
        selected_provider_ids: Sequence[str],
        limits: EmbeddingBatchLimits,
        request_schema: object,
        response_schema: object,
    ) -> None:
        if (
            callback.requirement != "embedding.execute.v1"
            or not callable(getattr(execution, "execute", None))
            or not selected_provider_ids
        ):
            raise EmbeddingSealedArtifactCallbackError(
                "embedding callback is unavailable"
            )
        try:
            Draft202012Validator.check_schema(request_schema)
            Draft202012Validator.check_schema(response_schema)
        except SchemaError as error:
            raise EmbeddingSealedArtifactCallbackError(
                "embedding callback is unavailable"
            ) from error
        self._callback = callback
        self._execution = execution
        self._binding = binding
        self._selected_provider_ids = tuple(selected_provider_ids)
        self._limits = limits
        self._request_schema = request_schema
        self._response_schema = response_schema

    def revalidate(self, callback: SealedArtifactCallback) -> None:
        if callback != self._callback:
            raise EmbeddingSealedArtifactCallbackError(
                "embedding callback is unavailable"
            )

    def invoke(self, name: str, request: bytes) -> bytes:
        if name != self._callback.name:
            raise EmbeddingSealedArtifactCallbackError(
                "embedding callback is unavailable"
            )
        try:
            value = json.loads(request.decode("utf-8"), object_pairs_hook=_unique)
            if not isinstance(value, Mapping) or set(value) != {"items"}:
                raise ValueError
            if (
                json.dumps(value, separators=(",", ":"), sort_keys=True).encode()
                != request
            ):
                raise ValueError
            Draft202012Validator(self._request_schema).validate(value)
            items = tuple(
                EmbeddingTextItem(item["id"], item["text"])
                for item in value["items"]
                if isinstance(item, Mapping) and set(item) == {"id", "text"}
            )
            if len(items) != len(value["items"]):
                raise ValueError
            vectors = self._execution.execute(
                binding=self._binding,
                selected_provider_ids=self._selected_provider_ids,
                package_limits=self._limits,
                items=items,
            )
            response = {
                "items": [
                    {"id": item.item_id, "vector": list(item.values)}
                    for item in vectors
                ]
            }
            Draft202012Validator(self._response_schema).validate(response)
            return json.dumps(response, separators=(",", ":"), sort_keys=True).encode()
        except (SchemaError, ValidationError, ValueError, TypeError) as error:
            raise EmbeddingSealedArtifactCallbackError(
                "embedding callback is unavailable"
            ) from error


def _unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value = dict(pairs)
    if len(value) != len(pairs):
        raise ValueError
    return value


class EmbeddingSealedArtifactCallbackResolver:
    """Resolve only the exact embedding callback already admitted by policy."""

    def __init__(
        self,
        *,
        execution: _EmbeddingExecution,
        limit_projectors: EmbeddingLimitProjectorRegistry,
    ) -> None:
        self._execution = execution
        self._limit_projectors = limit_projectors

    def resolve(
        self,
        descriptor: SealedArtifactRunnerDescriptor,
        policy: object,
        _revision: object,
    ) -> EmbeddingSealedArtifactCallbackProvider:
        try:
            binding = policy.embedding_execution_binding
            execution_descriptor = policy.execution_descriptor
            requirements = policy.capability_requirements
            selected = tuple(policy.selected_capability_provider_ids)
            callbacks = [
                callback
                for callback in descriptor.callbacks
                if callback.requirement == "embedding.execute.v1"
            ]
            if (
                not isinstance(binding, EmbeddingExecutionBinding)
                or len(callbacks) != 1
            ):
                raise ValueError
            selected_provider_id_for_requirement(
                requirements=requirements,
                selected_provider_ids=selected,
                capability_id="embedding.execute.v1",
            )
            limits = self._limit_projectors.project(execution_descriptor)
            request_schema, response_schema = _callback_schemas(
                descriptor, callbacks[0]
            )
            return EmbeddingSealedArtifactCallbackProvider(
                callback=callbacks[0],
                execution=self._execution,
                binding=binding,
                selected_provider_ids=selected,
                limits=limits,
                request_schema=request_schema,
                response_schema=response_schema,
            )
        except Exception as error:  # noqa: BLE001 - redacted receiver boundary.
            raise EmbeddingSealedArtifactCallbackError(
                "embedding callback is unavailable"
            ) from error


def _callback_schemas(
    descriptor: SealedArtifactRunnerDescriptor, callback: SealedArtifactCallback
) -> tuple[object, object]:
    """Resolve the callback's exact retained child contract and schema assets."""

    contracts = [
        contract
        for contract in descriptor.child_contracts
        if contract.digest == callback.child_contract_digest
    ]
    if len(contracts) != 1:
        raise ValueError
    contract = contracts[0]
    if sha256(contract.canonical_bytes).hexdigest() != contract.digest:
        raise ValueError
    value = json.loads(
        contract.canonical_bytes.decode("utf-8"), object_pairs_hook=_unique
    )
    if (
        not isinstance(value, Mapping)
        or json.dumps(value, separators=(",", ":"), sort_keys=True).encode()
        != contract.canonical_bytes
        or set(value)
        != {"body", "callback_name", "capability_requirement", "format_version"}
        or value["format_version"] != 1
        or value["callback_name"] != callback.name
        or value["capability_requirement"] != callback.requirement
        or not isinstance(value["body"], Mapping)
        or set(value["body"])
        != {"embed_request_schema_digest", "embed_response_schema_digest"}
    ):
        raise ValueError
    request_digest = value["body"]["embed_request_schema_digest"]
    response_digest = value["body"]["embed_response_schema_digest"]
    schemas = {schema.digest: schema.document for schema in descriptor.schema_assets}
    if (
        not isinstance(request_digest, str)
        or not isinstance(response_digest, str)
        or request_digest == response_digest
        or request_digest not in schemas
        or response_digest not in schemas
        or schemas[request_digest] is None
        or schemas[response_digest] is None
    ):
        raise ValueError
    return schemas[request_digest], schemas[response_digest]
