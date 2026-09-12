"""Host-private read-only asset handles for generation-worker children."""

from __future__ import annotations

from datetime import datetime
from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path
import stat

from dynamic_agent_runner.workflow_host.generation_worker import (
    GenerationWorkerLaunchDescriptor,
)
from dynamic_agent_runner.workflow_host.descriptor import DeclaredInputConverter
from dynamic_agent_runner.local_model_preparation import (
    LocalModelArtifact,
    LocalModelLoaderProfile,
    LocalModelPreparationRecipe,
    LocalModelTransformation,
    PreparedArtifactSet,
)
from dynamic_agent_runner.workflow_host.state import (
    OpaqueRecordError,
    PrivateStateStore,
)


class GenerationWorkerAssetHandleError(ValueError):
    """Raised without disclosing worker asset locations or contents."""


@dataclass(frozen=True)
class GenerationWorkerCoLocatedAssets:
    """Typed host-private assets reconstructed only in the worker child."""

    package_root: Path
    converter: DeclaredInputConverter
    prepared_set: PreparedArtifactSet
    sealed_payload_path: Path


class GenerationWorkerAssetHandleService:
    """Issue descriptor-bound opaque handles for verified immutable local assets."""

    _KIND = "generation_worker_read_only_asset"
    _CO_LOCATED_KIND = "generation_worker_co_located_assets"

    def __init__(self, *, store: PrivateStateStore, owner: str) -> None:
        if (
            not isinstance(store, PrivateStateStore)
            or not isinstance(owner, str)
            or not owner
        ):
            raise GenerationWorkerAssetHandleError(
                "generation worker asset is unavailable"
            )
        self._store = store
        self._owner = owner

    def issue(
        self,
        *,
        descriptor: GenerationWorkerLaunchDescriptor,
        source_path: Path,
        expected_digest: str,
        expires_at: datetime,
        now: datetime,
    ) -> str:
        """Issue one opaque handle after binding a verified regular asset."""

        if not isinstance(descriptor, GenerationWorkerLaunchDescriptor) or not _digest(
            expected_digest
        ):
            raise GenerationWorkerAssetHandleError(
                "generation worker asset is unavailable"
            )
        path = _verified_asset(source_path, expected_digest)
        try:
            return self._store.issue(
                kind=self._KIND,
                owner=self._owner,
                payload={
                    "descriptor": _descriptor_binding(descriptor),
                    "path": str(path),
                    "digest": expected_digest,
                },
                expires_at=expires_at,
                now=now,
            )
        except (OpaqueRecordError, TypeError, ValueError) as error:
            raise GenerationWorkerAssetHandleError(
                "generation worker asset is unavailable"
            ) from error

    def resolve(
        self,
        *,
        handle: str,
        descriptor: GenerationWorkerLaunchDescriptor,
        now: datetime,
    ) -> Path:
        """Return one revalidated asset only for the descriptor that issued it."""

        if (
            not isinstance(descriptor, GenerationWorkerLaunchDescriptor)
            or handle not in descriptor.asset_handles
        ):
            raise GenerationWorkerAssetHandleError(
                "generation worker asset is unavailable"
            )
        try:
            record = self._store.load(
                handle, expected_kind=self._KIND, owner=self._owner, now=now
            )
            payload = record.payload
            if payload.get("descriptor") != _descriptor_binding(descriptor):
                raise GenerationWorkerAssetHandleError(
                    "generation worker asset is unavailable"
                )
            return _verified_asset(Path(payload["path"]), payload["digest"])
        except (
            OpaqueRecordError,
            KeyError,
            TypeError,
            ValueError,
            GenerationWorkerAssetHandleError,
        ) as error:
            raise GenerationWorkerAssetHandleError(
                "generation worker asset is unavailable"
            ) from error

    def issue_co_located(
        self,
        *,
        descriptor: GenerationWorkerLaunchDescriptor,
        package_root: Path,
        converter: DeclaredInputConverter,
        prepared_set: PreparedArtifactSet,
        sealed_payload_path: Path,
        sealed_payload_digest: str,
        expires_at: datetime,
        now: datetime,
    ) -> str:
        """Bind generic converter, model, and payload assets behind one handle."""

        try:
            payload = _co_located_payload(
                descriptor=descriptor,
                package_root=package_root,
                converter=converter,
                prepared_set=prepared_set,
                sealed_payload_path=sealed_payload_path,
                sealed_payload_digest=sealed_payload_digest,
            )
            return self._store.issue(
                kind=self._CO_LOCATED_KIND,
                owner=self._owner,
                payload={"descriptor": _descriptor_binding(descriptor), **payload},
                expires_at=expires_at,
                now=now,
            )
        except (OpaqueRecordError, TypeError, ValueError) as error:
            raise GenerationWorkerAssetHandleError(
                "generation worker asset is unavailable"
            ) from error

    def resolve_co_located(
        self,
        *,
        handle: str,
        descriptor: GenerationWorkerLaunchDescriptor,
        now: datetime,
    ) -> GenerationWorkerCoLocatedAssets:
        """Reconstitute typed child-private assets for the exact descriptor."""

        if (
            not isinstance(descriptor, GenerationWorkerLaunchDescriptor)
            or handle not in descriptor.asset_handles
        ):
            raise GenerationWorkerAssetHandleError(
                "generation worker asset is unavailable"
            )
        try:
            record = self._store.load(
                handle,
                expected_kind=self._CO_LOCATED_KIND,
                owner=self._owner,
                now=now,
            )
            payload = record.payload
            if payload.get("descriptor") != _descriptor_binding(descriptor):
                raise GenerationWorkerAssetHandleError(
                    "generation worker asset is unavailable"
                )
            return _resolved_co_located_assets(payload, descriptor)
        except (
            OpaqueRecordError,
            KeyError,
            TypeError,
            ValueError,
            GenerationWorkerAssetHandleError,
        ) as error:
            raise GenerationWorkerAssetHandleError(
                "generation worker asset is unavailable"
            ) from error


