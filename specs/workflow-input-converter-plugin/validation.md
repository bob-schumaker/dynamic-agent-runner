# Workflow Input Converter Plugin Validation

## T4 isolation backend status

Status: unavailable; generated converter execution remains refused.

On macOS, `sandbox-exec` is installed at `/usr/bin/sandbox-exec`. The current
DAR executor, `execute_macos_sandbox_exec`, invokes it with the profile
`(version 1) (allow default)`. That profile provides no enforcement of the
T4 file, environment, credential, network, child-process, scratch, memory, or
process-count boundaries. It is therefore evidence only for the trusted-fixture
handoff and is not a candidate admission backend.

No alternate strict worker backend or reviewed profile is present in the
repository. T4.1 through T4.3 remain incomplete. DAR must not dynamically load
or execute a workflow-provided converter asset until a backend has passed every
required adversarial and real-platform check in
[`../local-tool-sandbox-hardening/spec.md`](../local-tool-sandbox-hardening/spec.md).

The local real-platform probe on 2026-09-07 attempted to launch `/bin/echo`
under the existing deny-by-default profile with only literal read, metadata, and
process-exec allowances for that binary. `sandbox-exec` rejected the profile
before launch with `sandbox_apply: Operation not permitted`. This platform
cannot provide the required backend through the installed `sandbox-exec`.
