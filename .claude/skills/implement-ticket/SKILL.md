---
name: implement-ticket
version: 6.0.0
last-updated: 2026-10-15
description: Implements a ticket end-to-end from a Jira or Linear ID, a markdown spec, a plain-text description, or a ready-made plan — run mode, plan gate, implementation, tests, visual checks, docs, and opt-in commit, wiki refresh, push, PR and review. Single- and multi-repo workspaces.
argument-hint: '[--from-jira TICKET-ID | --from-linear ISSUE-ID | --from-input "description" | --from-markdown PATH | --from-plan PATH] [--skip-questions | --autonomous] [--critique] [--skip-tests] [--skip-visual] [--create-commit] [--push-branch] [--create-pr] [--skip-pr-review] [--standard] [--full] [--skip-update-check] [--branch NAME]'
disable-model-invocation: true
---

# Implement Ticket

Input: $ARGUMENTS

Implement the ticket described above: resolve how much work the run earns, obtain a contract-valid implementation plan through the plan gate, then execute it.

## Flags

Input source — exactly ONE of (more than one, or none, is an error; fail with a clear message naming the conflicting flags):
- `--from-jira <TICKET-ID>` — implement from a Jira ticket (e.g., PROJ-123)
- `--from-linear <ISSUE-ID>` — implement from a Linear issue (e.g., ENG-123)
- `--from-input "description"` — implement from a plain-text description
- `--from-markdown <PATH>` — implement from a markdown SDD ticket
- `--from-plan <PATH>` — execute a ready-made plan: validate it against the plan contract, normalize via `/create-implementation-plan` if loose or incomplete; always non-interactive

Modifiers — the canonical contract (default, polarity, whether it is forwarded to `/create-implementation-plan`, the phase it gates, its config key, and the layered resolution order behind that key) is defined once in `.claude/skills/implement-ticket/docs/FLAGS.md`. Read it there; do not restate it here. Accepted modifiers: `--skip-questions` / `--autonomous` (identical), `--critique`, `--skip-tests`, `--skip-visual`, `--create-commit`, `--push-branch`, `--create-pr`, `--skip-pr-review`, `--standard`, `--full`, and the deprecated no-ops `--skip-pr` and `--skip-critique` (accept each with a one-line notice). An opt-in flag is a level-1 override that can only force its key on; when absent, the resolved baseline decides.
- `--skip-update-check` — skip framework-update detection in the Phase 0 preflight: run it as `QAF_SKIP_UPDATE_CHECK=1 qaf_run_preflight "$TICKET_ID"`. No effect on any other phase.
- `--branch <name>` — the feature branch is already checked out in every affected repo by the caller (an orchestrator, a CI job): Phase 3 reuses it instead of creating one. The caller records the PR base beforehand with `git config branch.<name>.gh-merge-base <base>`.

## Autonomy — `--skip-questions` / `--autonomous`

Either flag (they are identical) makes the WHOLE run autonomous, not just the plan gate: no phase asks the developer anything or waits on a human. Every ask site below names the answer an autonomous run takes — take it, record it in the run's artifacts, and continue; a site with no such answer STOPs with the reason. Phase 1 persists the decision as `autonomous` in `run-config.json`; later phases read it there rather than re-parsing `$ARGUMENTS`. Forward it to sub-skills as `--skip-questions`. The flag is the only autonomy signal, never inferred from the environment; an ask that reaches no developer STOPs naming the open question and the flag — except at a site that names a no-answer default, which takes it and continues: the Phase 0 update notice logs and moves on, and the run-mode interview resolves `standard`.

## Command Discipline

**Turn discipline.** A response with no tool call ends a headless run (CI, SDK, orchestrator) and kills every command it spawned. Whether a developer is watching is not detectable, so always assume none is: until Phase 12 completes or an Error Handling rule says STOP, every response MUST contain a tool call, except one that waits for a backgrounded delegation (see Delegation).

**Timeouts.** Every command that may run long gets an explicit timeout on the FIRST attempt — the shell tool's own timeout parameter, never the `timeout(1)` binary. Installs, builds and the plan's named test command get the maximum the tool accepts (`timeout: 600000`), and work that may exceed it is split beforehand (per service, directory or suite); any other verification command gets 180 s. A command that exceeds its timeout is over: record it as `timed out after <N>s` — a verification command becomes `unrunnable` — and move on. Never re-run it (the same script under another name or with extra arguments is a re-run), wait on it, poll for it (`sleep`, `Monitor`, `ScheduleWakeup`, loops), or read a backgrounded result: the notification may never arrive. Quote glob patterns passed to grep/find, and write file lists inline: under zsh an unmatched glob aborts the command and a list held in a variable reaches the tool as one path.

## Artifact Paths

All artifacts live at `<workspace-root>/.claude-temp/tickets/<TICKET_ID>/artifacts/`. `<workspace-root>` is the folder containing `.claude/` — in a multi-repo workspace the PARENT folder, never a child repo. Never write artifacts anywhere else (no `.claude/artifacts|screenshots|decisions/`, no `orchestration/artifacts/`, no child-repo `.claude-temp/`).

Resolve `ARTIFACTS_DIR` with this snippet at the start of every phase that needs the path — never park it in a shell variable: each phase runs its own shell, and repo operations use `git -C <repo>` so cwd never leaves the workspace root.

