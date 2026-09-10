"""RED admission-order sentinels for the sealed artifact workflow runner."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from dynamic_agent_runner.workflow_host.sealed_artifact_runner import (
    SealedArtifactRunnerAdmission,
    SealedArtifactRunnerAdmissionError,
)


class _Stage:
    def __init__(self, name: str, calls: list[str], *, fail: bool = False) -> None:
        self._name = name
        self._calls = calls
        self._fail = fail

    def __call__(self, *_args: object, **_kwargs: object) -> object:
        self._calls.append(self._name)
        if self._fail:
            raise RuntimeError(self._name)
        return object()


def _admission(
    *, fail_at: str | None = None
) -> tuple[SealedArtifactRunnerAdmission, list[str]]:
    calls: list[str] = []

    def stage(name: str) -> Callable[..., object]:
        return _Stage(name, calls, fail=name == fail_at)

    return (
        SealedArtifactRunnerAdmission(
            provenance=stage("provenance"),
            package_verification=stage("package_verification"),
            authorization=stage("authorization"),
            identity_resolution=stage("identity_resolution"),
            handle_validation=stage("handle_validation"),
            collector_allocation=stage("collector_allocation"),
            asset_execution=stage("asset_execution"),
        ),
        calls,
    )


@pytest.mark.parametrize(
    ("fail_at", "expected_calls"),
    [
        ("provenance", ["provenance"]),
        ("package_verification", ["provenance", "package_verification"]),
        (
            "authorization",
            ["provenance", "package_verification", "authorization"],
        ),
        (
            "identity_resolution",
            [
                "provenance",
                "package_verification",
                "authorization",
                "identity_resolution",
            ],
        ),
        (
            "handle_validation",
            [
                "provenance",
                "package_verification",
                "authorization",
                "identity_resolution",
                "handle_validation",
            ],
        ),
        (
            "collector_allocation",
            [
                "provenance",
                "package_verification",
                "authorization",
                "identity_resolution",
                "handle_validation",
                "collector_allocation",
            ],
        ),
    ],
)
def test_rejection_never_runs_a_later_admission_boundary(
    fail_at: str, expected_calls: list[str]
) -> None:
    admission, calls = _admission(fail_at=fail_at)

    with pytest.raises(SealedArtifactRunnerAdmissionError, match="unavailable"):
        admission.run(invocation=object())

    assert calls == expected_calls


def test_valid_admission_runs_the_fixed_boundary_order_once() -> None:
    admission, calls = _admission()

    admission.run(invocation=object())

    assert calls == [
        "provenance",
        "package_verification",
        "authorization",
        "identity_resolution",
        "handle_validation",
        "collector_allocation",
        "asset_execution",
    ]
