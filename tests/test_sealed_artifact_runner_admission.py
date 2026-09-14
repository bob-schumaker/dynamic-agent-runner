"""RED admission-order sentinels for the sealed artifact workflow receiver."""

from __future__ import annotations

import pytest

from dynamic_agent_runner.workflow_host.sealed_artifact_runner import (
    SealedArtifactRunnerAdmissionError,
    SealedArtifactWorkflowReceiver,
)


class _RecordingHost:
    def __init__(self, *, fail_at: str | None = None) -> None:
        self.events: list[str] = []
        self._fail_at = fail_at

    def registration(self, _invocation: object) -> object:
        return self._event("registration")

    def verify_package(self, _registration: object) -> object:
        return self._event("zip_verification")

    def authorize(self, _package: object) -> object:
        return self._event("authorization")

    def resolve_identities(self, _authorization: object) -> object:
        return self._event("identity_resolution")

    def validate_handles(self, _identities: object) -> object:
        return self._event("handle_metadata")

    def allocate_collector(self, _handles: object) -> object:
        return self._event("collector_allocation")

    def execute_asset(self, _collector: object) -> object:
        self._event("asset_import")
        self._event("input_byte_read")
        self._event("material_load")
        self._event("provider_entry")
        self._event("collector_write")
        self._event("output_handle_publication")
        return self._event("egress")

    def _event(self, name: str) -> object:
        self.events.append(name)
        if name == self._fail_at:
            raise RuntimeError(name)
        return object()


@pytest.mark.parametrize(
    ("fail_at", "expected_events"),
    [
        ("registration", ["registration"]),
        ("zip_verification", ["registration", "zip_verification"]),
        ("authorization", ["registration", "zip_verification", "authorization"]),
        (
            "identity_resolution",
            [
                "registration",
                "zip_verification",
                "authorization",
                "identity_resolution",
            ],
        ),
        (
            "handle_metadata",
            [
                "registration",
                "zip_verification",
                "authorization",
                "identity_resolution",
                "handle_metadata",
            ],
        ),
        (
            "collector_allocation",
            [
                "registration",
                "zip_verification",
                "authorization",
                "identity_resolution",
                "handle_metadata",
                "collector_allocation",
            ],
        ),
        (
            "asset_import",
            [
                "registration",
                "zip_verification",
                "authorization",
                "identity_resolution",
                "handle_metadata",
                "collector_allocation",
                "asset_import",
            ],
        ),
    ],
)
def test_rejection_has_no_later_receiver_effect(
    fail_at: str, expected_events: list[str]
) -> None:
    host = _RecordingHost(fail_at=fail_at)
    receiver = SealedArtifactWorkflowReceiver(host=host)

    with pytest.raises(SealedArtifactRunnerAdmissionError, match="unavailable"):
        receiver.run(invocation=object())

    assert host.events == expected_events


def test_receiver_runs_declared_admission_and_execution_order_once() -> None:
    host = _RecordingHost()
    receiver = SealedArtifactWorkflowReceiver(host=host)

    receiver.run(invocation=object())

    assert host.events == [
        "registration",
        "zip_verification",
        "authorization",
        "identity_resolution",
        "handle_metadata",
        "collector_allocation",
        "asset_import",
        "input_byte_read",
        "material_load",
        "provider_entry",
        "collector_write",
        "output_handle_publication",
        "egress",
    ]
