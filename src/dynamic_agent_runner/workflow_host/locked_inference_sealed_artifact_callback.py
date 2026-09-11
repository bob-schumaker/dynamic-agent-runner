"""Bind locked inference roles to the generic sealed-artifact callback seam."""

from __future__ import annotations

from collections.abc import Mapping

from dynamic_agent_runner.workflow_host.locked_inference import (
    InferenceRoles,
    LockedInferenceError,
    read_verified_inference_role_assets,
)
from dynamic_agent_runner.workflow_host.locked_inference_execution import (
    LockedInferenceExecutionService,
    LockedInferenceHostLimits,
)
from dynamic_agent_runner.workflow_host.capabilities import (
    CapabilityCatalog,
    CapabilityError,
    selected_provider_id_for_requirement,
)
from dynamic_agent_runner.workflow_host.locked_inference_provider_registry import (
    LockedInferenceProviderRegistry,
    LockedInferenceProviderRegistryError,
)
from dynamic_agent_runner.workflow_host.sealed_artifact_runner import (
    SealedArtifactCallback,
    SealedArtifactCallbackProvider,
    SealedArtifactRunnerDescriptor,
)


class LockedInferenceSealedArtifactCallbackError(ValueError):
    """Raised without exposing policy, asset, or provider details."""


class LockedInferenceExecutionFactory:
    """Create one private locked-inference service for one sealed invocation."""

    def __init__(
        self,
        *,
        capability_catalog: CapabilityCatalog,
        provider_registry: LockedInferenceProviderRegistry,
        host_limits: LockedInferenceHostLimits,
    ) -> None:
        self._capability_catalog = capability_catalog
        self._provider_registry = provider_registry
        self._host_limits = host_limits

    def create(
        self, *, policy: object, revision: object
    ) -> LockedInferenceExecutionService:
        roles = getattr(policy, "inference_roles", None)
        requirements = getattr(policy, "capability_requirements", None)
        selected_provider_ids = tuple(
            getattr(policy, "selected_capability_provider_ids", ())
        )
        root = getattr(revision, "package_root", None)
        if not isinstance(roles, InferenceRoles) or requirements is None:
            raise LockedInferenceSealedArtifactCallbackError(
                "locked inference callback is unavailable"
            )
        try:
            selected_provider_id = selected_provider_id_for_requirement(
                requirements=requirements,
                selected_provider_ids=selected_provider_ids,
                capability_id="model.generate.v1",
            )
            revalidated = self._capability_catalog.revalidate(selected_provider_ids)
            if (
                revalidated.status != "eligible"
                or revalidated.selected_provider_ids != selected_provider_ids
            ):
                raise CapabilityError("selected capability provider is unavailable")
            bindings = _bindings_for_roles(policy, roles, requirements)
            instructions, request_schemas, response_schemas = (
                read_verified_inference_role_assets(root=root, roles=roles)
            )
            providers = {
                role.role: self._provider_registry.resolve(
                    binding=bindings[role.role],
                    selected_provider_id=selected_provider_id,
                )
                for role in roles.roles
            }
        except (
            CapabilityError,
            LockedInferenceError,
            LockedInferenceProviderRegistryError,
        ) as error:
            raise LockedInferenceSealedArtifactCallbackError(
                "locked inference callback is unavailable"
            ) from error
        return LockedInferenceExecutionService(
            providers=providers,
            bindings=bindings,
            instructions=instructions,
            request_schemas=request_schemas,
            response_schemas=response_schemas,
            package_limits={
                role.role: LockedInferenceHostLimits(**role.limits.to_mapping())
                for role in roles.roles
            },
            host_limits=self._host_limits,
            revalidate=lambda role: self._revalidate(
                bindings[role],
                selected_provider_id,
                selected_provider_ids,
                providers[role],
            ),
        )

    def _revalidate(
        self,
        binding: object,
        selected_provider_id: str,
        selected_provider_ids: tuple[str, ...],
        provider: object,
    ) -> bool:
        try:
            result = self._capability_catalog.revalidate(selected_provider_ids)
            return (
                result.status == "eligible"
                and result.selected_provider_ids == selected_provider_ids
                and self._provider_registry.resolve(
                    binding=binding, selected_provider_id=selected_provider_id
                )
                is provider
            )
        except (CapabilityError, LockedInferenceProviderRegistryError):
            return False


