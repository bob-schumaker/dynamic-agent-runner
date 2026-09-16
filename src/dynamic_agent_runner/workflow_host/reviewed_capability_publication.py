"""Durable staged publication for reviewed host-capability outputs."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from dynamic_agent_runner.workflow_host.sealed_artifact_runner import (
    SealedArtifactOutputHandle,
    SealedArtifactOutputHandleService,
    SealedArtifactPrivateOutputSet,
)
from dynamic_agent_runner.workflow_host.state import (
    OpaqueRecord,
    OpaqueRecordError,
    PrivateStateStore,
)


class ReviewedCapabilityPublicationError(ValueError):
    """Raised when a staged reviewed-capability publication is unavailable."""


class ReviewedCapabilityPublicationHost(Protocol):
    """Host-owned reversible publication operations for one reservation."""

    def begin_pending_publication(
        self, *, reservation_id: str, generation_id: str
    ) -> None: ...

    def acknowledge_visibility(self, *, reservation_id: str) -> None: ...


@dataclass(frozen=True)
class ReviewedCapabilityPublicationReceipt:
    """The private terminal result that DAR may expose only after completion."""

    status: str
    generation_id: str
    published_at: str
    artifacts: tuple[SealedArtifactOutputHandle, ...]
    counts: Mapping[str, int]


class ReviewedCapabilityPublicationCoordinator:
    """Advance one staged output set through durable publication boundaries."""

    def __init__(
        self,
        *,
        store: PrivateStateStore,
        owner: str,
        artifacts: SealedArtifactOutputHandleService,
        host: ReviewedCapabilityPublicationHost,
    ) -> None:
        if (
            not isinstance(store, PrivateStateStore)
            or not isinstance(owner, str)
            or not owner
            or artifacts.owner != owner
            or not callable(getattr(host, "begin_pending_publication", None))
            or not callable(getattr(host, "acknowledge_visibility", None))
        ):
            raise ReviewedCapabilityPublicationError("publication is unavailable")
        self._store = store
        self._owner = owner
        self._artifacts = artifacts
        self._host = host

    def complete(
        self,
        *,
        reservation_id: str,
        private: SealedArtifactPrivateOutputSet,
        generation_id: str,
        counts: Mapping[str, int],
        now: datetime,
    ) -> ReviewedCapabilityPublicationReceipt:
        """Publish one already staged set only after every durable transition."""

        if (
            not isinstance(reservation_id, str)
            or not reservation_id
            or not isinstance(private, SealedArtifactPrivateOutputSet)
            or not isinstance(generation_id, str)
            or not generation_id
            or not isinstance(counts, Mapping)
        ):
            raise ReviewedCapabilityPublicationError("publication is unavailable")
        payload = {
            "reservation_id": reservation_id,
            "private_set_id": private.private_set_id,
            "generation_id": generation_id,
            "counts": dict(counts),
            "status": "prepared",
        }
        record: OpaqueRecord | None = None
        pending_attempted = False
        try:
            attempt_id = self._store.issue(
                kind="reviewed_capability_publication",
                owner=self._owner,
                payload=payload,
                expires_at=private.expires_at,
                now=now,
            )
            record = self._advance(attempt_id, payload, "commit_intent", now=now)
            pending_attempted = True
            self._host.begin_pending_publication(
                reservation_id=reservation_id, generation_id=generation_id
            )
            record = self._advance(attempt_id, record.payload, "host_pending", now=now)
            handles = self._artifacts.promote(private, now=now)
            record = self._advance(
                attempt_id,
                record.payload,
                "dar_promoted",
                handles=handles,
                now=now,
            )
            self._host.acknowledge_visibility(reservation_id=reservation_id)
            record = self._advance(attempt_id, record.payload, "host_visible", now=now)
            record = self._advance(attempt_id, record.payload, "completed", now=now)
        except Exception as error:  # noqa: BLE001 - host boundary varies.
            if pending_attempted and record is not None:
                try:
                    self._advance(
                        attempt_id,
                        record.payload,
                        "recovery_required",
                        now=now,
                    )
                except Exception:  # noqa: BLE001 - preserve the original failure.
                    pass
            raise ReviewedCapabilityPublicationError(
                "publication is unavailable"
            ) from error
        return ReviewedCapabilityPublicationReceipt(
            status="published",
            generation_id=generation_id,
            published_at=_timestamp(now),
            artifacts=handles,
            counts=dict(counts),
        )

    def _advance(
        self,
        attempt_id: str,
        payload: Mapping[str, object],
        status: str,
        *,
        now: datetime,
        handles: tuple[SealedArtifactOutputHandle, ...] = (),
    ) -> OpaqueRecord:
        replacement = {**payload, "status": status}
        if handles:
            replacement["artifacts"] = [
                {
                    "output_set_id": item.output_set_id,
                    "role": item.role,
                    "media_type": item.media_type,
                    "byte_count": item.byte_count,
                    "content_digest": item.content_digest,
                }
                for item in handles
            ]
        record = self._store.load(
            attempt_id,
            expected_kind="reviewed_capability_publication",
            owner=self._owner,
            now=now,
        )
        if record.payload != dict(payload):
            raise OpaqueRecordError("publication payload does not match")
        return self._store.replace_active_payload(
            attempt_id,
            expected_kind="reviewed_capability_publication",
            owner=self._owner,
            expected_payload_digest=record.payload_digest,
            payload=replacement,
            now=now,
        )


def _timestamp(now: datetime) -> str:
    if not isinstance(now, datetime) or now.tzinfo is None:
        raise ReviewedCapabilityPublicationError("publication is unavailable")
    return now.astimezone(UTC).isoformat().replace("+00:00", "Z")
