# Markdown Adapter

Writes the canonical bug report to a local markdown file. No MCP required, no duplicate lookup (no store to search).

## Requirements

- Write access to the target directory.

## Flag syntax

```
--to-markdown [PATH]
```

- A `.md` path with one bug → that file.
- Anything else (a folder, or several bugs) → a folder, default `bug-reports/`, with one file per bug named `<NN>-<title-slug>.md` (`NN` = the bug's number in the batch). Picking `Markdown file` in Phase 4's destination question uses this default unless the user names a path.

## Field mapping (canonical → Markdown)

| Canonical | Markdown section |
|-----------|-------------------|
| `title` | `# <title>` heading |
| `severity` + `priority` + `reproducibility` | metadata line: `**Severity**: major \| **Priority**: high`; append ` \| **Reproducibility**: <value>` only for `"intermittent"`/`"once"` ([SKILL.md](../references/output-formatting.md)) |
| `environment` | `**Environment**` bullet list |
| `preconditions` | `**Preconditions**` paragraph |
| `steps_to_reproduce` | `**Steps to Reproduce**` numbered list |
| `expected_result` / `actual_result` | `**Expected Result**` / `**Actual Result**` paragraphs |
| `regression` | `**Regression**` line |
| `test_reference` | `**Failing Test**` bullet list (omit the whole section when `test_reference.framework` is `null`) |
| `suspected_area` | `**Suspected Area**` bullet list |
| `evidence` (text: `stack_trace`, `log`) | `**Error Log**` fenced code block with the redacted error text, same source as [jira.md's error log comment](./jira.md#error-log-comment) — mandatory whenever `test_reference.framework` is non-null |
| `evidence` (binary) | `**Evidence**` list of paths |
| `linked_test_case` / `linked_ticket` | `**Links**` list |
| `tags` | `**Tags**` line |

## File template

````markdown
# <title>

**Severity**: major | **Priority**: high
**Regression**: yes (last known good: a1b2c3d)

## Environment
- App version: ...
- OS / Browser: ...
- Env: staging | Service: ...

## Preconditions
...

## Steps to Reproduce
1. ...

## Expected Result
...

## Actual Result
...

## Failing Test
- Framework: Playwright
- Test: checkout.spec.ts › applies discount code at checkout
- Run it locally: `npx playwright test tests/e2e/checkout.spec.ts -g 'applies discount code at checkout'`

## Error Log
```
<error.message + error.stack, the joined failureMessages[], WebdriverIO's error + standardError, or the JUnit <failure> message + text>
```

## Suspected Area
- ...

## Evidence
- ./test-results/checkout.spec.ts-report.json

## Links
- Test case: ...
- Ticket: ...

## Tags
tag-a, tag-b
````

## Phase 5 progress announcements

- Before the write: `⏳ Writing bug report to <path>...`

## Success report

Do not print a per-file report as each write finishes — Phase 5 (per [SKILL.md](../SKILL.md#phase-5-publish-via-adapter)) waits until every candidate in the run has been written and then prints **one consolidated block**, one [Output Formatting](../references/output-formatting.md) card per bug, each with its `Ticket` row set to `📝 Written to \`<path>\``.

## Errors

- Write fails (permission denied, parent directory doesn't exist, disk full): `❌ Failed to write the bug report to <path>: <underlying filesystem error>. Nothing was saved.` — then reprint the full canonical report per [SKILL.md's Error Handling](../SKILL.md#error-handling) so the work isn't lost. Do not silently retry at a different path without asking.
