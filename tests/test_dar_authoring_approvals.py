"""Tests for one-use wrapper approval records."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
import sys

import pytest


PLUGIN_SERVER_ROOT = Path(__file__).resolve().parents[1] / "dar-authoring" / "server"
sys.path.insert(0, str(PLUGIN_SERVER_ROOT))

from dar_workflow_server.approvals import (  # noqa: E402
    WorkflowApprovalError,
    WorkflowApprovalStore,
)
from dar_workflow_server.state import PrivateStateStore  # noqa: E402


NOW = datetime(2026, 8, 24, tzinfo=UTC)
DIGEST = "a" * 64


def _approvals(tmp_path: Path) -> WorkflowApprovalStore:
    return WorkflowApprovalStore(
        store=PrivateStateStore(tmp_path / "state"), owner="local-os-user-v1:501:ada"
    )


def test_approval_is_granted_and_consumed_once_for_the_exact_action(
    tmp_path: Path,
) -> None:
    approvals = _approvals(tmp_path)
    pending = approvals.request(action_digest=DIGEST, now=NOW)
    granted = approvals.grant(
        pending.approval_id, action_digest=DIGEST, now=NOW + timedelta(seconds=1)
    )

    approvals.consume(
        granted.approval_id, action_digest=DIGEST, now=NOW + timedelta(seconds=2)
    )

    with pytest.raises(WorkflowApprovalError, match="unavailable"):
        approvals.consume(
            granted.approval_id, action_digest=DIGEST, now=NOW + timedelta(seconds=2)
        )


def test_approval_rejects_a_changed_action_without_spending_the_request(
    tmp_path: Path,
) -> None:
    approvals = _approvals(tmp_path)
    pending = approvals.request(action_digest=DIGEST, now=NOW)

    with pytest.raises(WorkflowApprovalError, match="does not match"):
        approvals.grant(pending.approval_id, action_digest="b" * 64, now=NOW)

    granted = approvals.grant(pending.approval_id, action_digest=DIGEST, now=NOW)
    assert granted.action_digest == DIGEST
    with pytest.raises(WorkflowApprovalError, match="does not match"):
        approvals.consume(granted.approval_id, action_digest="b" * 64, now=NOW)
    approvals.consume(granted.approval_id, action_digest=DIGEST, now=NOW)


def test_approval_expires_without_creating_a_grant(tmp_path: Path) -> None:
    approvals = _approvals(tmp_path)
    pending = approvals.request(action_digest=DIGEST, now=NOW)

    with pytest.raises(WorkflowApprovalError, match="expired"):
        approvals.grant(
            pending.approval_id,
            action_digest=DIGEST,
            now=NOW + timedelta(minutes=2),
        )


def test_denied_approval_cannot_later_be_granted(tmp_path: Path) -> None:
    approvals = _approvals(tmp_path)
    pending = approvals.request(action_digest=DIGEST, now=NOW)

    approvals.deny(pending.approval_id, action_digest=DIGEST, now=NOW)

    with pytest.raises(WorkflowApprovalError, match="unavailable"):
        approvals.grant(pending.approval_id, action_digest=DIGEST, now=NOW)
