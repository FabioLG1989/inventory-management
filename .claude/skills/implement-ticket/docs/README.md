# implement-ticket

End-to-end ticket execution through a wiki-aware workflow. Phase 1 resolves the run mode once — an interactive run scans the ticket and interviews the developer to decide `simple` or `standard`; an autonomous run scans, settles forks by evidence, and resolves `simple` only when every strict criterion holds on that evidence alone; a pinned run resolves `standard` without the scan — and resolves the delivery gates in the same pass, so the phase list is known before any work is bought. A plan gate then obtains a contract-valid implementation plan — delegating to `/create-implementation-plan` for requirement sources, or accepting a ready-made plan via `--from-plan` — and the execution phases run it: branch, implementation, testing, visual verification, documentation, optional commit + wiki refresh (opt-in via `--create-commit` or `--full`), optional push (opt-in via `--push-branch`), optional PR creation + review (opt-in via `--create-pr` or `--full`), and the final report.

The scan allows focused reads and probes while they narrow a specific question about placement, behavior, impact, or verification; read count alone does not force `standard`. It stops when the verdict has enough evidence, a hard rule fires, or investigation expands or stops narrowing. Placement alternatives, the selected option, and deciding evidence stay under `## Scan Findings`; all existing `simple` eligibility criteria apply.

Installed dependencies do not decide run mode. Setup uses the catalog or repository instructions once per dependency root (600 s total). Unverified scopes are **UNTESTED** in the final report and PR body; static checks are supplemental.

## Invocation

The skill is user-invokable — invoke it directly using slash syntax (`/` in Claude Code, `$` in Codex CLI):

```
/implement-ticket --from-jira PROJ-123
/implement-ticket --from-jira https://your.atlassian.net/browse/PROJ-123
/implement-ticket --from-linear ENG-123
/implement-ticket --from-markdown ./specs/PROJ-123.md
/implement-ticket --from-input "Fix login validation bug where empty password bypasses auth"
/implement-ticket --from-plan ./PROJ-123-implementation-plan.md
```

With modifiers:

```
/implement-ticket --from-jira PROJ-123 --create-pr
/implement-ticket --from-jira PROJ-123 --skip-questions --skip-tests --skip-visual
```

## Flags

Canonical set, defaults, and the config keys live in [`FLAGS.md`](./FLAGS.md).

| Flag | Description | Example |
|---|---|---|
| `--from-jira <KEY-OR-URL>` | Implement from a Jira ticket | `--from-jira QAF-42` or `--from-jira https://company.atlassian.net/browse/QAF-42` |
| `--from-linear <ISSUE-ID>` | Implement from a Linear issue | `--from-linear ENG-123` |
| `--from-input "<desc>"` | Implement from a plain-text description | `--from-input "Add rate limiting to /api/login"` |
| `--from-markdown <PATH>` | Implement from a markdown SDD ticket | `--from-markdown ./specs/QAF-42.md` |
| `--from-plan <PATH>` | Execute a ready-made plan (validated, normalized if loose; always non-interactive) | `--from-plan ./QAF-42-implementation-plan.md` |
| `--skip-questions`, `--autonomous` | Autonomy switch (identical aliases) — makes the WHOLE run non-interactive: no phase asks a question or waits on a human; the run-mode scan still runs, settles forks by evidence, and admits `simple` only on its strict evidence bar. Forwarded to `/create-implementation-plan` as `--skip-questions`, which skips both its question waves | — |
| `--critique` | Forwarded to `/create-implementation-plan`: opt in to the adversarial critique step. Off by default; also enabled via the `critique` config key (`--skip-critique` is a deprecated no-op) | — |
| `--skip-tests` | Skip all test execution — Phase 4's implementer scoped runs and Phase 5; also a project default via the `skip_tests` config key | — |
| `--skip-visual` | Skip Phase 6 and Phase 3's BEFORE screenshots; also a project default via the `skip_visual` config key | — |
| `--create-commit` | Opt in to the local commit (Phase 8) and wiki refresh (Phase 9). Off by default — the run stops after docs, leaving changes uncommitted. Implied by `--push-branch` and `--create-pr` | — |
| `--push-branch` | Opt in to pushing the branch (Phase 10) without opening a PR. Off by default; implies `--create-commit` | — |
| `--create-pr` | Opt in to PR (Phase 10) and PR review (Phase 11). Off by default; implies `--push-branch` and `--create-commit` | — |
| `--skip-pr-review` | Skip Phase 11 (the PR is still pushed and opened); also a project default via the `skip_pr_review` config key | — |
| `--standard` | Pin a standard run, outranking everything, and skip the scan and interview; also unlocks Phase 5's full test matrix | — |
| `--full` | Turn on every optional step: pin a standard run (skipping the scan and interview), the adversarial critique, the full test matrix, the commit + wiki refresh, the push, and the PR + review. A live skip flag still removes its own step | — |
| `--skip-update-check` | Skip framework-update detection in the Phase 0 preflight | — |
| `--branch <name>` | Reuse a feature branch the caller already checked out (an orchestrator, a CI job) instead of creating one; the caller records its PR base in `git config branch.<name>.gh-merge-base` | — |
| `--skip-pr` | Deprecated no-op (PR is off by default) | — |