```bash
source ".claude/scripts/lib/bootstrap-preflight.sh"
qaf_resolve_artifacts_dir "$TICKET_ID"
```

Never assign a bare relative `.claude-temp/...` — it resolves against cwd and can leak into a child repo. Pass `--artifacts-dir "$ARTIFACTS_DIR"` to the sub-skills that accept it (`/wiki-refresh`, `/repo-fanout-pr`, `/pr-reviewer`); `/create-implementation-plan` takes `--ticket-id "$TICKET_ID"` and derives the identical path; `/fetch-ticket-context` reads the exported `ARTIFACTS_DIR`.

## Delegation

The agents under `.claude/agents/` (`planner`, `implementer-generic`, `visual-verifier`) and the general-purpose agent carry their own methodology. Delegate with a short prompt of paths and scope, never bodies; the agent reads its inputs itself and returns one line or the receipt it defines. A delegation the next step depends on runs in the foreground and is awaited. If it runs in the background anyway, await it with the runtime's wait tool; with none, end the turn without a tool call — its completion notice resumes the run, headless included — and never poll it. Dispatch independent entries concurrently: start them together in one turn and await them the same way. Context-heavy work — the ticket fetch, documentation maintenance, the wiki refresh, PR creation — is delegated so its reads never enter this context; `/pr-reviewer` runs inline because it delegates to its own specialists. Re-dispatch an entry by messaging its earlier implementer when the runtime can, and send only the failures or findings to fix: that agent already holds the plan and its own edits.

## Workspace

