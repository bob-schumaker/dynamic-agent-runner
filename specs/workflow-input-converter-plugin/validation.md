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

T4 validates exact Python-package entry-point loading and private
converter-to-runner handoff. T5 then validates authoring guidance, the complete
test and lint gates, and the authorized floorplan workflow run. Neither step
depends on a container runtime or OS-level sandbox.
