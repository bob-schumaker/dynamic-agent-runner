"""Generic local Transformers + PEFT single-image model adapter."""

from __future__ import annotations

import json
import secrets
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import Protocol

from dynamic_agent_runner.errors import ModelExecutionError
from dynamic_agent_runner.local_model_preparation import (
    PreparedArtifactSet,
    TRANSFORMERS_PEFT_SINGLE_IMAGE_V1,
    _valid_loader_profile,
)
from dynamic_agent_runner.multimodal_model_runner import (
    DARGenerationRequestContext,
    MultimodalRunnerDescriptor,
    MultimodalRunnerHealth,
    MultimodalRunnerResult,
    SealedMultimodalInputMaterializer,
    SealedMultimodalRequest,
)
from dynamic_agent_runner.openai_client import (
    ModelResponse,
    OpenAIModelRequest,
    build_openai_request,
)
from dynamic_agent_runner.workflow_host.capabilities import CapabilityContract
from dynamic_agent_runner.workflow_host.descriptor import DeclaredInputConverter
from dynamic_agent_runner.workflow_host.execution_descriptors import (
    ExecutionDescriptorAbi,
)
from dynamic_agent_runner.workflow_host.generation_resource_budgets import (
    GenerationRunnerCapability,
    GenerationResourceBudget,
    GenerationResourceBudgetError,
    GenerationExecutionHostPolicy,
    GenerationDeadline,
    GenerationMemoryReservationRequest,
    resolve_generation_resource_budget,
    reserve_generation_memory,
    validate_generation_budget_field,
)
from dynamic_agent_runner.workflow_host.generation_worker import (
    GenerationWorkerDeadlineExceeded,
    GenerationWorkerExecutionFailed,
    GenerationWorkerLaunchDescriptor,
    GenerationWorkerLauncher,
    GenerationWorkerOutputLimitExceeded,
    GenerationWorkerPackReceipt,
    GenerationWorkerProtocolError,
    GenerationWorkerSession,
)
from dynamic_agent_runner.workflow_host.generation_worker_assets import (
    GenerationWorkerCoLocatedAssets,
)


TRANSFORMERS_GENERATE_V1 = "transformers-generate-v1"
TRANSFORMERS_PEFT_GENERATION_V1_ABI = ExecutionDescriptorAbi(
    "transformers-peft-generation-v1",
    "1",
    "572b21f33b158466c1fee84d34a12770b91b62d9f031551e0d212aec9b8491d6",
)
TRANSFORMERS_GENERATE_MODEL_EXECUTION_CONTRACT = CapabilityContract(
    "model.execution.transformers-generate.v1",
    "1",
    "11f1e124898e8adb5f726b144235772def3ce41f23219d1e212b527834b9750b",
    (),
)
TRANSFORMERS_GENERATE_CONVERTER_CONTRACT = CapabilityContract(
    "model.converter.transformers-generate.v1",
    "1",
    "174e0315b88cd532806cac20f43f9c80cdea6ba99fbcc94dae6274613ecf5059",
    (),
)
TRANSFORMERS_GENERATE_CAPABILITY = GenerationRunnerCapability(
    runner_id=TRANSFORMERS_GENERATE_V1,
    max_effective_context_tokens=1_000_000,
    memory_admission_method="conservative_reservation",
    pre_packing_containment_method="runtime_allocation_limit",
    supported_execution_devices=frozenset({"cpu", "mps"}),
    worker_protocol="generation-worker-v1",
    bootstrap_hard_limit_method="runtime_allocation_limit",
    generation_hard_limit_method="runtime_allocation_limit",
)
_CONTINUATION_INSTRUCTION = (
    "Continue the exact response from where it stopped. Return only the remaining text."
)


def _shape_worker_protocol_error(
    error: GenerationWorkerProtocolError,
) -> ModelExecutionError:
    if isinstance(error, GenerationWorkerOutputLimitExceeded):
        return ModelExecutionError("model generation output limit exceeded")
    return ModelExecutionError("generation worker protocol invalid")


class TransformersPeftBackend(Protocol):
    """Minimal normalized generation boundary for the standard runner."""

    def generate(self, prompt: str, image: object, *, max_new_tokens: int) -> str:
        """Generate one text response from one in-memory image."""


class TransformersGenerateBackend(Protocol):
    """Private packed-input boundary for the standard runner."""

    @property
    def processor(self) -> object:
        """Return the reviewed processor used by the compatible converter."""

    def generate_packed(
        self, inputs: object, *, max_new_tokens: int, json_mode: bool = False
    ) -> str | GeneratedText:
        """Generate one response from converter-packed framework inputs."""


class PackedInputConverter(Protocol):
    """One workflow-bound converter compatible with the standard runner."""

    def pack(
        self,
        *,
        messages: tuple[Mapping[str, object], ...],
        payload: bytes,
        context: TransformersGenerateInputContext,
    ) -> PackedModelInput:
        """Return one private packed input for the compatible runner."""


@dataclass(frozen=True)
class GeneratedText:
    """One private generated fragment with its token-ceiling outcome."""

    content: str
    exhausted: bool
    generated_tokens: int | None = None
    runner_max_new_tokens: int | None = None
    backend_max_new_tokens: int | None = None


@dataclass(frozen=True)
class GenerationDebugFragment:
    """One content-free debug fact record for an admitted fragment."""

    fragment_index: int
    exhausted: bool
    generated_tokens: int | None
    output_bytes: int
    packed_context_tokens: int | None = None
    elapsed_milliseconds: int | None = None
    stop_classification: str | None = None
    worker_reaped: bool | None = None


@dataclass(frozen=True)
class GeneratedCompletion:
    """One assembled completion with safe generation metadata."""

    content: str
    metadata: Mapping[str, object]


DependencyLoader = Callable[[Path, Path], TransformersPeftBackend]
PackedDependencyLoader = Callable[[Path, Path], TransformersGenerateBackend]
ProcessorLoader = Callable[[Path], object]
ImageDecoder = Callable[[bytes], object]


class PackedModelInput:
    """One worker-private packed input that the runner consumes exactly once."""

    def __init__(self, inputs: object) -> None:
        self._inputs: object | None = inputs

    @property
    def is_cleared(self) -> bool:
        """Return whether this private input has been disposed."""

        return self._inputs is None

    def take(self) -> object:
        """Return the packed value until the runner clears it."""

        if self._inputs is None:
            raise ModelExecutionError("packed model input is unavailable")
        return self._inputs

    def clear(self) -> None:
        """Discard the private packed framework value."""

        self._inputs = None


class TransformersGenerateInputContext:
    """Restricted processor and packing facilities for a compatible converter."""

    def __init__(self, processor: object) -> None:
        self._processor = processor

    @property
    def processor(self) -> object:
        """Return the reviewed processor for this exact prepared model set."""

        return self._processor

    def pack(self, inputs: object) -> PackedModelInput:
        """Wrap one processor-produced value for the standard runner."""

        return PackedModelInput(inputs)


