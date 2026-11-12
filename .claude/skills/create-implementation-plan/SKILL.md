---
name: create-implementation-plan
version: 3.0.0
last-updated: 2026-10-15
description: Creates a reviewable, contract-conformant implementation plan for a ticket — interactively by default, autonomously with --skip-questions. Use when the user says "create an implementation plan", "plan PROJ-123", or wants to review and refine a plan before any code is written. Also invoked by /implement-ticket to obtain a plan.
argument-hint: '[--from-jira TICKET-ID | --from-linear ISSUE-ID | --from-input "description" | --from-markdown PATH | --from-plan PATH] [--ticket-id ID] [--skip-questions | --autonomous] [--critique] [--skip-wiki] [--output [PATH]]'
---

# Create Implementation Plan

Input: $ARGUMENTS

Produce the implementation plan for the ticket described above — wiki-aware, stress-tested by an adversarial critique when opted in, and (by default) shaped interactively with the developer before any code is written. All planning logic for the development workflow lives in this skill: `/implement-ticket` delegates to it whenever it receives a requirement source, and consumes the plan it writes. Execution never plans; planning never executes.

## Flags

Parse the input for these flags:

Input source — exactly ONE of (more than one, or none, is an error; fail with a clear message naming the conflicting flags):
- `--from-jira <TICKET-ID>` — plan from a Jira ticket (e.g., PROJ-123)
- `--from-linear <ISSUE-ID>` — plan from a Linear issue (e.g., ENG-123)
- `--from-input "description"` — plan from a plain text description
- `--from-markdown <PATH>` — plan from a markdown SDD ticket
- `--from-plan <PATH>` — refine an existing plan: preserve the developer's prose, fill only what is missing or loose against the plan contract, re-validate. A full entry point in its own right — bring a hand-written plan interactively to get it reviewed and iterated, or combine with `--skip-questions` as the non-interactive normalization hook other workflows invoke

Modifiers:
- `--ticket-id <ID>` — use ID verbatim as `TICKET_ID`, skipping derivation entirely; a delegating caller that already resolved the ticket identity passes it so producer and consumer compute the identical `$ARTIFACTS_DIR`. The caller also owns the preflight and the clean-tree check: Phase 1 only asserts its marker
- `--skip-questions` / `--autonomous` (identical) — autonomous mode for the **whole run**: it skips **both** question waves — the Phase 3 business wave (PM-delegated decisions carried in from the SDD) and the Phase 5 technical iteration loop. Technical open points are resolved by best judgment and recorded in the plan; each business item takes its `Recommended` value, stamped `UNCONFIRMED` and carried into the plan's `## Assumptions And Open Questions` so it is never presented as confirmed scope
- `--critique` — run the adversarial critique step (Phase 4). Opt-in: when absent, the baseline at `.resolved_defaults.tools["create-implementation-plan"].values.critique` in `.preflight-ok` decides; missing or `null` is off. `--skip-critique` is a deprecated no-op (critique is already off by default) — accept it with a one-line notice
- `--skip-wiki` — instruct the planner not to read the LLM wiki (fresh-clone/offline runs); it plans from the ticket context and source reads
- `--output [PATH]` — after writing the canonical artifact, copy it to PATH (creating parent directories); bare `--output` defaults to `./<TICKET_ID>-implementation-plan.md` for easy review

## Plan Contract

The produced plan MUST conform to the contract at `references/implementation-plan-contract.md` — the single authoritative definition of the canonical artifact path, the required vs expected sections, each section's shape, and the validation rules the executor enforces. Read it before producing or validating any plan; never re-derive the schema from memory.

Canonical artifact path (defined in the contract, restated here once):

```
$ARTIFACTS_DIR/plans/implementation-plan.md
```

with `$ARTIFACTS_DIR = <workspace-root>/.claude-temp/tickets/<TICKET_ID>/artifacts/`, resolved via `qaf_resolve_artifacts_dir` in `.claude/scripts/lib/bootstrap-preflight.sh`.

## Turn Discipline

A response with no tool call ends an unattended run (CI, SDK, orchestrator) and kills every command it spawned. Whether a developer is watching is not detectable, so assume none is: until Phase 6 verifies the artifact — and, under `--ticket-id`, until the caller's workflow completes — every response MUST contain a tool call, except one that waits for a backgrounded delegation. An ask through the ask channel is a tool call; printed prose is not. Every delegation runs in the foreground and is awaited. If one runs in the background anyway, await it with the runtime's wait tool; with none, end the turn without a tool call — its completion notice resumes the run, unattended included — and never poll it.