def _descriptor_binding(
    descriptor: GenerationWorkerLaunchDescriptor,
) -> dict[str, object]:
    return {
        "protocol_version": descriptor.protocol_version,
        "invocation_digest": descriptor.invocation_digest,
        "fragment_index": descriptor.fragment_index,
        "runner_id": descriptor.runner_id,
        "capability_contract_digest": descriptor.capability_contract_digest,
        "converter_id": descriptor.converter_id,
        "converter_asset_digest": descriptor.converter_asset_digest,
        "material_lock_digest": descriptor.material_lock_digest,
        "execution_descriptor_digest": descriptor.execution_descriptor_digest,
        "execution_device": descriptor.execution_device,
        "budget": asdict(descriptor.budget),
    }


def _verified_asset(source_path: object, expected_digest: object) -> Path:
    if not isinstance(source_path, Path) or not _digest(expected_digest):
        raise GenerationWorkerAssetHandleError("generation worker asset is unavailable")
    try:
        source_metadata = source_path.lstat()
        path = source_path.resolve(strict=True)
        metadata = path.stat()
        content = path.read_bytes()
    except OSError as error:
        raise GenerationWorkerAssetHandleError(
            "generation worker asset is unavailable"
        ) from error
    if (
        stat.S_ISLNK(source_metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
        or sha256(content).hexdigest() != expected_digest
    ):
        raise GenerationWorkerAssetHandleError("generation worker asset is unavailable")
    return path


def _digest(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _co_located_payload(
    *,
    descriptor: GenerationWorkerLaunchDescriptor,
    package_root: object,
    converter: object,
    prepared_set: object,
    sealed_payload_path: object,
    sealed_payload_digest: object,
) -> dict[str, object]:
    if (
        not isinstance(descriptor, GenerationWorkerLaunchDescriptor)
        or not isinstance(package_root, Path)
        or not isinstance(converter, DeclaredInputConverter)
        or not isinstance(prepared_set, PreparedArtifactSet)
        or not isinstance(sealed_payload_path, Path)
        or not _digest(sealed_payload_digest)
        or converter.converter_id != descriptor.converter_id
        or converter.asset_digest != descriptor.converter_asset_digest
        or converter.compatible_runner_contract_id != descriptor.runner_id
    ):
        raise GenerationWorkerAssetHandleError("generation worker asset is unavailable")
    root = package_root.resolve(strict=True)
    converter_path = _asset_within_root(
        root=root,
        entrypoint=converter.entrypoint,
        expected_digest=converter.asset_digest,
    )
    payload_path = _verified_asset(sealed_payload_path, sealed_payload_digest)
    recipe = prepared_set.recipe
    paths: dict[str, str] = {}
    for artifact in recipe.artifacts:
        paths[artifact.role] = str(
            _verified_asset(prepared_set.paths[artifact.role], artifact.sha256)
        )
    if prepared_set.recipe_digest != recipe.recipe_digest:
        raise GenerationWorkerAssetHandleError("generation worker asset is unavailable")
    return {
        "package_root": str(root),
        "converter": asdict(converter),
        "converter_path": str(converter_path),
        "prepared_recipe": _recipe_payload(recipe),
        "prepared_paths": paths,
        "prepared_recipe_digest": prepared_set.recipe_digest,
        "sealed_payload_path": str(payload_path),
        "sealed_payload_digest": sealed_payload_digest,
    }


def _resolved_co_located_assets(
    payload: dict[str, object], descriptor: GenerationWorkerLaunchDescriptor
) -> GenerationWorkerCoLocatedAssets:
    converter_mapping = payload["converter"]
    if not isinstance(converter_mapping, dict):
        raise GenerationWorkerAssetHandleError("generation worker asset is unavailable")
    converter = DeclaredInputConverter(**converter_mapping)
    package_root = Path(payload["package_root"])
    converter_path = _asset_within_root(
        root=package_root,
        entrypoint=converter.entrypoint,
        expected_digest=converter.asset_digest,
    )
    if (
        converter.converter_id != descriptor.converter_id
        or converter.asset_digest != descriptor.converter_asset_digest
        or converter.compatible_runner_contract_id != descriptor.runner_id
        or str(converter_path) != payload["converter_path"]
    ):
        raise GenerationWorkerAssetHandleError("generation worker asset is unavailable")
    recipe = _recipe_from_payload(payload["prepared_recipe"])
    paths_mapping = payload["prepared_paths"]
    if (
        not isinstance(paths_mapping, dict)
        or payload["prepared_recipe_digest"] != recipe.recipe_digest
    ):
        raise GenerationWorkerAssetHandleError("generation worker asset is unavailable")
    paths = {
        artifact.role: _verified_asset(
            Path(paths_mapping[artifact.role]), artifact.sha256
        )
        for artifact in recipe.artifacts
    }
    payload_path = _verified_asset(
        Path(payload["sealed_payload_path"]), payload["sealed_payload_digest"]
    )
    return GenerationWorkerCoLocatedAssets(
        package_root=package_root.resolve(strict=True),
        converter=converter,
        prepared_set=PreparedArtifactSet(recipe, paths),
        sealed_payload_path=payload_path,
    )


def _recipe_payload(recipe: LocalModelPreparationRecipe) -> dict[str, object]:
    return {
        "model_id": recipe.model_id,
        "adapter_id": recipe.adapter_id,
        "runner_id": recipe.runner_id,
        "recipe_id": recipe.recipe_id,
        "artifacts": [asdict(artifact) for artifact in recipe.artifacts],
        "transformation": (
            None if recipe.transformation is None else asdict(recipe.transformation)
        ),
        "loader_profile": (
            None if recipe.loader_profile is None else recipe.loader_profile.profile_id
        ),
    }


def _recipe_from_payload(value: object) -> LocalModelPreparationRecipe:
    if not isinstance(value, dict):
        raise GenerationWorkerAssetHandleError("generation worker asset is unavailable")
    artifacts = value.get("artifacts")
    transformation = value.get("transformation")
    loader_profile = value.get("loader_profile")
    if (
        not isinstance(artifacts, list)
        or not all(isinstance(artifact, dict) for artifact in artifacts)
        or transformation is not None
        and not isinstance(transformation, dict)
        or loader_profile is not None
        and not isinstance(loader_profile, str)
    ):
        raise GenerationWorkerAssetHandleError("generation worker asset is unavailable")
    try:
        return LocalModelPreparationRecipe(
            model_id=value["model_id"],
            adapter_id=value["adapter_id"],
            runner_id=value["runner_id"],
            recipe_id=value["recipe_id"],
            artifacts=tuple(LocalModelArtifact(**artifact) for artifact in artifacts),
            transformation=(
                None
                if transformation is None
                else LocalModelTransformation(**transformation)
            ),
            loader_profile=(
                None
                if loader_profile is None
                else LocalModelLoaderProfile(loader_profile)
            ),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise GenerationWorkerAssetHandleError(
            "generation worker asset is unavailable"
        ) from error


def _asset_within_root(*, root: Path, entrypoint: object, expected_digest: str) -> Path:
    if not isinstance(entrypoint, str) or not entrypoint:
        raise GenerationWorkerAssetHandleError("generation worker asset is unavailable")
    try:
        asset = (root / entrypoint).resolve(strict=True)
        asset.relative_to(root)
    except (OSError, ValueError) as error:
        raise GenerationWorkerAssetHandleError(
            "generation worker asset is unavailable"
        ) from error
    return _verified_asset(asset, expected_digest)
