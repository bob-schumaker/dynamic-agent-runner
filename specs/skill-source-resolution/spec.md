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

## Non-Goals

- No implicit loading from global user skill directories.
- No network fetching of skills.
- No execution of code from skill files.
- No automatic interpretation of arbitrary support files as prompt context.
- No mutation of generated package artifacts.
- No v1 loading from `source_path` outside the package bundle.

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
