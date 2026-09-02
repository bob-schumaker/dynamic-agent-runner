# Agent-Friendly CLI Reference

Use this reference when an agent-facing tool is a command-line interface or when
a local CLI should be callable from an agent workflow without fragile parsing,
interactive surprises, or unsafe shell behavior.

## Core Contract

- Prefer JSON for machine-facing output when the primary caller is an agent.
- Keep stdout for structured result data only.
- Send logs, warnings, progress, and diagnostics to stderr.
- Return non-zero exit codes for failures.
- Never enter an interactive prompt when required input is missing in an
  automation or agent path.
- Treat command output schemas, error codes, and flag names as compatibility
  contracts.

## Output Shape

Use a stable success envelope when the command has more than a trivial scalar
result:

```json
{
  "ok": true,
  "result": {},
  "warnings": [],
  "metadata": {
    "version": "1.0.0"
  }
}
```

Keep large responses bounded:

- support field selection when practical
- return summaries before full records when the agent only needs routing
  context
- include explicit truncation markers
- preserve identifiers or provenance needed for follow-up calls

## Error Shape

Use structured errors that let the agent recover:

```json
{
  "ok": false,
  "error": {
    "code": "MISSING_REQUIRED",
    "message": "Missing required --project-id.",
    "suggestion": "Pass --project-id <id> or run the discovery command first.",
    "retryable": false
  }
}
```

Write error JSON to stderr and exit non-zero. Avoid successful exit codes for
semantic failures.

## Exit Codes

Use a small stable set unless the repository already defines one:

- `0` - success
- `1` - general failure
- `2` - usage or validation error
- `10` - authentication failure
- `11` - permission failure
- `20` - requested object not found
- `30` - conflict, precondition failure, or stale state

Document any additional codes in the CLI help.

## Flags

Prefer long, explicit flags. Reserve familiar agent-facing flags when they fit:

- `--agent` - force machine-readable mode when another default may exist
- `--human` - force human-readable mode
- `--version` - print version information
- `--help` - describe commands, parameters, output, and errors
- `--yes` - confirm destructive operations
- `--dry-run` - preview without mutation
- `--quiet` - suppress non-essential stderr output
- `--fields` - select fields to reduce output size

Do not silently ignore unknown flags. Return a usage error with a suggestion.

## Input Safety

Validate CLI inputs like public API inputs:

- reject path traversal when paths are accepted
- reject control characters in identifiers and filenames
- reject secrets passed as arguments when they match obvious token patterns
- avoid accepting shell fragments as data unless the tool is explicitly a shell
  tool
- cap batch sizes and input document sizes
- require explicit confirmation for destructive operations

When input is externally sourced, prefer file or stdin contracts over shell
quoted arguments that encourage injection-prone command construction.

## Help And Self-Description

Agent-facing help should answer:

- what the command does
- when an agent should use it
- required and optional inputs
- output schema
- error codes
- side effects and approval requirements
- examples for common successful and failing calls

If the CLI has many commands, provide a compact summary command or machine
readable help output so agents can discover the correct command without trying
several wrong calls.

## Review Checklist

- [ ] JSON or another stable machine-readable format is available for all agent
      paths.
- [ ] stdout contains result data only.
- [ ] stderr contains logs, diagnostics, and structured errors.
- [ ] failures exit non-zero.
- [ ] missing inputs fail fast without prompting.
- [ ] destructive actions require explicit confirmation.
- [ ] `--dry-run` is available for risky changes where practical.
- [ ] error messages include a corrective suggestion.
- [ ] output size is bounded or selectable.
- [ ] sensitive inputs, paths, and shell metacharacters are validated.
