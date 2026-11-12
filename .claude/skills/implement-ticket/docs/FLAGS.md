# implement-ticket — Flag Contract

Single source of truth for the `/implement-ticket` flag surface. `SKILL.md` and the website docs defer to this table. The `(config key, default)` column names each flag's key in the layered-default hierarchy (see below), so a project or developer can override the default without passing the flag; `—` means the flag has no config key.

## Input source — exactly one (none, or more than one, is an error)

| Flag | Purpose |
|------|---------|
| `--from-jira <TICKET-ID>` | Implement from a Jira ticket |
| `--from-linear <ISSUE-ID>` | Implement from a Linear issue |
| `--from-input "description"` | Implement from a plain-text description |
| `--from-markdown <PATH>` | Implement from a markdown SDD ticket |
| `--from-plan <PATH>` | Execute a ready-made plan (always non-interactive) |

## Modifiers

| Flag | Default | Polarity | Forwarded to `/create-implementation-plan` | Gates | Config key (default) |
|------|---------|----------|---------------------------------------------|-------|------------------------|
| `--skip-questions` / `--autonomous` | fully interactive run | opt-out | yes (as `--skip-questions`) | **the whole run** — every ask site in every phase, and the forwarded plan gate | — |
| `--critique` | **adversarial critique OFF** | **opt-in** | yes | Phase 2 plan gate | `critique` (default `false`, under the `create-implementation-plan` tool section) |
| `--skip-tests` | testing ON | opt-out | no | Phase 4 (implementer scoped runs) **and** Phase 5 — at `simple`, Phase 5's lint operation still runs | `skip_tests` (default `false`; `true` skips) |
| `--skip-visual` | visual verification ON (auto-skips with no frontend changes) | opt-out | no | Phase 3 (BEFORE screenshots) **and** Phase 6 | `skip_visual` (default `false`; `true` skips) |
| `--create-commit` | **commit + wiki OFF** | **opt-in** | no | Phase 8 (implementation commit) **and** Phase 9 (wiki refresh) | `create_commit` (default `false`) |
| `--push-branch` | **push OFF** | **opt-in** | no | Phase 10 (push only — no PR, no review) | `push_branch` (default `false`) |
| `--create-pr` | **PR + review OFF** | **opt-in** | no | Phase 10 (push + PR) **and** Phase 11 (PR review) | `create_pr` (default `false`) |
| `--skip-pr-review` | PR review ON (only reached when a PR was created) | opt-out | no | Phase 11 | `skip_pr_review` (default `false`; `true` skips) |
| `--standard` | run mode resolved per ticket; single `run_tests` command | opt-out (pins `standard`) | no | Phase 1 (run mode) **and** Phase 5 (full test matrix) | — |
| `--full` | run mode resolved per ticket; single `run_tests` command; critique, commit, push and PR off | opt-in — pins `standard` **and** forces `critique`, `create_commit`, `push_branch` and `create_pr` on | yes (as `--critique`) | Phase 1 (run mode + gates), Phase 2 (critique), Phase 5 (full matrix), Phases 8–11 | — |

`--skip-questions` (alias `--autonomous`, identical) is the **autonomy switch**, and it is the only modifier whose scope is the run rather than a phase: with it set, no phase asks the developer anything and no phase waits on a human. Each ask site names the answer an autonomous run takes; a site with none STOPs. Phase 1 records it top-level in `run-config.json` as `autonomous` (not under `gates` — it has no config key, so there is no baseline to overlay), and later phases read it there. It is deliberately **not** settable as a project or personal default: autonomy is asked for per invocation, never inherited.

`--create-pr` **implies `--push-branch`**, which **implies `--create-commit`** — a PR needs a pushed branch and a push needs a commit, so each flag turns on the rungs below it.

`--skip-pr` and `--skip-critique` are **deprecated no-ops**: PR creation and the adversarial critique are already off by default, so they do nothing. Each is accepted with a one-line notice.

`--full` turns on **every optional step in this table**, and never turns back on a step a live skip flag removed — `--skip-tests`, `--skip-visual`, `--skip-pr-review` and `--skip-questions` each still drop their own step.

