# Local Model Preparation Validation

## Automated evidence

On 2026-09-07, the focused S1--S4 suite passed:

```text
103 passed in 1.00s
```

The complete repository gate also passed:

```text
1833 passed, 1 skipped, 7 deselected, 7 warnings
```

`poetry run ruff check src tests` and `git diff --check` passed. The seven
warnings are pre-existing unregistered `live_matrix` pytest marks.

## Manual floorplan acceptance

The following is historical evidence from the removed model-named preparation
CLI; it is not a current DAR interface:

```text
dar-package prepare --model qwen25-vl-3b-floorplan-grpo
```

with a path-free `ready` receipt. It then accepted the sealed JPEG ingress and
completed two local llama.cpp workflow invocations. Source files, cache roots,
artifact paths, converter commands, and preparation handles were not exposed in
the public preparation receipt or invocation receipt.

The original SVG-directed runs produced truncated repeated-shape streams with no
closing `</svg>` element. That request was not the model's documented output
contract: the reviewed FloorplanVLM material specifies structured floorplan
JSON. The acceptance package and feature contract were revised accordingly;
JSON-to-SVG rendering and SVG validation remain downstream workflow-local
tooling.

The direct llama.cpp adapter then forwarded explicit `max_tokens`,
`temperature`, and `stop` parameters. The historical floorplan binding used a
16,384-token context. A JSON-contract package registered, ingressed the sealed
JPEG, and reached the host execution boundary. The captured 4,096-token
response and a subsequent
8,192-token response were both unterminated JSON. A final run used the exact
published system schema and user prompt, but was likewise invalid at character
10,193. The historical T5.2 failure was therefore model/inference quality, not
preparation, sealed ingress, context allocation, or prompt schema. The
documented model workflow would have needed a model or inference-path correction
outside this DAR-preparation slice.

## Historical outcome

This is not a current release blocker. The package-bound successor owns current
material evidence in `../workflow-model-materials/tasks.md` M9.1--M9.6, and the
separate completed MPS receipt gate is
`../workflow-model-support-matrix/tasks.md` WMS3.3.

## Plugin regeneration

DAR now pins `marketplace-installer==0.1.2` in its development toolchain. The
owned `poetry run marketplace-installer` entrypoint plans and applies the
native-routed Agent Engineering invocation successfully, resolving the source
root from the source manifest and materializing both declared payload assets.
The regenerated tree passes the Agent Engineering plugin suite (10 passed) and
`git diff --check`.
