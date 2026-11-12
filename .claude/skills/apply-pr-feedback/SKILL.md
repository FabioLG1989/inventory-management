---
name: apply-pr-feedback
version: 2.0.0
last-updated: 2026-09-04
description: Applies GitHub PR review feedback to an existing branch. Use when a PR has a `CHANGES_REQUESTED` review and those changes must be pushed back to the same branch without opening a new PR. Scope-bounded: only addresses the requested feedback — never reimplements the ticket. Supports both single-repo projects and multi-repo workspaces (operating on one PR / one repo per invocation).
argument-hint: '--pr-url PR-URL --branch BRANCH-NAME [--pr-number PR-NUMBER] [--from-jira TICKET-ID] [--review-id REVIEW-ID] [--repo REPO-PATH] [--skip-questions | --autonomous] [--skip-tests]'
disable-model-invocation: true
---

# Apply PR Review Feedback

Input: $ARGUMENTS

Apply the requested changes from a GitHub PR review to the existing branch through a wiki-aware 7-phase workflow. The PR is updated by `git push` — this skill never opens a new PR and never posts comments to Jira or GitHub.

## Flags

Parse the input for these flags:

- `--pr-url <PR-URL>` — the full GitHub PR URL, e.g. `https://github.com/owner/repo/pull/42` (required). It names the owning repo, so the PR is unambiguous in a multi-repo workspace.
- `--branch <BRANCH-NAME>` — the existing branch the PR points at (required)
- `--pr-number <PR-NUMBER>` — the PR number on GitHub. Optional, and only a cross-check: when it disagrees with `--pr-url`, report the mismatch and continue with the number from the URL.
- `--from-jira <TICKET-ID>` — fetch ticket context from Jira (e.g., `PROJ-123`). Optional but recommended when the ticket id is not derivable from the branch name.
- `--review-id <REVIEW-ID>` — specific review to apply, as either the numeric REST id or the `PRR_…` node id. Optional; when omitted, the skill resolves the most recent review with state `CHANGES_REQUESTED`.
- `--repo <REPO-PATH>` — absolute path to the target git repo. Optional; defaults to the current working directory. Required when invoked from a multi-repo workspace root.
- `--skip-tests` — skip the testing phase (dev/experimental only)
- `--skip-questions` / `--autonomous` (identical) — autonomous mode for the **whole run**: no phase asks the developer anything and no phase waits on a human. Ambiguous review comments are resolved by the narrowest reading that satisfies the comment and recorded under `Assumptions` in `feedback-plan.md`. Required for unattended callers (schedulers, CI); never inferred from the environment.

The skill derives `TICKET_ID` in this order: `--from-jira` value → ticket id extracted from `--branch` (e.g., `feature/PROJ-123-foo` → `PROJ-123`) → fallback `PR-<PR-NUMBER>`. The derived id is used purely for artifact pathing; it does not change behavior.

## CRITICAL: Artifact Path Enforcement

All artifacts live at `<workspace-root>/.claude-temp/tickets/<TICKET_ID>/artifacts/`. `<workspace-root>` is the folder containing `.claude/` — in a multi-repo workspace the PARENT folder, never a child repo (even the one `--repo` points at). Never write artifacts anywhere else (no `.claude/artifacts|screenshots|decisions/`, no child-repo `.claude-temp/`).

Resolve `ARTIFACTS_DIR` with this snippet — re-run it at the start of any phase that needs the path. Run it and `qaf_run_preflight` unpiped: both set shell variables, which a pipe or `$(…)` discards.

```bash
source ".claude/scripts/lib/bootstrap-preflight.sh"
qaf_resolve_artifacts_dir "$TICKET_ID"
```

Never assign a bare relative `.claude-temp/...` — it resolves against cwd and can leak into a child repo. The PR-specific work lands under `$ARTIFACTS_DIR/pr/<repo-basename>/<PR-NUMBER>/`; ALWAYS pass `--artifacts-dir "$ARTIFACTS_DIR"` when invoking sub-skills.

## Multi-Repository Awareness

The workspace may be a single git repo OR a parent folder containing multiple independent child git repos (each with its own GitHub remote). A single GitHub PR is always scoped to one repo, so this skill operates on one repo per invocation:

