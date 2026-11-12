---
name: generate-test-cases
version: 1.2.3
last-updated: 2026-09-16
description: Generate structured, tool-agnostic test cases from a Jira ticket, free-form text, or markdown spec, and publish them to a test management tool (Qase, Jira subtasks, TestRail, Xray, or a markdown file). Distinct from requirement-coverage-gap-analysis, which checks whether an existing suite already covers a ticket's acceptance criteria instead of writing new cases. Use when asked to "create test cases", "generate QA cases", "write test cases for TICKET-123", or "crear casos de prueba" — but not "are we missing test cases for TICKET-123" or "what acceptance criteria have no test", which is a coverage-gap question, not a generation request.
argument-hint: '--from-jira <KEY> | --from-text "<text>" | --from-markdown <path>  [--to-qase [CODE] | --to-jira | --to-testrail [ID] | --to-xray | --to-markdown <path>]  [--format classic|gherkin] [--suite-id <ID>]  |  --from-* --format e2e-flow  (e2e-flow cannot be combined with --to-* flags)'
allowed-tools: Read, Write, Bash, Glob, Grep, Edit, Skill
---

# Generate Test Cases Skill

Turns a ticket, feature description, or markdown document into structured, ready-to-execute test cases and publishes them to any supported test management tool via output adapters.

## Contents

