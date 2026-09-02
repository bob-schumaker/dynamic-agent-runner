# Agent-Engineering Plugin Migration Record

## Metadata

- Status: Transfer complete; successor clean-Codex acceptance pending
- Owner: dynamic-agent-runner
- Governing transfer plan: `../ai-environment-roschuma/work-items/plans/dar-plugin-skill-ownership-migration-plan.md`
- Successor plugin: `plugins/agent-engineering`
- Task breakdown: `tasks.md`

## Delivery Record

This record is the DAR-side evidence for the single cross-repository transfer
and its remaining successor-acceptance gate. It does not authorize a generic
plugin-acceptance framework. Scoped DAR capability-model changes are authorized
only to compile declared deferred runtime needs into explicit host requirements;
they do not add scratch, session, subagent, retrieval, embedding, or resume
execution behavior.

- Source corpus revision: `6d43f44568dd82b778668f9392148083283d5676`
- DAR baseline revision: `1212667975af529a57b19604af13ed57ec0a0c9a`
- Marketplace: `dynamic-agent-runner` / `Dynamic Agent Runner`
- Runtime profile: retained as supplemental guidance under
  `references/dar-runtime-profile.md`
- Legacy disposition: the former `dar-authoring` plugin moved to
  `legacy-dar-authoring/` as historical migration evidence. Its implemented
  host/runtime contract is retained as the live
  [`authored-workflow-runtime-v1`](../authored-workflow-runtime-v1/spec.md)
  capability record; the marketplace exposes only the successor.

## Completed Transfer Evidence

- Delivered plugin: `agent-engineering` `0.1.0`
- Successor validation:
  - `poetry run python <plugin-creator>/scripts/validate_plugin.py
    plugins/agent-engineering` — passed
  - `poetry run pytest -q` — 1637 passed, 1 skipped, 7 deselected; seven
    existing unknown-mark warnings
  - `poetry run ruff check tests/test_agent_engineering_plugin.py
    tests/test_dar_authoring_live_capability_fixtures.py` — passed
- Runtime specification disposition: retained under
  [`authored-workflow-runtime-v1`](../authored-workflow-runtime-v1/spec.md) as
  the live v1 capability record; plugin-migration indexes point to this record.
- Commit authorization: granted for the completed transfer.

## Successor Clean-Codex Acceptance

The retired `dar-authoring` M4.4 harness proves the former plugin's
CLI-first author-then-run contract. It does not prove that a clean Codex
process can discover and follow the successor `agent-engineering` skill.

The migration is complete only when the successor has full bounded
end-to-end acceptance evidence. The test corpus must cover every `supported`
or `conditional` capability in
[`authored-workflow-runtime-v1`](../authored-workflow-runtime-v1/m4-4-workflow-capability-matrix.md)
with at least one clean-Codex author-then-run scenario. Each deferred capability
must have a clean-Codex scenario that reaches its declared refusal or
`capability_unavailable` boundary without fabricating a positive workflow.

Each scenario is a full end-to-end chain:

1. A clean Codex authoring process receives only a text request that explicitly
   targets DAR and the declared fixture inputs. Its temporary marketplace exposes
   only `agent-engineering`, whose only initial model-visible entry is the
   `agent-development` router. DAR runtime guidance is private routed content;
   the prompt must not name the retired plugin or embed the profile's CLI recipe.
   The harness may stage DAR's wheel in a test-scoped
   environment and expose its `dar-package` console script on `PATH`, but that
   wheel, path, and installation mechanism are not model-visible inputs.
2. A separate clean Codex invocation receives only the finalized saved package
   name and text run request. It must use `dar-package invoke`; it cannot select
   a package, register a revision, configure a profile or connection, or access
   the first process's state. The controller supplies narrow authoring and
   invoke-only launchers that mediate its private state; they must not expose a
   state-root path or state-root environment variable to either actor.
3. The harness verifies the generated package, finalization receipt, staged
   catalog revision, registration/preparation linkage, invocation receipt, and
   tool/approval traces against the checked-in scenario contract. Success is
   not inferred from model text or a claimed skill invocation.

The capability matrix assigns a stable ID and support status to each row. The
checked-in `tests/fixtures/m4-4-successor-coverage.json` manifest has a version
and, for every matrix ID, one or more entries containing the scenario ID,
`expected_status` (`pass`, `expected_capability_unavailable`, or
`expected_refusal`), configured fixture IDs, missing-fixture IDs, and expected
terminal status. A configured positive entry's fixture IDs must equal the
referenced scenario's `required_host_fixtures`; a missing-fixture negative entry
must point to a distinct immutable scenario contract and omit exactly one
prerequisite. Each entry binds the capability to its scenario's required gates,
fixture set, terminal phase, and capability-specific assertions; a capability
label alone is not evidence. The scenario checker must fail when a supported row
has no positive end-to-end scenario, a conditional row lacks configured positive
or missing-fixture negative coverage, a deferred row is treated as positive, an
entry is under-gated or mismatches its terminal phase, or a scenario claims a
capability absent from the matrix. Guardrails require configured `input` and
`tool_input` phase coverage and their missing-fixture boundaries.

