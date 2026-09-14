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
from dynamic_agent_runner.workflow_host.host import (
    LocalWorkflowHost,
    inspect_saved_workflow,
)
from dynamic_agent_runner.workflow_host.profiles import (
    FASTMAIL_TRIAGE_LLAMA_CPP_ADAPTER_ID,
)
from dynamic_agent_runner.workflow_host.workflow_support_matrix import (
    MaterialIdentity,
    WorkflowSupportCandidate,
    WorkflowSupportProfile,
)


_OPT_IN_ENV = "DAR_RUN_FASTMAIL_SUPPORT_PROBE"
_PROFILE_ID = "fastmail-triage-live-v1"
_PROMPT = "Triage the previous 24 hours of unread messages."
_ADAPTER_CAPABILITIES = ("search_email", "tool_use")
_ABI_CAPABILITIES = ("llama-cpp-function-calling-v1",)
_PROVIDER_CAPABILITIES = ("fastmail.search_email.read.v1",)


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
        request = _request_from_inspection(arguments)
        host = LocalWorkflowHost.open(arguments.state_root)
        receipt = run_fastmail_live_probe(
            request,
            dispatch=lambda: host.invoke_saved(
                package_name=arguments.workflow_id,
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
    parser.add_argument("--workflow-id", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--authorization-reference", required=True)
    parser.add_argument("--receipt", required=True, type=Path)
    return parser


def _request_from_inspection(arguments: argparse.Namespace) -> FastmailLiveProbeRequest:
    """Project one fixed Fastmail cell from immutable registered state."""

    try:
        inspection = inspect_saved_workflow(
            arguments.state_root, package_name=arguments.workflow_id
        )
        registration = inspection.registration
        policy = inspection.policy
        configured_profile = inspection.profile
        if (
            registration.workflow_id != arguments.workflow_id
            or registration.package_id != policy.package_id
            or registration.revision_digest != policy.revision_digest
            or registration.policy_digest != policy.policy_digest
            or registration.mcp_binding_id is None
            or configured_profile.adapter_id != FASTMAIL_TRIAGE_LLAMA_CPP_ADAPTER_ID
            or len(policy.declared_tools) != 1
            or policy.declared_tools[0].tool_id != "search_email"
            or policy.declared_tools[0].side_effect != "read"
            or policy.task_invocation.allowed_tool_ids != ("search_email",)
            or policy.task_invocation.max_total_tool_calls != 1
        ):
            raise ValueError
        material = _material_identity(registration.package_id, policy.model_materials)
        profile = WorkflowSupportProfile(
            profile_id=_PROFILE_ID,
            workflow_family="fastmail-triage",
            required_adapter_capabilities=_ADAPTER_CAPABILITIES,
            required_abi_capabilities=_ABI_CAPABILITIES,
            required_provider_capabilities=_PROVIDER_CAPABILITIES,
            required_host_capabilities=(),
            material_identity=material,
            execution_mode="live",
            authorization_required=True,
            implemented=True,
        )
        candidate = WorkflowSupportCandidate(
            adapter_id=configured_profile.adapter_id,
            adapter_capabilities=frozenset(_ADAPTER_CAPABILITIES),
            available_abi_capabilities=frozenset(_ABI_CAPABILITIES),
            provider_capabilities=frozenset(_PROVIDER_CAPABILITIES),
            host_capabilities=frozenset(),
            material_identity=material,
            authorization_granted=True,
        )
    except (AttributeError, TypeError, ValueError) as error:
        raise FastmailSupportProbeCommandError(
            "registered Fastmail workflow is invalid"
        ) from error
    return FastmailLiveProbeRequest(
        target=arguments.target,
        authorization_reference=arguments.authorization_reference,
        profile=profile,
        candidate=candidate,
    )


def _material_identity(package_id: str, lock: object) -> MaterialIdentity:
    if lock is None:
        raise ValueError
    sources = lock.sources
    return MaterialIdentity(
        package_id=package_id,
        material_lock_digest=lock.digest,
        material_roles=tuple(source.role for source in sources),
        artifact_digests={source.role: source.sha256 for source in sources},
    )


if __name__ == "__main__":
    raise SystemExit(main())