- [Purpose](#purpose)
- [When to Use vs Other Skills](#when-to-use-vs-other-skills)
- [Prerequisites](#prerequisites)
- [Input Modes](#input-modes)
- [Output Adapters](#output-adapters)
- [Workflow](#workflow)
- [Canonical Test Case Format](#canonical-test-case-format)
- [Quality Checks](#quality-checks)
- [Adding a New Output Adapter](#adding-a-new-output-adapter)
- [Error Handling](#error-handling)
- [Best Practices](#best-practices)
- [References](#references)

---

## Purpose

Automates the conversion of acceptance criteria and feature descriptions into well-structured test cases:

1. **Fetches the source** — pulls a Jira ticket, reads a markdown file, or accepts free-form text
2. **Analyzes the content** — extracts testable scenarios from descriptions, ACs, edge cases, and service boundaries
3. **Generates canonical test cases** — produces tool-agnostic cases with title, preconditions, steps, postconditions, priority, type, tags
4. **Publishes via an output adapter** — each `--to-*` flag selects an adapter that maps the canonical format to the target tool's API

**Principle**: Every test case must be independently executable. A tester reading only the test case (without the original ticket) should be able to run it. Generation is fully decoupled from the output tool.

---

## When to Use vs Other Skills

| Use case | Skill |
|----------|-------|
| Structured test cases from a ticket, spec, or description | `/generate-test-cases` |
| OWASP security test cases against a running app | `/owasp-security-testing` |
| WCAG accessibility compliance tests | `/accessibility-testing` |
| Load, stress, and soak performance tests | `/performance-testing` |
| API schema conformance and breaking change detection | `/api-contract-testing` |
| E2E user flow automation in Playwright | `/playwright-e2e-automation` |
| Which acceptance criteria already have a test vs. which don't (existing suite) | `/requirement-coverage-gap-analysis` |
| Is the data in these generated cases safe to commit (no PII, factories over literals) | `/test-data-strategy` |

---

## Prerequisites

**Common**: Claude Code with MCP support, plus at least one input source:
- **Atlassian MCP** (`mcp__claude_ai_Atlassian__*`) for `--from-jira`
- A local markdown file for `--from-markdown`
- Free-form text inline for `--from-text`

**Adapter-specific**: each adapter has its own MCPs/plugins/permissions — see the corresponding file under `adapters/`, loaded only when its `--to-*` flag is used.

**Optional**: existing suite passed via `--suite-id <ID>`; project conventions documented in `.claude/CLAUDE.md` (used to ground preconditions — service names, env vars, session cookie name, etc.).

---

## Input Modes

### `--from-jira <TICKET-KEY>`
Fetch the ticket and extract testable scenarios from description, ACs, and embedded checklists. Uses `mcp__claude_ai_Atlassian__getJiraIssue` with `responseContentFormat: markdown`.
```bash
/generate-test-cases --from-jira PROJ-123 --to-qase MYPROJ
```

### `--from-text "<description>"`
Accept free-form text and infer test cases.
```bash
/generate-test-cases --from-text "Users can add products to a wishlist and remove them" --to-qase MYPROJ
```

### `--from-markdown <PATH>`
Read a local markdown file (SDD ticket, spec document, etc.).
```bash
/generate-test-cases --from-markdown ./specs/PROJ-123.md --to-qase MYPROJ
```

---

## Output Adapters

Each `--to-*` flag selects an adapter that translates the canonical test case format into the target tool's payload. Generation is shared — only the adapter changes.

**Adapter details live in separate files under `adapters/` and are loaded on-demand.** Phase 4 reads only the file for the selected `--to-*` flag.

| Flag | Adapter file | Description |
|------|-------------|-------------|
| `--to-qase [CODE]` | [`adapters/qase.md`](./adapters/qase.md) | Publishes to Qase via MCP (suite + bulk-create). |
| `--to-jira` | [`adapters/jira.md`](./adapters/jira.md) | Creates one Jira Subtask per case under the source ticket. Requires `--from-jira`. |
| `--to-testrail [ID]` | [`adapters/testrail.md`](./adapters/testrail.md) | Publishes to TestRail (MCP) or falls back to CSV-importable markdown. |
| `--to-xray` | [`adapters/xray.md`](./adapters/xray.md) | Creates Xray Test issues in Jira (Xray plugin required). |
| `--to-markdown <path>` | [`adapters/markdown.md`](./adapters/markdown.md) | Writes all cases to a local markdown file. No MCP needed. |

**Display only** (no `--to-*` flag): prints a formatted summary in the conversation. Useful for review before publishing. No adapter file is loaded.

---

## Workflow

### Phase 0: Parse Arguments

Parse all arguments before doing anything else. Print usage if required arguments are missing.

```
Usage: /generate-test-cases
         --from-jira <KEY> | --from-text "<text>" | --from-markdown <path>
         [--to-qase [CODE]] | [--to-jira] | [--to-testrail [ID]] | [--to-xray] | [--to-markdown <path>]
         [--format classic|gherkin]
         [--suite-id <ID>]

       /generate-test-cases
         --from-* --format e2e-flow
         (--format e2e-flow cannot be combined with any --to-* flag)
```

**Guard**: if `--format e2e-flow` is present alongside any `--to-*` flag, stop immediately and print:

> `--format e2e-flow` is incompatible with output adapters (`--to-*`). E2E flow output uses a different schema (`journey_steps`, `shared_state`, `negative_branches`) that cannot be mapped to the canonical test case format adapters expect. Run without `--to-*` to display the flow in the conversation, then pass it to `/playwright-e2e-automation` for automated test generation.

### Phase 1: Load Source Content

**`--from-jira`**: call `mcp__claude_ai_Atlassian__getJiraIssue` and extract summary, description, checklist items (`- [ ] ...`), labels, issue type. Each checklist item is a test case candidate; labels/type feed tags.

Announce what was loaded:
```
✓ Loaded: PROJ-124 — Feature name
  Source: Jira (WorkItemType)
  Labels: ...
  Output adapter: Qase → project MYPROJ
```

### Phase 1.5: Ambiguity Gate

Before generating anything, check whether the source is actually testable as written. Do not proceed to Phase 3 on a guess when the ticket itself doesn't say — ask.

Flag a point as ambiguous when it would change a generated case's expected result, priority, or whether a case exists at all:
- A checklist item or AC contradicts the description, or contradicts another checklist item.
- A boundary-value or equivalence-class field (Phase 3b) has no stated limit ("large file" with no size, "invalid input" with no format).
- A decision-table rule (Phase 3b) has an undefined branch — the rule states 2 of 3 conditions' outcomes.
- A state transition's legality is unstated (can a `cancelled` order be reopened? the ticket never says).
- The description/ACs contain placeholder language (`TBD`, `TODO`, `???`, "tbc").
- **No checklist items and no extractable acceptance criteria at all** — never fall back to generating cases from the prose description alone; treat the absence itself as an ambiguity and route it through `/clarify-requirement`.

**With `--from-jira`**, call with `--ticket`:
```
/clarify-requirement --question "<the ambiguity, phrased for a one-line answer>" \
  --context "<which generated case(s) or coverage area this changes>" \
  --ticket <KEY> [--options "<a>|<b>"] [--recommended "<a>"] \
  --dedup-key "<a stable id for this checklist item/AC — see /clarify-requirement's --dedup-key>" \
  --artifacts-dir ".claude-temp/tickets/<KEY>/artifacts"
```
`--dedup-key` matters here because `--question` is phrased fresh by this skill each run; without a stable key, a reworded question on the next run misses the dedup check entirely and posts a duplicate Jira comment. `--artifacts-dir` matters for the same reason: without it `/clarify-requirement` has nowhere to persist a settled or pending answer, so a rerun against the same ticket re-asks or re-posts even when nothing changed.

**With `--from-text` or `--from-markdown`** there is no ticket to check comments on or post a question to, so omit `--ticket` entirely — do not invent one:
```
/clarify-requirement --question "<the ambiguity, phrased for a one-line answer>" \
  --context "<which generated case(s) or coverage area this changes>" \
  [--options "<a>|<b>"] --recommended "<a>"
```
Without `--ticket`, `/clarify-requirement` can only resolve interactively (MCP tool or `AskUserQuestion`) or fall back to `--recommended`; it never returns a "pending" state, because there is nothing to post to and nothing to check on a rerun. Always pass `--recommended` here — an unresolved, non-blocking, no-ticket call is a caller error (see that skill's Phase 3, the `--ticket` not set branch), and this input mode has no other way to make forward progress non-interactively.

Mark `--blocking` only when guessing wrong would produce a case asserting the *opposite* of correct behavior (e.g., a state-transition legality question) rather than merely a missing edge case.

**Marking assumed output** — never write a punctuation-bearing note like `(assumed — see PROJ-124 comment)` into `tags`: `tags` maps straight to Jira labels (`adapters/jira.md`) and Xray labels (`adapters/xray.md`), both of which reject whitespace and parentheses/em-dashes and will either fail the API call or silently strip the marker. This applies only to a case built from an assumed answer, per `/clarify-requirement`'s source classification — a resolved answer gets no assumed marker at all:
- Add a label-safe tag: `assumed-pending-<KEY>` for `headless-posted-pending`, or `assumed` for `headless-assumed`. No spaces, no punctuation beyond `-`.
- Append a human-readable line to that case's `postconditions`:
  - `headless-posted-pending`: `Assumed answer pending confirmation on <KEY> (comment #<posted_comment_id>): "<question>" → "<answer used>".`
  - `headless-assumed`: `Assumed answer (no ticket comment posted): "<question>" → "<answer used>".` — nothing is pending, and either there's no ticket or Atlassian MCP was unreachable, so never claim a comment exists to confirm on.

A blocking ambiguity with no resolution yet (ticket case: `headless-posted-pending` with no `--recommended` fallback used; no-ticket case: unresolved): skip only the dependent case(s), note them under a `## Pending Clarification` line in the Phase 4 report — `Pending on <KEY> (comment #<id>): <question>` when a ticket exists, or `Skipped — no ticket to ask against; rerun interactively or with --recommended: <question>` when it doesn't — and generate everything else. Never abort the whole batch over one unresolved point.

Do not flag routine gaps a QA engineer fills without a second thought (implied error-toast wording, obvious field labels) — see `/clarify-requirement`'s "When to call this" for the line.

Announce: `⏳ Checking for ambiguous or underspecified requirements...` before this phase, and after: `✓ No ambiguities found`, or `✓ Resolved N ambiguities (M from ticket comments, K asked, J pending on <KEY>)` for `--from-jira`, or `✓ Resolved N ambiguities (K asked, J using --recommended)` for `--from-text`/`--from-markdown`.

### Phase 2: Confirm Format

Resolves the format contract (title convention, fields, priority/type scales, step style). Persisted per project in `generate-test-cases.json` at the project root.

- **Config file present** → read it, print a one-line summary (`Style:` + truncated `Customizations:`), forward to Phase 3. Do NOT ask.
- **Config file missing** → load [`references/format-config.md`](./references/format-config.md) and follow its first-run flow (default preview, ask user, persist).

For full details (schema, returning vs first-run, temporary overrides) see [`references/format-config.md`](./references/format-config.md).

### Phase 3: Generate Test Cases

No user interaction, but announce every sub-step. Generate in **canonical format** (see below) with Phase 2 customizations applied — never tool-specific.

**Progress announcements:**
- Before 3a: `⏳ Analyzing ticket to identify test areas...`
- Before 3b: `⏳ Applying QA design techniques (BVA, equivalence partitioning, negatives...)`
- Before 3c: `⏳ Organizing test cases into logical groups...`
- Before 3d: `⏳ Writing test cases in canonical format...`
- Before 3e: `⏳ Verifying coverage checklist...`
- After 3e: `✓ Generated test cases across logical areas` — **do not include specific numbers until Phase 4 completes**.

#### 3a. Identify test areas

Scan the source for:
- **Explicit checklist items** (`- [ ] ...`) — each is a candidate
- **Acceptance criteria** — convert each into one or more cases
- **Edge cases** — empty, zero, max, concurrent
- **Error scenarios** — failed service calls, invalid input, timeouts
- **Integration points** — each external service call is a boundary
- **Persistence** — "persists between sessions" needs its own case
- **UI feedback** — badges, loading states, success/empty messages

#### 3b. Apply test design techniques

Deliberately apply the techniques below to avoid happy-path-only batches. The first four apply to almost every ticket; the rest fire only when their trigger condition holds.

**Always apply:**

- **Equivalence partitioning** — for each input field with a range/enumeration/category, group values into classes and test one representative per class. Example: an `age` field `0-12 free / 13-17 half / 18-64 full / 65+ senior` yields 4 cases, not one per integer.
- **Boundary value analysis (BVA)** — for each numeric/length-bounded field, test exact boundaries AND just outside. A "password 8-64 chars" rule yields at minimum: 7 (reject), 8 (accept), 64 (accept), 65 (reject). Boundary defects are one of the most common bug classes — never skip.
- **Negative testing** — for every positive case ask "what's its invalid/malicious twin?". Per field, generate: invalid format, wrong type, empty/null, oversized payload, unauthorized actor, concurrent modification, retry after partial failure. **Target ~40-50% negatives in the final batch.**
- **Error guessing (common pitfalls)** — race conditions, cache staleness, timezone/locale shifts, null/undefined propagation, integer overflow, UTF-8/emoji in text, retry idempotency, back-button behavior, session expiration mid-flow, very long strings, HTML/script injection, copy-paste of formatted content.

**Conditional:**

- **State transition testing** — when the feature has states (e.g. order: `created → paid → shipped → delivered`, optional `cancelled`). Generate one case per **legal** transition AND extra cases attempting **illegal** transitions (e.g., "cancel an already delivered order") asserting proper rejection.
- **Decision table testing** — when rules combine multiple conditions (e.g. "discount IF `user_tier = gold` AND `cart_total > 100` AND `NOT on_sale`"). Enumerate truth-table rows that produce distinct outcomes; collapse equivalent rows.

Four further techniques fire on their own triggers — **cross-endpoint consistency** (resource reachable via several endpoints), **security** (auth, authorization, or user data), **accessibility** (UI components, forms, modals), **performance** (SLA/throughput targets, lists, search, bulk operations). When any applies, read [`references/advanced-techniques.md`](./references/advanced-techniques.md) for what to generate; skip the file when none match.

#### 3c. Group into logical areas

Organize cases into groups reflecting the feature's structure (e.g., for a currency feature: Selector, Price Conversion, Correctness & Edge Cases).

#### 3d. Write each test case in canonical format

Every test case must have ALL fields populated — never leave one empty. See [Canonical Test Case Format](#canonical-test-case-format).

#### 3e. Coverage checklist

Before Phase 4, verify:
- [ ] Primary happy path
- [ ] Empty/zero state
- [ ] Each distinct CRUD-style operation
- [ ] Persistence (if mentioned)
- [ ] Currency/localization (if prices involved)
- [ ] Each integration point failure (service down, timeout)
- [ ] Each validation/error message in the ticket
- [ ] **At least one negative per input field** (invalid format, out-of-range, unauthorized, null/empty, oversized)
- [ ] **Boundary values for each bounded input** (exact min/max, just below/above)
- [ ] **Each legal state transition AND attempts at illegal transitions** (if stateful)
- [ ] **Decision-table rows enumerated** (if multi-condition rules)
- [ ] **Cross-endpoint consistency** (if resource accessible via multiple endpoints: creation via one path matches all read paths; mutations and deletions propagate; side effects on adjacent resources visible)
- [ ] **Security coverage** (if auth/authz involved: missing/expired auth → 401/403; IDOR probe → 403/404; no sensitive fields in responses; error messages don't expose internals)
- [ ] **Accessibility coverage** (if UI involved: alt text, keyboard operability, label associations, focus management)
- [ ] **Performance coverage** (if SLA or scale involved: response time under load, pagination, bulk operations)
- [ ] **Roughly 40-50% of cases are negative** (if below ~30%, revisit 3b)
- [ ] **Every concrete data value (email, phone, name, ID) is synthetic** — no real person's, customer's, or teammate's data, per [test-data-strategy](../test-data-strategy/SKILL.md)'s no-PII rule

A typical Story should yield at least 8–12 test cases.

#### 3f. For `--format e2e-flow` mode

When `--format e2e-flow` is specified, Phase 3 shifts from generating isolated test cases to generating **user journey flows**. Each flow represents one complete user path — from entry point to goal achieved — with state threaded across all steps.

**Generation approach:**

1. **Identify journeys**: scan the source for sequences of chained actions (login → action → outcome). Each distinct path from entry to exit is one flow. A ticket with Create + Edit + Delete produces 3 flows, not N isolated cases.

2. **Write the happy-path flow first**: document every step in order, recording the `shared_state` each step produces or consumes. Later steps may only reference state established by earlier steps.

3. **Identify negative branches**: for each step where input or auth can fail, record a `negative_branch` — what variation triggers it, what the expected result is, and a short `flow_name` for that branch. These become separate test scenarios but are derived from the main flow.

4. **Annotate shared state**: `shared_state` in each step documents what variables (entity IDs, tokens, UI values) are available from that point onward. The Playwright Implementer reads this to know which `let` declarations are needed and when they are assigned.

5. **Define teardown explicitly**: what must be cleaned up after this flow finishes? API calls, DB rows, sessions. If nothing needs cleanup, state it.

**Coverage target (e2e-flow mode):**
- [ ] At least one complete happy-path flow from entry to exit
- [ ] Every navigation step has a page/screen entry point and expected URL
- [ ] `shared_state` threaded correctly (each step only references state prior steps established)
- [ ] At least one `negative_branch` per critical decision point (auth, validation, permission)
- [ ] Teardown defined
- [ ] Each flow maps to a single Playwright `test.describe` block (record `maps_to_playwright` file path)

### Phase 4: Output via Adapter

When the user specifies a `--to-<name>` flag, **load the matching adapter file**:

1. Read `adapters/<name>.md` (relative to this skill directory).
2. Apply the field mapping table to transform canonical cases into the tool's payload.
3. Make the MCP/API calls in the order specified.
4. Use the progress announcements and success report template from the adapter file.

If no `--to-*` flag, skip adapter loading and print the formatted display-only summary.

After publishing, report with the actual count from the response. Example for Qase:
```
✅ Created 17 test cases
   Adapter: Qase
   Project: MYPROJ | Suite: "PROJ-124 - X Feature" (ID: 6)
   Created test cases with IDs 34–50
```

5. **Append pending clarifications, regardless of adapter or the display-only path.** Every adapter's success report template ends at its own created-count line — none of them has a field for a case Phase 1.5 skipped. Immediately after that report, unconditionally add:
```
## Pending Clarification
Pending on PROJ-124 (comment #45): Does removing the last item show an empty-cart state?
```
reusing the exact `Pending on <KEY> (comment #<id>): <question>` / `Skipped — no ticket to ask against; rerun interactively or with --recommended: <question>` lines Phase 1.5 already collected — one line per skipped ambiguity, the whole section omitted when nothing was skipped. Skipped cases never count toward the adapter's `Created N`.

Exit `0` when nothing was skipped. Exit `4` when at least one case was created/published and at least one was skipped for pending clarification — never `0` in that case, mirroring `/verify-with-argent`'s and `/verify-with-agent-device`'s exit-code contract so CI never reads a partially-blocked run as clean. Exit `1` when every candidate case was skipped and none were generated.

---

## Canonical Test Case Format

Default internal format produced by Phase 3. Every adapter consumes this. Customized via `generate-test-cases.json` (see [Phase 2](#phase-2-confirm-format)) — adapters always consume the canonical shape, so customizations must map cleanly to each adapter's field mapping table.

```json
{
  "title": "Feature | Scenario name",
  "preconditions": "Exact system state before the test. Be specific.",
  "steps": [
    { "action": "One atomic action", "expected_result": "Observable outcome" }
  ],
  "postconditions": "System state after success",
  "priority": "high | medium | low",
  "type": "functional | security | usability | accessibility | performance | compatibility",
  "tags": ["feature-name", "service-name", "test-area"],
  "format": "classic | gherkin"
}
```

**Priority** — `high`: core feature broken if it fails. `medium`: secondary flows / locale / secondary UI. `low`: cosmetic, accessibility convenience.

---

## E2E Flow Format

Used when `--format e2e-flow` is specified. Produces user journey flows instead of isolated test cases. Use this when the feature spans multiple screens, steps must happen in order, or the output will drive Playwright test generation via `/playwright-e2e-automation`.

```json
{
  "flow_name": "User authenticates and views personalized dashboard",
  "persona": "alice (regular user)",
  "entry_point": "Login page at /",
  "exit_condition": "Dashboard greeting visible at /dashboard",
  "preconditions": "User account 'alice' exists; frontend running at baseURL; backend at API_BASE_URL",
  "journey_steps": [
    {
      "step": 1,
      "phase": "entry",
      "action": "Navigate to / (login page)",
      "expected_result": "Login form visible with username input, password input, and Sign in button",
      "shared_state": {}
    },
    {
      "step": 2,
      "phase": "interaction",
      "action": "Fill username='alice', password='alice' and click Sign in",
      "expected_result": "Page redirects to /dashboard; /auth/login returns 200 with accessToken",
      "shared_state": { "authenticated": true }
    },
    {
      "step": 3,
      "phase": "assertion",
      "action": "Observe dashboard content after /users/me resolves",
      "expected_result": "Dashboard displays 'Hello, Alice.' using displayName from /users/me response",
      "shared_state": { "authenticated": true, "displayName": "Alice" }
    }
  ],
  "negative_branches": [
    {
      "branch_at_step": 2,
      "variation": "Invalid password",
      "action": "Fill username='alice', password='wrong' and click Sign in",
      "expected_result": "Stay on /; error message displayed; no redirect to /dashboard",
      "flow_name": "Login rejects invalid credentials"
    },
    {
      "branch_at_step": 2,
      "variation": "Empty credentials",
      "action": "Leave username and password empty and click Sign in",
      "expected_result": "Form validation prevents submission or error shown; stay on /",
      "flow_name": "Login blocks empty credential submission"
    }
  ],
  "teardown": "Close browser context (session discarded automatically)",
  "priority": "high",
  "type": "functional",
  "tags": ["auth", "login", "e2e-flow", "regression-suite"],
  "maps_to_playwright": "tests/auth.e2e.spec.ts"
}
```

**Key differences from classic format:**
- Steps are sequential and stateful — step N can only reference `shared_state` established by steps 1…N-1
- `negative_branches` replace isolated negative test cases — they document deviations from the happy path at specific decision points, not separate standalone cases
- `maps_to_playwright` records which Playwright spec file this flow drives. If the spec does not exist yet, record a placeholder path (e.g. `tests/auth.e2e.spec.ts`) — the field is **advisory only** until `/playwright-e2e-automation` actually creates the file. The Playwright Implementer must not assume the path exists; it treats this field as a target destination, not a source to read.
- `teardown` is explicit — the Playwright Implementer turns this into `afterAll` / `afterEach` hooks

**When to use `e2e-flow` vs `classic`:**

| Use `e2e-flow` when… | Use `classic` or `gherkin` when… |
|---|---|
| Feature spans 2+ screens or routes | Feature is a single, atomic interaction |
| Steps must run in order (step N depends on step N-1) | Cases should be independently executable |
| You'll pass output to `/playwright-e2e-automation` | You'll publish to Qase / Jira / TestRail |
| Ticket describes a complete user story | Ticket describes a single function or field |

**Type** — case's primary validation purpose (NOT execution context):
- `functional` — does the feature do what it should? Default.
- `security` — auth/authz, data exposure, injection, sessions.
- `usability` — clarity, flow, feedback, error messages.
- `accessibility` — screen readers, keyboard, contrast, ARIA, WCAG.
- `performance` — timing, throughput, resource usage, load.
- `compatibility` — browsers, devices, OS, resolutions, platforms.

**Suite membership** (regression / smoke / sanity / acceptance) — encode in `tags`, NOT in `type`. Examples: `["auth", "regression-suite"]`, `["checkout", "smoke"]`, `["uat", "order-flow"]`. A single case can belong to multiple suites without losing what it validates.

**Gherkin format** — steps use a single `value` field with Given/When/Then syntax instead of `action`/`expected_result`.

### Quality standards (applied during 3d)

- **Titles**: follow the convention from `generate-test-cases.json` (default `Feature | Scenario`). Good: `Currency | Badge count updates immediately after currency change`. Bad: `Test currency selector`.
- **Preconditions**: name exact services that must be running, whether data exists or is empty, session/cookie state. Avoid vague "user is logged in".
- **Steps**: one atomic action per step. Expected result must answer "how does the tester know it succeeded?" — not just "it works". If a step triggers a backend call, mention it so the case is testable at the service level.
- **Negatives ratio**: target ~40-50% negatives. Below ~30% → re-apply 3b. Above ~70% → confirm positive coverage isn't starved. Indicator of quality, not a hard quota.

---

## Quality Checks

Before finalizing a batch (end of Phase 3, before Phase 4 publishing), validate per-case, batch-level, and adapter output.

**Per case:**
- [ ] Title follows the configured convention (default: `Feature | Scenario`)
- [ ] Preconditions name exact services, data state, session requirements
- [ ] Every step has both `action` and `expected_result` (classic) or complete Given-When-Then (gherkin)
- [ ] Each step performs exactly one action
- [ ] Expected result is observable (not "it works")
- [ ] Postconditions describe final system state
- [ ] `priority` set with clear rationale
- [ ] `type` set
- [ ] `tags` include feature name and affected service(s)

**Batch:**
- [ ] At least one happy path
- [ ] At least one empty/zero state
- [ ] One case per distinct CRUD operation
- [ ] Persistence case (if applicable)
- [ ] Localization/currency case (if applicable)
- [ ] One failure case per integration point
- [ ] One case per validation/error message
- [ ] Cross-endpoint consistency case (if resource accessible via multiple endpoints)
- [ ] Security cases: auth header missing/expired, IDOR probe, response field audit (if auth/authz involved)
- [ ] Accessibility cases: alt text, keyboard, labels, focus management (if UI components involved)
- [ ] Performance cases: SLA threshold, pagination, scale behavior (if SLA or bulk operations mentioned)
- [ ] Story yields **8–12 cases minimum**
- [ ] No duplicate titles
- [ ] Consistent tagging across cases
- [ ] No real PII in any preconditions/steps value — see [test-data-strategy](../test-data-strategy/SKILL.md)

**E2E Flow batch (for `--format e2e-flow`):**
- [ ] Each flow has a distinct entry point and exit condition
- [ ] Steps are numbered sequentially and cover the complete path
- [ ] `shared_state` only references what prior steps established
- [ ] Every critical decision point has at least one `negative_branch`
- [ ] `teardown` defined (or explicitly stated as "none required")
- [ ] `maps_to_playwright` path recorded — if the spec file doesn't exist yet, the value is a placeholder and **advisory only** (not a path to read)

**Adapter output:**
- [ ] Field mapping applied per loaded `adapters/<tool>.md`
- [ ] MCP calls returned successful IDs (or markdown file written)
- [ ] Success report includes adapter name, project/suite, created IDs

---

## Changing the Saved Format

Stored in `generate-test-cases.json` at the project root. To re-ask the prompt: delete the file. To tweak without re-asking: edit `customizations` directly. To share across a team: commit it. Full schema and validation caveats in [`references/format-config.md`](./references/format-config.md).

---

## Adding a New Output Adapter

Create `adapters/<toolname>.md` (don't edit this skill) with sections: requirements, flag syntax, MCP/API calls, field mapping table, Phase 4 progress announcements, success report, errors/fallbacks, references. Add a row to the [Output Adapters](#output-adapters) table and update the `argument-hint`. Phase 3 generation logic does NOT change — the canonical format is stable.

---

## Examples

```bash
# Jira ticket → Qase (most common)
/generate-test-cases --from-jira PROJ-123 --to-qase MYPROJ

# Jira ticket → markdown file (preview before publishing)
/generate-test-cases --from-jira PROJ-123 --to-markdown ./cases.md
```

For all input/adapter combinations, gherkin variants, `--suite-id`, and full interactive transcripts (first-run config prompt, returning-run flow), see [`references/examples.md`](./references/examples.md).

---

## Error Handling

Adapter-specific errors live in each `adapters/*.md`. Common errors:

| Error | Message |
|------|---------|
| Missing input source | `❌ No input source specified. Use: --from-jira <KEY>, --from-text "<text>", or --from-markdown <path>` |
| Jira ticket not found | `❌ Could not fetch <KEY> from Jira. Check the ticket key and Atlassian MCP configuration.` |
| No testable content | Handled by the Phase 1.5 Ambiguity Gate — call `/clarify-requirement`, never generate silently from prose alone. |

---

## Best Practices

- **Generate in canonical format first** — keep destination-portability; never write tool-specific fields in Phase 3.
- **Cases must be independently executable** — preconditions name services, data states, session/cookie requirements explicitly.
- **One action per step**; expected result must be observable.
- **Cover the full matrix** — happy path, empty state, each CRUD, persistence, localization, integration failures, every validation message.
- **Tag by service and feature** for downstream filtering.
- **Prefer `--to-markdown` first** when exploring a new ticket — review locally before pushing to a shared tool.
- **Don't mix classic and gherkin** in the same run — pick one via `--format`.
- **Always capture returned IDs** from bulk-create responses and echo them in the success report.
- **Ask, don't assume, on decisions that change coverage** — the Phase 1.5 Ambiguity Gate exists because a guessed expected result is worse than a missing test case: it looks like coverage but asserts the wrong thing.

---

## Integration with Other Skills

- **`/clarify-requirement`** — called from Phase 1.5 whenever the source ticket leaves a coverage-affecting decision unstated. Checks the ticket's own comments for an existing answer before asking; see that skill for the full ask/post-to-Jira routing.
- After **`/create-sdd-ticket`** — turn a fully-specified ticket into executable tests.
- Pairs with **`/implement-ticket`** — generate cases from its plan's Testing Strategy, or run after implementation to create regression tests before the PR.
- **`--format e2e-flow` → `/playwright-e2e-automation`** — pass the flow output directly as the Planner's test plan input. The `journey_steps`, `negative_branches`, `shared_state`, and `teardown` fields map 1:1 to Playwright's `test.step()`, multi-context setup, `let` variable declarations, and `afterAll` hooks. This is the recommended two-step path for features that require real end-to-end automated coverage.
- Before generating a fresh batch for a ticket that already has some tests — **`/requirement-coverage-gap-analysis`** first, so generation targets only the confirmed gaps instead of regenerating cases for scenarios already covered.
- **`/test-data-strategy`** governs every concrete data value this skill writes into `preconditions`/`steps` (see the Phase 3e and Quality Checks bullets above) — its scanner can be run over any spec files this skill's output later becomes.
- **`/report-bug`** — when a generated test case is executed (manually or via `/playwright-e2e-automation`) and fails, `/report-bug --from-failure <path>` turns that failure into a structured bug report. The two skills mirror the same architecture (evidence → canonical format → adapter) in opposite directions: this skill documents what should be tested, `/report-bug` documents what already failed.

---

## References

- **Input**: Atlassian MCP `mcp__claude_ai_Atlassian__getJiraIssue` (markdown response).
- **Output adapters**: [`adapters/`](./adapters/) — one file per tool, loaded on-demand by Phase 4.
- **Advanced techniques**: [`references/advanced-techniques.md`](./references/advanced-techniques.md) — situational Phase 3b techniques, loaded on-demand.
- **Related skills**: [`/clarify-requirement`](../clarify-requirement/SKILL.md), [`/create-sdd-ticket`](../../020-development-workflow/create-sdd-ticket/SKILL.md), [`/implement-ticket`](../../020-development-workflow/implement-ticket/SKILL.md).
- **External**: [Gherkin Reference](https://cucumber.io/docs/gherkin/reference/).
- **Version history**: [`references/changelog.md`](./references/changelog.md).
