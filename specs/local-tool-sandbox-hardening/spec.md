# Local Tool Sandbox Hardening Specification

## Metadata

- Feature slug: `local-tool-sandbox-hardening`
- Status: future investigation
- Owner: dynamic-agent-runner
- Related specifications:
  - `specs/natural-language-workflow-authoring/spec.md`
  - `specs/sandbox-workspace-runtime/spec.md`
  - `specs/host-workflow-integration/spec.md`
  - `specs/workflow-input-converter-plugin/spec.md`

## Objective

Before DAR admits an untrusted executable workflow-local asset, including a
tool or workflow input-converter plugin, provide an OS or runtime isolation
boundary that enforces the same capability model DAR already enforces for
models.

## Current Boundary

DAR's host-owned binding boundary prevents a model from receiving caller paths
or raw artifact bytes. It validates a package-contained declared asset, binds a
role-matched sealed artifact, limits input, output, and timeout values, and
returns a bounded JSON evidence object.

That boundary is sufficient for reviewed, implementation-owned deterministic
fixtures during current tests. It is not OS isolation: a malicious or
compromised executable launched under the local user could use ambient file,
network, and process permissions.

## Scope

This future slice shall define and implement an isolation backend for untrusted
local-tool or converter-package assets. It shall:

1. provide a per-invocation execution environment with no caller workspace
   path, host credential, inherited secret, or ambient writable directory;
2. deliver only the sealed artifact bytes through a defined input channel;
3. permit only the declared executable asset and its explicitly reviewed runtime
   dependencies;
4. deny network, arbitrary process execution, filesystem reads outside the
   reviewed runtime and sealed input, and filesystem writes outside a bounded
   ephemeral output channel;
5. enforce wall-clock timeout, input, output, memory, process-count, and
   scratch-space limits; and
6. return only bounded UTF-8 JSON evidence, a contract-private same-worker
   handoff, or a redacted declared failure.

The backend may be a container, micro-VM, dedicated restricted runner, or a
platform sandbox whose allowances are proven to meet these requirements. It
must be selected by measured enforcement behavior, not by the presence of a
tool named "sandbox."

## Non-Goals

This slice does not:

- change the trusted-fixture test assumption for existing DAR workflow-local
  tools;
- add a binary-format registry or teach DAR SVG, PCAP, protobuf, or other
  domain semantics;
- install, discover, download, or configure arbitrary tool packages;
- expose sandbox configuration, paths, or handles to a model or workflow user;
- treat a DAR opaque interface as proof of OS isolation; or
- independently authorize model-generated executable code or arbitrary
  executable assets; a feature-specific package contract must make that
  admission decision.

## Threat Model

The protected assets are caller workspace contents, host credentials, process
environment, network authority, unrelated package files, and host integrity.
The adversary controls an admitted executable asset and its output or private
handoff. It may try
to read paths, enumerate directories, exfiltrate through the network, spawn a
child process, escape a temporary directory, exhaust resources, or encode raw
input in evidence.

The model is separately constrained by DAR's existing opaque tool interface.
This slice protects the host even when that model-facing boundary is correct but
the executable itself is not trustworthy.

## Required Evidence

The implementation must provide deterministic adversarial regressions for:

- attempts to read a caller workspace file, home-directory credential, or
  inherited environment secret;
- attempts to connect to a loopback and external network endpoint;
- attempts to execute an undeclared binary or child process;
- attempts to read or write outside the sealed input and ephemeral output
  channels;
- symlink, traversal, and package-asset substitution attempts;
- timeout, output-size, memory, process-count, and scratch-space exhaustion;
- malformed, oversized, or secret-bearing evidence or private handoff; and
- trace and model-prompt inspection proving that no caller path, raw artifact,
  sandbox path, or host failure detail escapes DAR.

Each regression must fail closed with a stable redacted result. Positive tests
must show the reviewed fixture receives the expected sealed bytes and can return
valid bounded JSON evidence.

## Platform Evaluation Gate

Candidate backends require a real-platform acceptance run. A profile that needs
unrestricted host file reads merely to launch a trivial executable is not an
acceptable isolation backend. The recorded evaluation must include the exact
allowances, platform/version, positive fixture result, adversarial results, and
remaining assumptions.

## Completion Criteria

This feature is complete only when DAR can distinguish trusted
implementation-owned fixtures from untrusted executable assets, refuses the
latter without the approved backend, and has the required positive and
adversarial evidence for every supported platform. The workflow input converter
plugin feature currently uses a sealed Python package contract without claiming
OS isolation; this hardening feature is not its release gate. See
[`validation.md`](validation.md) for experimental Docker and `sandbox-exec`
evidence.