## Progress Tracking

Copy this checklist into your working notes and check each phase off as you complete it:

```
Workflow Progress:
- [ ] Phase 0: Parse Input & Resolve Identity
- [ ] Phase 1: Preflight (Auto-bootstrap + Validation)
- [ ] Phase 2: Context Gathering
- [ ] Phase 3: Planning
- [ ] Phase 4: Adversarial Critique
- [ ] Phase 5: Iteration Loop
- [ ] Phase 6: Validate & Write Artifact
```

The checklist is the only phase tracking this skill keeps: notes never collide with the caller's task list, so it works identically standalone and under `/implement-ticket`. Never check a phase off when its outputs are missing, a required agent was not spawned, or an error occurred.

**Also record each transition with a timestamp.** The checklist dies with the session; timing must outlive it. This skill is the plan gate, the single largest block of a run, and which step inside it spends that time is invisible from the outside. `qaf_progress "$TICKET_ID" "2.<N>" "<name>" <status> ["<note>"]` (defined by `.claude/scripts/lib/bootstrap-preflight.sh`, sourced in Phase 0) appends one record to `$ARTIFACTS_DIR/progress.jsonl` — the same file `/implement-ticket` writes, so one aggregator serves the whole run — resolving the path itself. Key each record `2.<N>`, where `<N>` is this skill's own phase number: the plan gate is the caller's Phase 2, so its steps namespace under it (`2.0` through `2.6`); a bare `4` from each skill would pair one skill's start with the other's finish, and the aggregator reports a `2.<N>` row against its parent without adding it to the total.

Never spend a dedicated tool call on a progress append: a phase's first command starts with `qaf_progress … in_progress &&` and the command that verifies its outputs ends with `&& qaf_progress … completed`. A phase skipped by a flag still gets both records in one call, with a note naming why; a phase whose rule is violated gets `failed` with the reason, and STOPs.

## Phase Execution

Phases run in order; finish each before starting the next.

### Phase 0: Parse Input & Resolve Identity

Parse `$ARGUMENTS` for the five input flags and the modifiers listed under `## Flags`. Exactly one input flag must be present — zero or more than one → STOP with a clear error naming the conflicting or missing flags. `--critique` opts the Phase 4 critique in (its gate resolves there). `--skip-critique` → emit the one-line deprecation notice and ignore it.

When `--ticket-id <ID>` is present, use it verbatim as `TICKET_ID` — no slugification, no inspection of the input source. Otherwise derive `TICKET_ID` per `references/ticket-id-derivation.md`.

Resolve `ARTIFACTS_DIR` deterministically — an **absolute** path anchored at the workspace root, never relative to the current working directory:

```bash
source ".claude/scripts/lib/bootstrap-preflight.sh"
qaf_resolve_artifacts_dir "$TICKET_ID"
```

Record the interactivity mode once, in your notes — shell variables do not survive between commands: `INTERACTIVE=false` when `--skip-questions` or `--autonomous` is present, else `true`. It governs BOTH question waves — the Phase 3 business wave and the Phase 5 technical interview. Interactive by default; the flag is the only autonomy signal, never inferred from the environment. An ask channel that cannot return a usable answer (tool absent, empty, or EOF — an unattended caller that omitted `--skip-questions`) is never re-asked: the run continues as `INTERACTIVE=false` from that point and records every open point instead of STOPping.

### Phase 1: Preflight (Auto-bootstrap + Validation)

