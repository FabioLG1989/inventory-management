---
name: clarify-requirement
version: 1.0.0
last-updated: 2026-09-15
description: Resolve one ambiguous or underspecified requirement by checking the ticket's own comments first, then asking a human — never by silently picking an interpretation. Use when a QA skill (test-case generation, PR review, E2E planning) hits an acceptance criterion, edge case, or business rule that isn't stated and would change generated coverage, priority, or pass/fail criteria depending on the answer.
argument-hint: '--question "<the ambiguous point>" --context "<why it matters / what breaks if guessed wrong>" [--ticket <KEY>] [--options "<opt-A>|<opt-B>|..."] [--recommended "<label>"] [--blocking] [--dedup-key "<stable-id>"] [--artifacts-dir <path>] [--skip-questions]'
allowed-tools: Read, Write, Bash, AskUserQuestion, mcp__atlassian__getJiraIssue, mcp__atlassian__addCommentToJiraIssue
---

# Clarify Requirement

Turns "the ticket doesn't say, so I'll assume X" into an explicit answer with a source. Called by another QA skill (or a person) at the exact point a decision would otherwise be guessed.

## Purpose

Requirement text is frequently silent on the case that actually determines correct behavior — what happens at zero, who's authorized, which of two plausible readings of an AC is meant. A skill that fills that gap on its own bakes a guess into generated test cases, review verdicts, or E2E flows with no record that a guess was made. This skill makes that moment visible and answerable:

1. **Search the ticket's own comments** for an answer already given — most "ambiguous" requirements were already resolved by someone, just not folded back into the description.
2. **If unresolved, ask** — via the same MCP-first routing every interactive framework skill uses, never a silent default.
3. **When no human is present to answer synchronously** (`--skip-questions`, or the ask channel returns no usable answer), **post the question as a Jira comment** on the ticket instead of guessing, so it is answered asynchronously and visible to the team — and record the run's working assumption as explicitly provisional.
4. **Record the resolution** so a rerun against the same ticket never re-asks a settled question.

## When to call this (and when not to)

Call it for a decision that would change generated output — a different expected result, a different priority, a different pass/fail boundary, a different scope. Do **not** call it for phrasing gaps a reasonable QA engineer fills without a second thought (button label casing, which exact wording an error toast uses when the ticket only implies one exists). One question per ambiguity; batch nothing.

