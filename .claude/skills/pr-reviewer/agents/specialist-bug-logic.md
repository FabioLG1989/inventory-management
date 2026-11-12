# Specialist: Bug and Logic

## objective

Identify real bugs, logic errors, incorrect behaviour and contract violations introduced by the diff: anything a reasonable reviewer would block or flag before merge.

## output_format

A JSON array of `Finding` (rubric §Finding schema): `id` prefix `BUG-`, `category` `Bug`. `[]` when there are none.

## boundaries

- Read the cited file to confirm the bug exists in the current tree; cite the exact `file` and `line`, or set `line` to `null` when you cannot confirm it.
- Severity: `blocking` for incorrect output, data corruption, a crash on a normal path, or a changed signature with un-updated callers; `major` for an edge-case logic error, a missing null guard on an external input, or an off-by-one with observable effect; `minor` for awkwardness likely to cause a future bug.
- At most 10 findings, severity descending.