class TransformersGenerateRunner:
    """Run one verified Transformers + PEFT set from private packed inputs."""

    contract_id = TRANSFORMERS_GENERATE_V1
    supports_json_mode = True
    supports_generation_resource_budgets = True

    def __init__(
        self,
        prepared_set: PreparedArtifactSet,
        *,
        dependency_loader: PackedDependencyLoader | None = None,
        processor_loader: ProcessorLoader | None = None,
    ) -> None:
        self._base, self._adapter = _verified_prepared_paths(prepared_set)
        self._dependency_loader = dependency_loader or _load_default_backend
        self._processor_loader = processor_loader
        self._backend: TransformersGenerateBackend | None = None
        self._processor: object | None = None

    @property
    def processor(self) -> object:
        """Expose the reviewed processor and no model-loading controls."""

        if self._processor_loader is None:
            return self._get_backend().processor
        if self._processor is None:
            try:
                self._processor = self._processor_loader(self._base)
            except ImportError as error:
                raise ModelExecutionError(
                    "Transformers + PEFT dependencies unavailable"
                ) from error
        return self._processor

    @property
    def input_context(self) -> TransformersGenerateInputContext:
        """Return the restricted converter context for this runner."""

        return TransformersGenerateInputContext(self.processor)

    def generate(
        self,
        packed_input: PackedModelInput,
        *,
        max_new_tokens: int,
        json_mode: bool = False,
    ) -> str:
        """Consume one packed input and clear it on every exit path."""

        generated = self.generate_chunk(
            packed_input,
            max_new_tokens=max_new_tokens,
            json_mode=json_mode,
        )
        completion = generated.content.strip()
        return _validated_json_object(completion) if json_mode else completion

    def generate_chunk(
        self,
        packed_input: PackedModelInput,
        *,
        max_new_tokens: int,
        json_mode: bool = False,
        budget: GenerationResourceBudget | None = None,
    ) -> GeneratedText:
        """Generate one private fragment and report whether it hit its ceiling."""

        try:
            _validate_max_new_tokens(max_new_tokens)
            _validate_packed_generation_budget(
                packed_input, max_new_tokens=max_new_tokens, budget=budget
            )
            backend = self._get_backend()
            if json_mode:
                generated = backend.generate_packed(
                    packed_input.take(),
                    max_new_tokens=max_new_tokens,
                    json_mode=True,
                )
            else:
                generated = backend.generate_packed(
                    packed_input.take(), max_new_tokens=max_new_tokens
                )
            generated_text = _generated_text(generated)
            return GeneratedText(
                generated_text.content,
                generated_text.exhausted,
                generated_text.generated_tokens,
                runner_max_new_tokens=max_new_tokens,
                backend_max_new_tokens=generated_text.backend_max_new_tokens,
            )
        except ModelExecutionError:
            raise
        except Exception as error:  # noqa: BLE001 - backend errors vary.
            raise ModelExecutionError("local model generation failed") from error
        finally:
            packed_input.clear()

    def _get_backend(self) -> TransformersGenerateBackend:
        if self._backend is None:
            try:
                self._backend = self._dependency_loader(self._base, self._adapter)
            except ImportError as error:
                raise ModelExecutionError(
                    "Transformers + PEFT dependencies unavailable"
                ) from error
        return self._backend

    @property
    def uses_mps(self) -> bool:
        """Return whether the loaded backend selected the Apple MPS device."""

        return bool(getattr(self._get_backend(), "uses_mps", False))


class TransformersPeftGenerationWorkerRuntime:
    """Child-private converter, packed input, and compatible runner state."""

    def __init__(
        self,
        *,
        assets: GenerationWorkerCoLocatedAssets,
        converter: PackedInputConverter,
        runner: TransformersGenerateRunner,
    ) -> None:
        self._assets = assets
        self._converter = converter
        self._runner = runner
        self._packed: PackedModelInput | None = None
        self._remaining_generated_tokens: int | None = None

    def install_bootstrap_limit(
        self, max_memory_bytes: int, execution_device: str
    ) -> None:
        if (
            not isinstance(max_memory_bytes, int)
            or isinstance(max_memory_bytes, bool)
            or max_memory_bytes < 1
            or execution_device
            not in TRANSFORMERS_GENERATE_CAPABILITY.supported_execution_devices
        ):
            raise ModelExecutionError("model generation budget is unavailable")

    def pack(self) -> int:
        if self._packed is not None:
            raise ModelExecutionError("packed model input is unavailable")
        packed = self._converter.pack(
            messages=self._assets.messages,
            payload=self._assets.sealed_payload,
            context=self._runner.input_context,
        )
        if not isinstance(packed, PackedModelInput):
            raise ModelExecutionError("packed model input is unavailable")
        inputs = packed.take()
        input_ids = inputs.get("input_ids") if isinstance(inputs, Mapping) else None
        shape = getattr(input_ids, "shape", None)
        if (
            not isinstance(shape, Sequence)
            or len(shape) < 2
            or not isinstance(shape[-1], int)
            or isinstance(shape[-1], bool)
            or shape[-1] < 0
        ):
            packed.clear()
            raise ModelExecutionError("model generation context is unavailable")
        self._packed = packed
        return shape[-1]

    def authorize(
        self, receipt: GenerationWorkerPackReceipt, remaining_generated_tokens: int
    ) -> None:
        if (
            self._packed is None
            or not isinstance(receipt, GenerationWorkerPackReceipt)
            or not isinstance(remaining_generated_tokens, int)
            or isinstance(remaining_generated_tokens, bool)
            or remaining_generated_tokens < 1
        ):
            raise ModelExecutionError("generation worker protocol invalid")
        self._remaining_generated_tokens = remaining_generated_tokens

    def generate(self) -> tuple[bytes, int, int, int, bool]:
        packed = self._packed
        remaining_generated_tokens = self._remaining_generated_tokens
        self._packed = None
        self._remaining_generated_tokens = None
        if packed is None or remaining_generated_tokens is None:
            raise ModelExecutionError("generation worker protocol invalid")
        try:
            generated = self._runner.generate_chunk(
                packed,
                max_new_tokens=remaining_generated_tokens,
                json_mode=self._assets.json_mode,
            )
            generated_tokens = generated.generated_tokens
            if (
                not isinstance(generated_tokens, int)
                or isinstance(generated_tokens, bool)
                or generated_tokens < 0
                or generated_tokens > remaining_generated_tokens
            ):
                raise ModelExecutionError("generation worker protocol invalid")
            candidate = generated.content.encode("utf-8")
            return (
                candidate,
                generated_tokens,
                generated_tokens,
                len(candidate),
                generated.exhausted,
            )
        finally:
            packed.clear()


class TransformersPeftGenerationWorkerRuntimeFactory:
    """Receiver-installed child constructor for the Transformers conformance fixture."""

    def create_runtime(
        self, *, assets: GenerationWorkerCoLocatedAssets, converter: object
    ) -> TransformersPeftGenerationWorkerRuntime:
        if not isinstance(assets, GenerationWorkerCoLocatedAssets) or not callable(
            getattr(converter, "pack", None)
        ):
            raise ModelExecutionError("generation worker protocol invalid")
        return TransformersPeftGenerationWorkerRuntime(
            assets=assets,
            converter=converter,
            runner=TransformersGenerateRunner(
                assets.prepared_set, processor_loader=_load_default_processor
            ),
        )