**Before calling**: read whatever ticket/code/wiki context is already loaded (the calling skill's own Phase 1 output, `docs/llm-wiki/`, existing conventions). If it answers the question outright, use that — don't spend a question on something evidence already settled. This mirrors `grill-me`'s "explore before asking."

## Prerequisites

- **Atlassian MCP** (`mcp__atlassian__getJiraIssue`, `mcp__atlassian__addCommentToJiraIssue`) — only needed when `--ticket` is passed (comment search + comment posting). Without `--ticket`, this skill still runs the ask-a-human flow, it just has no ticket to search or post to.
- Nothing else. No `ARTIFACTS_DIR` bootstrap is required; pass `--artifacts-dir <path>` when the calling skill has one (e.g. `.claude-temp/tickets/<TICKET_ID>/artifacts`, the same path it hands to any other sub-skill) and this skill writes its decision record under `<path>/decisions/clarifications.jsonl` — otherwise it skips persistence and returns the answer for that run only. Phase 3's anti-duplicate check does not depend on this file — see Phase 3.

## Usage

```bash
# Called by another skill mid-workflow
/clarify-requirement \
  --question "Does removing the last item in the cart show an empty-cart state, or does the cart widget disappear entirely?" \
  --context "Changes the expected_result of the 'remove last item' test case and whether an empty-state case exists at all." \
  --ticket PROJ-124 \
  --options "Show empty-cart state|Hide the cart widget" \
  --recommended "Show empty-cart state" \
  --blocking
```

Flags:

| Flag | Required | Description |
|------|----------|-------------|
| `--question` | yes | The exact question, phrased so a one-line answer resolves it. |
| `--context` | yes | One sentence: what downstream output changes depending on the answer. Shown to the human so "why are you asking" is never a mystery. |
| `--ticket <KEY>` | no | Enables comment search (Phase 1) and Jira-comment fallback (Phase 3). Omit for `--from-text`/`--from-markdown` sources. |
| `--options "<a>\|<b>\|..."` | no | 2–3 concrete choices. Omit for a free-text answer. |
| `--recommended "<label>"` | no | With `--options` set, must match one option verbatim and is shown first, suffixed `(Recommended)`. Without `--options`, it's the free-text suggested answer instead. Required whenever `--blocking` is not set, with or without `--options` — it becomes the headless-fallback working assumption; a non-blocking call with neither is a caller error (see Phase 3, `--ticket` not set). |
| `--blocking` | no | This decision changes correctness, not just polish (e.g. security boundary, data-loss path, payment amount). In headless mode a blocking question is never silently assumed — see Phase 3. |
| `--dedup-key "<id>"` | no | A stable identifier for this exact ambiguity, chosen by the caller independently of `--question`'s wording — a slug of the checklist item/AC's own text, never regenerated text and never a positional index: a ticket edit that reorders or inserts checklist items shifts indices, so an index-keyed ambiguity can collide with an unrelated one and silently return its stale answer instead of asking or re-scanning. Pass this whenever `--question` is phrased fresh by an LLM each run, since reworded questions defeat text-based dedup. See **Dedup Key Matching** below for the rule Phase 1/3/4 and Error Handling all rely on. |
| `--artifacts-dir <path>` | no | Directory the calling skill already writes its own ticket artifacts to (e.g. `.claude-temp/tickets/<TICKET_ID>/artifacts`) — never inherited from an `$ARTIFACTS_DIR` environment variable, always passed explicitly, the same way `implement-ticket` hands the path to its sub-skills. When set, Phase 4 persists the decision record under `<path>/decisions/clarifications.jsonl` and Phase 3 reads it back. When omitted, the answer is known for this run only — see Phase 4. |
| `--skip-questions` | no | Never prompt: skip Phase 2 and go straight to the Phase 3 headless fallback. Pass it from an unattended run with no human (CI, SDK). |

Returns: `{ "answer": "<text>", "source": "comment #NNNN" | "mcp" | "interactive" | "headless-assumed" | "headless-posted-pending", "evidence": "<quote or citation>", "posted_comment_id": "<id>" }`. `posted_comment_id` is present only when `source` is `headless-posted-pending` — the caller needs it to cite the comment (e.g. `comment #<posted_comment_id>` in a postconditions note).

### Dedup Key Matching

When both sides have a dedup key, key equality decides it outright — a matching `--question` never overrides a key mismatch, so two deliberately different ambiguities with different keys never collide just because their phrasing happens to coincide. When at least one side has no dedup key, matching falls back to `--question` normalized (lowercased, whitespace collapsed) equality instead; either signal carrying over from the prior run is enough when it's the one available. Two calls that both simply omit `--dedup-key` are never a match on that account alone — an absent key matches nothing, only the question-text branch can match them; otherwise two unrelated key-less ambiguities on the same ticket could collide. Exception: a comment posted before `--dedup-key` existed for that ambiguity, if `--question` is *also* reworded on the very run that first adds the key, matches on neither and reposts once; every run after that matches cleanly on the now-stable key.

**Source classification, for callers marking output as provisional**: `headless-posted-pending` and `headless-assumed` are assumed — nothing confirmed them synchronously. `comment #N`, `mcp`, and `interactive` are resolved — a human or the ticket itself actually answered; never mark their output as assumed. Note that `headless-assumed` can occur even when `--ticket` was passed, if Atlassian MCP was unreachable (see Error Handling) — a caller that assumes only a ticket-less call produces `headless-assumed` will mishandle that case.

## Workflow

```bash
ARTIFACTS_DIR="<--artifacts-dir, if passed, else empty — never inherited from the environment>"
```

### Phase 1: Search existing comments

Skip if `--ticket` is not set.

If the calling skill fetched `## Comments` earlier in *this same invocation* (via `/fetch-ticket-context` or its own Jira load, called fresh this run), read that in memory — never re-fetch. This does **not** cover a `context.json` the caller merely found already on disk and reused without fetching (verify-* skills auto-fetch only when it's missing) — that snapshot predates this run and may be missing a reply posted since, or the skill's own prior comment Phase 3 needs to find. In that case, and whenever no `## Comments` from this run is available at all, call `mcp__atlassian__getJiraIssue` for `--ticket` with comments expanded (a single ticket's comments; do not invoke the full `/fetch-ticket-context` pipeline just for this).

**Run this phase unless Error Handling's dedup check already returned** — a stored record with `source` `comment #N` / `mcp` / `interactive` is settled and short-circuits before this phase runs at all, and so is a `headless-assumed` record with no `ticket` field on it (no ticket ever existed for that call). A stored `headless-assumed` record that *does* carry a `ticket` field, or a stored `headless-posted-pending` record, is not settled — Atlassian MCP being unreachable one run isn't the same as the ticket having nothing left to say — so this phase still runs; see Phase 4 for why a pending record must never skip the rescan.

Scan chronologically, most recent first, for a comment that answers `--question` — an explicit decision, a reply to a prior clarifying comment from this same skill (see Phase 3), a PM/lead statement settling the point. A comment answers the question only if it does so **directly**; a tangentially related comment is not evidence. If found: return immediately with `source: "comment #<id>"` and `evidence` = the quoted resolving line plus author + date. Do not ask anything — the ticket already has the answer.

### Phase 2: Ask — MCP-first routing

Detect the execution context exactly as `/create-sdd-ticket` does — from the arguments and this command, never from a terminal probe:

```bash
echo "QAF_ASK_USER_MCP_TOOL=${QAF_ASK_USER_MCP_TOOL:-UNSET}"
```

- `--skip-questions` passed → **headless**, go straight to Phase 3, even when the MCP tool is set.
- `QAF_ASK_USER_MCP_TOOL` non-empty → **MCP autonomous**.
- Otherwise → **interactive**.

An ask channel that returns no usable answer (tool absent, error, empty, or EOF) is never re-asked: go straight to Phase 3.

**MCP autonomous** — build the payload via `$MCP_AUQ_HOOKS/build-mcp-payload.sh` exactly as `/create-sdd-ticket` does, then call `$QAF_ASK_USER_MCP_TOOL`:

```bash
TICKET="<--ticket, if passed, else empty>"
PAYLOAD=$(MCP_SKILL=clarify-requirement MCP_PHASE=phase-2-ask MCP_TICKET_ID="${TICKET:-}" \
  bash "$MCP_AUQ_HOOKS/build-mcp-payload.sh")
# Build every field with jq -n --arg — never interpolate --question/--context/--recommended into a
# bash string literal: ticket-derived text can carry quotes/apostrophes/backslashes that break a
# single-quoted literal and, worst case, let a crafted line inject shell.
# id: --dedup-key if passed, else a slug of --question. options: --options entries (recommended
# first, " (Recommended)" suffix) if --options was passed, else [] — a free-text answer relies on
# the channel's own free-text capture, same as AskUserQuestion's auto-supplied "Other".
QUESTIONS_JSON=$(jq -n \
  --arg id "<--dedup-key, or a slug of --question>" \
  --arg question "<--question, verbatim>" \
  --arg context "<--context, verbatim>" \
  --arg recommended "<--recommended, or empty if not set>" \
  --argjson options '<"--options" entries as [{"label":...}, ...], or [] if --options was not passed>' \
  '[{id: $id, question: $question, context: $context, options: $options, multi_select: false}
    + (if $recommended != "" then {recommended_answer: $recommended} else {} end)]')
# Append the Jira-comment option via jq, only when --ticket is set, so it can never be dropped by hand
[[ -n "${TICKET:-}" ]] && QUESTIONS_JSON=$(jq -c 'map(.options += [{"label":"Post this as a question on the ticket instead"}])' <<<"$QUESTIONS_JSON")
"$QAF_ASK_USER_MCP_TOOL" "$(jq --argjson q "$QUESTIONS_JSON" '.questions=$q' <<<"$PAYLOAD")"
```

Read the reply from the tool's response.

**Interactive**, `--options` set — call the `AskUserQuestion` tool with `--question` as the question text, `--context` as its description, and `--options` as its options (recommended one first, suffixed `(Recommended)`) — never add an `Other` option, the tool supplies one automatically. If `--ticket` is set, append one more option: `Post this as a comment on <KEY> and continue later` (`--options` caps at 3 choices precisely so this fits the tool's 4-option limit).

**Interactive**, `--options` not set (free-text answer) — `AskUserQuestion` doesn't apply here: it requires 2-4 concrete choices, which an open-ended question has none of. Ask `--question` directly in conversation instead, with `--context` as the one-line reason, and read the human's free-text reply; if `--ticket` is set, mention that replying on the ticket instead works too. If the reply itself asks to defer (e.g. "just post it on the ticket") rather than answering, treat that exactly like the dedicated Jira-comment option in the other two routes below — do not record prose like that as a literal answer.

Either path: wait for the reply before returning.

Either way, on a resolved answer: `source: "mcp"` or `"interactive"`, `evidence`: the option label or free-text reply. If the human chose the Jira-comment option instead, there is no resolved answer — fall through to Phase 3's posting step and let it set `source: "headless-posted-pending"` as it would for any other deferral. Do **not** keep `"interactive"`/`"mcp"` on that record: those sources are treated as settled (Phase 1, Error Handling), so the run that posts the comment would become the last one that ever reads the ticket and the reply would never be picked up. Set `evidence: "deferred via interactive"` or `"deferred via mcp"` on the record instead, so it stays clear a human chose this rather than nobody being present to answer.

### Phase 3: Headless fallback — post, don't assume

Reached only when `--skip-questions` was passed, when the Phase 2 ask channel returned no usable answer, or when a human explicitly chose to defer to the ticket in Phase 2.

**If `--ticket` is set**: before posting, get `posted_comment_id` for this dedup key without posting a duplicate. If `$ARTIFACTS_DIR` is set and `clarifications.jsonl` has a `headless-posted-pending` record for this dedup key, use its stored `posted_comment_id` directly — Phase 1 already confirmed, by finding no answering comment, that the question is still open, so there's nothing left to verify. Otherwise — no `$ARTIFACTS_DIR`, or no such record yet, including the first run that adds `--dedup-key` to an ambiguity posted before it existed — scan **the ticket's own comments** (already loaded by Phase 1) for the skill's own prior comment on this exact ambiguity: a candidate is identified by the `🤖 **Clarification needed**` prefix and matches per **Dedup Key Matching** above (its trailing `_Ref:` line, or its embedded question text, against this call's `--dedup-key`/`--question`). This fallback is what keeps a run with no artifacts directory from re-posting the same question every time.

If `posted_comment_id` was found either way, do **not** post again — reuse it and skip straight to the return below. Otherwise post the question as a Jira comment via `mcp__atlassian__addCommentToJiraIssue`, addressed to the ticket (mention the assignee if one is set), formatted as:

```markdown
🤖 **Clarification needed** — <question text>

<context text>

Working assumption for this run (not yet confirmed): **<recommended, or "none — proceeding without this case" if no --recommended>**. Reply on this ticket to confirm or correct it.

_Ref: <dedup-key>_
```

Include the trailing `_Ref: <dedup-key>_` line only when `--dedup-key` was passed.

Capture the returned comment id as `posted_comment_id`, for the return value and, when `$ARTIFACTS_DIR` is set, for the record Phase 4 writes and a later run's fast path above.

Then:
- **`--blocking` set**: STOP this run's use of the answer entirely — do not generate the dependent output, do not use the recommended value. Return `source: "headless-posted-pending"` with no answer; the calling skill must skip whatever depended on it and say explicitly what was skipped and why, citing the posted comment.
- **`--blocking` not set**: proceed using `--recommended` as the answer, `source: "headless-posted-pending"`. Require the calling skill to mark whatever it produced from this answer as provisional using a marker that survives that output's own constraints: if the field is free text (a description, postconditions, a report line), write a human-readable note like `(assumed — pending reply on <KEY>#<posted_comment_id>)`; if the field is a constrained label/tag (Jira labels, Xray labels — no whitespace or punctuation), use a label-safe token instead, e.g. `assumed-pending-<KEY>`, and put the human-readable note in a free-text field on the same record. Never assume the caller's field accepts arbitrary punctuation — a label/tag field typically rejects whitespace and punctuation outright and silently strips or drops it, which erases the one signal that the value was assumed rather than confirmed. `--recommended` is required in this path; if omitted, treat as `--blocking`.

**If `--ticket` is not set** (free-text/markdown source, no ticket to post to): there is nowhere to ask and nowhere to check for a reply later, so this is a one-shot, unrecoverable-until-rerun-with-input decision, not a pending one. `--blocking` set → return unresolved and let the caller skip the dependent output. `--blocking` not set with `--recommended` → return it as `source: "headless-assumed"`; the caller marks output `(assumed)` (same free-text-vs-label-safe rule as above, without the `<KEY>#<comment>` citation since there is none). Neither set → return unresolved; a caller that reaches this state without a recommended answer had no business calling this skill non-blocking — surface that as a caller error, not a silent skip.

### Phase 4: Record the resolution

If `$ARTIFACTS_DIR` is set in the environment, append one line to `$ARTIFACTS_DIR/decisions/clarifications.jsonl` (create the `decisions/` dir if missing):

```json
{"question":"...","dedup_key":"cart-empty-state","ticket":"PROJ-124","answer":"...","source":"comment #45","evidence":"...","resolved_at":"2026-09-08T14:02:00Z"}
```

Omit `"dedup_key"` when `--dedup-key` wasn't passed. Include `"ticket"` whenever `--ticket` was passed to this call — even on a run where Phase 3 routed it through the ticket-not-set branch because Atlassian MCP was unreachable. That field is the only way a later run's dedup check can tell a genuinely ticket-less `headless-assumed` record (nothing to ever re-check) apart from one where a ticket existed but MCP happened to be down (see Error Handling).

For a `headless-posted-pending` result, `answer` is `null` and the record additionally carries `"posted_comment_id"` (the id from Phase 3) so a later run can find its own posted comment and skip re-posting; `evidence` is `"deferred via interactive"`/`"deferred via mcp"` when a human's Phase 2 deferral produced it, otherwise empty. `source: "headless-posted-pending"` and re-scan behavior are the same either way — nothing about a deferral makes the record more settled than an unattended post.

**A `headless-posted-pending` record is not a settled answer — it is a pointer to an open question**, deferred or not. It never short-circuits Phase 1: every run scans the ticket's comments regardless of what `clarifications.jsonl` holds, because the entire point of posting the question was to let the ticket answer it on a later run. What the stored record changes is Phase 3's *posting* step only — a rerun that reaches Phase 3 with the same question still pending reuses `posted_comment_id` instead of posting a duplicate comment. A rerun of the calling skill should still call `/clarify-requirement` again for the same question; this skill, not the caller, is what tells the difference between "still pending" and "now answered" by running Phase 1 fresh each time.

Only a genuinely resolved source (`comment #N`, `mcp`, `interactive`), or a `headless-assumed` record with no `ticket` field at all, is a settled answer worth trusting without re-scanning. A `headless-assumed` record that *does* carry a `ticket` field is not settled either, even though nothing is pending on it the way a `headless-posted-pending` record is: it means Atlassian MCP was unreachable that run, not that the ticket has nothing left to say, so a later run must still re-scan rather than trust the cached assumption forever — see Error Handling for how the dedup check treats all three cases differently.

If `$ARTIFACTS_DIR` is unset, skip persistence: a genuinely resolved answer (`comment #N` / `mcp` / `interactive` / `headless-assumed`) is then known for this run only, and a later run re-asks from scratch. This does **not** reopen the duplicate-Jira-comment problem — see Phase 3.

## Error Handling

| Condition | Behavior |
|---|---|
| `--question` or `--context` missing | `❌ /clarify-requirement requires --question and --context.` Abort — a question with no stated stakes is indistinguishable from noise. |
| `--options` set without `--recommended`, and the path reached is headless non-blocking | Treat as `--blocking` — there is no working assumption to fall back on. |
| `--ticket` set but Atlassian MCP unreachable | Skip Phase 1 and the Phase 3 posting step; fall through to Phase 2's ask (or, if already headless, treat as if `--ticket` were unset). Never fail the whole run over a missing MCP connection to a QA-blocking skill. |
| Same dedup key (see `--dedup-key`) has a stored record in `clarifications.jsonl` for this `--ticket`, with `source` in `comment #N` / `mcp` / `interactive`, or `source: "headless-assumed"` with no `ticket` field on the record | Return the stored answer directly, `source` unchanged. These are settled — do not re-scan, do not re-ask. |
| Same dedup key has a stored record with `source: "headless-assumed"` **and** a `ticket` field | NOT a dedup case, for the same reason as the row below: the record only means Atlassian MCP was unreachable on a prior run, not that the ticket had nothing to say. Run Phase 1 normally — if the ticket now has an answer, return it as `comment #N` and overwrite the stored record. Still unanswered → re-run Phase 2/3 as if no record existed. |
| Same dedup key has a stored record with `source: "headless-posted-pending"` | NOT a dedup case. Run Phase 1 normally — if the ticket now has an answer, return it as `comment #N` and overwrite the stored record. Still unanswered → proceed to Phase 3, which matches the ticket's own prior comment instead of posting again, and returns `headless-posted-pending` once more. |
| `--ticket` set, headless path reached, `$ARTIFACTS_DIR` unset | No stored record can exist, so neither row above applies. Phase 3's ticket-comment scan is what still prevents a duplicate post here — it does not depend on this file. A resolved answer (`comment #N`/`mcp`/`interactive`/`headless-assumed`), by contrast, really is only known for this run — see Phase 4. |

## Integration with Other Skills

- **`/generate-test-cases`** — calls this before Phase 3 (Generate Test Cases) whenever an acceptance criterion is missing a business rule the test-design techniques need (a boundary with no stated limit, a decision-table rule with an undefined branch, a checklist item that contradicts the description). See that skill's Phase 1.5 "Ambiguity Gate."
- **`/verify-with-argent`** and **`/verify-with-agent-device`** — call this while turning acceptance criteria into device-verification steps, whenever a criterion doesn't state a checkable outcome. See each skill's "Resolve the ticket and gather acceptance criteria" step.
- Any other `030-quality-assurance` skill that derives pass/fail criteria, priority, or scope from ticket text can call this the same way — one `/clarify-requirement` call per ambiguous point, at the point the ambiguity is found, not batched at the end. (`pr-reviewer`'s severity calls are the deliberate exception: its ambiguity is code-shaped, not requirement-shaped, and its rubric — "when ambiguous, the lower [severity]" — already resolves it without a human round-trip.)
- Complements, does not replace, `/fetch-ticket-context` (pure gathering — explicitly out of scope for judging comment intent) and `grill-me` (plan-level interview, not ticket-comment-aware). This skill is the narrow "one QA decision, checked against the ticket, asked if unanswered" primitive the other two don't cover.

## References

- **Routing pattern**: [`/create-sdd-ticket`](../../020-development-workflow/create-sdd-ticket/SKILL.md) Phase 3 — the interview this skill's Phase 2 reuses verbatim.
- **Comment semantics**: [`/fetch-ticket-context`](../../040-integrations/fetch-ticket-context/SKILL.md) `## Comments` section — id, author, timestamp format this skill's Phase 1 expects when reusing an already-fetched context.
- **Consumers**: [`/generate-test-cases`](../generate-test-cases/SKILL.md), [`/verify-with-argent`](../verify-with-argent/SKILL.md), [`/verify-with-agent-device`](../verify-with-agent-device/SKILL.md).
