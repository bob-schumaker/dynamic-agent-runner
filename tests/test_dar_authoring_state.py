"""Tests for DAR authoring's private opaque-record state store."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier

import pytest


PLUGIN_SERVER_ROOT = Path(__file__).resolve().parents[1] / "dar-authoring" / "server"
sys.path.insert(0, str(PLUGIN_SERVER_ROOT))

from dar_workflow_server.state import (  # noqa: E402
    OpaqueRecordError,
    PrivateStateStore,
)


NOW = datetime(2026, 8, 23, tzinfo=UTC)


def _store(tmp_path: Path) -> PrivateStateStore:
    return PrivateStateStore(tmp_path / "state")


def test_issued_handle_loads_only_for_its_kind_and_owner(tmp_path: Path) -> None:
    store = _store(tmp_path)
    handle = store.issue(
        kind="package_source",
        owner="local-user",
        payload={"source_digest": "a" * 64},
        expires_at=NOW + timedelta(minutes=5),
        now=NOW,
    )

    record = store.load(
        handle,
        expected_kind="package_source",
        owner="local-user",
        now=NOW,
    )

    assert record.kind == "package_source"
    assert record.owner == "local-user"
    assert (
        record.payload_digest
        == "cfafe9fa678e552e8152cac15c082681f95a53b765623a2cec077149e989c33f"
    )
    assert record.state == "active"
    assert record.payload == {"source_digest": "a" * 64}

    with pytest.raises(OpaqueRecordError, match="kind"):
        store.load(
            handle,
            expected_kind="prepared_input",
            owner="local-user",
            now=NOW,
        )
    with pytest.raises(OpaqueRecordError, match="owner"):
        store.load(
            handle,
            expected_kind="package_source",
            owner="other-user",
            now=NOW,
        )


def test_expired_revoked_and_consumed_handles_fail_closed(tmp_path: Path) -> None:
    store = _store(tmp_path)
    expired = store.issue(
        kind="prepared_input",
        owner="local-user",
        payload={"registration": "r1"},
        expires_at=NOW + timedelta(seconds=1),
        now=NOW,
    )
    revoked = store.issue(
        kind="prepared_input",
        owner="local-user",
        payload={"registration": "r2"},
        expires_at=NOW + timedelta(minutes=5),
        now=NOW,
    )
    consumed = store.issue(
        kind="prepared_input",
        owner="local-user",
        payload={"registration": "r3"},
        expires_at=NOW + timedelta(minutes=5),
        now=NOW,
    )

    store.revoke(revoked, owner="local-user", now=NOW)
    store.consume(consumed, expected_kind="prepared_input", owner="local-user", now=NOW)

    for handle, moment, expected in (
        (expired, NOW + timedelta(seconds=2), "expired"),
        (revoked, NOW, "revoked"),
        (consumed, NOW, "consumed"),
    ):
        with pytest.raises(OpaqueRecordError, match=expected):
            store.load(
                handle,
                expected_kind="prepared_input",
                owner="local-user",
                now=moment,
            )


def test_concurrent_consumers_have_exactly_one_winner(tmp_path: Path) -> None:
    store = _store(tmp_path)
    handle = store.issue(
        kind="prepared_input",
        owner="local-user",
        payload={"value": "one"},
        expires_at=NOW + timedelta(minutes=1),
        now=NOW,
    )
    other_store = _store(tmp_path)
    barrier = Barrier(2)

    def consume_once(candidate: PrivateStateStore) -> bool:
        barrier.wait()
        try:
            candidate.consume(
                handle,
                expected_kind="prepared_input",
                owner="local-user",
                now=NOW,
            )
        except OpaqueRecordError:
            return False
        return True

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(consume_once, (store, other_store)))

    assert results.count(True) == 1
    assert results.count(False) == 1


def test_forged_or_tampered_records_are_rejected(tmp_path: Path) -> None:
    store = _store(tmp_path)
    handle = store.issue(
        kind="registration",
        owner="local-user",
        payload={"registration_digest": "b" * 64},
        expires_at=NOW + timedelta(minutes=5),
        now=NOW,
    )

    with pytest.raises(OpaqueRecordError, match="unknown or forged"):
        store.load(
            f"{handle}x",
            expected_kind="registration",
            owner="local-user",
            now=NOW,
        )

    state_path = tmp_path / "state" / "records.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["records"][handle]["payload"]["registration_digest"] = "c" * 64
    state_path.write_text(json.dumps(state), encoding="utf-8")

    with pytest.raises(OpaqueRecordError, match="integrity"):
        store.load(
            handle,
            expected_kind="registration",
            owner="local-user",
            now=NOW,
        )


def test_records_survive_store_reopen(tmp_path: Path) -> None:
    store = _store(tmp_path)
    handle = store.issue(
        kind="package_source",
        owner="local-user",
        payload={"source_digest": "d" * 64},
        expires_at=NOW + timedelta(minutes=5),
        now=NOW,
    )

    reopened = _store(tmp_path)

    assert reopened.load(
        handle,
        expected_kind="package_source",
        owner="local-user",
        now=NOW,
    ).payload == {"source_digest": "d" * 64}
