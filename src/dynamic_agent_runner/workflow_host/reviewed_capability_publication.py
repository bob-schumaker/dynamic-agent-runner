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

    def query_current_outcome(self, *, reservation_id: str) -> str: ...

    def compensate(self, *, reservation_id: str) -> None: ...

    def assert_generation_current(
        self, *, reservation_id: str, generation_id: str
    ) -> bool: ...

    def unpublish_generation_atomically(
        self, *, reservation_id: str, generation_id: str
    ) -> None: ...


@dataclass(frozen=True)
class ReviewedCapabilityPublicationReceipt:
    """The private terminal result that DAR may expose only after completion."""

    status: str
    generation_id: str
    published_at: str
    artifacts: tuple[SealedArtifactOutputHandle, ...]
    counts: Mapping[str, int]


_COUNT_FIELDS = frozenset(
    {"source_records", "embedding_units", "indexed", "skipped", "deleted", "errored"}
)


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
            or not callable(getattr(host, "query_current_outcome", None))
            or not callable(getattr(host, "compensate", None))
            or not callable(getattr(host, "assert_generation_current", None))
            or not callable(getattr(host, "unpublish_generation_atomically", None))
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
            or not _valid_counts(counts)
        ):
            raise ReviewedCapabilityPublicationError("publication is unavailable")
        payload = {
            "replay_key": reservation_id,
            "reservation_id": reservation_id,
            "private_set_id": private.private_set_id,
            "generation_id": generation_id,
            "counts": dict(counts),
            "status": "prepared",
        }
        record: OpaqueRecord | None = None
        attempt_id: str | None = None
        try:
            attempt_id, replayed = self._store.issue_or_reuse(
                kind="reviewed_capability_publication",
                owner=self._owner,
                payload=payload,
                replay_key=reservation_id,
                conflict_keys={"reservation_id": reservation_id},
                expires_at=private.expires_at,
                now=now,
            )
            if replayed:
                record = self._store.load(
                    attempt_id,
                    expected_kind="reviewed_capability_publication",
                    owner=self._owner,
                    now=now,
                )
                if not _matches_completion_request(record.payload, payload):
                    raise ValueError
                if record.payload.get("status") == "completed":
                    return _receipt_from_record(record)
                raise ValueError
            record = self._advance(attempt_id, payload, "commit_intent", now=now)
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
            record = self._advance(
                attempt_id,
                record.payload,
                "completed",
                published_at=_timestamp(now),
                now=now,
            )
        except Exception as error:  # noqa: BLE001 - host boundary varies.
            if attempt_id is not None and record is not None:
                try:
                    if record.payload.get("status") in {"prepared", "commit_intent"}:
                        outcome = self._host.query_current_outcome(
                            reservation_id=reservation_id
                        )
                        if outcome == "pending":
                            self._advance(
                                attempt_id,
                                record.payload,
                                "recovery_required",
                                now=now,
                            )
                        else:
                            record = self._advance(
                                attempt_id, record.payload, "aborted", now=now
                            )
                            self._artifacts.discard(private, now=now)
                    else:
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
        return _receipt_from_record(record)

    def recover(
        self, *, reservation_id: str, now: datetime
    ) -> ReviewedCapabilityPublicationReceipt:
        """Resume only one host-confirmed pending attempt for this reservation."""

        if not isinstance(reservation_id, str) or not reservation_id:
            raise ReviewedCapabilityPublicationError("publication is unavailable")
        try:
            matches = [
                (attempt_id, record)
                for attempt_id, record in self._store.active_records(
                    kind="reviewed_capability_publication",
                    owner=self._owner,
                    now=now,
                )
                if record.payload.get("reservation_id") == reservation_id
                and record.payload.get("status") == "recovery_required"
            ]
            if len(matches) != 1:
                raise ValueError
            attempt_id, record = matches[0]
            generation_id = record.payload.get("generation_id")
            private_set_id = record.payload.get("private_set_id")
            counts = record.payload.get("counts")
            outcome = self._host.query_current_outcome(reservation_id=reservation_id)
            if (
                not isinstance(generation_id, str)
                or not isinstance(private_set_id, str)
                or not isinstance(counts, dict)
            ):
                raise ValueError
            if outcome != "pending":
                record = self._advance(
                    attempt_id, record.payload, "compensation_required", now=now
                )
                self._host.compensate(reservation_id=reservation_id)
                self._artifacts.discard(
                    SealedArtifactPrivateOutputSet(private_set_id, record.expires_at),
                    now=now,
                )
                self._advance(attempt_id, record.payload, "aborted", now=now)
                raise ValueError
            record = self._advance(attempt_id, record.payload, "host_pending", now=now)
            private = SealedArtifactPrivateOutputSet(private_set_id, record.expires_at)
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
            record = self._advance(
                attempt_id,
                record.payload,
                "completed",
                published_at=_timestamp(now),
                now=now,
            )
        except Exception as error:  # noqa: BLE001 - host boundary varies.
            raise ReviewedCapabilityPublicationError(
                "publication is unavailable"
            ) from error
        return _receipt_from_record(record)

    def maintain_retention(
        self,
        *,
        reservation_id: str,
        expires_at: datetime,
        now: datetime,
    ) -> str:
        """Retain current output sets or unpublish then retire non-current ones."""

        if not isinstance(reservation_id, str) or not reservation_id:
            raise ReviewedCapabilityPublicationError("publication is unavailable")
        try:
            matches = [
                (attempt_id, record)
                for attempt_id, record in self._store.active_records(
                    kind="reviewed_capability_publication",
                    owner=self._owner,
                    now=now,
                )
                if record.payload.get("reservation_id") == reservation_id
                and record.payload.get("status") == "completed"
            ]
            if len(matches) != 1:
                raise ValueError
            attempt_id, record = matches[0]
            generation_id = record.payload.get("generation_id")
            private_set_id = record.payload.get("private_set_id")
            artifacts = record.payload.get("artifacts")
            if (
                not isinstance(generation_id, str)
                or not isinstance(private_set_id, str)
                or not isinstance(artifacts, list)
            ):
                raise ValueError
            output_set_ids = {
                item.get("output_set_id")
                for item in artifacts
                if isinstance(item, dict) and isinstance(item.get("output_set_id"), str)
            }
            if len(output_set_ids) != 1:
                raise ValueError
            output_set_id = next(iter(output_set_ids))
            if self._host.assert_generation_current(
                reservation_id=reservation_id, generation_id=generation_id
            ):
                self._artifacts.extend_output_set(
                    output_set_id, expires_at=expires_at, now=now
                )
                self._store.extend_active_expiry(
                    attempt_id,
                    expected_kind="reviewed_capability_publication",
                    owner=self._owner,
                    expires_at=expires_at,
                    now=now,
                )
                return "retained"
            self._host.unpublish_generation_atomically(
                reservation_id=reservation_id, generation_id=generation_id
            )
            self._artifacts.discard(
                SealedArtifactPrivateOutputSet(private_set_id, record.expires_at),
                now=now,
            )
            self._advance(attempt_id, record.payload, "retired", now=now)
            return "retired"
        except Exception as error:  # noqa: BLE001 - host boundary varies.
            raise ReviewedCapabilityPublicationError(
                "publication is unavailable"
            ) from error

    def _advance(
        self,
        attempt_id: str,
        payload: Mapping[str, object],
        status: str,
        *,
        now: datetime,
        handles: tuple[SealedArtifactOutputHandle, ...] = (),
        published_at: str | None = None,
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
        if published_at is not None:
            replacement["published_at"] = published_at
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


def _valid_counts(counts: Mapping[str, int]) -> bool:
    return set(counts) == _COUNT_FIELDS and all(
        isinstance(value, int) and not isinstance(value, bool) and value >= 0
        for value in counts.values()
    )


def _matches_completion_request(
    stored: Mapping[str, object], requested: Mapping[str, object]
) -> bool:
    return all(
        stored.get(name) == requested.get(name)
        for name in (
            "replay_key",
            "reservation_id",
            "private_set_id",
            "generation_id",
            "counts",
        )
    )


def _receipt_from_record(record: OpaqueRecord) -> ReviewedCapabilityPublicationReceipt:
    payload = record.payload
    generation_id = payload.get("generation_id")
    published_at = payload.get("published_at")
    counts = payload.get("counts")
    artifacts = payload.get("artifacts")
    if (
        payload.get("status") != "completed"
        or not isinstance(generation_id, str)
        or not isinstance(published_at, str)
        or not isinstance(counts, dict)
        or not isinstance(artifacts, list)
    ):
        raise ReviewedCapabilityPublicationError("publication is unavailable")
    try:
        handles = tuple(
            SealedArtifactOutputHandle(
                output_set_id=item["output_set_id"],
                role=item["role"],
                media_type=item["media_type"],
                byte_count=item["byte_count"],
                content_digest=item["content_digest"],
                expires_at=record.expires_at,
            )
            for item in artifacts
            if isinstance(item, dict)
        )
    except (KeyError, TypeError) as error:
        raise ReviewedCapabilityPublicationError(
            "publication is unavailable"
        ) from error
    if len(handles) != len(artifacts):
        raise ReviewedCapabilityPublicationError("publication is unavailable")
    return ReviewedCapabilityPublicationReceipt(
        status="published",
        generation_id=generation_id,
        published_at=published_at,
        artifacts=handles,
        counts=counts,
    )
