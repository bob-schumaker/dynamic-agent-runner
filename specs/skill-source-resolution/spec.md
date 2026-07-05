# SKILL.md Source Resolution Specification

## Metadata

- Feature slug: `skill-source-resolution`
- Mode: `light`
- Artifact type: authoritative SDD feature specification
- Status: v1 implemented; source loading is opt-in and package-local only.
  The runtime still does not load arbitrary `SKILL.md` bodies outside declared
  package bundles.
- Primary spec: `specs/dynamic-agent-runner/spec.md`
- Related runtime surfaces:
  - package `skill-bundle/`
  - manifest `skills`
  - `llm_step.skill_refs`
  - runtime behavior overrides
  - prompt preparation and file-backed context metadata
- Evaluated external skill-loading provenance:
  - [`sickn33/antigravity-awesome-skills`](https://github.com/sickn33/antigravity-awesome-skills)
  - `/Users/roschuma/Repos/github/antigravity-awesome-skills/docs/users/discovery-manifest.md`
  - `/Users/roschuma/Repos/github/antigravity-awesome-skills/docs/integrations/jetski-cortex.md`
  - `/Users/roschuma/Repos/github/antigravity-awesome-skills/docs/users/agent-overload-recovery.md`
  - `/private/tmp/antigravity-awesome-skills-docs-graph/graphify-out/GRAPH_REPORT.md`

## Objective

Define how the runtime may load, trust, order, and inject `SKILL.md` source
content into effective model behavior without allowing arbitrary filesystem reads
or ambiguous prompt precedence.

## Existing Baseline

The runtime loads package-local skill bundle metadata and validates referenced
bundle paths. It preserves `skill_refs` on `llm_step` nodes, supports runtime
behavior overrides, and can opt into bounded package-local `SKILL.md` prompt
loading through `runtime.execution_policy.skill_source_resolution`. It still
defers arbitrary `SKILL.md` source-path resolution and does not treat source
files outside the package boundary as executable prompt material.

## Scope

This feature covers:

1. allowed skill-source locations
2. trust and provenance policy
3. path resolution and package-boundary enforcement
4. prompt injection precedence
5. conflict resolution across multiple skills
6. caching and reload policy
7. redaction and trace metadata
8. capability/status reporting for live, metadata-only, and rejected skill
   sources
9. lazy loading and overflow diagnostics for selected skill sources

## V1 Decisions

The first implementation slice should be deliberately narrow:

- Source loading is opt-in through
  `runtime.execution_policy.skill_source_resolution.enabled: true`.
- V1 loads only package-local skill bodies referenced by `skills[*].bundled_path`
  under the loaded package's `skill-bundle/` directory.
- Inline `skills[*].instructions` remains supported and continues to work when
  source loading is disabled.
- External skill roots, global user skill directories, network sources, and
  absolute `source_path` reads are deferred.
- Support files are validated as package-local metadata but are not loaded as
  prompt content in v1.
- Only UTF-8 text/Markdown `SKILL.md` bodies are supported.
- Default limits are conservative: 64 KiB per skill body, 256 KiB combined per
  node, and zero support files loaded into prompts.
- V1 byte budgets are implemented; token-aware budgets, maximum skills per
  turn, and explicit overflow behavior are follow-up policy extensions under
  this same feature boundary.
- Prompt injection order is:
  1. base system prompt
  2. base developer prompt
  3. effective skill instructions in deterministic `skill_refs` order
  4. prepared context lanes such as file-backed context
  5. user prompt
- Runtime behavior overrides can add, remove, replace, or reorder skill
  references, but v1 does not allow an override artifact to authorize arbitrary
  file reads outside package-local bundled skills.
- Loaded source provenance is redacted in traces by default: skill id, source
  kind, relative bundled path, byte count, content hash, and trust
  classification may be reported; raw body content is not trace payload.

## Functional Requirements

### FR-1: Resolve only approved skill sources

The runtime must load skill bodies only from approved package-local or
caller-authorized sources.

Acceptance criteria:

- Package-local `skill-bundle/` paths are resolved relative to the loaded runtime
  package.
- Caller-provided external skill roots require explicit configuration.
- Absolute paths, parent traversal, symlink escapes, and undeclared support files
  fail closed.
- Manifest metadata alone cannot authorize reading arbitrary host files.
- V1 source loading is disabled unless
  `runtime.execution_policy.skill_source_resolution.enabled` is true.
- V1 treats `source_path` as provenance only, not as read authorization.

### FR-2: Preserve trust and provenance metadata

Loaded skill bodies must carry source provenance.

Acceptance criteria:

- Each loaded skill records skill id, package id, bundled path, source kind,
  resolved path or opaque source id, content hash, and trust classification.
- External caller-authorized skills are distinguishable from generated package
  skills.
- Trace events and prepared-model-input metadata can identify which skills
  influenced a node without dumping full skill content by default.
- Package-local bundled skills use a `package_local` trust classification.

### FR-3: Define prompt injection precedence

Skill content must be inserted into model prompts deterministically.

Acceptance criteria:

- Precedence defines ordering among base system prompt, runtime behavior
  overrides, node prompt, skill instructions, file-backed context, and caller
  prompt.
- Multiple `skill_refs` on one node are ordered by explicit node order or a
  stable manifest order.
- Conflicting skill ids, duplicate refs, and missing required skills fail during
  preparation.
- Optional missing skills can be omitted only when declared optional.
- V1 injects source-loaded skill bodies through the existing skill-instruction
  message lane so prompt-cache and prepared-input diagnostics can distinguish
  skill instructions from user prompt text.

### FR-4: Support bounded content loading

Skill source loading must be bounded.

Acceptance criteria:

- Max skill file size, max combined skill content, and max support-file count are
  enforced.
- Binary files and unsupported encodings fail clearly.
- Markdown frontmatter or metadata is parsed only if explicitly supported.
- Support files are loaded only when referenced and allowed.
- V1 rejects unsupported encodings and binary-looking content before prompt
  assembly.

### FR-5: Compose with runtime behavior overrides

Overrides must not mutate the generated package or silently replace skill
semantics.

Acceptance criteria:

- Runtime overrides can add, disable, replace, or reorder effective skill
  bindings only through explicit allowed override operations.
- Overrides are validated against the immutable base package.
- Effective behavior is compiled into derived runtime state without changing
  `agent-design.md`, `agent-runtime.yaml`, `agent-graph.mmd`, or
  `skill-bundle/`.

### FR-6: Report loading and injection diagnostics

Skill resolution must be debuggable.

Acceptance criteria:

- Preparation reports loaded skills, omitted optional skills, disabled skills,
  duplicate refs, missing files, rejected paths, and size-limit failures.
- Trace payloads include redacted skill-source metadata.
- Model-facing prompts can be inspected through existing prepared-input
  structures subject to redaction policy.

### FR-7: Preserve current behavior unless enabled

Source loading must not change existing packages unless callers opt in.

Acceptance criteria:

- Packages with inline skill instructions behave the same when source loading is
  disabled.
- Packages with `skills[*].bundled_path` but no inline instructions still
  validate as metadata-only when source loading is disabled.
- Capability/status reports show `metadata.skill_refs` as metadata-only when the
  policy is absent or disabled.
- Capability/status reports show live package-local source loading only when the
  policy is enabled and all referenced package-local bodies pass validation.
- Source-loading failures are preparation/validation failures before model calls,
  not silent prompt omissions.

### FR-8: Keep skill loading lazy and selected-only

Skill-source resolution must not load every available `SKILL.md` file into a
prompt.

Acceptance criteria:

- Given a package contains many declared skills, when a node references none of
  them, then no skill bodies are loaded for that node.
- Given a node references a bounded subset of skills, when source loading is
  enabled, then only the effective selected `skill_refs` are resolved and read.
- Given a manifest or skill index is available, when resolving a node, then the
  manifest is used as lightweight discovery metadata and does not by itself
  authorize reading all skill bodies.
- Given a resolved path escapes the configured package-local root, when loading
  is attempted, then resolution fails closed before prompt assembly.

### FR-9: Add token-aware skill-source overflow behavior

Follow-up policy should enforce token-aware limits in addition to the existing
byte limits.

Acceptance criteria:

- Given `max_skill_tokens`, `max_node_skill_tokens`, or `max_skills_per_turn`
  is configured, when skill sources are resolved, then the runtime estimates
  selected skill-source tokens before prompt injection.
- Given selected skill sources exceed a token or count budget and
  `overflow_behavior: error` is configured, then preparation fails clearly with
  a package-owned diagnostic and no model call is made.
- Given selected skill sources exceed a token or count budget and a future
  truncation or omission behavior is configured, then the behavior is explicit,
  deterministic, and reflected in redacted metadata.
- Given skill-source overflow occurs, when traces or prepared-input metadata are
  inspected, then they report selected, omitted, rejected, and over-budget skill
  ids without raw skill body leakage.

## Non-Goals

- No implicit loading from global user skill directories.
- No network fetching of skills.
- No execution of code from skill files.
- No automatic interpretation of arbitrary support files as prompt context.
- No mutation of generated package artifacts.
- No v1 loading from `source_path` outside the package bundle.
- No automatic trajectory-to-skill extraction, skill rewriting, promotion, or
  persistence based on model outcomes.

## Design Constraints

- Keep package-local bundle resolution as the safest default.
- Require caller authorization for external skill roots.
- Make ordering deterministic and visible in prepared-input metadata.
- Keep raw skill bodies out of traces unless explicitly requested.
- Preserve current behavior when no source-loading policy is enabled.
- Prefer a small package-owned resolver module over embedding file-reading logic
  in the executor.

## Proposed Runtime Shape

Implemented v1 metadata:

```yaml
runtime:
  execution_policy:
    skill_source_resolution:
      enabled: true
      allowed_sources:
        - package_bundle
      max_skill_bytes: 65536
      max_node_skill_bytes: 262144
      load_support_files: false
      prompt_role: developer
```

This is not a broad plugin system. It is an opt-in resolver for already-declared
package-local bundled skills.

Planned follow-up policy growth remains under the same key:

```yaml
runtime:
  execution_policy:
    skill_source_resolution:
      max_skill_tokens: 4096
      max_node_skill_tokens: 16384
      max_skills_per_turn: 5
      overflow_behavior: error
```

`overflow_behavior: error` is the preferred first token-overflow behavior
because it gives callers a clear failure instead of silently truncating
instructions.

Implementation surfaces:

- `dynamic_agent_runner.skill_sources` for resolver dataclasses and
  package-local file loading
- `RuntimeManifest` or execution-policy helper for parsed
  `skill_source_resolution` policy
- `PreparedInputMetadata` and companion internal preparation structures for
  resolved instruction bodies and provenance
- `prepare_model_input(...)` / `_render_message_parts(...)` for injection and
  prepared-input metadata
- `capabilities.py` for live/metadata-only/rejected skill-source status
- `validation.py` for policy shape, path, size, encoding, and missing-source
  checks before execution

## Deferred Questions

- What external skill roots, if any, should be trusted after v1?
- Should support files become prompt content, retrieval inputs, or metadata-only
  diagnostics in a later slice?
- Should Markdown frontmatter be parsed into recognized fields after v1?
- Should runtime overrides be able to replace a bundled skill body, and if so
  what trust/provenance class should that carry?
- Should public API results expose content hashes by default or only through
  detailed diagnostics?
- Should duplicate skill ids across package and future external roots fail
  closed, prefer package-local skills, or require explicit precedence metadata?
- What redaction mode should expose raw skill content for debugging without
  making traces unsafe by default?
- Should token estimation use the active model tokenizer when available, a
  provider-neutral heuristic, or both with explicit metadata?
- If a caller later wants `overflow_behavior: omit`, what policy decides which
  selected skills may be omitted without changing task semantics?

## Future Caller-Owned Skill Selection Boundary

Procedural-memory examples suggest useful selection metadata, but learning and
mutating skills do not belong in source resolution. If a concrete caller needs
dynamic selection, extend this work area with a caller-supplied selector rather
than a runner-owned learning engine.

- The selector receives only eligible, already resolved skill descriptors plus
  bounded task/context metadata.
- It returns ordered skill ids with reason codes and optional caller-computed
  scores; it does not grant new file reads or return executable code.
- DAR revalidates selected ids against trust, exposure, compatibility, size,
  and prompt-budget policy before injection.
- Optional usage count, success/failure count, preconditions, version,
  provenance, and last-evaluated metadata remain caller supplied.
- DAR may trace the selection and eventual outcome, but it does not update
  scores, persist learned state, or mutate `skill-bundle/` automatically.
- A newly learned or rewritten skill becomes eligible only through an explicit
  package update or a future caller-authorized external binding contract.

This is a deferred extension to skill resolution and injection, not a separate
feature specification or implementation authorization.

## Validation Checklist

- [x] Package-local skill paths resolve within `skill-bundle/`.
- [x] Traversal and symlink escapes fail closed.
- [x] Missing required skill refs fail during validation.
- [x] Multiple skill refs inject in deterministic order.
- [x] Size and encoding limits are enforced.
- [x] Runtime overrides produce derived behavior without mutating package files.
- [x] Trace metadata identifies loaded skills without raw body leakage.
- [x] Source loading is opt-in and package-local in v1.
- [x] `source_path` remains provenance-only in v1.
- [x] Support files are not loaded as prompt content in v1.
- [x] Capability/status reporting distinguishes disabled metadata-only skill
      refs from live or rejected package-local source loading.
- [ ] Token-aware skill-source budgets are enforced before prompt injection.
- [ ] `overflow_behavior: error` produces clear diagnostics and makes no model
      call.
- [ ] Lazy-loading tests prove unreferenced `SKILL.md` bodies are not read.
- [ ] A future selector cannot select an unresolved, untrusted, disabled, or
      over-budget skill.
- [ ] Selection telemetry does not mutate skill sources or caller-owned
      success/usage state.