class TransformersPeftPackedInputAdapter:
    """Expose one converter-bound Transformers generation runner as an adapter."""

    input_converter_contract_id = TRANSFORMERS_GENERATE_V1

    def __init__(
        self,
        prepared_set: PreparedArtifactSet,
        *,
        converter: PackedInputConverter,
        runner: TransformersGenerateRunner | None = None,
        generation_budget: GenerationResourceBudget | None = None,
        generation_material_lock_digest: str | None = None,
        generation_host_policy: GenerationExecutionHostPolicy | None = None,
    ) -> None:
        _verified_prepared_paths(prepared_set)
        self._model_id = prepared_set.recipe.model_id
        self._adapter_id = prepared_set.recipe.adapter_id
        self._converter = converter
        self._runner = runner or TransformersGenerateRunner(prepared_set)
        self._generation_budget = generation_budget
        self._generation_material_lock_digest = generation_material_lock_digest
        self._generation_host_policy = generation_host_policy
        self._sealed_payload: bytes | None = None
        self._debug_fragment_recorder: (
            Callable[[GenerationDebugFragment], None] | None
        ) = None
        self._generation_worker_factory: object | None = None
        self._generation_worker_controller: object | None = None
        self._debug_fragment_index = 0

    @property
    def models(self) -> tuple[str, ...]:
        return (self._model_id,)

    @property
    def is_local(self) -> bool:
        return True

    @property
    def capabilities(self) -> dict[str, bool]:
        return {
            "text_generation": True,
            "multimodal_input": True,
            "json_mode": bool(getattr(self._runner, "supports_json_mode", False)),
        }

    @property
    def execution_profile_adapter_id(self) -> str:
        return self._adapter_id

    def resolved_model_id(self, model_id: str) -> str:
        return self._model_id if model_id == self._model_id else model_id

    def bind_sealed_payload(self, *, content: bytes) -> None:
        if not content or self._sealed_payload is not None:
            raise ModelExecutionError("sealed converter input is unavailable")
        self._sealed_payload = content

    def clear_sealed_payload(self) -> None:
        self._sealed_payload = None

    def create_response_from_canonical_payload(
        self,
        *,
        content: bytes,
        response_format: Mapping[str, object] | None = None,
        max_tokens: int | None = None,
    ) -> ModelResponse:
        """Run one receiver-materialized converter payload without protocol messages."""

        decode = getattr(self._converter, "decode_canonical_payload", None)
        if not isinstance(content, bytes) or not content or not callable(decode):
            raise ModelExecutionError("sealed converter input is unavailable")
        try:
            messages, payload = decode(content)
            if not isinstance(payload, bytes) or not payload:
                raise ModelExecutionError("sealed converter input is unavailable")
            request = build_openai_request(
                model=self._model_id,
                messages=messages,
                response_format=response_format,
                max_tokens=max_tokens,
            )
            self.bind_sealed_payload(content=payload)
            return self.create_response(request)
        except ModelExecutionError:
            raise
        except Exception as error:  # noqa: BLE001 - converter errors vary.
            raise ModelExecutionError("sealed converter input is unavailable") from error


    def set_debug_fragment_recorder(
        self, recorder: Callable[[GenerationDebugFragment], None] | None
    ) -> None:
        """Set the host-private observer for generated fragments in a debug run."""

        self._debug_fragment_recorder = recorder

    def create_response(self, request: OpenAIModelRequest) -> ModelResponse:
        if self._sealed_payload is None:
            raise ModelExecutionError("sealed converter input is unavailable")
        payload = self._sealed_payload
        self._debug_fragment_index = 0
        try:
            json_mode = _json_mode_requested(
                request.response_format,
                supported=bool(getattr(self._runner, "supports_json_mode", False)),
            )
            budget = self._resolved_generation_budget(request)
            deadline = GenerationDeadline.start(
                time.monotonic(),
                max_runtime_milliseconds=budget.max_runtime_milliseconds,
            )
            generation_kwargs: dict[str, object] = {
                "max_new_tokens": budget.max_new_tokens_per_fragment
            }
            if json_mode:
                generation_kwargs["json_mode"] = True
            messages = tuple(request.messages)
            max_continuations = budget.max_continuations
            if max_continuations:
                completion = self._generate_with_continuations(
                    messages=messages,
                    payload=payload,
                    max_continuations=max_continuations,
                    budget=budget,
                    deadline=deadline,
                    **generation_kwargs,
                )
                return ModelResponse(
                    content=completion.content,
                    metadata=completion.metadata,
                )
            packed = self._converter.pack(
                messages=messages,
                payload=payload,
                context=self._runner.input_context,
            )
            generated = self._generate_admitted_chunk(
                packed, budget=budget, deadline=deadline, **generation_kwargs
            )
            self._record_generated_fragment(generated)
            content = generated.content.strip()
            _validate_generated_completion(content, (generated,), budget)
            if json_mode:
                content = _validated_json_object(content)
            if bool(getattr(self._runner, "uses_mps", False)):
                return ModelResponse(
                    content=content,
                    metadata={
                        "generation": {
                            "device": "mps",
                            "chunk_count": 1,
                            "chunk_exhausted": [generated.exhausted],
                            "generated_tokens": [generated.generated_tokens],
                        }
                    },
                )
            return ModelResponse(content=content)
        except ModelExecutionError:
            raise
        except Exception as error:  # noqa: BLE001 - converter errors vary.
            raise ModelExecutionError("local model generation failed") from error
        finally:
            self.clear_sealed_payload()

    def _generate_with_continuations(
        self,
        *,
        messages: tuple[Mapping[str, object], ...],
        payload: bytes,
        max_new_tokens: int,
        max_continuations: int,
        json_mode: bool = False,
        budget: GenerationResourceBudget | None = None,
        deadline: GenerationDeadline | None = None,
    ) -> GeneratedCompletion:
        fragments: list[str] = []
        chunk_exhausted: list[bool] = []
        generated_tokens: list[int | None] = []
        continuation_messages = messages
        for continuation in range(max_continuations + 1):
            remaining = (
                budget.max_total_generated_tokens
                - sum(token for token in generated_tokens if token is not None)
                if budget is not None
                else max_new_tokens
            )
            if remaining < 1:
                raise ModelExecutionError("model generation token budget exceeded")
            packed = self._converter.pack(
                messages=continuation_messages,
                payload=payload,
                context=self._runner.input_context,
            )
            generated = self._generate_admitted_chunk(
                packed,
                max_new_tokens=min(max_new_tokens, remaining),
                json_mode=json_mode and continuation == 0,
                budget=budget,
                deadline=deadline,
            )
            self._record_generated_fragment(generated)
            fragments.append(generated.content)
            chunk_exhausted.append(generated.exhausted)
            generated_tokens.append(generated.generated_tokens)
            completion = "".join(fragments).strip()
            _validate_generated_completion(completion, tuple(generated_tokens), budget)
            incomplete_json = json_mode and _is_incomplete_json_object(completion)
            if not generated.exhausted and not incomplete_json:
                content = (
                    _validated_json_object(completion) if json_mode else completion
                )
                generation: dict[str, object] = {
                    "chunk_count": len(fragments),
                    "chunk_exhausted": chunk_exhausted,
                    "generated_tokens": generated_tokens,
                }
                if bool(getattr(self._runner, "uses_mps", False)):
                    generation["device"] = "mps"
                return GeneratedCompletion(
                    content=content, metadata={"generation": generation}
                )
            if continuation == max_continuations:
                raise ModelExecutionError("local model continuation limit exceeded")
            continuation_messages = (
                *continuation_messages,
                {"role": "assistant", "content": generated.content},
                {"role": "user", "content": _CONTINUATION_INSTRUCTION},
            )
        raise AssertionError("continuation loop must return or raise")

    def _resolved_generation_budget(
        self, request: OpenAIModelRequest
    ) -> GenerationResourceBudget:
        if self._generation_budget is None:
            raise ModelExecutionError("model generation budget is unavailable")
        try:
            return resolve_generation_resource_budget(
                declared=self._generation_budget,
                runner_capability=TRANSFORMERS_GENERATE_CAPABILITY,
                host=(
                    self._generation_host_policy.ceiling
                    if self._generation_host_policy is not None
                    else None
                ),
                execution_device=(
                    self._generation_host_policy.execution_device
                    if self._generation_host_policy is not None
                    else None
                ),
            )
        except GenerationResourceBudgetError as error:
            raise ModelExecutionError("model generation budget is invalid") from error

    def _generate_admitted_chunk(
        self,
        packed: PackedModelInput,
        *,
        max_new_tokens: int,
        json_mode: bool = False,
        budget: GenerationResourceBudget | None,
        deadline: GenerationDeadline | None,
    ) -> GeneratedText:
        if budget is None:
            return self._generate_chunk(
                packed, max_new_tokens=max_new_tokens, json_mode=json_mode, budget=None
            )
        policy = self._generation_host_policy
        material_lock_digest = self._generation_material_lock_digest
        if policy is None or material_lock_digest is None or deadline is None:
            packed.clear()
            raise ModelExecutionError("model generation budget is unavailable")
        try:
            deadline.require_remaining(time.monotonic())
            inputs = packed.take()
            input_ids = inputs.get("input_ids") if isinstance(inputs, Mapping) else None
            shape = getattr(input_ids, "shape", None)
            if not isinstance(shape, Sequence) or len(shape) < 2:
                raise ModelExecutionError("model generation context is unavailable")
            try:
                _validate_packed_generation_budget(
                    packed, max_new_tokens=max_new_tokens, budget=budget
                )
            except ModelExecutionError:
                packed.clear()
                raise
            reservation = reserve_generation_memory(
                policy.memory_reservation_provider,
                GenerationMemoryReservationRequest(
                    material_lock_digest=material_lock_digest,
                    runner_identity=str(
                        getattr(
                            self._runner, "contract_id", type(self._runner).__name__
                        )
                    ),
                    execution_device=policy.execution_device,
                    packed_context_tokens=shape[-1],
                    requested_new_tokens=max_new_tokens,
                    max_memory_bytes=budget.max_memory_bytes,
                    deadline_monotonic=deadline.expires_at,
                ),
            )
            try:
                return self._generate_chunk(
                    packed,
                    max_new_tokens=max_new_tokens,
                    json_mode=json_mode,
                    budget=budget,
                )
            finally:
                reservation.release()
        except GenerationResourceBudgetError as error:
            packed.clear()
            message = (
                "model generation deadline exceeded"
                if str(error) == "generation deadline exceeded"
                else "model generation memory budget is unavailable"
            )
            raise ModelExecutionError(message) from error

    def _generate_chunk(
        self,
        packed: PackedModelInput,
        *,
        max_new_tokens: int,
        json_mode: bool = False,
        budget: GenerationResourceBudget | None,
    ) -> GeneratedText:
        if budget is not None and not bool(
            getattr(self._runner, "supports_generation_resource_budgets", False)
        ):
            raise ModelExecutionError("model generation budget is unavailable")
        if budget is not None and not bool(
            getattr(self._runner, "supports_generation_deadline", False)
        ):
            raise ModelExecutionError("model generation deadline unavailable")
        kwargs: dict[str, object] = {
            "max_new_tokens": max_new_tokens,
            "json_mode": json_mode,
        }
        if budget is not None:
            kwargs["budget"] = budget
        return self._runner.generate_chunk(packed, **kwargs)

    def _record_generated_fragment(self, generated: GeneratedText) -> None:
        if self._debug_fragment_recorder is not None:
            self._debug_fragment_recorder(
                GenerationDebugFragment(
                    fragment_index=self._debug_fragment_index,
                    exhausted=generated.exhausted,
                    generated_tokens=generated.generated_tokens,
                    output_bytes=len(generated.content.encode("utf-8")),
                )
            )
            self._debug_fragment_index += 1