- In single-repo mode, omit `--repo`; the skill assumes the current working directory is the target repo.
- In multi-repo mode, pass `--repo <ABS-PATH>` pointing at the affected child repo. The skill targets that repo with `git -C <repo>` for every git operation and only re-runs tests inside that repo.

`PR_HOST`, `PR_SLUG` (`owner/repo`) and `PR_NUMBER` come from `--pr-url` alone — never from `$REPO`'s remote, which Phase 0 instead asserts matches them. Read all three off `--pr-url` again at the start of any later phase that needs them, and pass `GH_HOST="$PR_HOST"` on every `gh api` call, whose path carries no host of its own.

The LLM wiki remains workspace-scoped (one shared `docs/llm-wiki/` at the workspace root). Phase 2 consults it; Phase 4 (testing) runs only in the affected repo.

## CRITICAL: Progress Tracking

Emit this checklist before Phase 0, then re-emit it at the start of every phase with the states updated: `[x]` verified complete, `[>]` running, `[ ]` not started. A phase a flag removed checks off with its reason — `- [x] Phase 4: Testing (skipped: --skip-tests)`.

```
Workflow Progress:
- [ ] Phase 0: Preflight
- [ ] Phase 1: Context Reading
- [ ] Phase 2: Planning
- [ ] Phase 3: Implementation
- [ ] Phase 4: Testing (removed by --skip-tests)
- [ ] Phase 5: Quality
- [ ] Phase 6: Commit and Push
```

Each `### Phase N` section under `## Phase Execution` below is the single source of truth for what that phase does. Never check a phase off while its Expected outputs are missing, a required agent was not spawned, or an error occurred.

The checklist dies with the session, so also append one JSONL record per transition to `$ARTIFACTS_DIR/progress.jsonl`, which a resumed run reads — never memory — to decide which phases already completed. Re-resolve the path inside the same command: a variable set at one transition is gone by the next. Never spend a dedicated tool call on the append — ride the `in_progress` record on the phase's first command and the `completed` record on the command that verifies its Expected outputs.

```bash
source ".claude/scripts/lib/bootstrap-preflight.sh"
qaf_resolve_artifacts_dir "$TICKET_ID" >/dev/null
printf '{"phase": %s, "name": "%s", "status": "%s", "ts": "%s"}\n' \
  2 "Planning" "in_progress" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  >> "$ARTIFACTS_DIR/progress.jsonl"
```

Emit `in_progress` before starting each phase and `completed` only after verifying its Expected outputs. A phase skipped via flag still gets both, its `completed` record carrying `"note": "<why>"`. A violated Constraint emits `{"phase": N, "status": "failed", "reason": "<why>", "ts": "..."}` and STOPs.

## CRITICAL — Turn Discipline

This skill may be driven headlessly (CI, SDK, orchestrator), where a response with no tool call ends the run and kills every command it spawned. You cannot detect the mode, so always assume it: until Phase 6 completes or an Error Handling rule says STOP, every response MUST contain a tool call. Narrating intent is not progress.

- Long commands (dependency install, test suites, lint): pass the maximum timeout the Bash tool accepts on the FIRST attempt (`timeout: 600000`).
- If one is backgrounded anyway, re-run it in the foreground at max timeout. Never wait on a background task — `ScheduleWakeup`, `Monitor`, `sleep`, polling loops: the notification may never arrive, and teardown kills the command mid-write.
- A manifest edit and its lockfile regeneration are one atomic unit — never end a turn between them; a stale lockfile fails the next run's Phase 0 clean-tree check.

## Phase Execution

Execute each phase sequentially. Do not proceed to the next phase until the current phase is marked completed.

**Preflight marker check (Phase 1 onward):** at the start of every phase from Phase 1, assert `test -f "$ARTIFACTS_DIR/.preflight-ok"` exits 0. If the marker is missing, return to Phase 0 and rerun the preflight.

### Phase 0: Preflight (MANDATORY — Auto-bootstrap + Validation)

**Validate `--pr-url` first.** It must read as `https://<host>/<owner>/<repo>/pull/<number>`. If it does not parse, STOP before running anything below — never guess a repo or a number.