`WORKSPACE_MODE` (`single`|`multi`) and `child_repos` are written into `.preflight-ok` by Phase 0 — read them back (`jq -r .workspace_mode "$ARTIFACTS_DIR/.preflight-ok"`), never re-derive them from the tree. Every working-tree operation targets one repo with `git -C <repo>` (wrappers likewise: `make -C <repo>` or the tool's `--dir`); the wiki stays workspace-scoped at the root. In `single`, `AFFECTED_REPOS`, `DELIVERY_REPOS` and the PR set are all `[<workspace-root>]`. In `multi`, `.claude/skills/implement-ticket/references/multi-repo.md` defines the three sets and the workspace-root rules: read it in Phase 0, in the command that reads the marker, and apply it wherever a phase names one of the sets.

## Progress

Print this checklist before Phase 0 and again at the start of every phase with the states updated — `[x]` complete, `[>]` running, `[ ]` not started; a phase its flags or gates removed checks off with the reason (`- [x] Phase 5: Testing (skipped: --skip-tests)`):

```
Workflow Progress:
- [ ] Phase 0: Preflight
- [ ] Phase 1: Resolve Run Mode
- [ ] Phase 2: Obtain Plan
- [ ] Phase 3: Environment Setup
- [ ] Phase 4: Implementation
- [ ] Phase 5: Testing (removed by --skip-tests)
- [ ] Phase 6: Visual Verification (removed by --skip-visual or no frontend change)
- [ ] Phase 7: Documentation Update
- [ ] Phase 8: Implementation Commit
- [ ] Phase 9: Wiki Refresh (gated: create_commit)
- [ ] Phase 10: PR Creation (gated: push_branch for the push, create_pr for the PR)
- [ ] Phase 11: Review Loop (gated: create_pr, removed by --skip-pr-review)
- [ ] Phase 12: Final Report
```

The checklist dies with the session; the log must not. `qaf_progress "$TICKET_ID" <phase> "<name>" <status> ["<note>"]` (defined by `bootstrap-preflight.sh`) appends one record to `$ARTIFACTS_DIR/progress.jsonl`, resolving the path itself; a resumed run reads that file, never memory, to decide which phases already completed. Never spend a tool call on it: a phase's first command starts with `qaf_progress … in_progress &&`, and the command that verifies its outputs ends with `&& qaf_progress … completed`. A phase removed by a flag or by the mode emits both in one call with a note naming why; a phase that fails emits `failed` with the reason and STOPs — never `completed`. Keys are integers; a delegated skill's `2.<N>` records report against Phase 2 and never add to the total.

## Phases

Run them in order; a phase starts only after the previous one recorded `completed`. Each `### Phase N` section is the single source of truth for what that phase does and produces.

### Phase 0: Preflight

Parse `$ARGUMENTS` for the five input flags and the modifiers listed under `## Flags`. Exactly one input flag must be present — zero or more than one → STOP with a clear error naming the conflicting or missing flags. Derive `TICKET_ID` per `.claude/skills/create-implementation-plan/references/ticket-id-derivation.md`, and pin it through `--ticket-id` whenever Phase 2 delegates, so producer and consumer resolve the same `$ARTIFACTS_DIR`.

**Preflight.** `qaf_run_preflight` resolves the workspace-root `$ARTIFACTS_DIR` via `project_path()` and runs `ensure-context.sh` anchored to it (never a child repo):

```bash
source ".claude/scripts/lib/bootstrap-preflight.sh"
qaf_progress "$TICKET_ID" 0 Preflight in_progress && qaf_run_preflight "$TICKET_ID"
```

The script probes workspace topology, resolves the tool-default baseline, checks for a framework update, and on success writes `$ARTIFACTS_DIR/.preflight-ok` (git head, `workspace_mode`, `child_repos`, `framework_update`, `resolved_defaults`); on failure it writes `$ARTIFACTS_DIR/.preflight-failed` `{reason, ran_at}`. Trust its outputs — do not re-verify them. Wiki staleness is owned by `/wiki-refresh` (Phase 9). **If the script exits non-zero, STOP** — surface its output verbatim.

**Git-clean check.** `git -C <repo> status --porcelain` must be empty for the workspace root (`single`) or every `child_repos` entry from the marker (`multi`; the root's own check is in the multi-repo reference). Dirty tree → STOP naming the repo; the preflight cannot fix it.

**Framework update.** Read `jq -c .framework_update "$ARTIFACTS_DIR/.preflight-ok"`. When `.should_prompt` is `true`: `--skip-questions` / `--autonomous` in `$ARGUMENTS` → **autonomous**: log one line (`framework update <installed> → <latest> available`) and continue to Phase 1 — never prompt, and never write the decline state; otherwise `cat` `.claude/skills/implement-ticket/references/framework-update.md` in the same command and follow it — it owns the prompt, the upgrade path and the decline record, and an ask that returns no answer (no developer reachable) logs the same one line and continues; the notice never STOPs the run. When `.should_prompt` is `false`, say nothing — unless `.reason` is `check-unavailable` or `no-framework-checkout`, then emit one non-blocking line: update checks need the framework checkout at `<workspace-root>/qubika-agentic-framework/`; clone it there to receive new-release notices.

### Phase 1: Resolve Run Mode

Decides once how much work the rest of the run does, before any of it is bought.

**1. Ensure ticket context** at `$ARTIFACTS_DIR/context/ticket-context.md` — the scan's input and every later phase's; the plan gate finds it on disk and reuses it.

- `--from-jira` / `--from-linear`: delegate to the general-purpose agent with a prompt that exports `ARTIFACTS_DIR` to the absolute path resolved above, invokes `/fetch-ticket-context <ID> --provider jira|linear` with the matching explicit provider, and returns ONLY that skill's one-line summary (title, comment counts, artifact size) — never the body.
- `--from-markdown <PATH>`: copy the file to the canonical path, body verbatim, adding a one-line `source: <PATH>` frontmatter.
- `--from-input "description"`: render the description under `## Description`, with `## Ticket` carrying `$TICKET_ID`.
- `--from-plan <PATH>`: write a minimal file whose `## Description` summarizes the supplied plan's `## Summary`, frontmatter `source: <PATH>`. Fetch nothing.

Missing afterwards → STOP.

**2. Resolve the mode.** `.claude/skills/implement-ticket/references/run-mode.md` owns the resolution order, the scan, the interview, and what `simple` removes; nothing here or in any later phase restates it. A pinned run (`--full`, `--standard`, `--from-plan`) resolves `standard` by its first three rules without the scan — do not read the reference for it. An unpinned run reads it now and runs the scan, then (interactive only) the interview, persisting what each settled into `ticket-context.md` before the verdict. Settled findings and confirmed directions are pinned scope for everything downstream.

**3. Resolve the delivery gates in the same pass** — they decide the phase list as much as the mode does. `create_commit` is true when `--create-commit`, `--push-branch`, `--create-pr` or `--full` was passed, else the baseline at `.resolved_defaults.tools["implement-ticket"].values.create_commit` in `.preflight-ok`; `push_branch` likewise from `--push-branch`, `--create-pr` or `--full`, else its own baseline; `create_pr` likewise from `--create-pr` or `--full`, else its own baseline; `skip_visual` likewise from `--skip-visual` or its own baseline; `skip_tests` likewise from `--skip-tests` or its own baseline; `skip_pr_review` likewise from `--skip-pr-review` or its own baseline. A `create_pr` of true implies `push_branch`; a `push_branch` of true implies `create_commit`. Missing or `null` is off. Resolution contract: `.claude/skills/implement-ticket/docs/FLAGS.md`. Resolve `autonomous` here too — true exactly when `--skip-questions` or `--autonomous` was passed — but write it TOP-LEVEL, never under `gates`: it has no config key and no baseline to overlay. `max_review_iterations` is written top-level too: its baseline at `.resolved_defaults.tools["implement-ticket"].values.max_review_iterations`, or `3` when that is not a non-negative integer (missing, `null`, negative, fractional). It caps Phase 11's fix cycles; it is not a gate.

**4. At `simple` only, author the plan here** — Phase 2 will not delegate. Write `$ARTIFACTS_DIR/plans/implementation-plan.md` against the `### Plan Tier (micro-plans)` shape in `.claude/skills/create-implementation-plan/references/implementation-plan-contract.md`: the scan's wiki reads and Grep/Read findings become the `## Wiki Evidence` and `## Source Evidence` bullets, the interview's `## Directions Confirmed` answers — autonomously, the settled `## Scan Findings` — become pinned decisions, the pinned edit becomes the single implementation step, and `## Testing Strategy` names the exact verification command with the scan's probe result. `## Recommended Implementers` follows the contract's bucket-derivation rule — it is the dispatch list if Phase 4 escalates.

**5. Persist `run-config.json`** with a tool call, never narration — shell state does not cross a phase boundary:

```json
{"mode": "simple|standard",
 "source": "flag-full|flag-standard|confirmed|judgement|default",
 "reason": "<one sentence naming what decided it>",
 "autonomous": false,
 "max_review_iterations": 3,
 "gates": {"create_commit": false, "push_branch": false, "create_pr": false, "skip_pr_review": false,
           "skip_visual": false, "skip_tests": false},
 "scan": {"candidate_files": [], "services": [], "repos": [], "structural": [],
          "blast_radius": [], "delegated_decisions": 0, "forks": []}}
```

`scan` is the reference's evidence table — `blast_radius` the outside files with a reach or unchanged-call hit — recorded so a reduced run can be audited afterwards and Phase 5 can scope its tests; omit it when a flag pinned the mode. The resolving phase always writes the file — a re-run with different flags must not inherit a stale verdict. **An escalation edits `mode`, `source` and `reason` in place — never rewrites the file**: `gates` and `autonomous` are read by the delivery and ask sites, and replacing the document would silently turn off a commit or PR the run asked for, or re-open a prompt in an autonomous run:

```bash
jq --arg r "<the surprise>" '.mode="standard" | .source="judgement" | .reason=$r' \
  "$ARTIFACTS_DIR/run-config.json" > "$ARTIFACTS_DIR/run-config.json.tmp" \
  && mv "$ARTIFACTS_DIR/run-config.json.tmp" "$ARTIFACTS_DIR/run-config.json"
```

Report one line — `Run mode: <mode> (<source>) — <reason>`. Under `--full` only, print one more line right after it — `Enabled by --full: <steps>` — listing in phase order each optional step the resolved `gates` and the pinned mode actually enable (`standard run mode (scan and interview skipped)`, `adversarial plan critique`, `full test matrix`, `visual verification (when frontend changes exist)`, `commit + wiki refresh`, `push + PR`, `PR review`); a step a skip gate resolved off is simply absent. Report-only, never persisted.

Read the mode back wherever a phase needs it:

```bash
RUN_MODE=$(jq -r '.mode // "standard"' "$ARTIFACTS_DIR/run-config.json" 2>/dev/null || echo standard)
```

### Phase 2: Obtain Plan

This gate is the ONLY way a plan enters execution. Beyond the simple micro-plan Phase 1 wrote from its own scan, this skill never plans. The gate's products, consumed by every later phase: the contract-valid plan at `$ARTIFACTS_DIR/plans/implementation-plan.md`, plus `$ARTIFACTS_DIR/context/ticket-context.md` (Phase 1).

```bash
RUN_MODE=$(jq -r '.mode // "standard"' "$ARTIFACTS_DIR/run-config.json" 2>/dev/null || echo standard)
```

**At `simple`** — do not delegate. Validate the micro-plan Phase 1 wrote against the contract's `## Validation Rules` and continue. A failed rule means Phase 1's verdict was wrong: escalate the mode to `standard` per Phase 1's in-place edit, naming the failed rule as the reason, and take Branch A.

Otherwise take exactly one of the two branches:

**Branch A — requirement source** (`--from-jira` | `--from-linear` | `--from-input` | `--from-markdown`):

Invoke `/create-implementation-plan` with the same input flag and value this skill received, plus `--ticket-id "$TICKET_ID"`:

```
/create-implementation-plan --from-jira <TICKET-ID> --ticket-id "$TICKET_ID" [--skip-questions] [--critique]
```

(substituting `--from-linear <ISSUE-ID>`, `--from-input "description"`, or `--from-markdown <PATH>` for `--from-jira` as received). Forward the source flag unchanged, `--skip-questions` when the run is autonomous (either alias), and `--critique` when set or under `--full`; NEVER re-fetch the tracker — Phase 1 produced `ticket-context.md` and the delegated skill reuses it — and NEVER forward the execution-only flags: the delegated skill takes nothing beyond the source flag, `--ticket-id`, `--skip-questions` and `--critique`. It reuses the `ticket-context.md` Phase 1 wrote — including any `## Delegated Decisions Resolved` and `## Directions Confirmed` sections, which it treats as confirmed scope and never re-asks — and under `--ticket-id` it skips its own preflight and context phases, since this run owns both. Interactivity is owned entirely by the delegated skill: interactive by default, autonomous under `--skip-questions`.

The delegated skill prints no final message under `--ticket-id`; its return is this run's Phase 2 checkpoint, not a stopping point. The next action is the command that asserts `$ARTIFACTS_DIR/plans/implementation-plan.md` exists and is non-empty, riding Phase 2's `completed` record. If the invocation failed or the plan is missing, surface the delegated skill's error verbatim and STOP.

**Branch B — `--from-plan <PATH>`** (always non-interactive; never modify the user's file at `<PATH>`):

1. Read the supplied markdown and validate it against every rule under `## Validation Rules` in `.claude/skills/create-implementation-plan/references/implementation-plan-contract.md` — read that file; never re-derive the rules from memory.
2. **Valid** → `cp "<PATH>" "$ARTIFACTS_DIR/plans/implementation-plan.md"`.
3. **Loose or incomplete** → invoke `/create-implementation-plan --from-plan <PATH> --ticket-id "$TICKET_ID" --skip-questions` (forwarding `--critique` when set or under `--full`) to normalize: its refine mode preserves the developer's prose, fills only what is missing or loose, and writes the canonical artifact itself. On return, re-assert the `## Validation Rules` against the canonical plan; still non-conformant → STOP.

If the plan cannot be obtained, validated, or normalized, STOP. Never fall back to inline planning. Past this gate, never `Read` the plan whole into this session: each phase extracts the one section it consumes with a bounded command (`awk '/^## Recommended Implementers/{f=1;print;next} f&&/^## /{exit} f' "$ARTIFACTS_DIR/plans/implementation-plan.md"`); delegated agents receive its path and read it themselves.

### Phase 3: Environment Setup

**Branch**, per repo in `DELIVERY_REPOS`:

- **`--branch <name>` given** — the caller checked the branch out already: per repo in `AFFECTED_REPOS`, `git -C <repo> branch --show-current` MUST equal `<name>`, else STOP naming the repo and its active branch. Reuse it as `<branch>` in every later phase, create nothing, and report `reusing <name> → base <value>` (`<value>` = `git -C <repo> config branch.<name>.gh-merge-base`, or `unrecorded`; Phase 10 resolves it). In `multi`, the workspace root follows the multi-repo reference's lenient rule.
- **Otherwise create one feature branch PER repo in `DELIVERY_REPOS`** (e.g. `feature/PROJ-123-description`), same name in each. When the name already exists in any of them, locally or on `origin`, pick another one free in all of them; never reuse or delete an existing branch — only `--branch` reuses one. Then loop `git -C <repo> checkout -b <new-branch>` then `git -C <repo> config branch.<new-branch>.gh-merge-base <base>` (`<base>` = the branch it was cut from; Phase 10 opens that repo's PR against it). Cut each from its repo's active branch — no `checkout`/`switch` first, no base argument: the developer chose the base by checking it out. Any other base needs explicit per-repo consent from the developer — ask; never assume main/master/development. **Autonomous runs never ask for it**: with `autonomous` true in `run-config.json`, the active branch is the only permitted base, and a run that needs another one STOPs naming the repo, its active branch, and the base it wanted — consent an autonomous run can never obtain.

**BEFORE screenshots** — only when Phase 6 will run (frontend changes AND `.gates.skip_visual` is false in `run-config.json`): start the services the screenshots need via the command catalog's `setup`/`start_dev` wrapper (never raw compose invocations), confirm a reachable, authenticable route (a test credential or an unauthenticated page), and capture into `$ARTIFACTS_DIR/screenshots/before/`. Infeasible → record the route tried and what blocked it, skip capture, and Phase 6 skips.

**Verification environment** — skipped when `.gates.skip_tests` is true. Read the plan's probed verification commands. For missing prerequisites, prepare ONCE per dependency root: prefer the catalog's `setup`, otherwise derive a recipe from repository manifests, lockfiles, contributor docs or CI. Install the local checkout's declared test dependencies and required builds in an isolated or ignored environment; never install globally or rewrite tracked manifests or lockfiles. Allow 600 s total per root with `CI=true` and the command timeout rules.

Record the attempt before execution and its outcome afterward in `run-config.json::verification_env`, with cwd, env and command readiness per root. Reuse it on resume; do not repeat setup. Re-probe unresolved commands once. Only confirmed missing prerequisites justify marking a command unavailable; planned test files and inconclusive probes must be tried after edits.

### Phase 4: Implementation

```bash
RUN_MODE=$(jq -r '.mode // "standard"' "$ARTIFACTS_DIR/run-config.json" 2>/dev/null || echo standard)
```

**At `simple`** — no implementer agent. Apply the micro-plan yourself per the reduction table in `.claude/skills/implement-ticket/references/run-mode.md`, including its diff-equals-scope assertion and its escalate-on-surprise rule, then write the per-entry completion summary yourself (files changed, checks run, wiki pages consulted: none — the plan carries direct file evidence). An escalation re-enters this phase through the implementer dispatch below, which tolerates earlier edits on disk.

Otherwise, parse the plan's `Recommended Implementers` section into an ordered list and delegate each entry to its `<entry.agent>`.
**Dispatch** — when all entries' Scoped Files are pairwise disjoint (counting any lockfile or generated output an entry's steps rewrite) AND the plan carries a `## Cross-Stack Contract` section — pinning an interface, or declaring `None — entries are independent` — dispatch ALL entries at once, each prompt carrying that section verbatim when it pins an interface — and **under concurrent dispatch implementers follow the concurrent Verification variant below**: entries with disjoint files can still share one test wrapper, a dev-server port, a test database, or a build output directory, and a project-wide check sees another entry's half-done edits, so each reports the other commands it would have run and Phase 5's sequential project-level verification covers them. Otherwise **sequential** — wait for one to finish before dispatching the next, so later implementers see earlier edits on disk.

Keep each prompt short — the implementer's own prompt already covers methodology. Include only:

- Ticket ID and one-line summary.
- Input paths (PATHS, not bodies): `$ARTIFACTS_DIR/plans/implementation-plan.md`, `$ARTIFACTS_DIR/context/ticket-context.md`.
- A `## Scoped Files` block containing ONLY this entry's files (verbatim from the plan). The implementer MUST treat files outside this block as out of scope.
- Verification — resolve which variant to emit BEFORE composing the prompt (the agent never receives `run-config.json`): read `.gates.skip_tests` from `$ARTIFACTS_DIR/run-config.json`. Sequential dispatch with the gate off → instruct: before returning, run the plan's Testing Strategy commands covering this entry's files and report each command + result in the completion summary. Gate on → instruct: name those commands `unrun` in the completion summary without executing them — the gate suppresses test execution run-wide, not only Phase 5. Concurrent dispatch with the gate off → an entry that shares neither its `verification_env` root nor a service its tests need with another entry gets the sequential instruction; otherwise instruct: run only the lint and format checks, on this entry's Scoped Files, and name the rest `unrun`. Pass recorded cwd and env and command availability from `verification_env`; an unavailable command is reported `unrunnable (<reason>)`, never run and never a defect. Implementers do not repeat setup.
  Plan defects — report each with its evidence in the completion summary; never comply or silently substitute: a named command that needs a hook bootstrap, or an invalid invocation or target; a step deleting or loosening an existing assertion or test case without pinning its replacement; a pinned edit resting on a premise the source or an existing test contradicts; a step gated on a human action, a manual runtime observation, or an interactive session. Missing prerequisites are environment blockers even when a prior probe resolved, never plan defects. Do NOT run repo-wide suites, and never run `git stash` — the project-level run and the pre-existing-failure exclusion both belong to Phase 5. Report a failure you believe pre-existing; do not confirm it yourself.

Verify, **per entry**: code changes exist within that entry's scope; scoped verification ran, is named `unrunnable` with its environment blocker, or — under concurrent dispatch or the `skip_tests` gate — the commands it may not run are named unrun; the completion summary lists wiki pages consulted, each verification command + its result or `unrun` mark, and any fresh source checks. A completion summary reporting a plan defect: Read the cited evidence yourself. A verification-command defect on an entry whose edits are complete — `git diff --name-only` within its Scoped Files covers every file its steps name, and its other commands ran or are marked unrun — does not fail the entry: record the command `unrunnable (<reason>)`, correct `## Testing Strategy` in place when confirmed, and do not re-dispatch; Phase 5 covers it. Any other defect, or an entry that stopped short, fails the entry: confirmed → correct that plan step in place, recording the evidence beside it, and re-dispatch the entry — a human-gated step becomes an `- Assumptions:` entry naming the value assumed, and the step proceeds on it; not confirmed → re-dispatch with the step affirmed. Re-dispatches count against Phase 5's global 3-iteration budget. Under sequential dispatch, verify each entry before dispatching the next.

### Phase 5: Testing

If `.gates.skip_tests` is true in `run-config.json`: record the skip gate in `verification_env`; at `simple`, run ONLY the command catalog's lint operation (nothing else carries lint there) and skip the rest; otherwise skip this phase and continue.

```bash
RUN_MODE=$(jq -r '.mode // "standard"' "$ARTIFACTS_DIR/run-config.json" 2>/dev/null || echo standard)
```

**At `simple`** — run ONLY the micro-plan's named verification command plus the command catalog's lint operation, per the reduction table in `.claude/skills/implement-ticket/references/run-mode.md`; report `Tests scoped to verification command: <cmd>`. A code or verification-plan failure escalates the mode in place and re-runs this phase as `standard`. Environment unavailability never escalates the mode or repeats setup; record `UNTESTED` per the outcome rule below.

**Verification outcome — every mode.** Use the recorded cwd and env and add command results to `verification_env`. Real test or collection failures use the fix loop; missing prerequisites do not spend a fix iteration. A failure naming an unset environment variable is a missing prerequisite: re-run only that test once with a dummy value for that one variable (never a real `.env` value — its credentials reach live services), record it in `verification_env.env`, and mark the test `unrunnable (<var>)` only if it still fails. Report **UNTESTED** for any required scope without completed project-test execution (including zero tests or all tests skipped), while continuing through the resolved delivery gates. Parse/compile, lint and collection-only checks are supplemental. An inconclusive probe never justifies skipping execution.

**Standard execution:**
- The plan's `## Testing Strategy` names WHAT to verify (targets, scoped commands); HOW MUCH runs is this phase's call — never let a plan widen it to a repo-wide suite.
- **Resolve test commands from the project's command catalog**: read `framework-config.json::stack_profile.command_catalog.run_tests` in tier order (wrapper → readme → package_manager → ci). Prefer one aggregate entry without `per_service` that covers all changed services; otherwise resolve one command per changed service (longest-prefix match on `stack_profile.services[].path`). A `per_service` entry covers only its named service, never another changed service. A wrapper outranks a per-service package-manager command because it orchestrates the dependent services (databases, queues, identity providers) that a raw `pnpm test` / `pytest` silently skips. An entry that exits before running any test (missing script or binary) does not count. Skip only the exact unavailable command, not every command sharing its runner. For each uncovered service, try the scoped fallback. When neither can run, record `project tests unrunnable (<reason>)` and `UNTESTED` for that scope for Phase 12.
- No covering entry for a scope → run the detected runner (Jest, Pytest, Playwright, Vitest, etc.) in its single-run form, scoped to the changed files' owning test directories plus the plan's `## Impact Analysis` → `Related tests`, plus any files named in `run-config.json::scan.blast_radius` when present and non-empty — never an unscoped runner call or a repo-wide script in its place.
- Run each selected command once per affected repo, sequentially, with `CI=true` in its environment (a runner that defaults to watch mode then runs once and exits); add no coverage flags — keep whatever the command already emits. A whole-repo sweep and the full matrix (`run_unit_tests` with coverage, `run_integration_tests`, `run_e2e`) run ONLY when `run-config.json::source` is `flag-full` or `flag-standard` — the `standard` mode alone never widens the run.

In a multi-repo workspace, run the command in each affected child repo and namespace any coverage output under `$ARTIFACTS_DIR/coverage/<repo-basename>/`.

If tests fail: report failures outside every entry's `Scoped Files` and the changed files' impact radius as suspected pre-existing (likely not introduced by this ticket, unverified); exclude them from the fix set and the 3-iteration budget. Do not verify by mutating the tree. Record every failure classified this way — the test, and why it was so classified (outside every entry's scoped files, outside the change's impact radius) — for Phase 12's final report and the PR body: the classification is the one this run cannot verify, so the human reading it is what stands in for the verification.

For the rest, map each failing test file back to its owning service via longest-prefix match on `stack_profile.services[].path`, then re-dispatch ONLY the `Recommended Implementers` entries whose `Scoped Files` overlap with the failure set (sequentially, in the original listed order — even when Phase 4 dispatched concurrently). Max 3 fix iterations, **global** across all implementers and all repos in multi-repo workspaces. Still failing after the third → STOP and report.

### Phase 6: Visual Verification

If no frontend changes, `.gates.skip_visual` is true in `run-config.json`, or Phase 3 captured no BEFORE baseline (report why): skip this phase and continue.

Otherwise take screenshots of the affected pages into `$ARTIFACTS_DIR/screenshots/after/`, then compare them against the baseline with the screenshot-regression mode of `.claude/skills/ui-visual-testing/SKILL.md` (its `thresholds.regression` decides), writing diffs to `$ARTIFACTS_DIR/screenshots/diff/`. A page over threshold → delegate to `visual-verifier` with its diffs and apply the fixes it returns.

### Phase 7: Documentation Update

```bash
for repo in "${AFFECTED_REPOS[@]}"; do
  git -C "$repo" diff --name-only
  git -C "$repo" ls-files --others --exclude-standard
done | grep -v '^docs/llm-wiki/' > "$ARTIFACTS_DIR/context/changed-files.txt"
```

**Structural gate — every mode.** Skip `doc-updater` when no changed file is structural, per the structural definition in `.claude/skills/implement-ticket/references/run-mode.md`. The cheat-sheet covers the tech stack, commands and structure; a diff touching none of those cannot change it. Any doubt about a path — including one in a directory the cheat-sheet does not already describe, unless it is a test file — or an unreadable file list, runs the agent. Report the decision in one line naming either the structural path or that none was found. This is the ONLY licence to skip it — never skip because you judge that no docs need updating.

Run documentation maintenance in a delegated general-purpose agent, never inline, so its analyze-and-decide output stays out of this context. The prompt MUST contain:

- "Read and follow `.claude/skills/doc-updater/SKILL.md` exactly to maintain the `CLAUDE.md` cheat-sheet. Edit nothing else; per-service and repo-wide prescriptive conventions (each service page's `## Conventions & How-To` and `conventions/project.md`) and descriptive context all live in the wiki (`docs/llm-wiki/`), refreshed by `/wiki-refresh` in Phase 9, not a skill body."
- Changed files: the contents of `$ARTIFACTS_DIR/context/changed-files.txt`.
- Artifact PATHS (not bodies): `$ARTIFACTS_DIR/context/ticket-context.md`, `$ARTIFACTS_DIR/plans/implementation-plan.md`.
- "Return ONLY a one-line summary: the files updated, or `doc-updater: no cheat-sheet changes needed`."

When it returns, append Phase 7's `completed` record carrying the summary line as its note, then proceed. A no-change result is the expected outcome for most tickets and counts as success. Do not re-run doc-updater inline.

### Phase 8: Implementation Commit

Read the gate Phase 1 resolved: `CREATE_COMMIT=$(jq -r '.gates.create_commit // false' "$ARTIFACTS_DIR/run-config.json" 2>/dev/null || echo false)`.

If **CREATE_COMMIT is false**: make no commit. For each repo in `DELIVERY_REPOS`, list the changed files (`git -C <repo> status --porcelain`, excluding `docs/llm-wiki/**`; at the root only `.claude/CLAUDE.md`) so the engineer can review them. Emit exactly one line — `Changes left uncommitted in <N> repo(s). Re-run with --create-commit to commit locally, --push-branch to also push the branch, or --create-pr to also open a PR.` — then mark Phase 8 completed and continue with Phase 12. Phase 9 (wiki refresh) and Phases 10–11 all require a commit, so they are skipped.

Otherwise (**CREATE_COMMIT true**) — the run has entered the opt-in delivery path. Read `.claude/skills/implement-ticket/references/delivery-phases.md` once, now: it carries the mechanics for Phases 8 through 11, and the gates in this body do not restate them. Follow its `## Phase 8 — commit each affected repo` section exactly.

### Phase 9: Wiki Refresh

Reached only when **CREATE_COMMIT is true** (Phase 8 produced a commit); otherwise Phase 8 skipped straight to Phase 12, since the refresh diffs against — and commits alongside — the implementation commit.

Follow the delivery reference's `## Phase 9 — wiki refresh` section exactly (Phase 8 read it; re-read if it is no longer in context): delegated invocation, STATUS contract, and outcome branching. Do not proceed past a `hard-error` outcome.

### Phase 10: PR Creation

Confirm Phase 9 marked completed (wiki refreshed or confirmed unchanged). The implementation commit from Phase 8 and the optional wiki commit from Phase 9 are already on the branch — Phase 10 only pushes and opens PRs.

Read the gates Phase 1 resolved: `PUSH_BRANCH=$(jq -r '.gates.push_branch // false' "$ARTIFACTS_DIR/run-config.json" 2>/dev/null || echo false)` and `CREATE_PR=$(jq -r '.gates.create_pr // false' "$ARTIFACTS_DIR/run-config.json" 2>/dev/null || echo false)`. If **PUSH_BRANCH is false**: skip push, PR, and the entire Phase 11 review loop — the Phase 8 + Phase 9 commits stay on the branch. Emit exactly one line — `Committed locally on <branch>. Re-run with --push-branch to push the branch, or --create-pr to also open a PR and run review.` — then mark Phase 10 completed and continue with Phase 12. If **PUSH_BRANCH is true and CREATE_PR is false**: for each repo in the PR set (code repos first, the root last), `git -C <repo> push -u origin <branch>`; a non-zero exit STOPs naming the failed repo and every repo already pushed — except on the root, which is reported per the multi-repo reference and skipped. Emit exactly one line — `Pushed <branch> to origin in <N> repo(s); no PR opened. Re-run with --create-pr to open a PR and run review.` — then mark Phase 10 completed and continue with Phase 12 (Phase 11 has no PR to review).

Otherwise (**CREATE_PR true**): follow the delivery reference's `## Phase 10 — push + PR creation` section exactly — the whole PR set, whatever `len(PR set)`, goes through `/repo-fanout-pr --no-commit` in a delegated agent, and every PR URL is recorded. Do not proceed if any expected PR was not created (partial fanout over the code repos is failure; a missing root PR is reported, not failure).

### Phase 11: Review Loop

If `.gates.skip_pr_review` is true in `run-config.json`: skip this phase and continue.

Reached only when **CREATE_PR is true** (otherwise Phase 10 skipped straight to Phase 12).

```bash
RUN_MODE=$(jq -r '.mode // "standard"' "$ARTIFACTS_DIR/run-config.json" 2>/dev/null || echo standard)
MAX_REVIEW_ITERATIONS=$(jq -r '.max_review_iterations // 3' "$ARTIFACTS_DIR/run-config.json" 2>/dev/null || echo 3)
```

**At `simple`** — append `--quick` to every `/pr-reviewer --pr-url` call in the delivery reference's section: bug-logic and security specialists, no judge, per the reduction table in `.claude/skills/implement-ticket/references/run-mode.md`.

Follow the delivery reference's `## Phase 11 — review loop` section exactly: `/pr-reviewer` once per PR URL (inline — it delegates to its own specialists), scoped fix re-dispatches with re-tested and re-reviewed results under the global cap of `$MAX_REVIEW_ITERATIONS` fix cycles, the `posted.json` check, and the multi-repo aggregation pass. If the cap is reached with unresolved issues, report them and proceed to Phase 12.

### Phase 12: Final Report

Report final status with summary, matching what the run produced: with a PR (CREATE_PR), list every PR URL (multi-repo: one per PR-set entry, the workspace root's labelled as such) plus any `root commits left local` line from Phase 10; with a push but no PR (PUSH_BRANCH only), list the branch(es) pushed to origin and note no PR was opened; with a commit but no push (CREATE_COMMIT only), list the branch(es) carrying the local commits per `DELIVERY_REPOS` entry and note nothing was pushed; with neither (default), list the uncommitted changed files per `DELIVERY_REPOS` entry and note the run stopped before committing. Repeat any `root changes left uncommitted` line from Phases 0 or 3. Include the per-repo coverage paths under `$ARTIFACTS_DIR/coverage/` when coverage was produced, the test outcome from `verification_env` (executed commands and results, the explicit skip gate, or **UNTESTED** with the affected scope, blocker and attempted setup; report supplemental checks separately), the wiki refresh outcome (or that it was skipped), the PR review outcome (or that `skip_pr_review` skipped it) with any `review not posted:` note from Phase 11 beside its PR URL, the visual verification outcome (or the recorded reason it was skipped) plus, on GitHub, every `visual-evidence:` line Phase 10 appended to `$ARTIFACTS_DIR/pr/visual-evidence.txt` (read the file; other providers write none), and any test failures Phase 5 classified as suspected pre-existing (each with the reason it was so classified).

## Error Handling

If a phase fails:
- Do NOT emit a `completed` record for it
- Report which phase failed and why
- If Phase 0 fails: stop immediately
- If the LLM wiki (`docs/llm-wiki/*`, router `docs/llm-wiki/CLAUDE.md`) turns out to be missing at any point: stop and instruct the user to rerun `/initialize-project`
- If Phase 1 fails (ticket context could not be produced): stop and report
- If Phase 2 fails (plan could not be obtained, validated, or normalized): stop and report; surface `/create-implementation-plan`'s error verbatim. Do not fall back to inline planning.
- If Phase 5 fails after 3 fix iterations: stop and report
- For other phases: attempt to recover once, then stop if still failing

Environment prerequisites (git shapes, tracker MCPs, provider CLIs) are enforced by Phase 0's preflight; they and the per-phase skill/agent roster are documented in `.claude/skills/implement-ticket/docs/README.md`.