The coverage manifest is not an actor-input source. A checked-in, versioned
external scenario plan must map every unique coverage scenario ID to its package
name, workflow ID, author request, run request, and declared fixture set. The
external command accepts both artifacts, verifies their exact scenario-set and
fixture agreement, and rejects an unknown, missing, duplicate, or partial plan
entry before launching Codex.

The original 13 M4.4 scenario contracts remain the regression minimum,
including `document-summary-v1` as a positive case and `council-request-v1` as
an unavailable case; successor coverage may add scenarios but may not replace
or reduce that baseline.

The harness must expose only `agent-engineering` in its temporary marketplace.
It must reject the retired plugin name, legacy skill paths, plugin-provided MCP
or broker configuration, inherited model credentials, and undeclared package,
state, credential, or tool roots. It may use a test-scoped clean Codex
authentication source outside model-visible inputs, but live model calls remain
outside ordinary unit tests.

The successor acceptance surface is a generated native-routed plugin, not the
canonical direct-skill source tree. The canonical plugin manifest, icon assets,
and authored guidance remain source-owned inputs. Its generated tree exposes
only a small `agent-development` router `SKILL.md`; general agent-development
and DAR workflow-authoring guidance are private router modules. The router
member source contains only router instructions. Every other canonical artifact
is either named private-module content, a declared payload asset, or an explicit
exclusion; templates, schemas, validation scripts, and examples may not remain
under the visible router member. The generated `skills/` tree contains exactly
one host-visible router `SKILL.md`; its only permitted support subtree is the
packager-generated private-module instruction index under `references/modules/`.
Payload assets remain outside `skills/` and may not be implicitly absorbed into
that router surface.

Routing changes delivery topology, not the public interface. The generated
plugin retains the canonical public plugin identity (`agent-engineering`),
version, author, description, complete interface metadata and branding-asset
paths, marketplace selector, and the host-visible `agent-development` skill
identifier and supported bounded DAR behavior. A concise router frontmatter may
replace the direct skill body only when it is semantically equivalent for host
selection. Generated source maps, payload receipts, and private-module layout
are the only allowed interface differences.

Native routed packaging requires the source manifest name to differ from the
generated plugin name. Therefore the source-owned manifest uses the private
`agent-engineering-direct` build-input identity; it is never a marketplace
target. The generated manifest is the canonical public contract and must equal
the frozen direct-plugin manifest before its router-only skill topology is
considered accepted.

Before router-source restructuring, capture and freeze the complete direct-skill
timing baseline input and its plugin-tree digest. Retain that input only as
test-owned comparison collateral, never as a successor marketplace source. The
timing comparison binds the frozen direct input digest as well as the generated
root receipts.

The packager must plan before applying into a disposable generated root. The
plan and apply receipts must bind the router-authority and payload-asset
declarations, generated manifest, complete source map, payload manifest, and
release metadata. It must preserve the public manifest and branding assets, and
must reject any undeclared support-file ownership rather than making source
support files implicitly model-visible.

The external clean-Codex acceptance command stages that generated root in its
temporary marketplace. Static generated-tree and marketplace inspection proves
that the router is the sole initial visible skill surface. A DAR-targeted request
is proved only by its bounded package, receipt, and trace contract; acceptance
does not infer a private-module load or model reasoning event. Every successor
external replay uses the generated root. A direct-source run is permitted only
as a separately labeled timing baseline.

Timing comparison uses the same coverage and scenario-plan digests, prompts,
fixtures, controller version, actor configuration, Codex/model configuration,
and timeout for the direct baseline and generated-root replay. It records
redacted aggregate actor durations and excludes generation and temporary
marketplace staging. Generation, staging, and live-Codex replay are separate
phases; a successful routed replay does not authorize source cleanup,
publication, or installation.

The acceptance record must bind the canonical and generated plugin identities,
generated-manifest and marketplace digests, router-authority/payload/source-map/
release-metadata receipt digests, scenario/prompt/harness/controller versions,
final package digest, staged catalog revision, registration/preparation linkage,
terminal result, dispatch count, and timing-comparison provenance without
persisting prompt bodies, material content, credentials, or physical paths.

One fresh evidence directory contains one redacted record per unique scenario
ID plus a versioned aggregate manifest. The aggregate binds the coverage and
scenario-plan digests and every record's identifier, status, and digest. It
must reject missing, duplicate, or unknown records; neither the records nor the
aggregate may retain physical paths, prompt bodies, material content, or secrets.

This proves the externally observable contract of a clean successor-only Codex
environment; it does not claim access to unobservable model reasoning or a
private “skill loaded” event.

Ordinary tests run the full scenario lifecycle through deterministic fake model,
tool, connection, approval, and host collaborators for every manifest entry;
they make no network or live-Codex call. A separately authorized external
clean-Codex command replays the complete versioned manifest with the same fake
host collaborators and two clean actors. It rejects partial-manifest runs and
records only the redacted acceptance evidence described above.

The deterministic corpus now exercises the original deferred-runtime,
`council-request`, and `document-embedding` contracts through authoring and
finalization before registration rejects their declared missing host
capability. This is boundary evidence only, not support for those deferred
features.

Until this gate passes, `agent-engineering` is the only marketplace successor,
but the migration record must not claim successor clean-Codex author-then-run
acceptance.