class TransformersPeftMultimodalRunner:
    """Expose one prepared Transformers adapter through the multimodal protocol."""

    def __init__(
        self,
        *,
        descriptor: MultimodalRunnerDescriptor,
        adapter: TransformersPeftPackedInputAdapter,
    ) -> None:
        if not isinstance(descriptor, MultimodalRunnerDescriptor):
            raise ModelExecutionError("multimodal runner descriptor is invalid")
        if not callable(
            getattr(adapter, "create_response_from_canonical_payload", None)
        ):
            raise ModelExecutionError("multimodal runner adapter is unavailable")
        self._descriptor = descriptor
        self._adapter = adapter

    @property
    def runner_id(self) -> str:
        return self._descriptor.runner_id

    @property
    def protocol_id(self) -> str:
        return self._descriptor.protocol_id

    @property
    def protocol_version(self) -> str:
        return self._descriptor.protocol_version

    def describe(self) -> MultimodalRunnerDescriptor:
        return self._descriptor

    def health(self) -> MultimodalRunnerHealth:
        return MultimodalRunnerHealth("ready")

    def run(
        self,
        request: SealedMultimodalRequest,
        *,
        context: DARGenerationRequestContext,
        input_materializer: SealedMultimodalInputMaterializer | None = None,
    ) -> MultimodalRunnerResult:
        if input_materializer is None:
            raise ModelExecutionError("sealed converter input is unavailable")
        handles = tuple(
            handle for handle in request.handles if handle.role == "converter_input"
        )
        if len(handles) != 1:
            raise ModelExecutionError("sealed converter input is unavailable")
        materialized = input_materializer.resolve(
            handles[0],
            package_id=request.package_id,
            package_revision_digest=request.package_revision_digest,
            invocation_id=request.invocation_id,
            descriptor_digest=request.descriptor.contract_digest,
            expires_at=getattr(input_materializer, "expires_at", None),
            now=getattr(input_materializer, "now", None),
        )
        if not isinstance(materialized, bytes) or not materialized:
            raise ModelExecutionError("sealed converter input is unavailable")
        response = self._adapter.create_response_from_canonical_payload(
            content=materialized
        )
        generated_tokens = 0
        generation = response.metadata.get("generation")
        if isinstance(generation, Mapping):
            values = generation.get("generated_tokens")
            if isinstance(values, Sequence) and not isinstance(values, (str, bytes)):
                generated_tokens = sum(
                    value for value in values if isinstance(value, int) and value >= 0
                )
        return MultimodalRunnerResult(
            status="completed",
            text=response.content,
            output_handles=(),
            generated_tokens=generated_tokens,
            output_bytes=len(response.content.encode("utf-8")),
            coverage={"image": 1},
            worker_reaped=True,
            package_id=request.package_id,
            package_revision_digest=request.package_revision_digest,
            material_lock_digest=request.descriptor.material_lock_digest,
            converter_digest=request.descriptor.converter_digest,
            contract_digest=request.descriptor.contract_digest,
        )


class TransformersPeftSingleImageAdapter:
    """Expose the closed generic profile through DAR's existing adapter contract."""

    def __init__(
        self,
        prepared_set: PreparedArtifactSet,
        *,
        dependency_loader: DependencyLoader | None = None,
        image_decoder: ImageDecoder | None = None,
    ) -> None:
        self._base, self._adapter = _verified_prepared_paths(prepared_set)
        self._dependency_loader = dependency_loader or _load_default_backend
        self._image_decoder = image_decoder or _decode_image
        self._model_id = prepared_set.recipe.model_id
        self._adapter_id = prepared_set.recipe.adapter_id
        self._backend: TransformersPeftBackend | None = None
        self._sealed_image: object | None = None

    @property
    def models(self) -> tuple[str, ...]:
        return (self._model_id,)

    @property
    def is_local(self) -> bool:
        return True

    @property
    def capabilities(self) -> dict[str, bool]:
        return {"text_generation": True, "multimodal_input": True, "json_mode": False}

    @property
    def execution_profile_adapter_id(self) -> str:
        return self._adapter_id

    def resolved_model_id(self, model_id: str) -> str:
        return self._model_id if model_id == self._model_id else model_id

    def bind_sealed_image(self, *, content: bytes, media_type: str) -> None:
        if (
            not content
            or len(content) > 8 * 1024 * 1024
            or media_type not in {"image/jpeg", "image/png"}
            or self._sealed_image is not None
        ):
            raise ModelExecutionError("sealed image input is unavailable")
        try:
            self._sealed_image = _validate_decoded_image(self._image_decoder(content))
        except Exception as error:  # noqa: BLE001 - decoders vary.
            raise ModelExecutionError("sealed image input is unavailable") from error

    def clear_sealed_image(self) -> None:
        self._sealed_image = None

    def create_response(self, request: OpenAIModelRequest) -> ModelResponse:
        if self._sealed_image is None:
            raise ModelExecutionError("sealed image input is unavailable")
        image = self._sealed_image
        try:
            prompt = _user_prompt(request)
            max_new_tokens = _max_new_tokens(request)
            return ModelResponse(
                content=self._get_backend().generate(
                    prompt, image, max_new_tokens=max_new_tokens
                )
            )
        except ModelExecutionError:
            raise
        except Exception as error:  # noqa: BLE001 - backend errors vary.
            raise ModelExecutionError("local model generation failed") from error
        finally:
            self.clear_sealed_image()

    def _get_backend(self) -> TransformersPeftBackend:
        if self._backend is None:
            try:
                self._backend = self._dependency_loader(self._base, self._adapter)
            except ImportError as error:
                raise ModelExecutionError(
                    "Transformers + PEFT dependencies unavailable"
                ) from error
        return self._backend


