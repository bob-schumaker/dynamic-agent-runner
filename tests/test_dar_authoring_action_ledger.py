"""Tests for durable, redacted workflow external-action records."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier

import pytest


from dynamic_agent_runner.workflow_host.action_ledger import (  # noqa: E402
    ActionLedgerError,
    ExternalAction,
    ReviewedCapabilityReservationRequest,
    WorkflowActionLedger,
)
from dynamic_agent_runner.workflow_host.approvals import (  # noqa: E402
    WorkflowApprovalError,
    WorkflowApprovalStore,
)
from dynamic_agent_runner.workflow_host.state import PrivateStateStore  # noqa: E402


NOW = datetime(2026, 8, 23, tzinfo=UTC)


def _ledger(tmp_path: Path) -> WorkflowActionLedger:
    return WorkflowActionLedger(
        store=PrivateStateStore(tmp_path / "state"), owner="local-os-user-v1:501:ada"
    )


def _action() -> ExternalAction:
    return ExternalAction(
        workflow_id="email-helper",
        registration_digest="a" * 64,
        profile_id="v1.profile.signature",
        snapshot_id="v1.snapshot.signature",
        connection_generation=1,
        trace_correlation="run-1",
        tool_id="send_email",
        remote_tool_name="send_email",
        side_effect="write",
        normalized_arguments={
            "recipient": "ada@example.test",
            "body": "private email body",
        },
        workspace_artifact_hashes={"v1.body-artifact": "sha256:" + "b" * 64},
    )


def _reviewed_reservation(
    *, run_id: str = "run-1", job_opaque_id: str = "job-1"
) -> ReviewedCapabilityReservationRequest:
    return ReviewedCapabilityReservationRequest(
        run_id=run_id,
        package_registration_digest="a" * 64,
        package_revision_digest="b" * 64,
        declared_call_site_id="build_vector_index",
        template_capability_id="vector_index.build.v1",
        template_contract_version="1",
        template_digest="c" * 64,
        job_issuer_id="host-local",
        job_opaque_id=job_opaque_id,
        job_revision="1",
        job_digest="d" * 64,
        principal="local-os-user-v1:501:ada",
        approval_nonce="v1.approval.nonce",
    )


def test_ledger_persists_redacted_intent_then_dispatch_and_terminal_outcome(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)

    intent = ledger.record_intent(_action(), now=NOW)
    dispatched = ledger.claim_dispatch(intent.action_id, now=NOW)
    outcome = ledger.record_terminal(
        dispatched.action_id, "completed", now=NOW + timedelta(seconds=1)
    )

    assert intent.status == "intent"
    assert dispatched.status == "dispatched"
    assert outcome.status == "completed"
    assert intent.action_digest == dispatched.action_digest == outcome.action_digest
    state = (tmp_path / "state" / "records.json").read_text(encoding="utf-8")
    assert "private email body" not in state
    assert "ada@example.test" not in state
    assert '"connection_generation":"1"' in state
    assert '"trace_correlation":"run-1"' in state


@pytest.mark.parametrize(
    "changed_action",
    (
        lambda action: replace(action, registration_digest="c" * 64),
        lambda action: replace(action, profile_id="v1.profile.changed"),
        lambda action: replace(action, snapshot_id="v1.snapshot.changed"),
        lambda action: replace(
            action,
            normalized_arguments={
                **action.normalized_arguments,
                "recipient": "bea@example.test",
            },
        ),
        lambda action: replace(
            action,
            normalized_arguments={
                **action.normalized_arguments,
                "subject": "Changed subject",
            },
        ),
        lambda action: replace(
            action,
            workspace_artifact_hashes={"v1.body-artifact": "sha256:" + "c" * 64},
        ),
    ),
)
def test_pending_approval_rejects_every_action_digest_change(
    tmp_path: Path, changed_action
) -> None:
    ledger = _ledger(tmp_path)
    owner = "local-os-user-v1:501:ada"
    approvals = WorkflowApprovalStore(
        store=PrivateStateStore(tmp_path / "state"), owner=owner
    )
    original = ledger.record_intent(_action(), now=NOW)
    changed = ledger.record_intent(changed_action(_action()), now=NOW)
    pending = approvals.request(action_digest=original.action_digest, now=NOW)

    assert changed.action_digest != original.action_digest
    with pytest.raises(WorkflowApprovalError, match="does not match"):
        approvals.grant(
            pending.approval_id, action_digest=changed.action_digest, now=NOW
        )


def test_ledger_allows_exactly_one_atomic_dispatch_claim(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)
    action_id = ledger.record_intent(_action(), now=NOW).action_id
    other = _ledger(tmp_path)
    barrier = Barrier(2)

    def claim(candidate: WorkflowActionLedger) -> bool:
        barrier.wait()
        try:
            candidate.claim_dispatch(action_id, now=NOW)
        except ActionLedgerError:
            return False
        return True

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(claim, (ledger, other)))

    assert outcomes.count(True) == 1
    assert outcomes.count(False) == 1


def test_reviewed_capability_reservation_replays_only_the_exact_approved_tuple(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    request = _reviewed_reservation()

    reserved = ledger.reserve_reviewed_capability(request, now=NOW)
    replay = ledger.reserve_reviewed_capability(request, now=NOW)

    assert reserved.status == replay.status == "reserved"
    assert reserved.action_id == replay.action_id
    assert reserved.action_digest == replay.action_digest

    with pytest.raises(ActionLedgerError, match="reservation"):
        ledger.reserve_reviewed_capability(
            _reviewed_reservation(job_opaque_id="job-2"), now=NOW
        )
    with pytest.raises(ActionLedgerError, match="reservation"):
        ledger.reserve_reviewed_capability(
            _reviewed_reservation(run_id="run-2"), now=NOW
        )


def test_reviewed_capability_reservation_is_atomic_across_ledger_instances(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    other = _ledger(tmp_path)
    barrier = Barrier(2)

    def reserve(candidate: WorkflowActionLedger) -> str:
        barrier.wait()
        return candidate.reserve_reviewed_capability(
            _reviewed_reservation(), now=NOW
        ).action_id

    with ThreadPoolExecutor(max_workers=2) as executor:
        reservation_ids = tuple(executor.map(reserve, (ledger, other)))

    assert reservation_ids[0] == reservation_ids[1]


@pytest.mark.parametrize("status", ["denied", "cancelled", "failed"])
def test_ledger_records_nonexecuting_or_uncertain_terminal_outcomes(
    tmp_path: Path, status: str
) -> None:
    ledger = _ledger(tmp_path)
    intent = ledger.record_intent(_action(), now=NOW)

    outcome = ledger.record_terminal(intent.action_id, status, now=NOW)

    assert outcome.status == status


def test_ledger_records_an_uncertain_outcome_only_after_dispatch(
    tmp_path: Path,
) -> None:
    ledger = _ledger(tmp_path)
    intent = ledger.record_intent(_action(), now=NOW)
    dispatched = ledger.claim_dispatch(intent.action_id, now=NOW)

    outcome = ledger.record_terminal(dispatched.action_id, "outcome_unknown", now=NOW)

    assert outcome.status == "outcome_unknown"


def test_ledger_rejects_invalid_action_or_terminal_state(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)
    intent = ledger.record_intent(_action(), now=NOW)

    with pytest.raises(ActionLedgerError, match="terminal"):
        ledger.record_terminal(intent.action_id, "anything", now=NOW)
    with pytest.raises(ActionLedgerError, match="requires dispatch"):
        ledger.record_terminal(intent.action_id, "completed", now=NOW)
    with pytest.raises(ActionLedgerError, match="unavailable"):
        ledger.claim_dispatch("v1.unknown.signature", now=NOW)
