"""Durable, redacted state transitions for one external workflow action."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime

from dynamic_agent_runner.workflow_host.state import (
    OpaqueRecordError,
    PrivateStateStore,
)


class ActionLedgerError(ValueError):
    """Raised when an external action cannot move through its durable ledger."""


@dataclass(frozen=True)
class ExternalAction:
    """Wrapper-private action material used only to derive a non-secret digest."""

    workflow_id: str
    registration_digest: str
    profile_id: str
    snapshot_id: str
    connection_generation: int
    trace_correlation: str
    tool_id: str
    remote_tool_name: str
    side_effect: str
    normalized_arguments: Mapping[str, object]
    workspace_artifact_hashes: Mapping[str, str]


@dataclass(frozen=True)
class ActionLedgerEvent:
    """Redaction-safe receipt for one durable action state transition."""

    action_id: str
    action_digest: str
    status: str


class WorkflowActionLedger:
    """Append-only action states with one atomic intent-to-dispatch claim."""

    def __init__(self, *, store: PrivateStateStore, owner: str) -> None:
        if not isinstance(owner, str) or not owner:
            raise ActionLedgerError("action ledger owner is invalid")
        self._store = store
        self._owner = owner

    def record_intent(
        self, action: ExternalAction, *, now: datetime
    ) -> ActionLedgerEvent:
        """Persist non-secret intent before a future handler may dispatch."""

        digest = _action_digest(action)
        try:
            action_id = self._store.issue(
                kind="workflow_action_intent",
                owner=self._owner,
                payload=_payload(
                    digest,
                    "intent",
                    connection_generation=action.connection_generation,
                    trace_correlation=action.trace_correlation,
                ),
                expires_at=datetime.max.replace(tzinfo=UTC),
                now=now,
            )
        except OpaqueRecordError as error:
            raise ActionLedgerError("action intent is unavailable") from error
        return ActionLedgerEvent(action_id, digest, "intent")

    def claim_dispatch(self, intent_id: str, *, now: datetime) -> ActionLedgerEvent:
        """Atomically spend one intent, then durably record dispatch eligibility."""

        try:
            intent = self._store.load(
                intent_id,
                expected_kind="workflow_action_intent",
                owner=self._owner,
                now=now,
            )
            action_digest = _action_digest_from_payload(intent.payload, "intent")
            connection_generation, trace_correlation = _receipt_metadata(intent.payload)
            dispatch_id = self._store.consume_and_issue(
                intent_id,
                expected_kind="workflow_action_intent",
                owner=self._owner,
                new_kind="workflow_action_dispatched",
                new_payload=_payload(
                    action_digest,
                    "dispatched",
                    parent_action_id=intent_id,
                    connection_generation=connection_generation,
                    trace_correlation=trace_correlation,
                ),
                expires_at=datetime.max.replace(tzinfo=UTC),
                now=now,
            )
        except OpaqueRecordError as error:
            raise ActionLedgerError("action dispatch is unavailable") from error
        return ActionLedgerEvent(dispatch_id, action_digest, "dispatched")

    def record_terminal(
        self, action_id: str, status: str, *, now: datetime
    ) -> ActionLedgerEvent:
        """Consume an active intent/dispatch record and append its terminal state."""

        if status not in _TERMINAL_STATUSES:
            raise ActionLedgerError("action terminal status is invalid")
        try:
            source_status = self._terminal_source_status(action_id, now=now)
            if source_status == "intent" and status in {"completed", "outcome_unknown"}:
                raise ActionLedgerError("action terminal status requires dispatch")
            source = self._store.load(
                action_id,
                expected_kind=f"workflow_action_{source_status}",
                owner=self._owner,
                now=now,
            )
            action_digest = _action_digest_from_payload(source.payload, source_status)
            connection_generation, trace_correlation = _receipt_metadata(source.payload)
            terminal_id = self._store.consume_and_issue(
                action_id,
                expected_kind=f"workflow_action_{source_status}",
                owner=self._owner,
                new_kind="workflow_action_terminal",
                new_payload=_payload(
                    action_digest,
                    status,
                    parent_action_id=action_id,
                    connection_generation=connection_generation,
                    trace_correlation=trace_correlation,
                ),
                expires_at=datetime.max.replace(tzinfo=UTC),
                now=now,
            )
        except OpaqueRecordError as error:
            raise ActionLedgerError("action terminal state is unavailable") from error
        return ActionLedgerEvent(terminal_id, action_digest, status)

    def _terminal_source_status(self, action_id: str, *, now: datetime) -> str:
        try:
            self._store.load(
                action_id,
                expected_kind="workflow_action_dispatched",
                owner=self._owner,
                now=now,
            )
            return "dispatched"
        except OpaqueRecordError:
            self._store.load(
                action_id,
                expected_kind="workflow_action_intent",
                owner=self._owner,
                now=now,
            )
            return "intent"


_TERMINAL_STATUSES = frozenset(
    {"completed", "denied", "cancelled", "failed", "outcome_unknown"}
)


def _action_digest(action: ExternalAction) -> str:
    values = {
        "format_version": 1,
        "workflow_id": _text(action.workflow_id, "workflow_id"),
        "registration_digest": _digest(
            action.registration_digest, "registration_digest"
        ),
        "profile_id": _opaque_id(action.profile_id, "profile_id"),
        "snapshot_id": _opaque_id(action.snapshot_id, "snapshot_id"),
        "connection_generation": _positive_int(
            action.connection_generation, "connection_generation"
        ),
        "trace_correlation": _text(action.trace_correlation, "trace_correlation"),
        "tool_id": _text(action.tool_id, "tool_id"),
        "remote_tool_name": _text(action.remote_tool_name, "remote_tool_name"),
        "side_effect": _side_effect(action.side_effect),
        "normalized_arguments": _json_mapping(
            action.normalized_arguments, "normalized_arguments"
        ),
        "workspace_artifact_hashes": _artifact_hashes(action.workspace_artifact_hashes),
    }
    return hashlib.sha256(_canonical_json(values).encode("utf-8")).hexdigest()


def _payload(
    action_digest: str,
    status: str,
    *,
    parent_action_id: str | None = None,
    connection_generation: int | None = None,
    trace_correlation: str | None = None,
) -> dict[str, str]:
    payload = {"action_digest": action_digest, "status": status}
    if connection_generation is not None:
        payload["connection_generation"] = str(
            _positive_int(connection_generation, "connection_generation")
        )
    if trace_correlation is not None:
        payload["trace_correlation"] = _text(trace_correlation, "trace_correlation")
    if parent_action_id is not None:
        payload["parent_action_id"] = _opaque_id(parent_action_id, "parent_action_id")
    return payload


def _action_digest_from_payload(payload: Mapping[str, object], status: str) -> str:
    allowed = {
        "action_digest",
        "status",
        "connection_generation",
        "trace_correlation",
    }
    if status == "dispatched":
        allowed.add("parent_action_id")
    if set(payload) != allowed or payload.get("status") != status:
        raise OpaqueRecordError("action ledger record is invalid")
    return _digest(payload.get("action_digest"), "action_digest")


def _receipt_metadata(payload: Mapping[str, object]) -> tuple[int, str]:
    value = payload.get("connection_generation")
    if not isinstance(value, str) or not value.isdecimal():
        raise OpaqueRecordError("action ledger record is invalid")
    return (
        _positive_int(int(value), "connection_generation"),
        _text(payload.get("trace_correlation"), "trace_correlation"),
    )


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ActionLedgerError(f"action {label} is invalid")
    return value


def _digest(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ActionLedgerError(f"action {label} is invalid")
    return value


def _opaque_id(value: object, label: str) -> str:
    value = _text(value, label)
    if not value.startswith("v1."):
        raise ActionLedgerError(f"action {label} is invalid")
    return value


def _side_effect(value: object) -> str:
    if value not in {"write", "delete"}:
        raise ActionLedgerError("action side_effect is invalid")
    return value


def _positive_int(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ActionLedgerError(f"action {label} is invalid")
    return value


def _json_mapping(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise ActionLedgerError(f"action {label} is invalid")
    try:
        parsed = json.loads(_canonical_json(dict(value)))
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        raise ActionLedgerError(f"action {label} is invalid") from error
    if not isinstance(parsed, dict):
        raise ActionLedgerError(f"action {label} is invalid")
    return parsed


def _artifact_hashes(value: Mapping[str, str]) -> dict[str, str]:
    result = _json_mapping(value, "workspace_artifact_hashes")
    for artifact_id, content_hash in result.items():
        _opaque_id(artifact_id, "artifact_id")
        if (
            not isinstance(content_hash, str)
            or len(content_hash) != 71
            or not content_hash.startswith("sha256:")
            or any(
                character not in "0123456789abcdef" for character in content_hash[7:]
            )
        ):
            raise ActionLedgerError("action content hash is invalid")
    return result  # type: ignore[return-value]


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