def _user_prompt(request: OpenAIModelRequest) -> str:
    user_messages = [
        message for message in request.messages if message.get("role") == "user"
    ]
    if len(user_messages) != 1:
        raise ModelExecutionError("model request must contain one user message")
    prompt = user_messages[0].get("content")
    if not isinstance(prompt, str) or not prompt.strip():
        raise ModelExecutionError("model request has no user message")
    return prompt


def _max_new_tokens(request: OpenAIModelRequest) -> int:
    value = request.extra.get("max_tokens", 1024)
    _validate_max_new_tokens(value)
    return value


def _validate_packed_generation_budget(
    packed_input: PackedModelInput,
    *,
    max_new_tokens: int,
    budget: GenerationResourceBudget | None,
) -> None:
    if budget is None:
        return
    if max_new_tokens > budget.max_new_tokens_per_fragment:
        raise ModelExecutionError("model generation budget is invalid")
    inputs = packed_input.take()
    input_ids = inputs.get("input_ids") if isinstance(inputs, Mapping) else None
    shape = getattr(input_ids, "shape", None)
    if (
        not isinstance(shape, Sequence)
        or len(shape) < 2
        or not isinstance(shape[-1], int)
        or isinstance(shape[-1], bool)
        or shape[-1] < 0
    ):
        raise ModelExecutionError("model generation context is unavailable")
    if shape[-1] + max_new_tokens > budget.max_effective_context_tokens:
        raise ModelExecutionError("model generation context exceeds limit")


def _validate_generated_completion(
    content: str,
    generated: tuple[GeneratedText | int | None, ...],
    budget: GenerationResourceBudget | None,
) -> None:
    if budget is None:
        return
    if len(content.encode("utf-8")) > budget.max_total_output_bytes:
        raise ModelExecutionError("model generation output exceeds limit")
    token_counts = tuple(
        item.generated_tokens if isinstance(item, GeneratedText) else item
        for item in generated
    )
    if any(
        not isinstance(count, int) or isinstance(count, bool) or count < 0
        for count in token_counts
    ):
        raise ModelExecutionError("model generation budget is unavailable")
    if sum(token_counts) > budget.max_total_generated_tokens:
        raise ModelExecutionError("model generation token budget exceeded")


def _validate_max_new_tokens(value: object) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ModelExecutionError("model generation limit is invalid")


def _json_mode_requested(
    response_format: Mapping[str, object] | None, *, supported: bool
) -> bool:
    if response_format is None:
        return False
    if dict(response_format) != {"type": "json_object"}:
        raise ModelExecutionError("local model response format is unsupported")
    if not supported:
        raise ModelExecutionError("local model runner does not support JSON mode")
    return True


def _validated_json_object(value: str) -> str:
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError) as error:
        raise ModelExecutionError("local model returned invalid JSON") from error
    if not isinstance(parsed, dict):
        raise ModelExecutionError("local model returned invalid JSON")
    return value


def _is_incomplete_json_object(value: str) -> bool:
    """Return whether a JSON object prefix ends only because it is incomplete."""

    normalized = value.rstrip()
    try:
        json.loads(normalized)
    except json.JSONDecodeError as error:
        return error.pos == len(normalized)
    return False


def _generated_text(value: str | GeneratedText) -> GeneratedText:
    if isinstance(value, GeneratedText):
        return value
    if not isinstance(value, str):
        raise ModelExecutionError("local model returned an invalid response")
    return GeneratedText(value, exhausted=False)


def _generation_exhausted(
    generated: object, prefix_length: int, max_new_tokens: int
) -> bool:
    shape = getattr(generated, "shape", None)
    try:
        return shape[1] - prefix_length >= max_new_tokens
    except (IndexError, TypeError):
        return False


def _generated_token_count(generated: object, prefix_length: int) -> int | None:
    shape = getattr(generated, "shape", None)
    try:
        return shape[1] - prefix_length
    except (IndexError, TypeError):
        return None


def _json_mode_prefix_filter(processor: object) -> object:
    try:
        from lmformatenforcer import JsonSchemaParser
        from lmformatenforcer.tokenenforcer import (
            TokenEnforcer,
            TokenEnforcerTokenizerData,
        )

        tokenizer = processor.tokenizer  # type: ignore[attr-defined]
        token_zero = tokenizer.encode("0")[-1]
        regular_tokens = []
        for token_id in range(len(tokenizer)):
            if token_id in tokenizer.all_special_ids:
                continue
            after_zero = tokenizer.decode([token_zero, token_id])[1:]
            decoded = tokenizer.decode([token_id])
            regular_tokens.append(
                (token_id, after_zero, len(after_zero) > len(decoded))
            )
        token_data = TokenEnforcerTokenizerData(
            regular_tokens,
            lambda tokens: tokenizer.decode(tokens).rstrip("�"),
            tokenizer.eos_token_id,
            False,
            len(tokenizer),
        )
        return _TransformersPrefixAllowedTokensFn(
            TokenEnforcer(token_data, JsonSchemaParser(None))
        )
    except (AttributeError, ImportError, TypeError, ValueError) as error:
        raise ModelExecutionError("local model JSON mode is unavailable") from error


class _TransformersPrefixAllowedTokensFn:
    """Adapt lm-format-enforcer to Transformers' public tokenizer API."""

    def __init__(self, token_enforcer: object) -> None:
        self._token_enforcer = token_enforcer

    def __call__(self, _batch_id: int, sent: object) -> list[int]:
        tokens = sent.tolist()  # type: ignore[attr-defined]
        allowed = self._token_enforcer.get_allowed_tokens(tokens)
        return list(allowed.allowed_tokens)


def _verified_prepared_paths(prepared_set: PreparedArtifactSet) -> tuple[Path, Path]:
    if (
        prepared_set.recipe.loader_profile != TRANSFORMERS_PEFT_SINGLE_IMAGE_V1
        or not _valid_loader_profile(prepared_set.recipe)
    ):
        raise ModelExecutionError("prepared artifact set is incompatible")
    try:
        return prepared_set.group_path("base"), prepared_set.group_path("adapter")
    except KeyError as error:
        raise ModelExecutionError("prepared artifact set is incompatible") from error


def _decode_image(content: bytes) -> object:
    from io import BytesIO

    from PIL import Image

    image = Image.open(BytesIO(content))
    return image.copy()


def _validate_decoded_image(image: object) -> object:
    width = getattr(image, "width", None)
    height = getattr(image, "height", None)
    if (
        not isinstance(width, int)
        or not isinstance(height, int)
        or width < 1
        or height < 1
        or width * height > 32_000_000
    ):
        raise ValueError("image is invalid")
    return image


def _load_default_backend(base: Path, adapter: Path) -> TransformersPeftBackend:
    from peft import PeftModel
    from transformers import AutoModelForImageTextToText, AutoProcessor

    processor = AutoProcessor.from_pretrained(
        base, local_files_only=True, trust_remote_code=False
    )
    model_arguments: dict[str, object] = {
        "local_files_only": True,
        "trust_remote_code": False,
        "torch_dtype": "auto",
    }
    mps = _mps_available()
    if mps:
        model = AutoModelForImageTextToText.from_pretrained(base, **model_arguments)
    else:
        model = AutoModelForImageTextToText.from_pretrained(
            base, device_map="auto", **model_arguments
        )
    model = PeftModel.from_pretrained(
        model, adapter, is_trainable=False, local_files_only=True
    )
    if mps:
        model.to("mps")
        model.eval()
    return _LoadedTransformersPeftBackend(
        model=model,
        processor=processor,
    )


def _load_default_processor(base: Path) -> object:
    from transformers import AutoProcessor

    return AutoProcessor.from_pretrained(
        base, local_files_only=True, trust_remote_code=False
    )


def _mps_available() -> bool:
    try:
        import torch

        return torch.backends.mps.is_available()
    except (AttributeError, ImportError):
        return False


