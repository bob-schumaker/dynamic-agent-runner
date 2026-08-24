"""Wrapper-private, one-use approval records for external actions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from dar_workflow_server.state import OpaqueRecordError, PrivateStateStore


class WorkflowApprovalError(ValueError):
    """Raised when a wrapper approval is unavailable or does not bind an action."""


@dataclass(frozen=True)
class WorkflowApproval:
    """An opaque pending or granted approval receipt."""

    approval_id: str
    action_digest: str
    expires_at: datetime


class WorkflowApprovalStore:
    """Persist pending and granted approvals for one local OS principal."""

    def __init__(self, *, store: PrivateStateStore, owner: str) -> None:
        if not isinstance(owner, str) or not owner:
            raise WorkflowApprovalError("approval owner is invalid")
        self._store = store
        self._owner = owner

    def request(self, *, action_digest: str, now: datetime) -> WorkflowApproval:
        """Issue one short-lived, opaque pending approval for an action digest."""

        digest = _digest(action_digest)
        issued_at = _utc(now)
        expires_at = issued_at + timedelta(seconds=60)
        try:
            approval_id = self._store.issue(
                kind="workflow_action_approval_pending",
                owner=self._owner,
                payload={"action_digest": digest},
                expires_at=expires_at,
                now=issued_at,
            )
        except OpaqueRecordError as error:
            raise WorkflowApprovalError("approval is unavailable") from error
        return WorkflowApproval(approval_id, digest, expires_at)

    def grant(
        self, approval_id: str, *, action_digest: str, now: datetime
    ) -> WorkflowApproval:
        """Atomically turn a matching pending approval into one granted receipt."""

        digest = _digest(action_digest)
        try:
            pending = self._store.load(
                approval_id,
                expected_kind="workflow_action_approval_pending",
                owner=self._owner,
                now=now,
            )
            _require_digest(pending.payload, digest)
            granted_id = self._store.consume_and_issue(
                approval_id,
                expected_kind="workflow_action_approval_pending",
                owner=self._owner,
                new_kind="workflow_action_approval_granted",
                new_payload={"action_digest": digest},
                expires_at=pending.expires_at,
                now=now,
            )
        except OpaqueRecordError as error:
            if "expired" in str(error):
                raise WorkflowApprovalError("approval has expired") from error
            raise WorkflowApprovalError("approval is unavailable") from error
        return WorkflowApproval(granted_id, digest, pending.expires_at)

    def consume(self, approval_id: str, *, action_digest: str, now: datetime) -> None:
        """Atomically spend exactly one matching granted approval at dispatch."""

        digest = _digest(action_digest)
        try:
            granted = self._store.load(
                approval_id,
                expected_kind="workflow_action_approval_granted",
                owner=self._owner,
                now=now,
            )
            _require_digest(granted.payload, digest)
            self._store.consume(
                approval_id,
                expected_kind="workflow_action_approval_granted",
                owner=self._owner,
                now=now,
            )
        except OpaqueRecordError as error:
            if "expired" in str(error):
                raise WorkflowApprovalError("approval has expired") from error
            raise WorkflowApprovalError("approval is unavailable") from error


def _require_digest(payload: dict[str, object], expected: str) -> None:
    if set(payload) != {"action_digest"} or payload.get("action_digest") != expected:
        raise WorkflowApprovalError("approval action does not match")


def _digest(value: object) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise WorkflowApprovalError("approval action digest is invalid")
    return value


def _utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise WorkflowApprovalError("approval time is invalid")
    return value.astimezone(UTC)
