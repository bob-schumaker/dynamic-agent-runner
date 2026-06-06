# SKILL.md Source Resolution Specification

## Metadata

- Feature slug: `skill-source-resolution`
- Mode: `light`
- Artifact type: future feature specification
- Status: proposed future feature; current runtime preserves skill metadata and
  skill refs but does not load arbitrary `SKILL.md` bodies
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
bundle paths. It preserves `skill_refs` on `llm_step` nodes and supports runtime
behavior overrides. It intentionally defers arbitrary `SKILL.md` source-path
resolution and does not treat source files outside the package boundary as
executable prompt material.

## Scope

This feature covers:

1. allowed skill-source locations
2. trust and provenance policy
3. path resolution and package-boundary enforcement
4. prompt injection precedence
5. conflict resolution across multiple skills
6. caching and reload policy
7. redaction and trace metadata

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

### FR-2: Preserve trust and provenance metadata

Loaded skill bodies must carry source provenance.

Acceptance criteria:

- Each loaded skill records skill id, package id, bundled path, source kind,
  resolved path or opaque source id, content hash, and trust classification.
- External caller-authorized skills are distinguishable from generated package
  skills.
- Trace events and prepared-model-input metadata can identify which skills
  influenced a node without dumping full skill content by default.

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

### FR-4: Support bounded content loading

Skill source loading must be bounded.

Acceptance criteria:

- Max skill file size, max combined skill content, and max support-file count are
  enforced.
- Binary files and unsupported encodings fail clearly.
- Markdown frontmatter or metadata is parsed only if explicitly supported.
- Support files are loaded only when referenced and allowed.

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

## Non-Goals

- No implicit loading from global user skill directories.
- No network fetching of skills.
- No execution of code from skill files.
- No automatic interpretation of arbitrary support files as prompt context.
- No mutation of generated package artifacts.

## Design Constraints

- Keep package-local bundle resolution as the safest default.
- Require caller authorization for external skill roots.
- Make ordering deterministic and visible in prepared-input metadata.
- Keep raw skill bodies out of traces unless explicitly requested.
- Preserve current behavior when no source-loading policy is enabled.

## NEEDS CLARIFICATION

- Should package-local `skill-bundle/` `SKILL.md` bodies load by default, or only
  when a caller enables source loading?
- What exact prompt precedence should apply across system prompt, skills,
  overrides, file-backed context, and node prompt?
- Should skill files support frontmatter, and if so what fields are recognized?
- Are support files loaded as prompt content, validation inputs, or metadata
  only?
- What size limits should apply per file and per node?
- What external skill roots, if any, should be trusted?
- Should content hashes be exposed in public API results?
- How are duplicate skill ids across package and external roots resolved?
- Can runtime overrides replace a bundled skill body?
- What redaction rules apply to skill content in prepared-input traces?

## Validation Checklist

- [ ] Package-local skill paths resolve within `skill-bundle/`.
- [ ] Traversal and symlink escapes fail closed.
- [ ] Missing required skill refs fail during preparation.
- [ ] Multiple skill refs inject in deterministic order.
- [ ] Size and encoding limits are enforced.
- [ ] Runtime overrides produce derived behavior without mutating package files.
- [ ] Trace metadata identifies loaded skills without raw body leakage.