class _LoadedTransformersPeftBackend:
    """Run the documented standard multimodal chat-template flow locally."""

    def __init__(self, *, model: object, processor: object) -> None:
        self._model = model
        self._processor = processor

    @property
    def processor(self) -> object:
        """Expose only the reviewed processor to the converter contract."""

        return self._processor

    @property
    def uses_mps(self) -> bool:
        """Return whether this loaded model is executing on Apple MPS."""

        return str(getattr(self._model, "device", "")).split(":", 1)[0] == "mps"

    def generate(self, prompt: str, image: object, *, max_new_tokens: int) -> str:
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": image},
                    {"type": "text", "text": prompt},
                ],
            }
        ]
        inputs = self._processor.apply_chat_template(
            messages,
            add_generation_prompt=True,
            tokenize=True,
            return_dict=True,
            return_tensors="pt",
        )
        return self.generate_packed(
            inputs, max_new_tokens=max_new_tokens
        ).content.strip()

    def generate_packed(
        self, inputs: object, *, max_new_tokens: int, json_mode: bool = False
    ) -> GeneratedText:
        """Generate from converter-owned processor inputs within one worker."""

        move = getattr(inputs, "to", None)
        try:
            input_ids = inputs["input_ids"]  # type: ignore[index]
            packed = move(self._model.device) if callable(move) else inputs
            prefix_length = input_ids.shape[1]
        except (AttributeError, KeyError, TypeError, IndexError) as error:
            raise ModelExecutionError("packed model input is invalid") from error
        generation_kwargs: dict[str, object] = {
            "do_sample": False,
            "max_new_tokens": max_new_tokens,
        }
        if json_mode:
            generation_kwargs["prefix_allowed_tokens_fn"] = _json_mode_prefix_filter(
                self._processor
            )
        import torch

        with torch.inference_mode():
            generated = self._model.generate(
                **packed,
                **generation_kwargs,
            )
        decoded = self._processor.batch_decode(
            generated[:, prefix_length:], skip_special_tokens=True
        )
        if not decoded or not isinstance(decoded[0], str) or not decoded[0].strip():
            raise ModelExecutionError("local model returned an empty response")
        generated_tokens = _generated_token_count(generated, prefix_length)
        return GeneratedText(
            decoded[0],
            exhausted=_generation_exhausted(generated, prefix_length, max_new_tokens),
            generated_tokens=generated_tokens,
            backend_max_new_tokens=max_new_tokens,
        )


