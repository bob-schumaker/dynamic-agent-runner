# Workflow Input Converter Plugin Validation

## T4 isolation backend status

Status: unavailable; generated converter execution remains refused.

On macOS, `sandbox-exec` is installed at `/usr/bin/sandbox-exec`. The current
DAR executor, `execute_macos_sandbox_exec`, invokes it with the profile
`(version 1) (allow default)`. That profile provides no enforcement of the
T4 file, environment, credential, network, child-process, scratch, memory, or
process-count boundaries. It is therefore evidence only for the trusted-fixture
handoff and is not a candidate admission backend.

`DockerSandboxExecutor` is a candidate strict worker envelope. It requires a
host-configured digest-pinned image and uses a read-only root filesystem,
network denial, dropped capabilities, no-new-privileges, a non-root worker,
one bounded process, bounded memory and stdout, a bounded scratch tmpfs, a
single read-only asset mount, and a sanitized environment. Deterministic unit
tests cover those fixed controls and symlink rejection. It is not selected for
generated converter execution and T4 remains incomplete until its same-worker
converter/model protocol and real-platform acceptance are complete. DAR must
not dynamically load or execute a workflow-provided converter asset until a
backend has passed every required adversarial and real-platform check in
[`../local-tool-sandbox-hardening/spec.md`](../local-tool-sandbox-hardening/spec.md).

The real host-terminal probe on 2026-09-07, run in a temporary Herdr
workspace, established that `sandbox-exec` itself launches: `/bin/echo` exits
successfully under `(version 1) (allow default)`. A deny-by-default candidate
for that same executable aborts with exit status 134, both when it allows only
the executable and when it additionally permits reads under `/System` and
`/usr/lib`. The earlier direct-Codex `sandbox_apply: Operation not permitted`
result was consequently a Codex-launch limitation, not evidence about the
host terminal. The strict candidate has failed to launch and is not an
admission backend; no conclusion about every possible macOS profile follows
from this probe.

The same Herdr workspace confirmed on 2026-09-07 that the `docker` CLI is
installed, but its configured OrbStack socket is absent; `docker version`
cannot connect to an engine. No reviewed worker image or live Docker acceptance
evidence is available on this host. This is a host-environment blocker for
T4.3, not evidence that the candidate's controls work.
