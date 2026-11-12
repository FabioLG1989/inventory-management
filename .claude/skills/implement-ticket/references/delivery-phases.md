# Delivery mechanics — Phases 8–11

Loaded by `/implement-ticket` when **CREATE_COMMIT** resolves true (Phase 8's gate; `--create-pr` implies it). The SKILL body owns each phase's gate — the `run-config.json` read and the skip branch; this file owns what runs once the gate opens. `DELIVERY_REPOS`, the PR set and every workspace-root rule are defined in `multi-repo.md` (single-repo: every set is the one workspace repo).

## Phase 8 — commit each affected repo

For each repo in `DELIVERY_REPOS` — `AFFECTED_REPOS` first, then (`multi`) the workspace root, whose only change is the Phase 7 cheat-sheet edit:

1. List changed files with `git -C <repo> status --porcelain`; exclude `docs/llm-wiki/**` (Phase 9 owns it). (`multi`) At the workspace root list `git -C <root> status --porcelain -- .claude/CLAUDE.md` only: nothing else in the parent folder is ever staged. Empty list → STOP (single-repo) or skip with a note (multi-repo, the root included).
2. `git -C <repo> add -- <files>` then `git -C <repo> commit -m "<message>"`. Never `git add .` / `-A` / `commit -a`. Do not skip hooks.
3. Write the new SHA to `$ARTIFACTS_DIR/commits/<repo-basename>.sha`.

If a pre-commit hook fails in a code repo, surface the output verbatim and STOP. Earlier sibling commits remain for inspection. On the workspace root it is `commit failed` per `multi-repo.md`: report it with the hook output and continue.

## Phase 9 — wiki refresh

Invocation: `/wiki-refresh --commit --ticket <TICKET-ID> --artifacts-dir $ARTIFACTS_DIR` — multi-repo aware; one invocation handles the whole workspace. Drop `--commit` (here and in the delegated prompt below) whenever the workspace root is not in `DELIVERY_REPOS`: the refreshed wiki stays uncommitted instead of landing on the root's current branch. Because `--artifacts-dir` is passed, its preflight reuses this run's `.preflight-ok` marker (tolerating the HEAD moved by the Phase 8 commit) instead of re-running the full flow.

Delegate it to a general-purpose agent, never inline — its git diffs, wiki page bodies, `index.md`, and drift analysis are context-heavy and the orchestrator needs only the outcome. The prompt MUST contain:

- "Read and follow `.claude/skills/wiki-refresh/SKILL.md` exactly, invoked as `/wiki-refresh --commit --ticket <TICKET-ID> --artifacts-dir $ARTIFACTS_DIR`. It is multi-repo aware — one invocation handles the whole workspace."
- "Return ONLY: `STATUS: <fresh|changed|commit-failed|hard-error> ; new-service: <name|none> ; summary: <one-line>`."

The commit happens inside the delegated agent; downstream phases read git state, not its context.

Branch on the outcome:

- `hard-error` (`.state.json` missing, AI parse failure, or page update failed) → STOP and report. Do NOT create the PR.
- `commit-failed` (pages and `.state.json` written, the commit's pre-commit hook failed) → `single`: STOP and report, as for `hard-error`. `multi`: `commit failed` on the workspace root per `multi-repo.md` — report it with the hook output, mark Phase 9 completed and continue.
- `new-service: <name>` (not `none`) → carry the suggestion into the Phase 10 PR body; do NOT auto-invoke `/wiki-add-service` — the user decides whether the new service is worth documenting now.
- `fresh` or `changed` (no changes, or pages refreshed) → mark Phase 9 completed with the summary and continue. In `multi` the wiki commit lands on the workspace root's `<branch>`; Phase 10's PR set picks it up.

## Phase 10 — push + PR creation

The PR set (`multi-repo.md`) decides what gets a PR, NOT `WORKSPACE_MODE` (a `multi` workspace touching one child with no root commit still gets a single PR). Every PR set, one repo or many, goes through the fanout:

`/repo-fanout-pr --no-commit --repos <csv> --branch <branch> --ticket <TICKET-ID> --artifacts-dir $ARTIFACTS_DIR [--body-append $ARTIFACTS_DIR/pr/body-append.md]` (`<csv>` = the PR set joined by commas, absolute paths, no spaces — the workspace root is listed like any child). It detects each repo's git host from its origin remote, asserts the tree is clean + branch ahead of base, pushes, and opens one PR per repo with `gh`, `glab` or `az` — code PRs cross-linked, the workspace-root PR linking to them, never the reverse. Each PR targets the recorded fork point (`git -C <repo> config branch.<branch>.gh-merge-base`), passed explicitly; unset → the fanout resolves it per repo and prints the guess. A CLI never falls through to the repository's default branch. When Phase 5 classified any test failure as suspected pre-existing, first write `$ARTIFACTS_DIR/pr/body-append.md` — a `## Suspected pre-existing test failures` section naming each one and why (outside every entry's scoped files, outside the change's impact radius) — and pass it with `--body-append`; that classification is unverified, and the PR reviewer is the only one who can reject it. For every **UNTESTED** scope in `verification_env`, append a `## Tests not run — UNTESTED` section naming the blocker and attempted setup, and pass `--body-append`. List supplemental checks separately.

PR creation is delegated to a general-purpose agent — the fanout logic is context-heavy and the orchestrator needs only the resulting URL(s). The prompt reads `.claude/skills/repo-fanout-pr/SKILL.md` and invokes it with the flags above; end it with "Return ONLY: `STATUS: <ok|partial|error> ; result-path: fanout/result.json ; pr-urls: <csv>`." After the agent returns, record every PR URL; a root entry in `$ARTIFACTS_DIR/fanout/result.json` with `pr_url: null` is reported as `root commits left local on <root>:<branch> (<its errors[] reason>)` and the run continues.

**Visual evidence (github.com only, best-effort):** three repo-independent preconditions gate the whole step, checked in this order — the repo's origin remote host (`git -C <repo> remote get-url origin`) is exactly `github.com` (else `not GitHub`), `$ARTIFACTS_DIR/screenshots/` holds PNGs (else `no screenshots`), and `gh pr edit --help` lists `--attach` (else `gh < 2.99`). For each PR whose repo owns the screenshotted UI (multi-repo: judge from the plan's `Affected Repositories`; unsure → every PR), resolve that PR's own `<owner>/<repo>` from the `repos[].remote` sitting beside that `pr_url` in `$ARTIFACTS_DIR/fanout/result.json`, else from `gh repo view --json nameWithOwner -q .nameWithOwner` run in `<repo>` — then gate that PR alone on its own `gh repo view <owner>/<repo> --json visibility -q .visibility` not returning `PUBLIC` (public asset URLs need no authentication; the reason is `public repo`). One repo's visibility never authorises a sibling repo's PR. A non-zero exit from either call skips that PR rather than falling through to the attach — `owner/repo unknown` for the resolution, `visibility unknown` for the probe. When the gate passes, run exactly once:

`gh pr edit <URL> --attach '<abs>/screenshots/diff/<f>.png#diff <f>' …` — `$ARTIFACTS_DIR/screenshots/diff/` first, then `$ARTIFACTS_DIR/screenshots/after/`, then `$ARTIFACTS_DIR/screenshots/before/`, ascending lexicographic by filename within each directory; the first ≤ 12 files of that sequence, each < 10 MB, absolute paths, and the outcome line carries the omitted count when the cap truncates. The template's alt text is ASCII with spaces, `-`, `_` and `.`, never `'` or `#`, and the guard covers the whole argument, not just the basename — skip the whole step with the reason `unsafe artifacts path` when `$ARTIFACTS_DIR` carries `'` or `#`, and skip a single screenshot when only its basename does. gh appends them to the existing body. Never retry or substitute another command on a non-zero exit: uploads cannot be undone and the PR already exists; the reason is `attach failed`. Append `visual-evidence: attached <N> files to <URL>` or `not attached (<reason>)` to `$ARTIFACTS_DIR/pr/visual-evidence.txt`, one line per PR — Phase 11's review loop runs between here and Phase 12, so the outcome has to survive on disk.

Do not proceed if any expected PR was not created: `STATUS: partial` or `error` (a code-repo PR missing) is treated as failure; the root's PR is never expected — the fanout records a failed root in `errors[]` and still exits 0.

## Phase 11 — review loop

For each PR URL Phase 10 produced for an `AFFECTED_REPOS` entry (single-repo: one URL; multi-repo: one per affected child — the workspace root's PR, matched by `repos[].path` in `$ARTIFACTS_DIR/fanout/result.json`, is not reviewed):

- Run `/pr-reviewer --pr-url <URL> --jira-key <TICKET-ID> --mode automated --artifacts-dir "$ARTIFACTS_DIR" [--repos <abs-repo-path>] [--quick]`. Its `specialist-security-style` agent covers diff-level security; for a deeper SAST pass, engineers run `/security-review` standalone.

  Run it inline — it delegates to its own specialist agents.

  `--artifacts-dir "$ARTIFACTS_DIR"` is the absolute, workspace-root-anchored ticket dir from Phase 0. The skill writes its output tree UNDER it (`$ARTIFACTS_DIR/pr/...`) — never inside a child repo, even though `--repos` points at one.
- If blocking issues are found: map each finding's file path back to its owning service (longest-prefix on `stack_profile.services[].path`); re-dispatch ONLY the `Recommended Implementers` entries whose `Scoped Files` overlap with the finding set, in the original listed order; re-run tests per Phase 5, update the PR testing section if outcomes changed, and re-review.
- Exit when approved or the cap is reached: max `$MAX_REVIEW_ITERATIONS` fix cycles (the SKILL body reads it from `run-config.json`; `0` posts the review and runs none), **global** across all PRs, all implementers, and all repos. If the cap is reached with unresolved issues, report them and proceed to Phase 12.
- Before recording `completed`, assert `posted.json` exists in each reviewed PR's review dir (`$ARTIFACTS_DIR/pr/review/`; multi-repo `$ARTIFACTS_DIR/pr/<repo-basename>/review/`). Missing → the phase still completes, its note `review not posted: <URL> — <first line of post-error.txt>`; never re-run the reviewer for it.

In a multi-repo workspace, run the review once per PR URL — each invocation passes the corresponding repo path via `--repos <abs>`; fix commits land in the corresponding repo (`git -C <repo>`).

**Multi-repo aggregation (after the loop):** when more than one PR URL was reviewed for the same ticket, run `/pr-reviewer --aggregate --jira-key <TICKET-ID> --artifacts-dir "$ARTIFACTS_DIR"` inline — emits `$ARTIFACTS_DIR/pr/cross-repo-summary.{json,md}` describing cross-repo concerns (API contract mismatches, schema skew, shared-dep conflicts) and a recommended merge order. Skip the aggregation pass in single-repo mode.
