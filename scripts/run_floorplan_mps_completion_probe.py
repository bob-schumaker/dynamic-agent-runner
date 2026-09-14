#!/usr/bin/env python3
"""Run one explicitly authorized floorplan MPS completion probe."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

from dynamic_agent_runner.workflow_host.floorplan_mps_completion_probe import (
    FloorplanMpsCompletionEvidence,
    FloorplanMpsCompletionProbeError,
    FloorplanMpsCompletionProbeRequest,
    floorplan_mps_completion_profile,
    run_floorplan_mps_completion_probe,
)
from dynamic_agent_runner.workflow_host.generation_worker_controllers import (
    darwin_mps_generation_execution_host_policy,
)
from dynamic_agent_runner.workflow_host.host import (
    LocalWorkflowHost,
    LocalWorkflowHostError,
    inspect_saved_workflow,
)
from dynamic_agent_runner.workflow_host.workflow_support_matrix import (
    WorkflowSupportCandidate,
)


_OPT_IN_ENV = "DAR_RUN_FLOORPLAN_MPS_COMPLETION_PROBE"
_PROMPT = "Create the floorplan from the sealed image. Return only JSON."


class FloorplanMpsCompletionProbeCommandError(RuntimeError):
    """Raised when the manual floorplan completion command is invalid."""


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        if os.environ.get(_OPT_IN_ENV) != "1":
            raise FloorplanMpsCompletionProbeCommandError(
                f"set {_OPT_IN_ENV}=1 to authorize a floorplan MPS completion probe"
            )
        inspection = inspect_saved_workflow(
            arguments.state_root, package_name=arguments.package_name
        )
        profile = floorplan_mps_completion_profile(inspection.policy)
        descriptor = inspection.policy.execution_descriptor
        if descriptor is None:
            raise FloorplanMpsCompletionProbeCommandError("floorplan policy is invalid")
        try:
            host_policy = darwin_mps_generation_execution_host_policy(
                ceiling=descriptor.budget
            )
        except Exception:
            host_policy = None
        candidate = WorkflowSupportCandidate(
            adapter_id=inspection.profile.adapter_id,
            adapter_capabilities=frozenset(inspection.profile.capabilities),
            available_abi_capabilities=frozenset({descriptor.architecture_abi.abi_id}),
            provider_capabilities=frozenset({"transformers-generate-v1"}),
            host_capabilities=frozenset({"mps"})
            if host_policy is not None
            else frozenset(),
            material_identity=profile.material_identity,
            authorization_granted=True,
        )
        request = FloorplanMpsCompletionProbeRequest(
            target=arguments.target,
            authorization_reference=arguments.authorization_reference,
            profile=profile,
            candidate=candidate,
        )

        def dispatch() -> FloorplanMpsCompletionEvidence:
            if host_policy is None:
                raise FloorplanMpsCompletionProbeCommandError(
                    "floorplan MPS policy is unavailable"
                )
            host = LocalWorkflowHost.open(
                arguments.state_root,
                generation_execution_host_policy=host_policy,
            )
            artifact = host.ingress_default_file(
                workflow_id=inspection.registration.workflow_id,
                path=arguments.image,
                now=datetime.now(UTC),
            )
            prepared = host.prepare(
                workflow_id=inspection.registration.workflow_id,
                prompt=_PROMPT,
                workspace_artifact_ids=(artifact.artifact_id,),
                now=datetime.now(UTC),
            )
            debug = host.run_debug(
                workflow_id=inspection.registration.workflow_id,
                prepared_input_id=prepared.prepared_input_id,
                now=datetime.now(UTC),
            )
            diagnostic = host.debug_diagnostic(
                debug.diagnostic_id, now=datetime.now(UTC)
            )
            fragments = diagnostic.fragments
            if (
                debug.status != "completed"
                or debug.result is None
                or diagnostic.terminal is None
                or diagnostic.terminal.admitted is None
                or len(fragments) != 1
                or fragments[0].worker_reaped is not True
            ):
                raise FloorplanMpsCompletionProbeCommandError(
                    "floorplan completion evidence is unavailable"
                )
            fragment = fragments[0]
            return FloorplanMpsCompletionEvidence(
                execution_descriptor_digest=descriptor.digest,
                packed_context_tokens=fragment.packed_context_tokens,
                aggregate_generated_tokens=fragment.generated_tokens,
                aggregate_output_bytes=fragment.output_bytes,
                worker_reaped=fragment.worker_reaped,
                model_json_admitted=True,
                terminal_svg_validated=True,
            )

        receipt = run_floorplan_mps_completion_probe(request, dispatch=dispatch)
        arguments.receipt.write_text(
            json.dumps(receipt, sort_keys=True, indent=2) + "\n", encoding="utf-8"
        )
        print(json.dumps(receipt, sort_keys=True, separators=(",", ":")))
        return 0
    except (
        FloorplanMpsCompletionProbeError,
        FloorplanMpsCompletionProbeCommandError,
        LocalWorkflowHostError,
        ValueError,
    ) as error:
        print(f"floorplan-mps-completion-probe: {error}", file=sys.stderr)
        return 2


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-root", required=True, type=Path)
    parser.add_argument("--package-name", required=True)
    parser.add_argument("--image", required=True, type=Path)
    parser.add_argument("--target", required=True)
    parser.add_argument("--authorization-reference", required=True)
    parser.add_argument("--receipt", required=True, type=Path)
    return parser


if __name__ == "__main__":
    raise SystemExit(main())
