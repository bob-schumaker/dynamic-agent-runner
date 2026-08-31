"""Private, authenticated opaque-record storage for DAR authoring."""

from __future__ import annotations

import base64
import fcntl
import hashlib
import hmac
import json
import os
import secrets
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator, Mapping


class OpaqueRecordError(ValueError):
    """Raised when an opaque record cannot be used safely."""


@dataclass(frozen=True)
class OpaqueRecord:
    """A private record returned only after handle authentication and checks."""

    kind: str
    owner: str
    payload: dict[str, Any]
    payload_digest: str
    issued_at: datetime
    expires_at: datetime
    state: str


class PrivateStateStore:
    """A small per-user store for authenticated opaque records.

    Callers hold only an opaque handle. Every record is MAC-protected using a
    store-local key, so a changed on-disk record fails closed before its payload
    is returned.
    """

    def __init__(self, root: Path) -> None:
        self._root = root
        self._records_path = root / "records.json"
        self._lock_path = root / "records.lock"
        self._key_path = root / "record-key"
        self._root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self._key = self._load_or_create_key()

    @classmethod
    def for_current_user(cls, app_name: str = "dar-authoring") -> PrivateStateStore:
        """Create the v1 store in the current OS user's private state location."""

        if sys_platform() == "darwin":
            root = Path.home() / "Library" / "Application Support" / app_name
        else:
            state_home = os.environ.get("XDG_STATE_HOME")
            root = (
                Path(state_home) if state_home else Path.home() / ".local" / "state"
            ) / app_name
        return cls(root)

    def issue(
        self,
        *,
        kind: str,
        owner: str,
        payload: Mapping[str, Any],
        expires_at: datetime,
        now: datetime,
    ) -> str:
        """Issue one active opaque record with a bounded lifetime."""

        _require_nonempty(kind, "kind")
        _require_nonempty(owner, "owner")
        issued_at = _as_utc(now, "now")
        expiry = _as_utc(expires_at, "expires_at")
        if expiry <= issued_at:
            raise OpaqueRecordError("expires_at must be after now")
        payload_copy = _canonical_payload(payload)
        handle = self._new_handle()
        raw_record = self._new_raw_record(
            kind=kind,
            owner=owner,
            payload=payload_copy,
            issued_at=issued_at,
            expires_at=expiry,
        )
        with self._mutation_lock():
            records = self._read_records()
            records[handle] = raw_record
            self._write_records(records)
        return handle

    def load(
        self,
        handle: str,
        *,
        expected_kind: str,
        owner: str,
        now: datetime,
    ) -> OpaqueRecord:
        """Load an active record only for its intended kind and owner."""

        _require_nonempty(expected_kind, "expected_kind")
        record = self._validated_record(handle, owner=owner)
        if record.kind != expected_kind:
            raise OpaqueRecordError("opaque record kind does not match")
        self._require_active(record, now)
        return record

    def active_records(
        self, *, kind: str, owner: str, now: datetime
    ) -> tuple[tuple[str, OpaqueRecord], ...]:
        """Return the caller's active records of one internal kind."""

        _require_nonempty(kind, "kind")
        _require_nonempty(owner, "owner")
        with self._mutation_lock():
            records = self._read_records()
            active: list[tuple[str, OpaqueRecord]] = []
            for handle in sorted(records):
                raw_record = records[handle]
                if raw_record.get("owner") != owner:
                    continue
                record = self._validated_record_from_records(
                    handle, owner=owner, records=records
                )
                if record.kind != kind:
                    continue
                try:
                    self._require_active(record, now)
                except OpaqueRecordError:
                    continue
                active.append((handle, record))
        return tuple(active)

    def revoke(self, handle: str, *, owner: str, now: datetime) -> None:
        """Irreversibly revoke an active record owned by the caller."""

        with self._mutation_lock():
            records = self._read_records()
            self._active_record(
                handle, expected_kind=None, owner=owner, now=now, records=records
            )
            self._change_state_in_records(records, handle, "revoked")

    def consume(
        self,
        handle: str,
        *,
        expected_kind: str,
        owner: str,
        now: datetime,
    ) -> OpaqueRecord:
        """Consume an active record after validating its complete binding."""

        with self._mutation_lock():
            records = self._read_records()
            record = self._active_record(
                handle,
                expected_kind=expected_kind,
                owner=owner,
                now=now,
                records=records,
            )
            self._change_state_in_records(records, handle, "consumed")
            return record

    def consume_and_issue(
        self,
        handle: str,
        *,
        expected_kind: str,
        owner: str,
        new_kind: str,
        new_payload: Mapping[str, Any],
        expires_at: datetime,
        now: datetime,
    ) -> str:
        """Atomically consume one active record and issue its replacement."""

        _require_nonempty(expected_kind, "expected_kind")
        _require_nonempty(new_kind, "new_kind")
        _require_nonempty(owner, "owner")
        issued_at = _as_utc(now, "now")
        expiry = _as_utc(expires_at, "expires_at")
        if expiry <= issued_at:
            raise OpaqueRecordError("expires_at must be after now")
        payload_copy = _canonical_payload(new_payload)
        replacement = self._new_handle()
        replacement_record = self._new_raw_record(
            kind=new_kind,
            owner=owner,
            payload=payload_copy,
            issued_at=issued_at,
            expires_at=expiry,
        )
        with self._mutation_lock():
            records = self._read_records()
            self._active_record(
                handle,
                expected_kind=expected_kind,
                owner=owner,
                now=now,
                records=records,
            )
            raw_record = records.get(handle)
            if raw_record is None:
                raise OpaqueRecordError("unknown or forged opaque record")
            raw_record["state"] = "consumed"
            raw_record["mac"] = self._record_mac(raw_record)
            records[replacement] = replacement_record
            self._write_records(records)
        return replacement

    def _validated_record(self, handle: str, *, owner: str) -> OpaqueRecord:
        return self._validated_record_from_records(
            handle, owner=owner, records=self._read_records()
        )

    def _validated_record_from_records(
        self,
        handle: str,
        *,
        owner: str,
        records: Mapping[str, Mapping[str, Any]],
    ) -> OpaqueRecord:
        _require_nonempty(owner, "owner")
        self._validate_handle(handle)
        raw_record = records.get(handle)
        if raw_record is None:
            raise OpaqueRecordError("unknown or forged opaque record")
        if not isinstance(raw_record, dict) or not hmac.compare_digest(
            str(raw_record.get("mac", "")), self._record_mac(raw_record)
        ):
            raise OpaqueRecordError("opaque record integrity check failed")
        record = _to_record(raw_record)
        if not hmac.compare_digest(record.owner, owner):
            raise OpaqueRecordError("opaque record owner does not match")
        return record

    def _active_record(
        self,
        handle: str,
        *,
        expected_kind: str | None,
        owner: str,
        now: datetime,
        records: Mapping[str, Mapping[str, Any]],
    ) -> OpaqueRecord:
        record = self._validated_record_from_records(
            handle, owner=owner, records=records
        )
        if expected_kind is not None and record.kind != expected_kind:
            raise OpaqueRecordError("opaque record kind does not match")
        self._require_active(record, now)
        return record

    def _change_state_in_records(
        self, records: dict[str, dict[str, Any]], handle: str, state: str
    ) -> None:
        raw_record = records.get(handle)
        if raw_record is None:
            raise OpaqueRecordError("unknown or forged opaque record")
        raw_record["state"] = state
        raw_record["mac"] = self._record_mac(raw_record)
        self._write_records(records)

    @contextmanager
    def _mutation_lock(self) -> Iterator[None]:
        """Hold an advisory cross-process lock while replacing record state."""

        descriptor = os.open(self._lock_path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)

    def _require_active(self, record: OpaqueRecord, now: datetime) -> None:
        if record.expires_at <= _as_utc(now, "now"):
            raise OpaqueRecordError("opaque record has expired")
        if record.state != "active":
            raise OpaqueRecordError(f"opaque record is {record.state}")

    def _new_handle(self) -> str:
        token = secrets.token_urlsafe(32)
        signature = _handle_signature(self._key, token)
        return f"v1.{token}.{signature}"

    def _new_raw_record(
        self,
        *,
        kind: str,
        owner: str,
        payload: dict[str, Any],
        issued_at: datetime,
        expires_at: datetime,
    ) -> dict[str, Any]:
        raw_record = {
            "kind": kind,
            "owner": owner,
            "payload": payload,
            "payload_digest": _digest(payload),
            "issued_at": _timestamp(issued_at),
            "expires_at": _timestamp(expires_at),
            "state": "active",
        }
        raw_record["mac"] = self._record_mac(raw_record)
        return raw_record

    def _validate_handle(self, handle: str) -> None:
        parts = handle.split(".") if isinstance(handle, str) else []
        if len(parts) != 3 or parts[0] != "v1":
            raise OpaqueRecordError("unknown or forged opaque record")
        if not hmac.compare_digest(parts[2], _handle_signature(self._key, parts[1])):
            raise OpaqueRecordError("unknown or forged opaque record")

    def _load_or_create_key(self) -> bytes:
        try:
            return base64.urlsafe_b64decode(self._key_path.read_bytes())
        except FileNotFoundError:
            key = secrets.token_bytes(32)
            descriptor = os.open(
                self._key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
            )
            with os.fdopen(descriptor, "wb") as key_file:
                key_file.write(base64.urlsafe_b64encode(key))
            return key

    def _read_records(self) -> dict[str, dict[str, Any]]:
        try:
            value = json.loads(self._records_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        if not isinstance(value, dict) or not isinstance(value.get("records"), dict):
            raise OpaqueRecordError("opaque record store is invalid")
        return value["records"]

    def _write_records(self, records: Mapping[str, Mapping[str, Any]]) -> None:
        temporary = self._records_path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps({"records": records}, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        os.chmod(temporary, 0o600)
        os.replace(temporary, self._records_path)

    def _record_mac(self, raw_record: Mapping[str, Any]) -> str:
        signed = {key: value for key, value in raw_record.items() if key != "mac"}
        return hmac.new(self._key, _canonical_json(signed), hashlib.sha256).hexdigest()


def sys_platform() -> str:
    """Keep platform lookup patchable without importing platform metadata."""

    return sys.platform


def _canonical_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise OpaqueRecordError("payload must be a mapping")
    value = json.loads(_canonical_json(dict(payload)))
    if not isinstance(value, dict):  # pragma: no cover - ensured by Mapping input.
        raise OpaqueRecordError("payload must be a mapping")
    return value


def _canonical_json(value: object) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise OpaqueRecordError(
            "opaque record value must be JSON serializable"
        ) from error


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _handle_signature(key: bytes, token: str) -> str:
    return (
        base64.urlsafe_b64encode(
            hmac.new(key, token.encode("ascii"), hashlib.sha256).digest()[:16]
        )
        .decode("ascii")
        .rstrip("=")
    )


def _to_record(raw_record: Mapping[str, Any]) -> OpaqueRecord:
    required = {
        "kind",
        "owner",
        "payload",
        "payload_digest",
        "issued_at",
        "expires_at",
        "state",
        "mac",
    }
    if set(raw_record) != required:
        raise OpaqueRecordError("opaque record integrity check failed")
    payload = _canonical_payload(raw_record["payload"])
    if raw_record["payload_digest"] != _digest(payload):
        raise OpaqueRecordError("opaque record integrity check failed")
    if raw_record["state"] not in {"active", "revoked", "consumed"}:
        raise OpaqueRecordError("opaque record integrity check failed")
    return OpaqueRecord(
        kind=_required_text(raw_record["kind"], "kind"),
        owner=_required_text(raw_record["owner"], "owner"),
        payload=payload,
        payload_digest=raw_record["payload_digest"],
        issued_at=_parse_timestamp(raw_record["issued_at"]),
        expires_at=_parse_timestamp(raw_record["expires_at"]),
        state=raw_record["state"],
    )


def _require_nonempty(value: str, name: str) -> None:
    if not isinstance(value, str) or not value:
        raise OpaqueRecordError(f"{name} must be a non-empty string")


def _required_text(value: object, name: str) -> str:
    _require_nonempty(value, name)  # type: ignore[arg-type]
    return value  # type: ignore[return-value]


def _as_utc(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise OpaqueRecordError(f"{name} must be timezone-aware")
    return value.astimezone(UTC)


def _timestamp(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _parse_timestamp(value: object) -> datetime:
    if not isinstance(value, str):
        raise OpaqueRecordError("opaque record integrity check failed")
    try:
        return _as_utc(
            datetime.fromisoformat(value.replace("Z", "+00:00")), "timestamp"
        )
    except ValueError as error:
        raise OpaqueRecordError("opaque record integrity check failed") from error