**Auto-bootstrap.** Set the environment and run the deterministic preflight:

```bash
REPO="$(git -C "${REPO:-$(pwd)}" rev-parse --show-toplevel)"   # --repo, else cwd; normalized to repo root
PR_URL="<from --pr-url>"
PR_HOST="<host, read off $PR_URL>"
PR_SLUG="<owner/repo, read off $PR_URL>"
PR_NUMBER="<number, read off $PR_URL>"
TICKET_ID="<resolved-id>"
source ".claude/scripts/lib/bootstrap-preflight.sh"
qaf_run_preflight "$TICKET_ID"   # absolute ARTIFACTS_DIR at workspace root; runs ensure-context.sh
mkdir -p "$ARTIFACTS_DIR/pr/$(basename "$REPO")/$PR_NUMBER/commits"
```

`qaf_run_preflight` resolves the workspace-root `$ARTIFACTS_DIR` (never inside `$REPO`) and runs `ensure-context.sh` anchored to it, which writes `$ARTIFACTS_DIR/.preflight-ok` on success or `$ARTIFACTS_DIR/.preflight-failed` on failure. Trust its outputs — do not re-verify them. If it exits non-zero, STOP and surface its output verbatim.

**Checks (after the script succeeds):**

- `git -C "$REPO" status --porcelain` returns empty (working tree clean).
- `git -C "$REPO" rev-parse --abbrev-ref HEAD` equals `<--branch value>`. If not, STOP — never `git checkout`/`switch` on the user's behalf.
- `gh auth status` succeeds and `(cd "$REPO" && gh repo view --json url -q .url)` names the same host and `owner/repo` as `$PR_URL`. Mismatch or error → STOP: the PR belongs to `$PR_HOST/$PR_SLUG`, not `$REPO`; in a multi-repo workspace pass `--repo` pointing at that repo's checkout.
- `gh pr view "$PR_URL" --json headRefName -q .headRefName` equals `<--branch value>`. Mismatch or error → STOP.
- If `--pr-number` was passed and differs from the number derived from `--pr-url`, report the mismatch and continue with the derived one.
- If `--from-jira` was passed, Jira MCP is available.

Any failure → STOP and report; the preflight cannot fix these.

CONTINUE WITH Phase 1.

### Phase 1: Context Reading

Produce a single canonical artifact at `$ARTIFACTS_DIR/pr/<repo-basename>/<PR-NUMBER>/review-context.md` so every later phase reads from one path.

- Resolve `TICKET_ID` per the Flags rule and confirm it.
- If `--from-jira <TICKET-ID>`: MUST invoke `/fetch-ticket-context` (the skill writes the ticket body to `$ARTIFACTS_DIR/context/ticket-context.md` — reference that path from `review-context.md`, do not duplicate the body).
- Fetch PR metadata and the review list:
  ```bash
  set -euo pipefail
  gh pr view "$PR_URL" \
    --json title,body,headRefName,baseRefName,files,url \
    > "$ARTIFACTS_DIR/pr/$(basename "$REPO")/$PR_NUMBER/pr.json"
  GH_HOST="$PR_HOST" gh api --paginate "repos/$PR_SLUG/pulls/$PR_NUMBER/reviews" \
    | jq -s 'add' > "$ARTIFACTS_DIR/pr/$(basename "$REPO")/$PR_NUMBER/reviews.json"
  ```
- Resolve `REVIEW_ID` from `reviews.json` — always the numeric `id`, never `node_id`: the entry whose `id` or `node_id` matches `--review-id`, else the `CHANGES_REQUESTED` entry with the latest `submitted_at`. `gh pr view --json reviews` is not a source — it exposes only the `PRR_…` node id, which REST rejects with 404.
- Fetch the review's inline comments:
  ```bash
  set -euo pipefail
  GH_HOST="$PR_HOST" gh api --paginate "repos/$PR_SLUG/pulls/$PR_NUMBER/comments" \
    | jq -s --argjson rid "$REVIEW_ID" 'add | [.[] | select(.pull_request_review_id == $rid)]' \
    > "$ARTIFACTS_DIR/pr/$(basename "$REPO")/$PR_NUMBER/inline-comments.json"
  ```
  Filtering the PR-wide list by `pull_request_review_id` is deliberate: the per-review endpoint `/reviews/$REVIEW_ID/comments` returns `line: null` and only a diff `position`, which is not a file line.
