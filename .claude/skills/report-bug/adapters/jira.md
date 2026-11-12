# Jira Bug Adapter

Creates the canonical bug report as a **Bug**-type issue in Jira.

## Requirements

- An Atlassian MCP server connected — project-scoped in `.mcp.json` or the claude.ai connector. Tools below are named by operation only; resolve their prefix per [SKILL.md's MCP tool resolution](../SKILL.md#mcp-tool-resolution).
- **Optional, for real file attachments**: `JIRA_API_TOKEN` and `JIRA_EMAIL`, read from the environment first, then from a gitignored `.env.local` at the project root — never from `.env`, which is often committed (check with `git check-ignore -v .env.local`; if it isn't ignored, add `.env.local` to `.gitignore` before creating it). Without these, evidence falls back to the path-in-comment behavior below. See [Evidence attachment](#evidence-attachment-screenshotvideotrace) for exactly how these are used and why they must never be typed into the conversation.

## Flag syntax

```
--to-jira
```

No project key needed as a flag — resolve the project from `--from-ticket`'s key prefix when present. Otherwise, call `getVisibleJiraProjects` (action: `create`, filtered to projects whose issue types include `Bug`): if exactly one project is visible, use it directly without asking — asking "which project?" when there's only one answer is exactly the kind of question worth skipping; only ask the user when more than one project is visible.

## Duplicate lookup

Before creating the issue, search Jira via `searchJiraIssuesUsingJql` with a JQL query scoped to the target project and issue type Bug, matching on the sanitized keywords from [SKILL.md Phase 2](../SKILL.md#phase-2-evidence-gathering) (e.g. `project = PROJ AND issuetype = Bug AND text ~ "discount checkout"`). Show up to 5 candidates with key + summary + status + link; ask the user to proceed, link the new evidence as a comment on an existing issue instead, or abort.

Only same-platform matches count — see [SKILL.md's same-platform rule](../SKILL.md#phase-2-evidence-gathering): the JQL query is text-only, so filter its results by the `[UI]`/`[Mobile]`/`[BE]` title tag (compare `[Mobile]` only with `[Mobile]`, `[BE]` with `[BE]`, `[UI]` with `[UI]`) and drop other matches silently.

## MCP tools

| Purpose | Tool | Notes |
|---------|------|-------|
| Site | `getAccessibleAtlassianResources` | returns `id` (the `cloudId`) and `url`; one site → use it |
| Projects | `getVisibleJiraProjects` | `cloudId`, `action: "create"`, `expandIssueTypes: true`; keep projects with a `Bug` issue type |
| Duplicate lookup | `searchJiraIssuesUsingJql` | `cloudId`, `jql` |
| Create | `createJiraIssue` | `cloudId`, `projectKey`, `issueTypeName`, `summary`, `description`, `additional_fields` |
| Comment | `addCommentToJiraIssue` | `cloudId`, `issueIdOrKey`, `commentBody` |
| Link | `createIssueLink` | only when `linked_ticket` is set |

If a live schema differs from this table, re-inspect the live tool schema (`ToolSearch` for the tool name) and follow it; do not invent an argument or silently drop a field — report the discrepancy.

- `createJiraIssue` with `issueTypeName: "Bug"`. Capture the returned issue key AND its URL for the success report below — the tool response's `webUrl` is the browsable link; use it as-is rather than constructing one.
- If `linked_ticket` is set, link the created bug to it via `createIssueLink` (relationship: "relates to" / "is caused by" — pick "is caused by" pointing from the parent ticket to the bug when the bug was discovered while working the parent ticket; use "relates to" otherwise).

## Field mapping (canonical → Jira Bug)

| Canonical | Jira field |
|-----------|------------|
| `title` | `summary` |
| `preconditions` + `steps_to_reproduce` + `expected_result` + `actual_result` + `test_reference` | `description` (formatted markdown, see template below) |
| `severity` | `additional_fields.labels: ["severity-<value>"]` unless the project has a dedicated Severity custom field, in which case set that field directly |
| `priority: "urgent"` | `additional_fields.priority.name: "Highest"` |
| `priority: "high"` | `additional_fields.priority.name: "High"` |
| `priority: "medium"` | `additional_fields.priority.name: "Medium"` |
| `priority: "low"` | `additional_fields.priority.name: "Low"` |
| `tags` | `additional_fields.labels` (merged with the severity label above) |
| `evidence[]` | **Text** (`stack_trace`, `log`, textual `test_report`) — see [Error log comment](#error-log-comment) below: mandatory on every ticket, Playwright, Detox, or unit-test alike. <br>• **`screenshot`/`video`/`trace`** (binary) — see [Evidence attachment](#evidence-attachment-screenshotvideotrace) below: attach for real via the REST API when credentials are available, else fall back to a path-in-comment. |

### Error log comment

Every ticket this adapter creates gets a comment with the actual error text — the `redact` output from [SKILL.md Phase 4](../SKILL.md#phase-4-generate-the-canonical-bug-report), never the raw text — pasted in a fenced code block — this step is never optional and never satisfied by the binary attachments alone (screenshot/trace/HTML report). A reviewer must be able to read the failure on the ticket itself without downloading and unzipping a trace first.

- **Playwright**: `error.message` + `error.stack` from the JSON report (same text already captured as the `stack_trace` evidence entry in [Phase 1](../references/report-extraction.md)).
- **Vitest/Jest/Detox**: the joined `failureMessages[]` for that test (there is no `error.stack` field for this shape — the joined message text is the whole of the available evidence). Detox's `failureMessages[]` text is an Espresso/EarlGrey assertion dump rather than a JS stack trace, but it's pasted the same way.
- **WebdriverIO/Appium**: the failing test's `error` followed by its `standardError` (the stack).
- **JUnit XML**: the `<failure>`/`<error>` element's `message` followed by its text.
- **`--from-text`/`--from-ticket`**: skip this comment — there is no captured error log to paste (`test_reference.framework` is `null`).

Post it via `addCommentToJiraIssue` right after creating the issue, as its own comment (or combined with the binary-evidence comment below, as long as the actual text appears in a fenced code block rather than just a filename/path):

```markdown
**Error log (<framework> stack trace):**
​```
<error.message + error.stack, or the joined failureMessages[]>
​```
```

This applies regardless of whether credentials are configured for binary attachments (see below) — unit-test failures in particular have no screenshot/trace/HTML report to attach at all, but they still have failure text that must be pasted here.

### Full HTML report attachment (Playwright only)

Whenever `test_reference.framework` is `Playwright` and an HTML report exists for the run, always attach the **whole report**, zipped, to every Jira issue created from that run — not just the per-test screenshot/trace. `index.html` alone is not self-contained (it loads per-test artifacts from a sibling `data/` folder by content hash), so it must travel as a directory, not a single file. The report is `<run>/playwright-report/` for `--run`; otherwise the `html` reporter's output folder (the project's `playwright.config.ts` reporters list, default `playwright-report/`), and only when its `index.html` is no older than the run's start (`stats.startTime` in the loaded JSON report) — an older one is from another run:

Zip it with the `zip` command of [SKILL.md's evidence script](../SKILL.md#evidence-files) (`out`: `.claude-temp/report-bug/playwright-report.zip`), then upload the zip via the same REST API attachment call as any other binary evidence (see below), to **every** issue being created from that run (one zip, attached N times — once per issue — for an N-candidate `--from-run` batch, not just the first). No comment about it.

Skip this (don't fabricate a report or a zip) when no report qualifies — e.g. the project's `playwright.config.ts` doesn't configure the `html` reporter, its report predates the run, or the candidate came from `--from-failure` against a report shape without one. This only applies to `test_reference.framework: "Playwright"`; Vitest/Jest candidates have no HTML report to attach. A **Detox** candidate has no equivalent single-report bundle either, but if its Detox config configures the `artifacts` plugin and a per-test `<rootDir>/<run-id>/<test-name>/` directory exists (`<rootDir>`: the config's `artifacts.rootDir`, default `./artifacts` beside the config) (see [Phase 1](../references/report-extraction.md)), zip and attach *that* directory the same way — one zip per failing test, not the whole run — since Detox scopes artifacts per test rather than per run. If `zip` exits with `zip is not installed…`, attach nothing for this step and follow [SKILL.md → No `zip`/`unzip`](../SKILL.md#evidence-files).

### Evidence attachment (screenshot/video/trace)

No tool in the live Atlassian MCP tool list uploads attachments (search that list for "attachment"/"upload" before relying on this, and use such a tool instead once one exists). Binary evidence has two paths depending on whether `JIRA_API_TOKEN`/`JIRA_EMAIL` are available (see [Requirements](#requirements)):

**With credentials (real attachment, preferred):** run the `jira-attach` command of [SKILL.md's evidence script](../SKILL.md#evidence-files) with `site` (the host of the resource `url`, e.g. `acme.atlassian.net`), `issue` (the created key) and, as `files`, the `upload` path of every evidence file for that issue from the script's `sanitize` command — never the originals. It uploads to `/rest/api/3/issue/<KEY>/attachments`, reads `JIRA_EMAIL`/`JIRA_API_TOKEN` itself and passes them to `curl` on stdin — never type, `source`, export or print them. The bytes go straight from disk to Jira, never through the model's context. Native attachments are Jira Cloud only (`*.atlassian.net`). Any non-zero exit — no credentials (3), a self-hosted Server/Data Center site or invalid input (2), an unexpected failure (1) — means no native upload: use the fallback below. A file with `ok: false` in the output falls back the same way; retry only those files.

`ok: true` means the file shows up natively in Jira's Attachments panel with a thumbnail, viewable directly without any extra comment. **Never add a comment about attachments** — neither describing them ("screenshot X shows Y") nor how to open them (`npx playwright show-trace`, unzip + `show-report`). The Attachments panel already shows them; the only comment this adapter posts is the [error log](#error-log-comment).

**Don't attach redundant duplicates.** If more than one screenshot would show the same on-screen state (e.g. Detox's `takeWhen.testDone` snapshot next to its automatic `testFnFailure.png` — identical when the failing assertion is the test's last line), attach only the one that best represents the failure moment (`testFnFailure.png`) and skip the rest. One clear screenshot beats two identical ones.

**Without credentials (fallback, path-in-comment):** state the limitation explicitly and run `sanitize` anyway and list each file's `upload` path (never the original) in a comment so the user can drag-and-drop it into the ticket; do not silently omit it and do not claim it's attached.

**Never do this instead:** do not try to read a binary evidence file into the model's own context (e.g. base64-encoding it to pass as a parameter to some other MCP tool, such as a Google Drive upload tool). Base64 of binary data tokenizes far worse than its byte count (a 22KB slice of a trace costs ~200k tokens), so it is a dead end at any size. The REST API path above is the only sound way to move a binary evidence file into a tool — the bytes never enter the model's context at all.

### Description template

```markdown
## Preconditions
<preconditions>

## Steps to Reproduce
1. ...

## Expected Result
<expected_result>

## Actual Result
<actual_result>

## Failing Test
- Framework: <test_reference.framework>
- Test: <test_reference.test_name> (<test_reference.file>)
- Run it locally: `<test_reference.rerun_command>`
```
Omit the whole `## Failing Test` section when `test_reference.framework` is `null` (a `--from-text`/`--from-ticket` candidate has no runnable test to point at) — don't print a section full of `null`s.

**Drop any field line whose value is `null`/not applicable instead of printing it** — "N/A" or "null" tells the reader nothing they didn't already know, omission does. `environment` is deliberately not in the description template at all (see below) — this rule is about the remaining template fields (e.g. an empty `preconditions` on a `--from-text` candidate).

**`environment` (app version/OS/browser/env/service) is never printed into the filed ticket body.** It's low-signal for a fixed local dev/practice setup and, when it does matter (staging vs. prod, a specific browser), that's exactly the kind of thing worth a real Jira field/label rather than free text nobody reads. Keep it in the canonical JSON and Phase 2's conversation summary only.

**Don't append a meta-explanation of *why* a field is missing into the filed ticket.** If `regression.is_regression` couldn't be determined (e.g. a brand-new project with no git history to replay against), just don't mention regression at all — do not write "(regression: null — this app has no git history yet)" into the ticket body. That reasoning belongs in the conversation's evidence-gathering summary (Phase 2), which the reporter already saw before filing; a developer reading the ticket later doesn't need the report-bug run's own bookkeeping explained back to them.

**`## Reproducibility` follows the general rule in [SKILL.md's Output Formatting](../references/output-formatting.md)** — omit the section entirely when `reproducibility` is `"always"`; only include it (bare value) for `"intermittent"`/`"once"`.

## Phase 5 progress announcements

- Before duplicate lookup: `⏳ Searching Jira for existing bug reports...`
- Before creation: `⏳ Creating Jira Bug issue...`
- Before the error log comment (mandatory whenever `test_reference.framework` is non-null): `⏳ Adding error log comment...`
- Before each binary upload (only with credentials, one per file): `⏳ Attaching <filename>...`
- Before the path-in-comment fallback (only without credentials): `⏳ Adding evidence comment...`

## Success report

Do not print a per-issue report as each Jira call finishes — Phase 5 (per [SKILL.md](../SKILL.md#phase-5-publish-via-adapter)) waits until every candidate in the run has been created (or linked as a duplicate) and then prints **one consolidated block**, one [Output Formatting](../references/output-formatting.md) card per bug, each with its `Ticket` row filled in:

- Created: `✅ [<KEY>](<URL>)`
- Linked as duplicate instead of filed: `🔗 Linked as duplicate of [<KEY>](<URL>)`

Directly under a card's table, add at most one extra short line for evidence status when it's not the trivial case — do not repeat the description/expected/actual, the card already has them:
- `📎 Evidence: <N> file(s) attached natively` (credentials path — real Jira attachments, uploaded via the REST API)
- `⚠️ Screenshots/video/trace pending manual attach — paths in the comment` (fallback path, no credentials — see [Evidence attachment](#evidence-attachment-screenshotvideotrace))
- `📎 Full Playwright report attached (playwright-report.zip)` when [Full HTML report attachment](#full-html-report-attachment-playwright-only) applied — omit entirely for a non-Playwright candidate or when no HTML report qualified
- `📎 Detox artifacts attached (<test-name>.zip)` when the Detox artifacts-folder fallback described in that same section applied — omit when the candidate isn't Detox or no `artifacts` plugin was configured for the run
- `📝 Error log posted as a comment` when [Error log comment](#error-log-comment) applied — omit only for a `--from-text`/`--from-ticket` candidate with no captured error text

A reviewer must be able to read the card block alone, without opening Jira, and know what got filed.

## Errors

- Project key unresolvable: `❌ --to-jira needs a target project. Pass --from-ticket <KEY> or specify the project when prompted.`
- `getVisibleJiraProjects` (or any Jira call) returns `403 Forbidden` while `getAccessibleAtlassianResources` lists the site: the connected Atlassian server has no Jira access (e.g. a connector granted Confluence scopes only). `❌ The connected Atlassian MCP can't reach Jira on <site> (403). Grant the connector Jira access, or authenticate the project-scoped server: /mcp → atlassian → Authenticate. Nothing was filed.` — the other destinations still publish.
- `createJiraIssue` call itself fails (invalid project key, no permission to create issues, field validation rejected by the Jira project's screen config, rate limit, network error): `❌ Failed to create the bug in Jira: <error returned by the tool>. Nothing was filed.` — then reprint the full canonical report per [SKILL.md's Error Handling](../SKILL.md#error-handling). Do not retry silently; do not fall back to a different project without asking.
- Evidence comment or attachment upload fails after the issue was created successfully: this is NOT a filing failure — the bug ticket exists. Report `⚠️  Bug <KEY> created, but <the evidence comment|attaching <filename>> failed: <error>. Evidence paths: <sanitized upload paths>` and still show the success report with the ticket link; do not roll back the created issue. A failed attachment upload falls back to the path-in-comment behavior for that file rather than silently dropping it.

## References

- [Atlassian REST — Create issue](https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issues/#api-rest-api-3-issue-post)
