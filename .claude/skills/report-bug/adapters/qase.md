# Qase Adapter

Publishes a canonical bug report as a **defect** in Qase via MCP.

## Requirements

- A Qase MCP server with a valid API token — project-scoped in `.mcp.json` or a hosted connector. Tools below are named by operation only; resolve their prefix per [SKILL.md's MCP tool resolution](../SKILL.md#mcp-tool-resolution).

## Flag syntax

```
--to-qase [PROJECT-CODE]
```

If `PROJECT-CODE` is omitted, list the projects with `qase_api` (`GET /v1/project`): exactly one → use it without asking; more than one → ask which, showing each `code` and `title`.

## Duplicate lookup

Before creating the defect, search existing Qase defects in the target project with `qql_search`, one `title ~` clause per sanitized keyword, joined with `or`, from [SKILL.md Phase 2](../SKILL.md#phase-2-evidence-gathering) (letters and digits only, so nothing can break out of the quoted string):
```
entity = "defect" and project = "<CODE>" and (title ~ "<keyword1>" or title ~ "<keyword2>")
```
Show up to 5 candidates with title + status + link; ask the user to proceed, link the new evidence to an existing defect instead, or abort. The API returns no defect URL: every link to a defect, here and in the success report, is `https://app.qase.io/defect/<CODE>/view/<id>` — the `/view/` segment is required, the page doesn't open without it.

Only same-platform matches count — see [SKILL.md's same-platform rule](../SKILL.md#phase-2-evidence-gathering): compare `[Mobile]` only with `[Mobile]`, `[BE]` with `[BE]`, `[UI]` with `[UI]`, and drop other matches silently.

## MCP tools

- `qql_search` — duplicate lookup.
- `qase_attachment_upload` — upload each evidence file first, in one call via `files[]` (`file_path` = each file's `upload` path from the `sanitize` command of [SKILL.md's evidence script](../SKILL.md#evidence-files) — never the original — for a local stdio server); returns a `hash` per file. Uploading alone attaches nothing — the hash has to be passed to `attachments` on the next call. A hosted connector cannot read local files: when the upload reports a file not found, never base64-encode it — list each file's `upload` path from `sanitize` (never the original) under `**Evidence:**` in `actual_result` instead.
- `qase_defect_upsert` — creates (no `id`) or updates (with `id`) the defect. Requires `code`, `title`, `actual_result`, `severity` to create.
- `qase_get` (`entity: "defect"`) — read back a created defect to confirm/report its state.
- `qase_api` (`GET /v1/project`) — lists projects (`code`, `title`) when no code was given.

## Field mapping (canonical → Qase defect)

The live `qase_defect_upsert` schema is much flatter than Jira's or Qase's own *test case* schema — there is **no** `preconditions`, `steps_to_reproduce`, `expected_result`, `description`, or `priority` field on a defect. Only `title`, `actual_result`, `severity`, `status`, `tags`, `attachments`, `custom_field` exist.

| Canonical | Qase field |
|-----------|------------|
| `title` | `title` |
| `preconditions` + `steps_to_reproduce` + `expected_result` + `actual_result` + `test_reference` + stack trace | folded into one formatted `actual_result` block — see template below. This is the only rich-text field a defect has. |
| `severity: "blocker"` | `severity: "blocker"` |
| `severity: "critical"` | `severity: "critical"` |
| `severity: "major"` | `severity: "major"` |
| `severity: "minor"` | `severity: "minor"` |
| `severity: "trivial"` | `severity: "trivial"` |
| (none — `undefined`/`normal` also exist as enum values but the canonical format has no equivalent) | n/a |
| `priority` | **no live equivalent, and no substitute text either** — `qase_defect_upsert` rejects unknown fields, and per [SKILL.md](../references/output-formatting.md) a filed ticket never explains why a field is missing. Just don't mention priority in the defect at all. |
| `environment` | **never printed into the defect body** — no dedicated field, and per [SKILL.md](../references/output-formatting.md) it's not worth restating as free text either (same call as Jira's description template, which also excludes it). Keep it in the canonical JSON and Phase 2's conversation summary only. |
| `tags` | `tags` (plain string array, e.g. `["checkout", "payments"]`) |
| `linked_test_case` | **no live way to link a defect to a run/case/result** — the API has no such relation. Mention the ID/URL in `actual_result` text instead. |
| `evidence[]` | upload each file via `qase_attachment_upload`, collect the returned hashes, pass them all to `qase_defect_upsert`'s `attachments` array. Already visible with previews in Qase's Attachments panel — no "Evidence attached: X, Y, Z" line in `actual_result`, same rule as Jira's Attachments panel (see [jira.md](./jira.md#evidence-attachment-screenshotvideotrace)), and **never** how-to-open instructions (`npx playwright show-trace`, unzip + `show-report`). |
| Playwright HTML report / Detox per-test artifacts | same rule as [jira.md](./jira.md#full-html-report-attachment-playwright-only), including the fallback when `zip`/`unzip` is not installed (an archive `sanitize` rejects with `missingTool` is listed by path, not uploaded): zip the folder with the script's `zip` command and add its hash to `attachments` on every defect created from that run |
| `reproducibility` | per [SKILL.md's Output Formatting rule](../references/output-formatting.md) — **omit entirely** (row and text) when `"always"`; when `"intermittent"`/`"once"`, add one bare-value line inside `actual_result` (no dedicated field) |
| `regression` | **never printed into the defect body**, matching Jira (its description template has no Regression section either) — the conclusion and its reasoning live in the Phase 2 conversation summary and the Phase 4/5 chat card, not in the filed defect. |

### `actual_result` template

Fold the fields with no dedicated Qase field into one Markdown block, in this order — skip any line whose value is null/not applicable, same rule as [SKILL.md](../references/output-formatting.md):

```
**Preconditions:** <preconditions>

**Steps to reproduce:**
<numbered steps_to_reproduce>

**Expected:** <expected_result>

**Actual:** <actual_result>

<only if reproducibility is "intermittent"/"once">**Reproducibility:** <value>

**Test:** <framework> — <test_name>
File: <file>
Rerun: `<rerun_command>`

**Stack trace:**
```
<redacted stack trace, if present in evidence>
```
```

No `Environment`, `Priority`, generic `Evidence attached`, how-to-open, or explained `Regression` lines — see the field mapping table above for why each is excluded.

## Phase 5 progress announcements

- Before duplicate lookup: `⏳ Searching Qase for existing defects...`
- Before uploading evidence: `⏳ Uploading evidence to Qase...`
- Before creation: `⏳ Creating defect in Qase...`

## Success report

Do not print a per-defect report as each Qase call finishes — Phase 5 (per [SKILL.md](../SKILL.md#phase-5-publish-via-adapter)) waits until every candidate in the run has been created (or linked as a duplicate) and then prints **one consolidated block**, one [Output Formatting](../references/output-formatting.md) card per bug, each with its `Ticket` row filled in:

- Created: `✅ [<CODE>-<id>](https://app.qase.io/defect/<CODE>/view/<id>)`
- Linked as duplicate instead of filed: `🔗 Linked as duplicate of [<CODE>-<id>](https://app.qase.io/defect/<CODE>/view/<id>)`

A reviewer must be able to read the card block alone, without opening Qase, and know what got filed.

## Errors

- Schema mismatch between this file and the live MCP tool: re-inspect the live tool schema (`ToolSearch` for `qase_defect_upsert`); do not invent an argument or silently drop the field — report the discrepancy to the user.
- Defect-creation call itself fails (invalid project code, no permission, invalid field value, rate limit, network error): `❌ Failed to create the defect in Qase: <error returned by the tool>. Nothing was filed.` — then reprint the full canonical report per [SKILL.md's Error Handling](../SKILL.md#error-handling). Do not retry silently.
- No Qase server resolves: `❌ --to-qase needs a Qase MCP server. Add it to .mcp.json with a QASE_API_TOKEN, or connect the hosted Qase connector.` Nothing was filed; reprint the canonical report per [SKILL.md's Error Handling](../SKILL.md#error-handling).
- `qase_api` or any other Qase tool returns `Authentication failed... 401`: the MCP server process doesn't have `QASE_API_TOKEN` in its environment even though `.mcp.json` references it — this happens when the token was exported to `~/.zshrc`/`.env.local` *after* the host app (e.g. VS Code) was last launched, since env-var substitution in `.mcp.json` only resolves from the environment the host process itself inherited at startup. Tell the user to fully quit and relaunch the host app (from a terminal that already has the var exported, or on macOS after running `launchctl setenv QASE_API_TOKEN "$QASE_API_TOKEN"` in such a terminal, which copies the value without typing it) — reloading a window/terminal is not enough.

## References

- [Qase API — Defects](https://developers.qase.io/reference/get-defect)