- Read the diff of files referenced by the review:
  ```bash
  git -C "$REPO" diff origin/$(jq -r .baseRefName < "$ARTIFACTS_DIR/pr/$(basename "$REPO")/$PR_NUMBER/pr.json")...HEAD -- <touched-files>
  ```
- If `docs/analysis/<TICKET_ID>.md` exists, read it into context.
- Write `$ARTIFACTS_DIR/pr/<repo-basename>/<PR-NUMBER>/review-context.md` with sections: `## Ticket Context` (path reference), `## PR Metadata` (url, title, headRefName, baseRefName), `## Target Review` (review id, author, state, body), `## Inline Comments` (each with `path:line — author: body`), `## Affected Files Diff`, `## Existing Analysis Memo` (path reference if present).

CRITICAL: If `REVIEW_ID` does not resolve — no `CHANGES_REQUESTED` review and no `--review-id`, or a `--review-id` matching no entry — STOP. Report `No actionable CHANGES_REQUESTED review on PR #<PR-NUMBER>`.

CONTINUE WITH Phase 2.

### Phase 2: Planning

Produce `$ARTIFACTS_DIR/pr/<repo-basename>/<PR-NUMBER>/feedback-plan.md` with `Scope`, `Wiki Evidence`, `Source Evidence`, and `Out-of-scope rejections` sections, plus `Assumptions` when the run is autonomous.

- Read `review-context.md`.
- Read `docs/llm-wiki/CLAUDE.md` (router) and `docs/llm-wiki/wiki/index.md`. Match the files affected by the review against the index to identify the 0–2 most relevant pages; read their bodies only if a comment touches architecture or a documented contract. Cite paths under `Wiki Evidence`.
- Impact check: when a comment asks to change a shared utility, a public API, or a function with many callers, Grep the symbol's references repo-wide ONCE (word-boundary, test directories included) and cite the hits under `Source Evidence` as `path:line`.
- For every planned change, link it to a specific inline comment or to the review body. Items the review raised but that the agent intentionally will not act on go under `Out-of-scope rejections` with a one-line reason.

CRITICAL: Do not plan a reimplementation. Do not plan changes outside the scope of the review feedback. Do not import unrelated cleanup. If a comment is ambiguous and a load-bearing decision depends on its meaning, use `AskUserQuestion` rather than guessing — unless `--skip-questions` / `--autonomous` is set, which never asks: resolve it by the narrowest reading that satisfies the comment and record the choice under `Assumptions`.

CONTINUE WITH Phase 3.

### Phase 3: Implementation

- Apply only the changes planned in Phase 2.
- Respect prior decisions recorded in `docs/analysis/<TICKET_ID>.md` that are still `Status: ACTIVE`.
- For non-trivial changes (more than 3 files OR any item flagged `risk: high` in the plan), spawn the implementer:
  ```
  Task(
    subagent_type: "implementer-generic",
    prompt: <short brief naming review-context.md path and feedback-plan.md path>
  )
  ```
  The implementer reads the plan and review context, applies the changes, and emits a completion summary captured to `$ARTIFACTS_DIR/pr/<repo-basename>/<PR-NUMBER>/implementer-summary.md`.
- For trivial changes (≤3 files, no `risk: high`), apply inline using `Edit`/`Write`.
- If `docs/analysis/<TICKET_ID>.md` exists, append a new entry to the `Historical Feedback And Decisions` section recording the review id, date, summary of feedback, and the resolution. Do NOT create that file if it does not already exist.

CRITICAL: Do not modify files unrelated to the feedback. After implementation, run `git -C "$REPO" diff --name-only` and verify every modified path appears in the plan's `Scope`. If a file outside scope was touched, STOP and report.

CONTINUE WITH Phase 4.

### Phase 4: Testing

If `--skip-tests` flag: mark completed as "Skipped via flag" and continue.

Otherwise:

