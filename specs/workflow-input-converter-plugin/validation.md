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

## T5 evidence — 2026-09-07

- T5.1 was RED until Agent Engineering guidance stated the fixed
  workflow-sealed Python converter package form, exact
  `transformers-generate-v1` contract, and rejection of live callables,
  dependency installation, arbitrary paths, runtime package selection, and a
  format registry. The focused plugin suite is green: `11 passed`.
- T5.2 regenerated the native-routed Agent Engineering payload from the source
  manifest. The pre-regeneration output was retained separately after its
  recorded digest did not match the dirty local tree.
- T5.3 passed `1900 passed, 1 skipped, 7 deselected`; the seven warnings are
  the existing unregistered `live_matrix` marks. Ruff and `git diff --check`
  passed.
- T5.4 used the durable prepared logical Qwen closure, the fixed
  `transformers-generate-v1` converter contract, and one sealed JPEG site-plan
  input. The runner completed model generation, but the workflow-local strict
  SVG validator rejected the incomplete model result. This is not successful
  acceptance: no bounded normalized JSON reached workflow-local JSON-to-SVG
  tooling.
- A follow-up local probe used the model card's role-separated JSON schema and
  deterministic 4,096-token generation pattern against the same sealed image.
  It produced nonempty output but no parseable JSON. The probe emitted only the
  parse outcome and output byte count; it retained no generated content.

T5.4 remains blocked. The reviewed model's documented output is structured
floorplan JSON, while repeated authorized runs—including the published
inference pattern—have not produced a complete parseable instance. DAR has no
JSON parser or SVG renderer by design; a corrected model/inference path and a
workflow-local JSON-to-SVG package are required before rerunning the gate. T5.5
release is therefore not authorized.
Neither the blocked acceptance nor the completed T5.1--T5.3 work depends on a
container runtime or OS-level sandbox.
