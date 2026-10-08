"""Contract tests for the host-owned sealed output handler."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from concurrent.futures import ThreadPoolExecutor

import pytest

from dynamic_agent_runner.workflow_host.sealed_artifact_runner import (
    SealedArtifactOutput,
    SealedArtifactOutputHandleService,
)
from dynamic_agent_runner.workflow_host.state import PrivateStateStore


NOW = datetime(2026, 9, 24, tzinfo=UTC)
DECLARATION = "f" * 64
REVISION = "e" * 64


def _declaration() -> tuple[SealedArtifactOutput, ...]:
    return (SealedArtifactOutput("result", "application/octet-stream", 16, None),)


def _request():
    from dynamic_agent_runner.workflow_host import (
        sealed_artifact_output_handler as module,
    )

    return module.SealedArtifactOutputStageRequest(
        receiver_id="receiver",
        workflow_id="workflow",
        package_id="package",
        revision_digest=REVISION,
        invocation_id="invocation",
        descriptor_digest=DECLARATION,
        outputs=(("result", "application/octet-stream", b"output"),),
        expires_at=NOW + timedelta(minutes=1),
    )


def _handler(tmp_path):
    from dynamic_agent_runner.workflow_host.sealed_artifact_output_handler import (
        SealedArtifactOutputHandler,
    )

    service = SealedArtifactOutputHandleService(
        store=PrivateStateStore(tmp_path / "state"), owner="host"
    )
    return SealedArtifactOutputHandler(
        service=service,
        declaration_resolver=lambda workflow_id, package_id, digest: (
            _declaration()
            if (workflow_id, package_id, digest) == ("workflow", "package", DECLARATION)
            else None
        ),
    )


def test_request_values_are_immutable_and_bound() -> None:
    from dynamic_agent_runner.workflow_host import (
        sealed_artifact_output_handler as module,
    )

    request = _request()
    assert request.outputs == (("result", "application/octet-stream", b"output"),)
    with pytest.raises((AttributeError, TypeError)):
        request.receiver_id = "foreign"  # type: ignore[misc]

    binding = module.SealedArtifactOutputReadBinding(
        receiver_id="receiver", revision_digest=REVISION, invocation_id="invocation"
    )
    assert binding.receiver_id == "receiver"


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("receiver_id", ""),
        ("workflow_id", ""),
        ("package_id", ""),
        ("invocation_id", ""),
        ("revision_digest", "E" * 64),
        ("descriptor_digest", "short"),
    ),
)
def test_request_rejects_invalid_identity_values(field: str, value: str) -> None:
    from dynamic_agent_runner.workflow_host import (
        sealed_artifact_output_handler as module,
    )

    values = {
        "receiver_id": "receiver",
        "workflow_id": "workflow",
        "package_id": "package",
        "revision_digest": REVISION,
        "invocation_id": "invocation",
        "descriptor_digest": DECLARATION,
        "outputs": (("result", "application/octet-stream", b"output"),),
        "expires_at": NOW + timedelta(minutes=1),
    }
    values[field] = value
    with pytest.raises(module.SealedArtifactOutputHandlerError):
        module.SealedArtifactOutputStageRequest(**values)


def test_request_rejects_naive_expiry_and_mutable_candidates() -> None:
    from dynamic_agent_runner.workflow_host import (
        sealed_artifact_output_handler as module,
    )

    with pytest.raises(module.SealedArtifactOutputHandlerError):
        module.SealedArtifactOutputStageRequest(
            receiver_id="receiver",
            workflow_id="workflow",
            package_id="package",
            revision_digest=REVISION,
            invocation_id="invocation",
            descriptor_digest=DECLARATION,
            outputs=[("result", "application/octet-stream", b"output")],
            expires_at=NOW.replace(tzinfo=None),
        )


def test_stage_promote_read_returns_only_opaque_handles(tmp_path) -> None:
    handler = _handler(tmp_path)
    private = handler.stage_declared(_request(), now=NOW)
    assert "output" not in repr(private)
    handles = handler.promote(private, now=NOW)
    assert len(handles) == 1
    assert (
        handler.read(
            handles[0],
            binding=handler.read_binding("receiver", REVISION, "invocation"),
            now=NOW,
        )
        == b"output"
    )


def test_discard_is_idempotent_and_does_not_revoke_promoted_output(tmp_path) -> None:
    handler = _handler(tmp_path)
    private = handler.stage_declared(_request(), now=NOW)
    handler.discard(private, now=NOW)
    handler.discard(private, now=NOW)

    private = handler.stage_declared(_request(), now=NOW)
    handles = handler.promote(private, now=NOW)
    handler.discard(private, now=NOW)
    assert (
        handler.read(
            handles[0],
            binding=handler.read_binding("receiver", REVISION, "invocation"),
            now=NOW,
        )
        == b"output"
    )


def test_promote_replay_returns_the_same_handles(tmp_path) -> None:
    handler = _handler(tmp_path)
    private = handler.stage_declared(_request(), now=NOW)
    first = handler.promote(private, now=NOW)
    assert handler.promote(private, now=NOW) == first


def test_expired_private_and_public_values_are_terminal(tmp_path) -> None:
    from dynamic_agent_runner.workflow_host.sealed_artifact_output_handler import (
        SealedArtifactOutputHandlerError,
    )

    handler = _handler(tmp_path)
    private = handler.stage_declared(_request(), now=NOW)
    with pytest.raises(SealedArtifactOutputHandlerError, match="output_expired"):
        handler.promote(private, now=private.expires_at)
    handler.discard(private, now=private.expires_at)


def test_concurrent_promote_and_discard_have_one_terminal_winner(tmp_path) -> None:
    handler = _handler(tmp_path)
    private = handler.stage_declared(_request(), now=NOW)

    def promote() -> str:
        try:
            handler.promote(private, now=NOW)
            return "promoted"
        except Exception as error:  # noqa: BLE001 - assert terminal classification.
            return str(error)

    def discard() -> str:
        try:
            handler.discard(private, now=NOW)
            return "discarded"
        except Exception as error:  # noqa: BLE001 - assert terminal classification.
            return str(error)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = [
            future.result()
            for future in (executor.submit(promote), executor.submit(discard))
        ]

    assert set(results) <= {"promoted", "discarded", "output_unavailable"}
    assert "promoted" in results or "discarded" in results