- **Resolve the test command from `framework-config.json::stack_profile.command_catalog`** — look up `run_tests`, `run_unit_tests`, `run_integration_tests`, `run_e2e`. The first entry of each operation array is the highest-tier candidate (wrapper → readme → package_manager → ci). Prefer the wrapper (`make tests`, `just test`, `task test`, `./scripts/test.sh`) over per-service package-manager commands when both exist.
- Only fall back to auto-detection (Jest, Pytest, Playwright, Vitest) when the catalog has NO entry for the relevant operation.
- Run the suites that cover the files touched by Phase 3. A full-suite run is optional; targeted runs are preferred for review fixes.

If tests fail: re-spawn the implementer with the failing output OR fix inline if trivial. Max 3 fix iterations.

CRITICAL: If tests still fail after 3 iterations, STOP. Report failure. Do not continue.

CONTINUE WITH Phase 5.

### Phase 5: Quality

- Resolve lint and format commands from `framework-config.json::stack_profile.command_catalog` (`run_lint`, `run_format`). Fall back to auto-detection only if the catalog has no entry.
- Run lint; apply trivial auto-fixes (`--fix`, format-on-save equivalent).
- Re-run lint to confirm a clean state.

CONTINUE WITH Phase 6.

### Phase 6: Commit and Push

- Verify with `git -C "$REPO" status --porcelain` that no files outside the plan's `Scope` are modified. If a stray file appears, STOP and report — never silently commit it.
- Stage planned files only:
  ```bash
  git -C "$REPO" add -- <file1> <file2> ...
  ```
  Never `git add .` / `-A` / `-a`.
- Commit:
  ```bash
  git -C "$REPO" commit -m "fix($TICKET_ID): address review #$REVIEW_ID on PR #$PR_NUMBER" \
    -m "$(cat <<'EOF'
  - <comment 1 summary>
  - <comment 2 summary>
  EOF
  )"
  ```
  Do not skip hooks (`--no-verify` is forbidden).
- Record the new SHA:
  ```bash
  git -C "$REPO" rev-parse HEAD > "$ARTIFACTS_DIR/pr/$(basename "$REPO")/$PR_NUMBER/commits/head.sha"
  ```
- Push:
  ```bash
  git -C "$REPO" push origin "$BRANCH"
  ```
  The PR is updated automatically by the push. Never create a new PR. Never post comments to Jira or GitHub.

CRITICAL:

- If a pre-commit hook fails, surface output verbatim and STOP. The commit did not happen — investigate the hook failure rather than retrying with `--no-verify`.
- If `git push` fails with non-fast-forward, STOP and report. Do NOT `--force` without explicit user consent.

## Error Handling

If a phase fails:

- Do NOT emit a `completed` record for it.
- Report which phase failed and why.
- Phase 0 failure: stop immediately.
- If the LLM wiki (`docs/llm-wiki/*`) turns out to be missing when Phase 2 needs it: stop and instruct the user to rerun `/initialize-project` — no CLI restart can create it.
- Phase 1 failure (no `CHANGES_REQUESTED` review found and no `--review-id`): stop and report.
- Phase 2 failure (cannot derive a scoped plan from the review): stop and report.
- Phase 3 failure (stray file modifications detected): stop and report; user must clean the working tree before retrying.
- Phase 4 failure after 3 fix iterations: stop and report.
- Phase 6 failure (pre-commit hook, non-fast-forward push): stop and report — never bypass.
- Other phases: attempt to recover once, then stop if still failing.

## Skills and Agents Used

- `/fetch-ticket-context` — Phase 1 (Jira tickets only).
- `implementer-generic` agent — Phase 3 and Phase 4 (fixes); only for non-trivial changes.

## Prerequisites

- Project initialized with `/initialize-project` (LLM wiki at the workspace root with `docs/llm-wiki/CLAUDE.md` present).
- Git: the target repo is on `--branch` with a clean working tree, and `origin` is reachable.
- `gh` CLI installed and authenticated against the host named by `--pr-url`.
- For `--from-jira`: Jira MCP configured.
- A review with state `CHANGES_REQUESTED` exists on PR `--pr-url`, or a specific `--review-id` is passed.
