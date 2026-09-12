"""Host-private read-only asset handles for generation-worker children."""

from __future__ import annotations

from datetime import datetime
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path
import stat

from dynamic_agent_runner.workflow_host.generation_worker import (
    GenerationWorkerLaunchDescriptor,
)
from dynamic_agent_runner.workflow_host.state import (
    OpaqueRecordError,
    PrivateStateStore,
)


class GenerationWorkerAssetHandleError(ValueError):
    """Raised without disclosing worker asset locations or contents."""


class GenerationWorkerAssetHandleService:
    """Issue descriptor-bound opaque handles for verified immutable local assets."""

    _KIND = "generation_worker_read_only_asset"

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