class LockedInferenceSealedArtifactCallbackResolver:
    """Resolve only descriptor callbacks authorized by exact inference roles."""

    def __init__(
        self,
        *,
        execution: LockedInferenceExecutionService | None = None,
        execution_factory: LockedInferenceExecutionFactory | None = None,
    ) -> None:
        if (execution is None) == (execution_factory is None) or (
            execution is not None and not callable(getattr(execution, "generate", None))
        ):
            raise LockedInferenceSealedArtifactCallbackError(
                "locked inference callback is unavailable"
            )
        self._execution = execution
        self._execution_factory = execution_factory

    def resolve(
        self,
        descriptor: SealedArtifactRunnerDescriptor,
        policy: object,
        revision: object | None = None,
    ) -> SealedArtifactCallbackProvider:
        roles = getattr(policy, "inference_roles", None)
        if not isinstance(roles, InferenceRoles):
            raise LockedInferenceSealedArtifactCallbackError(
                "locked inference callback is unavailable"
            )
        callbacks = {callback.name: callback for callback in descriptor.callbacks}
        try:
            for callback in callbacks.values():
                role = roles.for_role(callback.name)
                if (
                    callback.requirement != role.capability_id
                    or descriptor.asset_digest not in role.authorized_asset_digests
                ):
                    raise LockedInferenceError("inference role is unavailable")
        except LockedInferenceError as error:
            raise LockedInferenceSealedArtifactCallbackError(
                "locked inference callback is unavailable"
            ) from error
        try:
            execution = self._execution or self._execution_factory.create(
                policy=policy, revision=revision
            )
        except LockedInferenceSealedArtifactCallbackError:
            raise
        return _LockedInferenceCallbackProvider(execution, callbacks)


def _bindings_for_roles(
    policy: object, roles: InferenceRoles, requirements: object
) -> dict[str, object]:
    bindings = tuple(getattr(policy, "locked_inference_bindings", ()))
    material_sets = getattr(policy, "model_material_sets", None)
    resolved = {getattr(binding, "role", None): binding for binding in bindings}
    generation = next(
        (
            requirement
            for requirement in getattr(requirements, "required_capabilities", ())
            if getattr(requirement, "capability_id", None) == "model.generate.v1"
        ),
        None,
    )
    if (
        len(resolved) != len(bindings)
        or set(resolved) != {role.role for role in roles.roles}
        or material_sets is None
        or generation is None
        or "structured" not in generation.required_features
    ):
        raise LockedInferenceError("inference binding is unavailable")
    for role in roles.roles:
        binding = resolved[role.role]
        try:
            material_lock_digest = material_sets.for_role(role.material_role).digest
        except Exception as error:
            raise LockedInferenceError("inference binding is unavailable") from error
        if (
            getattr(binding, "material_role", None) != role.material_role
            or getattr(binding, "material_lock_digest", None) != material_lock_digest
            or getattr(binding, "capability_contract_version", None)
            != generation.contract_version
            or getattr(binding, "capability_contract_digest", None)
            != generation.contract_digest
        ):
            raise LockedInferenceError("inference binding is unavailable")
    return resolved


class _LockedInferenceCallbackProvider:
    def __init__(
        self,
        execution: LockedInferenceExecutionService,
        callbacks: Mapping[str, SealedArtifactCallback],
    ) -> None:
        self._execution = execution
        self._callbacks = dict(callbacks)

    def revalidate(self, callback: SealedArtifactCallback) -> None:
        if self._callbacks.get(callback.name) != callback:
            raise LockedInferenceSealedArtifactCallbackError(
                "locked inference callback is unavailable"
            )

    def invoke(self, name: str, request: bytes) -> bytes:
        if name not in self._callbacks or not isinstance(request, bytes):
            raise LockedInferenceSealedArtifactCallbackError(
                "locked inference callback is unavailable"
            )
        try:
            return self._execution.generate(name, request)
        except Exception as error:  # Provider failures remain private to the asset.
            raise LockedInferenceSealedArtifactCallbackError(
                "locked inference callback is unavailable"
            ) from error
