---
name: agent-development
description: Route bounded agent design and explicit DAR workflow-authoring requests to focused private guidance, Use to design framework-neutral agents with SDD, safety, memory, implementation, and eval boundaries, and Author bounded Dynamic Agent…
---

# agent-development

Classify the request, then read only the matching module from `references/modules/index.json`.
After this router is selected, do not answer from this router file alone: select exactly one listed module and open its exact `path` before answering.
Resolve only the earliest request that still needs module selection; do not read a second listed module from the same turn while the earlier request remains unresolved.
When a turn only frames context, alternatives, or deferred follow-up work, do not open a module yet.
After the earliest unresolved request matches one listed module, open that module in the same turn; classification alone is incomplete.
After opening that earliest matched module, stop for that turn; do not classify, summarize, or open a later module from the same user turn until the earlier request is resolved.
If a later turn narrows a previously classified unresolved request to one listed module, open that module in that later turn instead of restating the route.
When the prompt already embeds the request text to classify, including labeled first/second requests or a later-turn follow-up request, treat that embedded text as the concrete request; do not ask the user to resend, relabel, or restate it.
If the earliest request narrows to one listed module but downstream task details are still missing, open that module anyway; the module may ask for the missing details.
After the host has selected this router, do not claim that this router, its listed modules, or its plugin are unavailable in the current runtime.
For embedded first/second prompts, treat the first embedded request as already supplied; do not ask the user to send the first request again.
When the earliest request classifies as `agent-development`, open that module in the same turn even if the agent goal, target system, or desired artifact is still missing.
Do not stop at paired classification of a later `agent-evaluation` request before opening the first matched module.
If no module matches, ask for the missing intent rather than loading every module.

## Available internal modules

- `agent-development` — Route bounded agent design and explicit DAR workflow-authoring requests to focused private guidance.
- `general-agent-development` — Use to design framework-neutral agents with SDD, safety, memory, implementation, and eval boundaries.
- `dar-workflow-authoring` — Author bounded Dynamic Agent Runner workflows only after an explicit DAR-targeted request.