**Unattended delivery.** Two routes leave no human in the loop: `--skip-questions`, and `--from-plan` (non-interactive by definition — the plan gate normalizes it with `--skip-questions`). `--full` on either commits, pushes and opens the PR unattended. The `Enabled by --full:` line prints in Phase 1, so it informs a developer at the terminal and nobody else; the durable record of what a run was allowed to do is `gates` in `run-config.json`, resolved before any step is bought.

`--standard` pins `standard` and unlocks the full test matrix — nothing else. `--full` + `--standard` is not a conflict: the run is identical to `--full` alone.

`critique` lives under the `create-implementation-plan` tool section because that skill owns the behavior: it resolves the baseline itself from `.preflight-ok`, so standalone `/create-implementation-plan` runs honor the config too; `/implement-ticket` only forwards the `--critique` flag.

## Resolution hierarchy

Each `(config key)` default is resolved per-argument in one fixed order, highest wins:

1. **CLI switch** — the flag passed on the command for that run (e.g. `--create-pr`). Opt-in flags can only force their key on.
2. **Personal** — the developer's `<config-dir>/.framework-defaults.local.json`, git-ignored (never committed, never affects teammates). Same shape as the config block: `{ "implement-ticket": { "create_pr": true } }`.
3. **Project** — `framework-config.json` → `tool_defaults.implement-ticket` (the committed team default).
4. **Shipped** — the value in `scripts/tool-defaults.json` (this table's default column).

The deterministic preflight (`ensure-context.sh`) resolves levels 2-4 once and stamps the baseline into `.preflight-ok` under `resolved_defaults`; **Phase 1 overlays level 1 and writes the outcome to `run-config.json` under `gates`**, which is what Phases 3 through 6, 8, 10 and 11 read. A tool with no section or an unreadable/unrecognized value falls through to the next source with no error — so `create_commit`, `push_branch` and `create_pr` default to off everywhere they are not set. How `initialize-project` and `sync-framework-resources` seed and carry the block forward is described in [`README.md`](./README.md).

## Config-only keys

No flag: resolved through levels 2-4 above and written top-level in `run-config.json`, never under `gates`.

| Key | Default | Gates | Effect |
|---|---|---|---|
| `max_review_iterations` | `3` | Phase 11 | fix cycles (re-dispatch → re-test → re-review) after a blocking PR review; `0` posts the review and never auto-fixes. Any value that is not a non-negative integer resolves to `3` |

## Run mode

`--full` and `--standard` are the only overrides of a decision the run otherwise makes for itself, once, in **Phase 1**. Either also unlocks Phase 5's full test matrix (unit with coverage, integration, E2E); without one the run executes the command catalog's single `run_tests` entry covering the change. The resolution order, the pre-plan scan, the developer interview behind the `simple` verdict, and the table of what `simple` removes per phase all live in `.claude/skills/implement-ticket/references/run-mode.md` — the single owner; the persisted `run-config.json` shape lives in the skill's Phase 1. This table's job stops at the flags.

Scoping is **always on**: no config key enables or disables it, and there is no `--simple` flag — `simple` is confirmed by the developer or, autonomously, earned on the scan's evidence bar (the reference's Verdict), never forced. An autonomous run (`--skip-questions` / `--autonomous`) skips the interview; its scan still runs, and whenever the verdict is `standard` its settled findings bind the planner.

## Default run

With no modifiers a run resolves its mode, implements the plan, runs the project's preferred `run_tests` command (the full matrix needs `--full` or `--standard`; `skip_tests` resolving true skips all test execution instead) and (when frontend changes exist and `skip_visual` resolves false) visual verification, and updates documentation — then stops, leaving all changes uncommitted in the working tree. The plan gate's adversarial critique requires `critique` to resolve true (via `--critique` or a team/personal default). The local commit and wiki refresh require `create_commit` to resolve true (via `--create-commit` or a team/personal default); the push requires `push_branch` to resolve true (via `--push-branch` or a team/personal default), which implies `create_commit`; PR and PR review require `create_pr` to resolve true (via `--create-pr` or a team/personal default), which implies `push_branch`; `skip_pr_review` resolving true skips the review alone. `--full` resolves all four true at once — it is the single flag that turns every optional step on.