Exactly one input-source flag (`--from-jira` / `--from-linear` / `--from-input` / `--from-markdown` / `--from-plan`) is required. Flags are space-separated in a single argument string. The full modifier contract (defaults, polarity, config keys, run modes) lives in [`FLAGS.md`](./FLAGS.md).

## What happens when you invoke it

One `SKILL.md` serves both providers: the sync pipeline substitutes the provider placeholders (config dir, temp dir, instruction file, provider name) and writes it to the target project. Delegation is described generically — each provider runs the named agent the way its runtime does — and the skill reads its references lazily: the run-mode scan only on an unpinned run, the multi-repo rules only in a multi-repo workspace, the framework-update prompt only when one is due, and the delivery mechanics only once a commit was requested.

| Phase | Work | Key agents/skills |
|---|---|---|
| 0 | Flag parsing + deterministic preflight (`ensure-context.sh`: workspace topology + tool defaults) + git-clean check (multi-repo: every child, plus the root's wiki and cheat-sheet paths; a dirty root is reported, never fatal) + framework-update notice | — |
| 1 | Resolve run mode — ticket context, delivery gates, `run-config.json`; unpinned runs add the pre-plan scan and the micro-plan at `simple`, interactive ones the developer interview | `/fetch-ticket-context` |
| 2 | Obtain Plan — delegate planning or validate/normalize a `--from-plan` file | `/create-implementation-plan` |
| 3 | Environment setup — reuse a prepared branch or create one in every delivery repo (multi-repo: affected children plus, when a commit is enabled, the workspace root, where a failed root branch step is reported, never fatal), taking a name free in every repo when the one derived is taken (an existing branch is reused only through `--branch`), and record its PR base; BEFORE screenshots only when visual verification will run; prepare unresolved verification commands once per dependency root using the catalog or a recipe derived from repository manifests, contributor docs and CI (600 s total); record cwd, environment overrides, setup evidence and readiness in `run-config.json::verification_env` | — |
| 4 | Implementation | `implementer-generic` agent |
| 5 | Testing (the catalog's single `run_tests` entry covering the change, run non-interactively; full matrix under the `--full` or `--standard` flag; up to 3 fix iterations; skipped when `skip_tests` resolves true — at `simple`, lint still runs) | `implementer-generic` on failure |
| 6 | Visual verification (skipped with no frontend changes, `skip_visual`, or no BEFORE baseline) | `ui-visual-testing`, `visual-verifier` agent |
| 7 | Documentation updates | `/doc-updater` |
| 8 | Implementation commit (per affected repo, plus the workspace root's cheat-sheet edit in multi-repo; opt-in via `--create-commit` or `--full`) | — |
| 9 | Wiki refresh — committed on the feature branch (multi-repo: the workspace root's; opt-in via `--create-commit` or `--full`) | `/wiki-refresh` |
| 10 | Push (opt-in via `--push-branch`) + PR creation (opt-in via `--create-pr` or `--full`) for every repo with commits — multi-repo: each affected child (cross-linked) plus a workspace-root PR (wiki/cheat-sheet) that links to the code PRs; a failed root push or PR is reported, never fatal | `/repo-fanout-pr` (multi-repo) |
| 11 | Review loop (code PRs only — the workspace-root PR is not reviewed; up to `max_review_iterations` fix cycles, default 3, `0` posts the review and never fixes; an unposted review is reported, not fatal; skipped when `skip_pr_review` resolves true; bug-logic and security specialists only at `simple`) | `/pr-reviewer`, `implementer-generic` |
| 12 | Final report | — |

The run mode reduces work only at Phases 2, 4, 5 and 11, and only as described in [`../references/run-mode.md`](../references/run-mode.md) — the single owner of the scan, the interview and the reduction table.

Each phase re-emits the `Workflow Progress:` checklist and appends an `in_progress` / `completed` / `failed` JSONL record to `progress.jsonl` under the run's artifacts directory through the `qaf_progress` helper, which a resumed run reads to skip completed phases.

## Prerequisites

- Project initialized with `/initialize-project`
- `/create-implementation-plan` skill installed and synced (the plan gate delegates to it)
- Git repository with remote configured — multi-repo: the parent may be a plain folder (its wiki/cheat-sheet changes stay uncommitted) or a git repo with an `origin`; a root without one, or whose push or PR fails, is reported and its wiki/cheat-sheet commits stay local while the code PRs proceed
- For `--from-jira` / `--from-linear`: the tracker's MCP server configured (consumed by `/fetch-ticket-context` in Phase 1)
- For `--from-plan`: no tracker MCP needed — the plan file is the only input
- LLM wiki at `docs/llm-wiki/` (generated by `/initialize-project`)
- For Phase 10 PR creation: the CLI matching each repo's host, authenticated — `gh` for GitHub (2.99+ attaches visual evidence to private/internal github.com PRs; not GitHub Enterprise Server), `glab` for GitLab, `az` with the `azure-devops` extension for Azure DevOps
- `--branch <name>`: a caller that checked out the feature branch beforehand (an orchestrator, a CI job) passes its name; Phase 3 reuses it and Phase 10 opens the PR against `git config branch.<name>.gh-merge-base` — the key `gh pr create` reads when `--base` is absent — which the caller sets when preparing the branch

## Configurable defaults

Every config key resolves per run, highest wins: the CLI switch (`max_review_iterations` has no flag), then the developer's git-ignored `<config-dir>/.framework-defaults.local.json`, then the project's `framework-config.json` → `tool_defaults`, then the shipped default. `initialize-project` seeds the block with shipped defaults on a first run and on a re-run carries every value the project already set forward, backfilling only the keys it lacks; `sync-framework-resources` applies the same rule. Neither flow overwrites a value a team already chose, so re-initializing never resets your defaults; a project predating a key simply falls through to the shipped default.

## Artifacts

All artifacts for a ticket live under the provider's temp dir (`.claude-temp/` for Claude, `.codex-temp/` for Codex):

```
<TEMP_DIR>/tickets/<TICKET_ID>/artifacts/
├── .preflight-ok         # Phase 0 marker (git_head, workspace_root, workspace_mode, child_repos — children only — resolved_defaults)
├── run-config.json       # Phase 1 (mode, source, reason, autonomous, max_review_iterations, gates, scan); Phase 3 adds verification_env (setup and test outcomes)
├── progress.jsonl        # one record per phase transition, written by qaf_progress
├── context/              # ticket-context.md (Phase 1, incl. interview answers)
├── plans/                # implementation-plan.md (+ plan-critique.json when the critic ran)
├── coverage/             # Phase 5 coverage reports (per repo in multi-repo)
├── screenshots/          # Phase 6 (before/after/diff); attached to the GitHub PR in Phase 10
├── commits/              # Phase 8 commit SHAs per delivery repo
└── pr/                   # Phase 11 review outputs + Phase 10 visual-evidence.txt
```

This directory is git-ignored — artifacts never pollute PRs.
