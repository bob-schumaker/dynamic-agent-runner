# Local Tool Sandbox Hardening Validation

## Status

Future work. No backend is admitted for malicious local-tool or converter
package code.

## macOS `sandbox-exec` probes

In a temporary Herdr workspace on 2026-09-07, permissive
`(version 1) (allow default)` execution succeeded. Deny-by-default candidate
profiles for `/bin/echo` aborted with exit status 134, including a candidate
that allowed the executable and `/System` plus `/usr/lib` reads. The earlier
direct-Codex `sandbox_apply: Operation not permitted` result was a Codex launch
limitation, not host-terminal evidence. No strict `sandbox-exec` profile is an
admission backend.

## Docker envelope probes

`DockerSandboxExecutor` is an experimental candidate. Its fixed envelope uses a
digest-pinned image, read-only root filesystem, no network, dropped
capabilities, no-new-privileges, a non-root one-process worker, bounded memory
and stdout, bounded writable scratch, one read-only asset mount, and a
sanitized environment.

On macOS through OrbStack Docker `29.4.0`, a locally cached probe image showed
environment, caller host-file, network, child-process, and outside-write access
denied while bounded scratch was allowed. The repository executor also failed
closed for a one-second CPU loop, 8 KiB output against a 4 KiB boundary, a
2 MiB scratch write against a 1 MiB tmpfs, and a 128 MiB allocation against a
64 MiB memory limit.

The probe image has Python but no `transformers` or `peft`; no reviewed worker
image is available locally, and Docker image acquisition failed TLS validation.
These observations are future hardening evidence only. They do not authorize
execution of malicious package code and do not gate the sealed Python converter
package feature.
