# Linear Adapter

Creates the canonical bug report as an **issue** in Linear, labeled `Bug`.

## Requirements

- The Linear MCP server (`https://mcp.linear.app/mcp`), connected either project-scoped — the same server `/fetch-ticket-context --provider linear` and `/create-sdd-ticket --save-to-linear` use:
  ```bash
  claude mcp add --transport http --scope project linear https://mcp.linear.app/mcp
  ```
  — or through the claude.ai Linear connector or a plugin. Tools below are named by operation only; resolve their prefix per [SKILL.md's MCP tool resolution](../SKILL.md#mcp-tool-resolution). Auth is OAuth, not a token — for the project-scoped server run `/mcp` → `linear` → **Authenticate** once in an interactive session. If no server resolves, or it is disconnected or unauthorized, stop with a setup error (see [Errors](#errors)); never fall back to the GraphQL API for issue creation.
- No API key needed — file uploads also go through the MCP server (see [Evidence attachment](#evidence-attachment-screenshotvideotrace)).

## Flag syntax

```
--to-linear [TEAM-KEY | https://linear.app/<workspace>/team/<KEY>/... | https://linear.app/<workspace>/project/<slug>]
```

- **Team key** (e.g. `ENG`) or **team URL** → create in that team, no project.
- **Project URL** → resolve the project first, then its team; stop if the project maps to zero or several teams without a clear pick (show the candidates).
- **Omitted** → list the teams visible to the authenticated user: exactly one → use it without asking; more than one → ask which team.

Reject non-`linear.app` URLs and issue URLs used as a destination — a destination is a team or a project, never an existing issue.

## MCP tools

| Purpose | Tool | Notes |
|---------|------|-------|
| List teams | `list_teams` | `query` filter; returns `id` + `name` (key comes from `get_user("me").teams[].key`) |
| Search issues (dup lookup) | `list_issues` | `team`, `query`, `label: "Bug"`, `includeArchived`; `state` accepts a type or name |
| List labels | `list_issue_labels` | `team`, `name` filter |
| Create label | `save_issue_label` | `name`, `color`, `teamId` (omit for a workspace label) |
| Create issue | `save_issue` | create = no `id`; `team` (name/ID) + `title` required; `labels` takes **names or IDs**; `priority` is a **number**; `relatedTo` for relations; `links` for URL attachments |
| Comment | `save_comment` | `issueId` (an identifier like `ENG-1` works) + `body` (Markdown, literal newlines — no `\n` escapes) |
| Upload file | `prepare_attachment_upload` → `PUT` → `create_attachment_from_upload` | see [Evidence attachment](#evidence-attachment-screenshotvideotrace) |

`create_attachment` (base64) is deprecated by the server itself — never use it. If a future server version renames or reshapes any of these, follow the live schema, report the discrepancy, and update this table; don't invent an argument or silently drop a field.

## Duplicate lookup

Before creating the issue, search the target team's issues with the MCP issue-list tool, using the sanitized keywords from [SKILL.md Phase 2](../SKILL.md#phase-2-evidence-gathering) as the query and filtering to the `Bug` label when the tool supports label filters. Include closed issues (a reopened bug is a stronger signal than a new one). Show up to 5 candidates with identifier + title + status + link; ask the user to proceed, link the new evidence as a comment on an existing issue instead, or abort.

Only same-platform matches count — see [SKILL.md's same-platform rule](../SKILL.md#phase-2-evidence-gathering): compare `[Mobile]` only with `[Mobile]`, `[BE]` with `[BE]`, `[UI]` with `[UI]`, and drop other matches silently.

## MCP calls, in order

1. **Resolve the team** (and project, if given) with `list_teams` / `get_user("me")` → keep its ID.
2. **Resolve labels** with `list_issue_labels` in that team/workspace: `Bug` and `severity-<value>`. If either is missing, create it with `save_issue_label` (announce `⏳ Creating label <name>...` — a one-time side effect per workspace, not per bug). Tag labels from `tags` are applied **only if they already exist** — do not create a new workspace label for every tag; mention any skipped tag once in the success report line.
3. **Create the issue** with `save_issue`: `team`, `labels` (names or IDs), `priority`, `title`, `description` (and project ID when targeting a project). Leave `state` unset so Linear puts it in the team's default intake state (Triage/Backlog). Capture the returned identifier (e.g. `ENG-123`) **and** its `url` — use the returned URL as-is, don't construct one.
4. **Error log comment** — mandatory, see [below](#error-log-comment).
5. **Binary evidence** — upload + comment, see [Evidence attachment](#evidence-attachment-screenshotvideotrace).
6. **`linked_ticket`**: if it's a Linear identifier, pass it in `save_issue`'s `relatedTo`; if it's a Jira key, put one `Related: <KEY or URL>` line at the end of the description — that's actionable context, not bookkeeping.

## Field mapping (canonical → Linear issue)

| Canonical | Linear field |
|-----------|--------------|
| `title` | `title` |
| `preconditions` + `steps_to_reproduce` + `expected_result` + `actual_result` + `test_reference` | `description` (native Markdown — same template as [jira.md](./jira.md#description-template)) |
| `severity` | label `severity-<value>` (Linear has no severity field) |
| `priority: "urgent"` | `priority: 1` |
| `priority: "high"` | `priority: 2` |
| `priority: "medium"` | `priority: 3` |
| `priority: "low"` | `priority: 4` |
| — | label `Bug` (always) |
| `tags` | existing labels only, merged with the two above |
| `environment` | **never printed into the issue** — same rule as [jira.md](./jira.md#description-template) |
| `regression` | **never printed into the issue** — same rule as Jira and Qase |
| `reproducibility` | omit when `"always"`; for `"intermittent"`/`"once"` add a `## Reproducibility` section with the bare value, per [SKILL.md](../references/output-formatting.md) |
| `linked_ticket` | relation or `Related:` line, see step 6 above |
| `evidence[]` | text → [error log comment](#error-log-comment); binary → [evidence attachment](#evidence-attachment-screenshotvideotrace) |

Linear's priority enum is `0` = No priority, `1` = Urgent, `2` = High, `3` = Medium, `4` = Low. Verified live: `save_issue.priority` takes the number.

All the ticket-content rules in [jira.md's Description template](./jira.md#description-template) apply unchanged: no null/N-A lines, no meta-explanations of missing fields, no `Environment` section, and none of the Phase 4 callouts (`💡`/`⚠️`).

### Error log comment

Identical to [jira.md](./jira.md#error-log-comment): every issue created from a runnable failure gets a comment with the redacted error text in a fenced code block (Playwright `error.message` + `error.stack`; Vitest/Jest/Detox joined `failureMessages[]`; WebdriverIO/Appium `error` + `standardError`; JUnit XML `<failure>`/`<error>` message + text). Skipped only for `--from-text`/`--from-ticket` (no captured error). Post it with `save_comment` right after creating the issue.

### Evidence attachment (screenshot/video/trace)

The Linear MCP server uploads files natively via a signed URL, so the bytes go straight from disk and never enter the model's context. Run `sanitize` from [SKILL.md's evidence script](../SKILL.md#evidence-files) once for all files first (it returns each file's `upload` path, `size` and `contentType`; always upload `upload`), then **one file at a time** — prepare, PUT, finalize, then the next file (signed URLs expire after 60 seconds):

1. `prepare_attachment_upload` with `issue`, `filename`, `contentType`, and `size` from `sanitize`.
2. Run the script's `put` command with `file` = that entry's `upload`, `url` = `uploadRequest.url` and `headers` = `uploadRequest.headers` copied verbatim (casing included — any change is a 403).
3. On `ok: true`, `create_attachment_from_upload` with `issue` + the returned `assetUrl` (+ `title`). This makes the file show under the issue's attachments.

Then post **one** evidence comment with `save_comment` that embeds the assets: screenshots inline (`![testFnFailure.png](<assetUrl>)`, which Linear renders as an image), other files as links (`[trace.zip](<assetUrl>)`). Nothing else: no "screenshot X shows Y" narration and **never** how-to-open instructions (`npx playwright show-trace`, unzip + `show-report`).

**Full Playwright HTML report / Detox artifacts:** same rule as [jira.md](./jira.md#full-html-report-attachment-playwright-only), including the fallback when `zip`/`unzip` is not installed (an archive `sanitize` rejects with `missingTool` is listed by path, not uploaded): zip the HTML report jira.md picks (Playwright) or the per-test artifacts folder jira.md names (Detox) with the script's `zip` command and upload the zip to **every** issue created from that run, linked in the evidence comment.

**Don't attach redundant duplicates.** Pick the one screenshot that best shows the failure (e.g. Detox's `testFnFailure.png`), same as Jira.

**If an upload fails** (403, expired URL after one fresh retry, or MCP error): say so explicitly and list each failed file's `upload` path from `sanitize` (never the original) in the evidence comment so the user can drag-and-drop the files into the issue. Don't omit them and don't claim they're attached.

**Never** read or base64-encode a binary file into the model's context to pass it to a tool — that's why the deprecated `create_attachment` is off-limits. See [jira.md](./jira.md#evidence-attachment-screenshotvideotrace) for why.

## Phase 5 progress announcements

- Before duplicate lookup: `⏳ Searching Linear for existing bug reports...`
- Before creating a missing label (one-time): `⏳ Creating label <name>...`
- Before creation: `⏳ Creating Linear issue...`
- Before the error log comment: `⏳ Adding error log comment...`
- Before each binary upload: `⏳ Uploading <filename>...`
- Before the evidence comment: `⏳ Adding evidence comment...`

## Success report

Same consolidated-block rule as [jira.md](./jira.md#success-report): one [Output Formatting](../references/output-formatting.md) card per bug once every candidate is done, with the `Ticket` row set to:

- Created: `✅ [<ID>](<URL>)`, e.g. `✅ [ENG-123](https://linear.app/<workspace>/issue/ENG-123/...)`
- Linked as duplicate instead of filed: `🔗 Linked as duplicate of [<ID>](<URL>)`

Optional short lines under the table, only when they apply:
- `📎 Evidence: <N> file(s) uploaded`
- `⚠️ Screenshots/video/trace pending manual attach — paths in the comment` (upload failed)
- `📎 Full Playwright report attached (playwright-report.zip)` / `📎 Detox artifacts attached (<test-name>.zip)`
- `📝 Error log posted as a comment`
- `🏷️ Skipped non-existent labels: <tags>` (tags that had no matching workspace label)

## Errors

- No Linear server resolves, or it is disconnected or unauthorized: `❌ --to-linear needs the Linear MCP server. Connect the claude.ai Linear connector, or run: claude mcp add --transport http --scope project linear https://mcp.linear.app/mcp — then /mcp → linear → Authenticate.` Nothing was filed; reprint the canonical report per [SKILL.md's Error Handling](../SKILL.md#error-handling).
- Team or project unresolvable or ambiguous: show the resolved candidates and stop. `❌ Could not resolve Linear team/project "<input>". Nothing was filed.`
- Issue-creation call itself fails (no permission, invalid label/team ID, validation error, rate limit, network error): `❌ Failed to create the bug in Linear: <error returned by the tool>. Nothing was filed.` Then reprint the full canonical report. Do not retry silently; do not switch team without asking.
- `502 upstream_unavailable` on a write (`save_comment`, `save_issue`): the write may have landed anyway. Check first (`list_comments` / `list_issues`) and retry only if it's really missing, or you'll post a duplicate.
- Schema mismatch with this file: re-inspect the live tool schema; do not invent an argument or switch transport. Report the discrepancy.
- Comment, label, or upload fails **after** the issue was created: not a filing failure. Report `⚠️  Bug <ID> created, but <step> failed: <error>. Evidence paths: <sanitized upload paths>`, still show the success card, never roll back the issue. A failed upload falls back to path-in-comment for that file.

## References

- [Linear MCP server](https://linear.app/docs/mcp)
- [Linear — Priority](https://linear.app/docs/priority)
