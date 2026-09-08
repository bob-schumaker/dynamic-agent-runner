# Workflow Input Converter Plugin Validation

## Current delivery boundary

The converter delivery path is a sealed Python package loaded through the
manifest-bound standard converter interface. Package identity, entry point,
compatible runner contract, and resource declarations are validated at
registration; prompt and payload bytes cannot choose or replace them.

The current feature does not claim OS isolation from malicious converter code.
Docker, `sandbox-exec`, and other full-isolation backends are future work under
[`../local-tool-sandbox-hardening/spec.md`](../local-tool-sandbox-hardening/spec.md).
Their existing probe evidence is recorded in
[`../local-tool-sandbox-hardening/validation.md`](../local-tool-sandbox-hardening/validation.md).

## Remaining feature validation

T4 is complete. Fake-only loader tests prove that DAR loads only the
digest-bound manifest entry point, requires the exact contract attributes and
`converter` object, and rejects stale assets with no fallback module or callable.
Deferred Transformers adapter tests prove a package must be bound before it can
accept bytes and that packed input reaches the standard runner. Runner tests
prove redacted package-load failure, payload cleanup on worker failure and
cancellation, and trace redaction. Focused package, runner, ingress,
registration, and trace regressions passed on 2026-09-07.

T5 now validates authoring guidance, the complete test and lint gates, and the
authorized floorplan workflow run. Neither step depends on a container runtime
or OS-level sandbox.