class DeferredTransformersPeftSingleImageAdapter:
    """Resolve the verified set only when the workflow consumes sealed input."""

    def __init__(
        self,
        *,
        model_id: str,
        adapter_id: str,
        resolve_prepared_set: Callable[[], PreparedArtifactSet],
    ) -> None:
        self._model_id = model_id
        self._adapter_id = adapter_id
        self._resolve_prepared_set = resolve_prepared_set
        self._adapter: TransformersPeftSingleImageAdapter | None = None
        self._packed_adapter: TransformersPeftPackedInputAdapter | None = None
        self._converter: PackedInputConverter | None = None
        self._generation_budget: GenerationResourceBudget | None = None
        self._generation_material_lock_digest: str | None = None
        self._generation_execution_descriptor_digest: str | None = None
        self._generation_host_policy: GenerationExecutionHostPolicy | None = None
        self._payload_bound = False
        self._debug_fragment_recorder: (
            Callable[[GenerationDebugFragment], None] | None
        ) = None
        self._generation_worker_factory: object | None = None
        self._generation_worker_controller: object | None = None
        self._worker_converter_package_root: Path | None = None
        self._worker_converter: DeclaredInputConverter | None = None
        self._worker_sealed_payload: bytes | None = None

    @property
    def input_converter_contract_id(self) -> str:
        return TRANSFORMERS_GENERATE_V1

    @property
    def capabilities(self) -> dict[str, bool]:
        return {"text_generation": True, "multimodal_input": True, "json_mode": True}

    @property
    def execution_profile_adapter_id(self) -> str:
        return self._adapter_id

    @property
    def models(self) -> tuple[str, ...]:
        return (self._model_id,)

    @property
    def is_local(self) -> bool:
        return True

    def resolved_model_id(self, model_id: str) -> str:
        return self._model_id if model_id == self._model_id else model_id

    def bind_sealed_image(self, *, content: bytes, media_type: str) -> None:
        self._resolved_adapter().bind_sealed_image(
            content=content, media_type=media_type
        )

    def clear_sealed_image(self) -> None:
        if self._adapter is not None:
            self._adapter.clear_sealed_image()

    def bind_input_converter(
        self, *, package_root: Path, converter: DeclaredInputConverter
    ) -> None:
        """Load the exact manifest-bound converter before accepting payload bytes."""

        if (
            self._payload_bound
            or converter.compatible_runner_contract_id != TRANSFORMERS_GENERATE_V1
        ):
            raise ModelExecutionError("sealed converter input is unavailable")
        from dynamic_agent_runner.workflow_host.input_converter_loader import (
            InputConverterLoadError,
            load_input_converter,
        )

        try:
            loaded = load_input_converter(
                package_root=package_root, converter=converter
            )
        except InputConverterLoadError as error:
            raise ModelExecutionError(
                "sealed converter input is unavailable"
            ) from error
        self._converter = loaded  # type: ignore[assignment]
        self._packed_adapter = None

    def bind_generation_budget(
        self,
        *,
        descriptor: object,
        material_lock_digest: str,
        host_policy: GenerationExecutionHostPolicy,
    ) -> None:
        """Bind the sealed descriptor budget before accepting converter payloads."""

        if self._payload_bound:
            raise ModelExecutionError("model generation budget is unavailable")
        try:
            budget = validate_generation_budget_field(descriptor)
            if (
                not isinstance(material_lock_digest, str)
                or len(material_lock_digest) != 64
                or any(
                    character not in "0123456789abcdef"
                    for character in material_lock_digest
                )
            ):
                raise GenerationResourceBudgetError("generation budget is invalid")
            execution_descriptor_digest = getattr(descriptor, "digest", None)
            if (
                not isinstance(execution_descriptor_digest, str)
                or len(execution_descriptor_digest) != 64
                or any(
                    character not in "0123456789abcdef"
                    for character in execution_descriptor_digest
                )
            ):
                raise GenerationResourceBudgetError("generation budget is invalid")
            if not isinstance(host_policy, GenerationExecutionHostPolicy):
                raise GenerationResourceBudgetError("generation budget is invalid")
        except GenerationResourceBudgetError as error:
            raise ModelExecutionError("model generation budget is invalid") from error
        controller = self._generation_worker_controller
        supported_execution_devices = getattr(
            controller, "supported_execution_devices", None
        )
        if controller is not None and (
            not isinstance(supported_execution_devices, frozenset)
            or host_policy.execution_device not in supported_execution_devices
        ):
            raise ModelExecutionError("generation worker is unavailable")
        self._generation_budget = budget
        self._generation_material_lock_digest = material_lock_digest
        self._generation_execution_descriptor_digest = execution_descriptor_digest
        self._generation_host_policy = host_policy
        self._packed_adapter = None

    def bind_generation_worker(
        self, *, factory: object, controller: object, capability: object
    ) -> None:
        """Bind only the reviewed worker pair for the compatible runner."""

        if (
            self._generation_worker_factory is not None
            or capability is not TRANSFORMERS_GENERATE_CAPABILITY
            or getattr(factory, "runner_id", None) != capability.runner_id
            or getattr(factory, "capability", None) is not capability
            or not callable(getattr(factory, "create_for_invocation", None))
            or getattr(controller, "runner_id", None) != capability.runner_id
            or not isinstance(
                getattr(controller, "supported_execution_devices", None), frozenset
            )
            or not capability.supported_execution_devices
            & controller.supported_execution_devices
        ):
            raise ModelExecutionError("local model runner is unavailable")
        self._generation_worker_factory = factory
        self._generation_worker_controller = controller

    def bind_sealed_payload(self, *, content: bytes) -> None:
        if self._payload_bound:
            raise ModelExecutionError("sealed converter input is unavailable")
        if self._generation_worker_factory is not None:
            raise ModelExecutionError("generation worker is unavailable")
        if (
            self._generation_budget is None
            or self._generation_host_policy is None
            or self._generation_material_lock_digest is None
        ):
            raise ModelExecutionError("model generation budget is unavailable")
        self._resolved_packed_adapter().bind_sealed_payload(content=content)
        self._payload_bound = True

    def create_response_from_canonical_payload(
        self,
        *,
        content: bytes,
        response_format: Mapping[str, object] | None = None,
        max_tokens: int | None = None,
    ) -> ModelResponse:
        """Decode one converter-owned payload before entering the existing adapter."""

        converter = self._converter
        decode = getattr(converter, "decode_canonical_payload", None)
        if not isinstance(content, bytes) or not content or not callable(decode):
            raise ModelExecutionError("sealed converter input is unavailable")
        try:
            messages, payload = decode(content)
            if not isinstance(payload, bytes) or not payload:
                raise ModelExecutionError("sealed converter input is unavailable")
            request = build_openai_request(
                model=self._model_id,
                messages=messages,
                response_format=response_format,
                max_tokens=max_tokens,
            )
            self.bind_sealed_payload(content=payload)
            return self.create_response(request)
        except ModelExecutionError:
            raise
        except Exception as error:  # noqa: BLE001 - converter errors vary.
            raise ModelExecutionError("sealed converter input is unavailable") from error

    def bind_worker_converter_payload(
        self, *, package_root: Path, converter: DeclaredInputConverter, content: bytes
    ) -> None:
        """Retain sealed converter inputs for child-only construction."""

        if (
            self._payload_bound
            or self._generation_worker_factory is None
            or not isinstance(package_root, Path)
            or not isinstance(converter, DeclaredInputConverter)
            or converter.compatible_runner_contract_id != TRANSFORMERS_GENERATE_V1
            or not isinstance(content, bytes)
            or not content
            or len(content) > converter.max_input_bytes
        ):
            raise ModelExecutionError("sealed converter input is unavailable")
        self._worker_converter_package_root = package_root
        self._worker_converter = converter
        self._worker_sealed_payload = content
        self._payload_bound = True

    def clear_sealed_payload(self) -> None:
        if self._packed_adapter is not None:
            self._packed_adapter.clear_sealed_payload()
        self._worker_converter_package_root = None
        self._worker_converter = None
        self._worker_sealed_payload = None
        self._payload_bound = False

    def set_debug_fragment_recorder(
        self, recorder: Callable[[GenerationDebugFragment], None] | None
    ) -> None:
        """Set the host-private recorder for a converter-backed debug run."""

        self._debug_fragment_recorder = recorder
        if self._packed_adapter is not None:
            self._packed_adapter.set_debug_fragment_recorder(recorder)

    def create_response(self, request: OpenAIModelRequest) -> ModelResponse:
        if self._payload_bound:
            try:
                if self._generation_worker_factory is not None:
                    return self._create_worker_response(request)
                return self._resolved_packed_adapter().create_response(request)
            finally:
                self.clear_sealed_payload()
        return self._resolved_adapter().create_response(request)

    def _create_worker_invocation_factory(
        self,
        request: OpenAIModelRequest,
        *,
        budget: GenerationResourceBudget | None = None,
        messages: tuple[Mapping[str, object], ...] | None = None,
        fragment_index: int = 0,
    ) -> object:
        """Bind one child-only factory from sealed request-scoped inputs."""

        factory = self._generation_worker_factory
        converter = self._worker_converter
        package_root = self._worker_converter_package_root
        sealed_payload = self._worker_sealed_payload
        budget = budget or self._generation_budget
        material_lock_digest = self._generation_material_lock_digest
        execution_descriptor_digest = self._generation_execution_descriptor_digest
        host_policy = self._generation_host_policy
        create_for_invocation = getattr(factory, "create_for_invocation", None)
        if (
            not isinstance(request, OpenAIModelRequest)
            or not callable(create_for_invocation)
            or not isinstance(converter, DeclaredInputConverter)
            or not isinstance(package_root, Path)
            or not isinstance(sealed_payload, bytes)
            or not sealed_payload
            or not isinstance(budget, GenerationResourceBudget)
            or not isinstance(material_lock_digest, str)
            or not isinstance(execution_descriptor_digest, str)
            or not isinstance(host_policy, GenerationExecutionHostPolicy)
            or not isinstance(fragment_index, int)
            or isinstance(fragment_index, bool)
            or fragment_index < 0
        ):
            raise ModelExecutionError("generation worker is unavailable")
        try:
            canonical_messages = request.messages if messages is None else messages
            canonical_invocation = json.dumps(
                {
                    "messages": canonical_messages,
                    "sealed_payload_digest": sha256(sealed_payload).hexdigest(),
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            now = datetime.now(UTC)
            return create_for_invocation(
                invocation_id=secrets.token_hex(32),
                invocation_digest=sha256(canonical_invocation).hexdigest(),
                fragment_index=fragment_index,
                converter=converter,
                package_root=package_root,
                prepared_set=self._resolve_prepared_set(),
                messages=canonical_messages,
                sealed_payload=sealed_payload,
                sealed_payload_digest=sha256(sealed_payload).hexdigest(),
                json_mode=_json_mode_requested(request.response_format, supported=True),
                material_lock_digest=material_lock_digest,
                execution_descriptor_digest=execution_descriptor_digest,
                execution_device=host_policy.execution_device,
                budget=budget,
                expires_at=now
                + timedelta(milliseconds=budget.max_runtime_milliseconds),
                now=now,
            )
        except (TypeError, ValueError) as error:
            raise ModelExecutionError("generation worker is unavailable") from error

    def _create_worker_response(self, request: OpenAIModelRequest) -> ModelResponse:
        """Execute one bounded fragment and retain only aggregate parent facts."""

        json_mode = _json_mode_requested(request.response_format, supported=True)
        budget = self._resolved_worker_generation_budget(request)
        deadline = GenerationDeadline.start(
            time.monotonic(), max_runtime_milliseconds=budget.max_runtime_milliseconds
        )
        controller = self._generation_worker_controller
        host_policy = self._generation_host_policy
        if not isinstance(host_policy, GenerationExecutionHostPolicy):
            raise ModelExecutionError("generation worker is unavailable")
        try:
            content, generated_tokens, output_bytes, chunk_count = (
                self._run_worker_fragments(
                    request=request,
                    controller=controller,
                    budget=budget,
                    deadline=deadline,
                    host_policy=host_policy,
                )
            )
            if json_mode:
                content = _validated_json_object(content)
            return ModelResponse(
                content=content,
                metadata={
                    "generation": {
                        "chunk_count": chunk_count,
                        "generated_tokens": generated_tokens,
                        "output_bytes": output_bytes,
                    }
                },
            )
        except ModelExecutionError:
            raise
        except GenerationResourceBudgetError as error:
            if str(error) == "generation deadline exceeded":
                raise ModelExecutionError(
                    "model generation deadline exceeded"
                ) from error
            if str(error) == "generation memory budget is unavailable":
                raise ModelExecutionError(
                    "model generation memory budget is unavailable"
                ) from error
            raise ModelExecutionError(
                "model generation budget is unavailable"
            ) from error
        except GenerationWorkerDeadlineExceeded as error:
            raise ModelExecutionError("model generation deadline exceeded") from error
        except GenerationWorkerExecutionFailed as error:
            raise ModelExecutionError("local model generation failed") from error
        except GenerationWorkerProtocolError as error:
            raise _shape_worker_protocol_error(error) from error

    def _run_worker_fragments(
        self,
        *,
        request: OpenAIModelRequest,
        controller: object,
        budget: GenerationResourceBudget,
        deadline: GenerationDeadline,
        host_policy: GenerationExecutionHostPolicy,
    ) -> tuple[str, int, int, int]:
        """Continue only while child exhaustion and all parent counters permit it."""

        messages = tuple(request.messages)
        fragments: list[str] = []
        generated_tokens = 0
        output_bytes = 0
        for fragment_index in range(budget.max_continuations + 1):
            deadline.require_remaining(time.monotonic())
            remaining_generated_tokens = (
                budget.max_total_generated_tokens - generated_tokens
            )
            remaining_output_bytes = budget.max_total_output_bytes - output_bytes
            if remaining_generated_tokens < 1:
                raise ModelExecutionError("model generation token budget exceeded")
            if remaining_output_bytes < 1:
                raise ModelExecutionError("model generation output limit exceeded")
            fragment_budget = replace(
                budget, max_total_output_bytes=remaining_output_bytes
            )
            factory = self._create_worker_invocation_factory(
                request,
                budget=fragment_budget,
                messages=messages,
                fragment_index=fragment_index,
            )
            fragment_started_at = time.monotonic()
            result = self._run_worker_fragment(
                factory=factory,
                controller=controller,
                budget=fragment_budget,
                deadline=deadline,
                host_policy=host_policy,
                remaining_generated_tokens=remaining_generated_tokens,
            )
            elapsed_milliseconds = max(
                int((time.monotonic() - fragment_started_at) * 1_000), 0
            )
            try:
                fragment = result.candidate.decode("utf-8")
            except UnicodeDecodeError as error:
                raise ModelExecutionError(
                    "local model returned an invalid response"
                ) from error
            generated_tokens += result.generated_tokens
            output_bytes += len(result.candidate)
            if (
                result.aggregate_generated_tokens != result.generated_tokens
                or result.aggregate_output_bytes != len(result.candidate)
                or generated_tokens > budget.max_total_generated_tokens
                or output_bytes > budget.max_total_output_bytes
            ):
                raise ModelExecutionError("generation worker protocol invalid")
            if self._debug_fragment_recorder is not None:
                self._debug_fragment_recorder(
                    GenerationDebugFragment(
                        fragment_index=fragment_index,
                        exhausted=result.exhausted,
                        generated_tokens=result.generated_tokens,
                        output_bytes=len(result.candidate),
                        packed_context_tokens=result.packed_context_tokens,
                        elapsed_milliseconds=elapsed_milliseconds,
                        stop_classification=(
                            "completed"
                            if not result.exhausted
                            else (
                                "continuation_limit_exceeded"
                                if fragment_index == budget.max_continuations
                                else "continuation"
                            )
                        ),
                        worker_reaped=result.worker_reaped,
                    )
                )
            fragments.append(fragment)
            content = "".join(fragments).strip()
            if not result.exhausted:
                if not content:
                    raise ModelExecutionError("local model returned an empty response")
                return content, generated_tokens, output_bytes, fragment_index + 1
            if fragment_index == budget.max_continuations:
                raise ModelExecutionError("local model continuation limit exceeded")
            messages = (
                *messages,
                {"role": "assistant", "content": fragment},
                {"role": "user", "content": _CONTINUATION_INSTRUCTION},
            )
        raise AssertionError("worker continuation loop must return or raise")

    def _run_worker_fragment(
        self,
        *,
        factory: object,
        controller: object,
        budget: GenerationResourceBudget,
        deadline: GenerationDeadline,
        host_policy: GenerationExecutionHostPolicy,
        remaining_generated_tokens: int,
    ) -> object:
        """Launch, pack, reserve, authorize, and reap one worker fragment."""

        create_descriptor = getattr(factory, "create_launch_descriptor", None)
        if not callable(create_descriptor):
            raise GenerationWorkerProtocolError("generation worker protocol invalid")
        descriptor = create_descriptor()
        if (
            not isinstance(descriptor, GenerationWorkerLaunchDescriptor)
            or descriptor.budget != budget
            or descriptor.execution_device != host_policy.execution_device
        ):
            raise GenerationWorkerProtocolError("generation worker protocol invalid")
        session = GenerationWorkerSession(
            invocation_id=descriptor.invocation_id,
            invocation_digest=descriptor.invocation_digest,
            converter_digest=descriptor.converter_asset_digest,
            material_lock_digest=descriptor.material_lock_digest,
            execution_device=descriptor.execution_device,
            max_total_generated_tokens=budget.max_total_generated_tokens,
            max_total_output_bytes=budget.max_total_output_bytes,
            initial_fragment_index=descriptor.fragment_index,
        )
        launcher = GenerationWorkerLauncher()
        child = launcher.launch(
            factory=factory, controller=controller, deadline=deadline
        )
        receipt = self._worker_pack_receipt(
            launcher=launcher,
            child=child,
            controller=controller,
            session=session,
            descriptor=descriptor,
            budget=budget,
            deadline=deadline,
            remaining_generated_tokens=remaining_generated_tokens,
        )
        try:
            return launcher.generate(
                child=child,
                session=session,
                receipt=receipt,
                remaining_generated_tokens=min(
                    budget.max_new_tokens_per_fragment, remaining_generated_tokens
                ),
                provider=host_policy.memory_reservation_provider,
                request=GenerationMemoryReservationRequest(
                    material_lock_digest=descriptor.material_lock_digest,
                    runner_identity=descriptor.runner_id,
                    execution_device=descriptor.execution_device,
                    packed_context_tokens=receipt.packed_context_tokens,
                    requested_new_tokens=min(
                        budget.max_new_tokens_per_fragment, remaining_generated_tokens
                    ),
                    max_memory_bytes=budget.max_memory_bytes,
                    deadline_monotonic=deadline.expires_at,
                ),
                deadline=deadline,
                now=time.monotonic(),
                controller=controller,
            )
        finally:
            child = None

    def _worker_pack_receipt(
        self,
        *,
        launcher: GenerationWorkerLauncher,
        child: object,
        controller: object,
        session: GenerationWorkerSession,
        descriptor: GenerationWorkerLaunchDescriptor,
        budget: GenerationResourceBudget,
        deadline: GenerationDeadline,
        remaining_generated_tokens: int,
    ) -> object:
        """Reject context growth before the worker receives authorization."""

        try:
            receipt = launcher.pack_receipt(
                child=child,
                session=session,
                fragment_index=descriptor.fragment_index,
                max_memory_bytes=budget.max_memory_bytes,
                execution_device=descriptor.execution_device,
                deadline=deadline,
                controller=controller,
            )
        except Exception:
            child = None
            raise
        requested_new_tokens = min(
            budget.max_new_tokens_per_fragment, remaining_generated_tokens
        )
        if (
            receipt.packed_context_tokens + requested_new_tokens
            > budget.max_effective_context_tokens
        ):
            launcher.abort(child=child, controller=controller, deadline=deadline)
            raise ModelExecutionError("model generation context limit exceeded")
        return receipt

    def _resolved_worker_generation_budget(
        self, request: OpenAIModelRequest
    ) -> GenerationResourceBudget:
        """Resolve the sealed budget before the child factory binds it."""

        budget = self._generation_budget
        policy = self._generation_host_policy
        if budget is None or policy is None:
            raise ModelExecutionError("model generation budget is unavailable")
        try:
            return resolve_generation_resource_budget(
                declared=budget,
                runner_capability=TRANSFORMERS_GENERATE_CAPABILITY,
                host=policy.ceiling,
                execution_device=policy.execution_device,
            )
        except GenerationResourceBudgetError as error:
            raise ModelExecutionError("model generation budget is invalid") from error

    def _resolved_adapter(self) -> TransformersPeftSingleImageAdapter:
        if self._adapter is None:
            self._adapter = TransformersPeftSingleImageAdapter(
                self._resolve_prepared_set()
            )
        return self._adapter

    def _resolved_packed_adapter(self) -> TransformersPeftPackedInputAdapter:
        if self._packed_adapter is None:
            if self._converter is None:
                raise ModelExecutionError("sealed converter input is unavailable")
            self._packed_adapter = TransformersPeftPackedInputAdapter(
                self._resolve_prepared_set(),
                converter=self._converter,
                generation_budget=self._generation_budget,
                generation_material_lock_digest=self._generation_material_lock_digest,
                generation_host_policy=self._generation_host_policy,
            )
            self._packed_adapter.set_debug_fragment_recorder(
                self._debug_fragment_recorder
            )
        return self._packed_adapter
