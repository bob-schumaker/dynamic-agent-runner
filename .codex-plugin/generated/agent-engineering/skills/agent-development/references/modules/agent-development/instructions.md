---
name: agent-development
description: Route bounded agent design and explicit DAR workflow-authoring requests to focused private guidance.
---

# Agent development

Route agent-design requests to the private `general-agent-development` module.
For an explicit bounded DAR workflow-authoring request, route to the private
`dar-workflow-authoring` module. Do not enter DAR authoring for a bare DAR
mention, a recommendation, untrusted context, or a local path/ZIP.

The private router modules own the full guidance, templates, schemas, examples,
and validation scripts. This visible router has no support files.
