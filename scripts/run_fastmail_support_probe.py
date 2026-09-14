#!/usr/bin/env python3
"""Run one explicitly authorized, read-only Fastmail support probe.

This manual command is intentionally excluded from pytest and CI. It uses an
already configured host and already registered package; it neither provisions a
model nor configures an MCP connection.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

from dynamic_agent_runner.workflow_host.fastmail_live_probe import (
    FastmailLiveProbeError,
    FastmailLiveProbeRequest,
    run_fastmail_live_probe,
)
from dynamic_agent_runner.workflow_host.host import LocalWorkflowHost
from dynamic_agent_runner.workflow_host.workflow_support_matrix import (
    MaterialIdentity,
    WorkflowSupportCandidate,
    WorkflowSupportProfile,
)


_OPT_IN_ENV = "DAR_RUN_FASTMAIL_SUPPORT_PROBE"
_PROFILE_ID = "fastmail-triage-live-v1"
_PROMPT = "Triage the previous 24 hours of unread messages."


class FastmailSupportProbeCommandError(RuntimeError):
    """Raised when the manual Fastmail support command is invalid."""


def main(argv: list[str] | None = None) -> int:
    """Run one selected Fastmail workflow and write its redacted receipt."""

    arguments = _parser().parse_args(argv)
    try:
        if os.environ.get(_OPT_IN_ENV) != "1":
            raise FastmailSupportProbeCommandError(
                f"set {_OPT_IN_ENV}=1 to authorize a Fastmail support probe"
            )
        if arguments.profile != _PROFILE_ID:
            raise FastmailSupportProbeCommandError("Fastmail probe profile is invalid")
        profile, candidate = _support_facts(arguments.support_facts)
        if (
            profile.material_identity is None
            or arguments.package_name != profile.material_identity.package_id
        ):
            raise FastmailSupportProbeCommandError(
                "Fastmail probe package identity is invalid"
            )
        request = FastmailLiveProbeRequest(
            target=arguments.target,
            authorization_reference=arguments.authorization_reference,
            profile=profile,
            candidate=candidate,
        )
        host = LocalWorkflowHost.open(arguments.state_root)
        receipt = run_fastmail_live_probe(
            request,
            dispatch=lambda: host.invoke_saved(
                package_name=arguments.package_name,
                prompt=_PROMPT,
                workspace_files=(),
                dry_run=False,
                approval_broker=None,
                now=datetime.now(UTC),
            ),
        )
        arguments.receipt.write_text(
            json.dumps(receipt, sort_keys=True, indent=2) + "\n", encoding="utf-8"
        )
        print(json.dumps(receipt, sort_keys=True, separators=(",", ":")))
        return 0
    except (
        FastmailLiveProbeError,
        FastmailSupportProbeCommandError,
        ValueError,
    ) as error:
        print(f"fastmail-support-probe: {error}", file=sys.stderr)
        return 2


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-root", required=True, type=Path)
    parser.add_argument("--package-name", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--authorization-reference", required=True)
    parser.add_argument("--support-facts", required=True, type=Path)
    parser.add_argument("--receipt", required=True, type=Path)
    return parser


def _support_facts(
    path: Path,
) -> tuple[WorkflowSupportProfile, WorkflowSupportCandidate]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict) or set(value) != {"candidate", "profile"}:
            raise ValueError
        profile_value = value["profile"]
        candidate_value = value["candidate"]
        if not isinstance(profile_value, dict) or not isinstance(candidate_value, dict):
            raise ValueError
        profile = WorkflowSupportProfile(
            profile_id=_text(profile_value, "profile_id"),
            workflow_family=_text(profile_value, "workflow_family"),
            required_adapter_capabilities=_strings(
                profile_value, "required_adapter_capabilities"
            ),
            required_abi_capabilities=_strings(
                profile_value, "required_abi_capabilities"
            ),
            required_provider_capabilities=_strings(
                profile_value, "required_provider_capabilities"
            ),
            required_host_capabilities=_strings(
                profile_value, "required_host_capabilities"
            ),
            material_identity=_material(profile_value["material_identity"]),
            execution_mode=_text(profile_value, "execution_mode"),
            authorization_required=_bool(profile_value, "authorization_required"),
            implemented=_bool(profile_value, "implemented"),
        )
        candidate = WorkflowSupportCandidate(
            adapter_id=_text(candidate_value, "adapter_id"),
            adapter_capabilities=frozenset(
                _strings(candidate_value, "adapter_capabilities")
            ),
            available_abi_capabilities=frozenset(
                _strings(candidate_value, "available_abi_capabilities")
            ),
            provider_capabilities=frozenset(
                _strings(candidate_value, "provider_capabilities")
            ),
            host_capabilities=frozenset(_strings(candidate_value, "host_capabilities")),
            material_identity=_material(candidate_value["material_identity"]),
            authorization_granted=_bool(candidate_value, "authorization_granted"),
        )
    except (KeyError, OSError, TypeError, ValueError) as error:
        raise FastmailSupportProbeCommandError("support facts are invalid") from error
    return profile, candidate


def _material(value: object) -> MaterialIdentity | None:
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != {
        "artifact_digests",
        "material_lock_digest",
        "material_roles",
        "package_id",
    }:
        raise ValueError
    digests = value["artifact_digests"]
    if not isinstance(digests, dict):
        raise ValueError
    return MaterialIdentity(
        package_id=_text(value, "package_id"),
        material_lock_digest=_text(value, "material_lock_digest"),
        material_roles=_strings(value, "material_roles"),
        artifact_digests={str(name): str(digest) for name, digest in digests.items()},
    )


def _text(value: dict[str, object], name: str) -> str:
    item = value[name]
    if not isinstance(item, str):
        raise ValueError
    return item


def _strings(value: dict[str, object], name: str) -> tuple[str, ...]:
    items = value[name]
    if not isinstance(items, list):
        raise ValueError
    return tuple(items)


def _bool(value: dict[str, object], name: str) -> bool:
    item = value[name]
    if not isinstance(item, bool):
        raise ValueError
    return item


if __name__ == "__main__":
    raise SystemExit(main())