**Under `--ticket-id`** the caller ran the preflight and the clean-tree check moments ago: assert `$ARTIFACTS_DIR/.preflight-ok` exists (missing → STOP: the caller's Phase 0 did not complete), read `WORKSPACE_MODE` from it (`jq -r .workspace_mode "$ARTIFACTS_DIR/.preflight-ok"`), and continue — run nothing else here.

**Standalone**, run the deterministic preflight. `qaf_run_preflight` resolves the workspace-root `$ARTIFACTS_DIR` via `project_path()` and runs `ensure-context.sh` anchored to it (never a child repo):

```bash
source ".claude/scripts/lib/bootstrap-preflight.sh"
qaf_run_preflight "$TICKET_ID"
```

The script probes workspace topology and on success writes `$ARTIFACTS_DIR/.preflight-ok` (git head, `workspace_mode`, `child_repos`, `resolved_defaults`); on failure it writes `$ARTIFACTS_DIR/.preflight-failed` `{reason, ran_at, …}`. Trust its outputs — do not re-verify them. **If the script exits non-zero, STOP** — surface its output verbatim.

**Git-clean check.** `git -C <repo> status --porcelain` must be empty for the workspace root (`single`) or every `child_repos` entry from the marker (`multi`). Dirty tree → STOP and report; the preflight cannot fix it. Read `WORKSPACE_MODE` from the marker — Phase 3 requires `## Affected Repositories` in the plan when `multi`.

### Phase 2: Context Gathering

Produce a single canonical artifact at `$ARTIFACTS_DIR/context/ticket-context.md` regardless of input source. Every later phase reads from that path; nobody re-fetches from a tracker / re-reads the SDD markdown / re-parses `--from-input`. Under `--ticket-id` an existing artifact is the caller's, possibly carrying `## Delegated Decisions Resolved` and `## Directions Confirmed` sections from its interview — reuse it as-is: do not re-fetch, rewrite, or overwrite it, and skip straight to Phase 3. Standalone, reuse one the same way only when it came from this same, unchanged input; otherwise produce it anew below.

- If `--from-jira <TICKET-ID>` or `--from-linear <ISSUE-ID>`: delegate to a general-purpose agent so the full ticket dump never enters this session. Its prompt (a) exports `ARTIFACTS_DIR` to the absolute path resolved in Phase 0; (b) invokes `/fetch-ticket-context <ID> --provider jira|linear` with the matching explicit provider, which writes the canonical `ticket-context.md`; (c) returns ONLY the skill's one-line summary (title, comment counts, artifact size) — never the ticket body. On return, assert `ticket-context.md` exists; missing → STOP.
- If `--from-markdown <PATH>`: copy the SDD ticket file to `$ARTIFACTS_DIR/context/ticket-context.md` (preserve the original body verbatim; add a one-line frontmatter `source: <PATH>`).
- If `--from-input "description"`: render the description into the same canonical file under a `## Description` heading; add `## Ticket` with the `TICKET_ID` derived in Phase 0 as the synthetic id.
- If `--from-plan <PATH>`: do NOT fetch anything; write a minimal `ticket-context.md` whose `## Description` summarizes the supplied plan's `## Summary` section and notes the plan file as source (one-line frontmatter `source: <PATH>`). The refine path still needs a context artifact for the planner.

The SDD's `## Open Questions & Delegated Decisions` section (when the source ticket has one) rides along verbatim inside `ticket-context.md` — it travels with the ticket, so no separate artifact is needed. Phase 3's business wave reads it directly from there. Phase 2's only product is the canonical context artifact; do not proceed without it.

### Phase 3: Planning

#### Business wave — resolve PM-delegated decisions first

Before any drafting, resolve the delegated decisions the PM handed to the developer. Read the `## Open Questions & Delegated Decisions` section from `$ARTIFACTS_DIR/context/ticket-context.md` — the SDD body rides along there verbatim from Phase 2, so the section travels with the ticket and needs no local artifact. Items already recorded under `## Delegated Decisions Resolved` (a delegating caller's interview) are confirmed scope — ask only the unresolved ones; when none remain, skip this wave. Each item follows the fixed shape `create-sdd-ticket` emits: `field`, origin (`delegated` / `headless-assumption`), `Question:`, `Options presented:`, `Recommended:`. When the section is present with unresolved items, ask the developer these **business** questions — unless `INTERACTIVE=false` (`--skip-questions`), which takes the autonomous fallback below without asking:

- Present each item as multiple-choice using its `Options presented`, with the item's `Recommended` value listed **first** and its label suffixed ` (Recommended)`; the channel adds its own free-text option. Batch all items in one round.
- **Ask channel:** when `QAF_ASK_USER_MCP_TOOL` is set, build the payload with `MCP_SKILL=create-implementation-plan MCP_PHASE=business-clarification` and call the tool it names; otherwise ask the developer directly.
- Record each **human-answered** item in `$ARTIFACTS_DIR/context/ticket-context.md` under a `## Delegated Decisions Resolved` heading as `Q: … → Decided: …` — the planner consumes these as confirmed business scope.
- **Autonomous fallback** (`INTERACTIVE=false`) — resolve each item with its `recommended` value, without asking, and record it under the same `## Delegated Decisions Resolved` heading as `Q: … → Auto-resolved (UNCONFIRMED business decision): …`. An auto-resolved item is NEVER confirmed scope; the `Draft the plan` step below carries it into the plan's `## Assumptions And Open Questions` so an autonomous run always flags it for review.

When the section is absent or lists no items (`--from-input`, `--from-plan`, or an SDD with no delegated decisions), skip this wave.

#### Draft the plan

With `--from-plan`, this phase runs the refine variant (see `#### --from-plan refine variant` below) instead of the draft step.

Otherwise, delegate to `planner`. Keep the prompt short — the planner's own prompt already covers methodology, including how it reads the wiki (router → index → the conventions and sections the ticket points at, or the precedent short-circuit) and when it checks source. Include only the items below — no scope hints or investigation notes of your own, which would steer the planner past the evidence:

- Ticket ID and one-line summary.
- Output path: `$ARTIFACTS_DIR/plans/implementation-plan.md` — the planner writes the plan there itself and returns a receipt (path, implementers, repos, open-question count).
- Input path (PATH, not body): `$ARTIFACTS_DIR/context/ticket-context.md`. Entries under its `## Delegated Decisions Resolved` and `## Directions Confirmed` sections, and the settled entries under `## Scan Findings`, are confirmed scope — plan to them; never contradict or re-open them. Only its `unresolved fork:` entries are the planner's to decide; a settled scan finding reopens only under the exception the planner's own prompt carries — its source check shows the settled option raising, or breaking an existing test the ticket does not name.
- The plan contract path: `.claude/skills/create-implementation-plan/references/implementation-plan-contract.md` — instruct the planner to read it and conform to it; it is the authoritative output schema.
- `WORKSPACE_MODE` (from the preflight marker) — in `multi` mode the plan MUST include an `## Affected Repositories` section per the contract.
- With `--skip-wiki`: "Do not read the LLM wiki; plan from the ticket context and source reads."

The planner wrote the plan. Assert `$ARTIFACTS_DIR/plans/implementation-plan.md` exists and is non-empty; missing or empty → STOP, surfacing the planner's returned text verbatim. Never transcribe plan content — no phase of this skill emits the plan body.

If the business wave auto-resolved any delegated decision (the `UNCONFIRMED` items above), `Edit` each into the plan's `## Assumptions And Open Questions` as `Q: … → Auto-resolved (unconfirmed business decision): …` before validating — an autonomous run must never present a delegated decision as confirmed. Items answered by a human are already confirmed scope and are not carried here.

Verify the draft against the contract's `## Validation Rules` (read `references/implementation-plan-contract.md`; never re-derive the rules from memory). A draft that fails a rule is sent back to the planner with the failed rule named, before any developer sees it. Do not proceed if the planner was not delegated to (outside the `--from-plan` verbatim pass-through) or the plan file is missing.

#### `--from-plan` refine variant

This routine is the normalization entry point other workflows invoke as `/create-implementation-plan --from-plan <PATH> --skip-questions` — keep it self-sufficient; make no assumptions about who invoked it.

1. Read the supplied markdown. Parse it against the contract: which REQUIRED sections are present or absent, whether `## Recommended Implementers` is well-formed with every entry naming `implementer-generic`, and whether `## Affected Repositories` is present when `WORKSPACE_MODE=multi`.
2. **Already fully valid** → `cp "<PATH>" "$ARTIFACTS_DIR/plans/implementation-plan.md"` and continue — the critique still runs when its gate resolved on, and the iteration loop runs when interactive.
3. **Loose or incomplete** → enrich, never rewrite: preserve the developer's prose untouched. Delegate to the planner in refine mode — the prompt is the standard Phase 3 prompt PLUS the supplied plan path PLUS an explicit instruction list of ONLY the missing or loose sections to produce (e.g., derive `## Recommended Implementers` from the named files via the contract's language-bucket rule, add `## Source Evidence` from targeted Grep/Read checks), and the hard rule "do not alter existing sections". The planner merges and writes the canonical path itself; re-validate against the contract.

### Phase 4: Adversarial Critique

Opt-in. Resolve the gate now: `--critique` forces it on; otherwise read the baseline — `jq -r '.resolved_defaults.tools["create-implementation-plan"].values.critique // false' "$ARTIFACTS_DIR/.preflight-ok"` — where missing or `null` is off. Off → skip the phase, record the progress note `"critique off (opt-in via --critique or the critique config key)"`, and continue with Phase 5.

When on, it runs exactly once, immediately after Phase 3 produces the draft (or the refine variant produces the enriched plan), BEFORE any developer interaction, in all input modes.

Delegate to a general-purpose agent whose prompt is the body of `.claude/skills/create-implementation-plan/agents/devils-advocate-planner.md`. Inputs (paths, not bodies):

- the draft plan: `$ARTIFACTS_DIR/plans/implementation-plan.md`
- `$ARTIFACTS_DIR/context/ticket-context.md`

The critic returns a single `critiqueReport` JSON object with three buckets — `improvements`, `assumptions_to_ask`, `gaps_or_risks`. Persist it verbatim to `$ARTIFACTS_DIR/plans/plan-critique.json`. The critic advises; it never rewrites the plan.

Consume the report by mode:

- **Interactive** (`INTERACTIVE=true`): `assumptions_to_ask` + `gaps_or_risks` seed Phase 5's Stage A disambiguation branches; `improvements` appear in the digest and inform the edit-vs-re-spawn judgment.
- **Autonomous** (`INTERACTIVE=false`): record ALL findings under the plan's `## Assumptions And Open Questions`; apply `confidence: high` improvements by best judgment via `Edit` on the plan file, then re-validate against the contract.

### Phase 5: Iteration Loop

The **technical** question wave (plan-time ambiguities), distinct from the Phase 3 business wave. Interactive mode only — skip entirely when `INTERACTIVE=false` / `--skip-questions` (open points are already recorded under `## Assumptions And Open Questions` — by Phase 4 when the critique ran, by the planner and business wave otherwise). The business wave was gated by the same flag in Phase 3.

Two sequential stages: **Stage A (Disambiguation)** resolves every branch to a developer-confirmed decision — no entry may remain under `- Open questions:`; only then does **Stage B (Confirmation)** ask for the final verdict. Never ask for approval while any branch is open.

**Digest** — render to open each stage; never dump the whole plan file. Begin it with the full plan's location on its own line — `Full plan: $ARTIFACTS_DIR/plans/implementation-plan.md`, with `$ARTIFACTS_DIR` expanded to its resolved absolute path (never print the literal variable) — so the developer can open the complete plan before answering. Contents: `## Summary`, `## Impact Analysis` highlights, `## Implementation Steps` titles, top `## Risk Assessment` risks, `## Recommended Implementers`, and — when the critique ran — the critic's `improvements`.

**Ask channel** — both stages ask through it: when `QAF_ASK_USER_MCP_TOOL` is set, build the payload with the stage's `MCP_PHASE` and call the tool it names; otherwise ask the developer directly. If the channel cannot return a usable answer (tool absent, empty, or EOF), do NOT re-ask: record the open points under `## Assumptions And Open Questions` and finish as `INTERACTIVE=false`.

```bash
PAYLOAD=$(MCP_SKILL=create-implementation-plan MCP_PHASE="<stage>" MCP_TICKET_ID="${TICKET_ID:-}" \
  bash "$MCP_AUQ_HOOKS/build-mcp-payload.sh")
```

Then call the tool named by `$QAF_ASK_USER_MCP_TOOL` with `jq '.questions=[ <stage questions> ]' <<<"$PAYLOAD"` as its input.

**Re-spawn threshold** — apply feedback with `Edit` in place by DEFAULT. Re-delegate to the planner ONLY when feedback changes the technical approach, the affected services/files/repos, the requirements, or the implementer buckets; wording, ordering, scoping-down, clarifying a step, or test tweaks are always inline edits. To re-delegate: append a cumulative `## Developer Feedback` section (newest last) to `$ARTIFACTS_DIR/context/ticket-context.md`, re-run Phase 3's planner delegation (it reads that artifact), then re-run Phase 4 on the fresh draft (when its gate resolved on) and return to Stage A before any verdict.

#### Stage A — Disambiguation

Every question carries a **recommended answer** and the **dependency it unblocks**. **Explore before asking**, but a branch closes without a question ONLY when `ticket-context.md`, the plan's evidence sections, or a source read answers it *definitively* — your own recommendation is never a closure, so every judgment call is put to the developer (who may accept it or override). A branch already answered under `## Delegated Decisions Resolved` or `## Directions Confirmed` in `ticket-context.md` is closed — never re-ask it.

1. Render the digest.
2. Enumerate EVERY branch under `- Open questions:` in `## Assumptions And Open Questions`: the critic's `assumptions_to_ask` + `gaps_or_risks` (`$ARTIFACTS_DIR/plans/plan-critique.json`, when the critique ran), plus your own scan for each decision the draft leaves implicit — ambiguous scope, unnamed target files, hand-wavy steps, untested behavior, and any structural fork the plan silently picked (e.g. inline handler vs new file/router).
3. Seed one mandatory **test-scope** entry under `- Open questions:`, asked first in its round — unless `## Directions Confirmed` already records the test-scope decision (a prior resolution): then apply it to the draft instead of re-asking. The question: a multi-select of the test kinds this implementation should create. Offer only kinds with detected infrastructure in the affected services (`framework-config.json::stack_profile.services[].testing` — `{}` is verified-none, `null`/absent is unknown; neither is offered) plus `No new tests` (exclusive: when selected, other selections are ignored); mark the kinds the draft's `## Testing Strategy` proposes ` (Recommended)`. No kind offerable → ask a two-option question instead: skip new tests, or author them anyway — on that answer, collect the kind and runner as a dependent question in the next round (an option label carries no free text). On resolution, set each bucket left unchosen on the question to `None — user-confirmed` and each bucket never offered to `None — no detected infrastructure` (only the first records a developer decision); declining `e2e` rewrites only the e2e portion of `E2E/manual checks:`, keeping its manual/visual checks. Align each step's `- Tests:` line, and append the decision under `## Directions Confirmed` in `$ARTIFACTS_DIR/context/ticket-context.md` (create the section if absent); a full opt-out still keeps `Commands to run:` naming the scoped regression command. Chunking never drops this item — overflow moves other items to an additional call.
4. Resolve them in batched rounds through the ask channel (`MCP_PHASE=plan-disambiguation`): all independent branches in one round, chunked at 4 per call; a branch whose question depends on another's answer waits for the next round. If an answer crosses the re-spawn threshold, take that path instead.
5. On each resolution: `Edit` it into the plan and move the entry from `- Open questions:` to `- Assumptions:` as `Q: … → Decided: …`. If integrating exposes a new branch, add it under `- Open questions:`.
6. GATE: advance to Stage B only when `- Open questions:` is empty — while any entry remains, keep asking. The sole exception is an ask channel that returns no usable answer, which flips the whole run to `INTERACTIVE=false`.

#### Stage B — Confirmation

1. Re-render the digest (now updated).
2. Ask **Approve / Adjust** (`MCP_PHASE=plan-confirmation`; two options).
3. **Approve** → continue to Phase 6.
4. **Adjust** → ask "Which part(s) would you like to adjust, and how?", then apply per the re-spawn threshold: inline `Edit` → back to step 1; otherwise → fresh draft, back to Stage A.
5. Loop until Approve. The developer may instead hand-edit the `--output` copy and re-enter via `--from-plan`.

### Phase 6: Validate & Write Artifact

Phase 3 already verified the draft against the contract's `## Validation Rules`. Re-validate here ONLY when the plan changed since that check (critique edits, iteration edits, refine merge) — check every rule in `references/implementation-plan-contract.md`; never restate or re-derive the rules here. Any violation → STOP loudly, naming the failed rule. Unchanged → record the progress note `"unchanged since draft validation"` and skip. Either way the produced artifact is executor-ready.

The validated plan lives at the canonical artifact path: `$ARTIFACTS_DIR/plans/implementation-plan.md`.

`--output [PATH]` handling: copy the canonical artifact to PATH, creating parent directories (`mkdir -p`) as needed; a bare `--output` defaults to `./<TICKET_ID>-implementation-plan.md` (repo-root-relative).

**Standalone** (no `--ticket-id`): the final message prints the canonical artifact path, the `--output` copy path if any, and a brief digest (the `## Summary` plus the recommended implementer list).

**Under `--ticket-id`**: this skill is the caller's Phase 2 and the run is not over. Print no final message and no digest — the command that verifies the artifact and appends the `2.6` `completed` record is this skill's last action, and the caller's next phase follows in the same response. `2.6` closes the plan gate, never the run.

Artifacts produced: `context/ticket-context.md`, `plans/implementation-plan.md` — both under `$ARTIFACTS_DIR`, byte-identical paths to what the execution workflow consumes.
