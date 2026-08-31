# A3 C0 Sealed-Host Boundary Analysis

## Evidence

- `LocalModelProfileControlPlane` accepts only
  `strict-local-adapter-v1` records with a loopback `base_url`, and
  `create_local_adapter(...)` constructs only the HTTP local adapter.
- `LocalWorkflowHost.open(...)` unconditionally calls that factory.
- `WorkflowRunner` is annotated with `OpenAIClientAdapter`, but it calls
  `run_agent_workflow(...)`.
- `run_agent_workflow(...)` is the existing synchronous wrapper around
  `run_agent_workflow_async(...)`; the executor accepts both synchronous and
  asynchronous OpenAI adapter types when no event loop is already running. Its
  existing active-loop failure remains outside the A3 host seam.

## Resulting A3 boundary

A3 does not need a new async runner. It needs a discriminated human-owned
profile/factory, a runner type widened to the existing async adapter type,
strict adapter coverage, and an exact active-profile check before sealed-input
consumption. It does not add a nested-loop workaround or a second host
execution API.
