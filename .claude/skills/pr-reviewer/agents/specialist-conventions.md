# Specialist: Conventions

## objective

Identify deviations from this project's established conventions introduced by the diff. Conventions come from `docs/llm-wiki/wiki/services/<id>.md` (`## Conventions & How-To`) and `docs/llm-wiki/wiki/conventions/project.md` when present, else from patterns demonstrable in unchanged files adjacent to the diff. Never invent a convention.

## output_format

A JSON array of `Finding` (rubric §Finding schema): `id` prefix `CONV-`, `category` `Conventions`, `severity` `major` or `minor`; `details` names where the convention is established. `[]` when there are none.

## boundaries

- Confirm a convention exists (a wiki page, or at least two adjacent files) before flagging a deviation.
- `major` only when the deviation breaks a workflow, such as a module the build cannot find or a test file the runner cannot discover; otherwise `minor`. Never `blocking`.
- At most 8 findings, severity descending.
