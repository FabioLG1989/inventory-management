---
name: create-sdd-ticket
description: Generate a lean, product-only specification ticket (SDD) from a plain idea, markdown draft, Jira ticket, or Linear issue. Runs a BDD-first, PM-driven interview — asks one product / business-behavior question at a time (each with a recommended answer), auto-resolves only code-verifiable facts, validates against INVEST, and emits Given-When-Then acceptance scenarios with no technical or implementation detail. Use when the user says "/create-sdd-ticket", asks to create or refine an SDD ticket, spec, user story, or acceptance criteria, or wants an implementation-ready product spec from Jira, Linear, or markdown.
argument-hint: '[--from-input "..." | --from-jira JIRA-URL-OR-KEY | --from-linear ISSUE-ID | --from-markdown PATH] [--save-to-jira [BOARD-URL] | --save-to-linear [TEAM-OR-PROJECT-URL] | --save-to-markdown [PATH]] [--skip-update-check] [--skip-questions]'
---

# Create SDD Ticket

Input: `$ARGUMENTS`

Generate a complete product specification ticket from plain text, Jira, Linear, or markdown. The skill answers **"what does it have to do?"** — product behavior, PM-confirmed. The **"how do I build it?"** question is out of scope and owned by `implement-ticket`'s planner agent.

**Write every word of the ticket in plain, simple English for a non-technical reader.** Be ruthlessly concise and concrete: short sentences, real examples, no jargon, no implementation terms, no filler — a product stakeholder reads it without a glossary. This governs the whole ticket (user story, success criteria, edge cases, everything); BDD scenarios additionally follow the business-language rules in [references/bdd-guide.md](references/bdd-guide.md).

## Invocation

Invoke the skill directly with arguments such as:

```text
/create-sdd-ticket --from-input "Add user authentication with JWT tokens" --save-to-markdown "./specs/AUTH-001.md"
/create-sdd-ticket --from-jira "PROJ-123" --save-to-jira "https://company.atlassian.net/jira/software/c/projects/PROJ/boards/1"
/create-sdd-ticket --from-linear "ENG-123" --save-to-linear
/create-sdd-ticket --from-markdown "./specs/DRAFT-001.md" --save-to-markdown "./specs/FEAT-001.md"
```

Optional flags:

- `--project-key <KEY>`
- `--issue-type <TYPE>` — `Story`, `Task`, or `Bug`
- `--priority <PRIORITY>` — `High`, `Medium`, or `Low`
- `--skip-wiki` — bypass the Phase 0.2 wiki preload (freshly-cloned or offline projects); also forwarded to the Phase 0 preflight
- `--skip-update-check` — skip framework-update detection in the Phase 0 preflight (equivalent to `QAF_SKIP_UPDATE_CHECK=1`)
- `--skip-questions` — never prompt, for unattended runs with no human (CI, SDK); the Phase 0 update prompt and the Phase 3 interview both take the headless path

## Input And Output Modes

**Inputs** (exactly one required):

- `--from-input "description"` — create from a plain-language idea
- `--from-jira <JIRA-URL-OR-KEY>` — refine an existing Jira ticket
- `--from-linear <ISSUE-ID>` — refine an existing Linear issue
- `--from-markdown <PATH>` — refine an existing markdown draft

**Outputs:**

- `--save-to-jira [BOARD-URL]` — save the ticket to Jira. Create-vs-update is decided by **input mode**, not by the save target: when the input was `--from-jira <KEY>` the source `<KEY>` is always the write target and the value (board URL, ticket URL, or absent) has no routing effect; when the input was `--from-input` or `--from-markdown` a new issue is created in the board's project (see §Saving To Jira in Phase 7)
- `--save-to-linear [TEAM-OR-PROJECT-URL]` — save to Linear via its MCP server (see §Saving To Linear in Phase 7). Existing Linear input updates its exact source issue; every other input creates and requires a Linear team or project URL.
- `--save-to-markdown <PATH>` — save the ticket exactly to that path
- `--save-to-markdown` with no path, or any markdown output when no path is given — default to `.claude-temp/tickets/<ticket-id>/<ticket-id>.md`
- no output flag — print the completed canonical ticket for review

## Workflow

Copy this checklist into your working notes and check each phase off as you complete it — the gating sub-phases (0.1, 0.2) and the INVEST pass (Phase 5) are the easiest to skip silently:

```
Workflow Progress:
- [ ] Phase 0: Preflight
- [ ] Phase 0.1: Inject conventions
- [ ] Phase 0.2: Wiki preload
- [ ] Phase 1: Parse input
- [ ] Phase 2: Gap detection
- [ ] Phase 3: Product interview
- [ ] Phase 4: Apply answers
- [ ] Phase 5: INVEST
- [ ] Phase 6: BDD scenarios
- [ ] Phase 7: Output ticket
```

### Phase 0: Preflight (MANDATORY — do not skip)

Before any other phase — before reading the ticket source, consulting the wiki, or asking gap questions — run the deterministic preflight bootstrap exactly as written:

Resolve `TICKET_ID` once here — the Jira key for `--from-jira`, the exact issue identifier for `--from-linear`, otherwise a stable draft id (a slug of the `--from-input` text or the `--from-markdown` basename) — and set a single `ARTIFACTS_DIR` from it. **Every later phase reuses this exact `$ARTIFACTS_DIR`**; never reassign it to a per-phase subpath, or the `.preflight-ok` marker written here will not be found.

```bash
cd "$(git rev-parse --show-toplevel)"
TICKET_ID="<Jira key, Linear issue identifier, or stable draft id>"
ARTIFACTS_DIR=".claude-temp/tickets/$TICKET_ID"
PREFLIGHT_ARGS=()
[ -n "${SKIP_WIKI:-}" ] && PREFLIGHT_ARGS+=("--skip-wiki")
[ -n "${SKIP_UPDATE_CHECK:-}" ] && PREFLIGHT_ARGS+=("--skip-update-check")
bash ".claude/scripts/ensure-context.sh" --artifacts-dir "$ARTIFACTS_DIR" "${PREFLIGHT_ARGS[@]}"
```

The script records the workspace topology and repo HEADs, resolves tool defaults, checks for a framework update, and writes a JSON success marker at `$ARTIFACTS_DIR/.preflight-ok`; a fresh marker is reused in ~1 s.

**If the script exits non-zero, branch on input mode:**

- **`--from-jira` / `--from-linear` / `--from-markdown`** → **STOP** and surface the output verbatim. These inputs refine work against existing code, so a verified workspace is load-bearing.
- **`--from-input`** → **best-effort**. A plain idea often has no code to ground against yet, and a PM-facing spec must stay trivially simple at the edge. Log `preflight failed — grounding limited` and continue, grounding recommendations on the description and conventions alone.

If it exits 0, every later phase asserts `test -f "$ARTIFACTS_DIR/.preflight-ok"` before doing work; if the marker is missing outside best-effort `--from-input` mode, return to Phase 0.

**Framework-update prompt.** Read `jq -c .framework_update "$ARTIFACTS_DIR/.preflight-ok"`. `.installed` is what this project runs, `.checkout` what the framework clone holds on disk, `.latest` what exists upstream. When `.should_prompt` is `true`, before Phase 0.1 present `<installed> → <latest>`, `.action` (`sync` = resource sync; `initialize` = breaking, needs re-initialization), and `.release_notes_url` when non-null — adding, when `.reason` is `checkout-ahead-of-install`, that the release is already in the framework checkout and only the project-side apply is missing (nothing to download) — and, when `.migrations` is non-empty, naming its entries as the migration scripts the upgrade will run for them, in the order listed — the framework runs them, the engineer does not — then prompt with the same routing as Phase 3: with `--skip-questions` log one line (`framework update <installed> → <latest> available`) and continue, never prompting; otherwise `$QAF_ASK_USER_MCP_TOOL` when set, else an interactive prompt — offering "Upgrade now" or "Continue on current version":

- **Upgrade now** → run `bash "$WS/qubika-agentic-framework/scripts/apply-framework-update.sh" --framework-path "$WS/qubika-agentic-framework" --tag <latest> --action <action> --provider <provider>` plus one `--migration <path>` per `.migrations` entry, **in the order the array lists them** (that order is the order they must run in) (`WS` = `.workspace_root`, provider = `.provider`, both from the marker). Then **STOP regardless of its exit** and tell the engineer to re-run their original command — never continue this run on swapped-out framework files. On non-zero exit surface its stderr (e.g. it refused a dirty framework tree); when `.action` is `initialize` also tell them to run `"$WS/qubika-agentic-framework/scripts/initialize-project.sh"` first — that action is reached only when a release the upgrade crosses declares it needs a re-initialization, which supersedes every migration, so `.migrations` is empty there. On a successful sync the result's `.touched_paths` lists the project files the sync rewrote — name them and tell the engineer to commit or stash those before re-running, or the clean-tree check will reject the re-run.
- **Continue on current version** → record the decline so this version stays quiet on later runs: `printf '{"declined_version":"%s"}\n' "<latest>" > ".claude/.framework-update-state.json"`. Then proceed to Phase 0.1; nothing was swapped.

When `.should_prompt` is `false`, say nothing — unless `.reason` is `check-unavailable` or `no-framework-checkout`, then emit one non-blocking line: update checks need the framework checkout at `<workspace-root>/qubika-agentic-framework/`; clone it there to receive new-release notices.

### Phase 0.1: Inject Project Conventions

Read the prescriptive conventions that carry product-relevant signal — each affected service page's `## Conventions & How-To` section (`docs/llm-wiki/wiki/services/<id>.md`):

- `### Code Rules` — gotchas with WRONG/CORRECT examples, naming, error handling, data-layer / validation patterns that inform behavioral edge cases
- `### Testing` — validation and error-handling patterns, consulted **only** to frame edge/error scenarios (Topic 6)

Skip each service's `### Multi-File Workflows` — it is the planner's *how* (which files a change must touch) and has no bearing on product behavior. Repo-wide rules live on `docs/llm-wiki/wiki/conventions/project.md`. If the wiki is missing (project not initialized), fall back to `.claude/CLAUDE.md` plus explicit codebase inspection. Phase 0.1 carries **prescriptive** rules; descriptive context (what the system IS) comes from Phase 0.2.

### Phase 0.2: Wiki Context Preload

Phases 0.1 and 0.2 are complementary along a strict prescriptive/descriptive line — each service page's `## Conventions & How-To` is authoritative for "how we DO this here", the rest of the wiki for "what this system IS" (architecture, boundaries, data flows). By construction each fact lives in exactly one place; if one appears in both, the descriptive sections win on descriptive claims and the `## Conventions & How-To` section wins on prescriptive rules.

If `docs/llm-wiki/` exists, defer retrieval to the wiki's own router:

1. **Read the router.** Read `docs/llm-wiki/CLAUDE.md` (Claude) or `docs/llm-wiki/AGENTS.md` (Codex). Capped ~150 lines; its decision table names which page answers which question.
2. **Pick 1–3 pages from `index.md`** — `docs/llm-wiki/wiki/index.md` is the summary catalog (one line per page). Match the user's idea against the summaries; read **only** those page bodies.
3. **Persist** the loaded context to `.claude-temp/tickets/<draft-id>/context/wiki-context.md` with sections `## ROUTER`, `## WIKI_INDEX_SNAPSHOT`, and `## WIKI_CORE`.

**Tier discipline:** router → 1–3 page bodies. Never read every wiki page; stop wikilink traversal at depth 2. Questions the pages leave open are resolved by the Phase 2 Grep routing, not by wider reading here.

**Fallback:** if `docs/llm-wiki/` is missing (project not yet initialized), log `wiki unavailable — falling back to CLAUDE.md only` and proceed to Phase 1 with Phase 0.1's prescriptive context only. Do NOT fail the skill.

When `--skip-wiki` is passed, likewise log `wiki unavailable — falling back to CLAUDE.md only` and skip directly to Phase 1. Use it only when the wiki is known to be drift-prone — the framework's default assumption is that the wiki is fresher than any prescriptive skill body.

### Phase 1: Parse Input Source

Detect the active input mode, load the source, validate accessibility and basic structure, and normalize it into a working internal representation.

#### When `--from-jira` or `--from-linear`: invoke `/fetch-ticket-context` (MANDATORY)

For tracked input, invoking `/fetch-ticket-context` is **mandatory**. The canonical artifact at `$ARTIFACTS_DIR/context/ticket-context.md` — body, comments, linked resources, attachments, related tickets — is the source of truth. Do not bypass the artifact with a description-only tracker call; that drops the comment material the SDD synthesis depends on.

Reuse the same `$ARTIFACTS_DIR` from Phase 0 — do not create a divergent `artifacts/` subpath. Provider selection is explicit and never inferred from identifier shape.

```bash
mkdir -p "$ARTIFACTS_DIR/context"
/fetch-ticket-context "$TICKET_ID" --provider <jira|linear>
# Artifact now at: $ARTIFACTS_DIR/context/ticket-context.md
```

Then parse: `## Ticket` (id, title, type, status, priority, labels, sprint, epic), `## Description` (base requirement — a starting point, not the final word), `## Acceptance Criteria` (initial AC, subject to comment deltas), `## Comments` (authoritative input alongside the description — see [Comment-aware synthesis](#comment-aware-synthesis)), `## Linked Resources`, `## Related Tickets`.

### Phase 2: Intelligent Gap Detection

Validate the canonical ticket against the SDD requirements. For every missing or weak field, apply the **Gap Classifier** — the keystone of the product-only scope — before touching any inference tool:

| Gap type | Definition | Action |
|---|---|---|
| Code-verifiable fact | An objective fact about existing code: does X exist? who calls Y? is Z in service A? what does the system do today? | Auto-resolve via wiki / grep. Record evidence. |
| Product judgment | A decision only the PM can make: who should use this? what behavior is in scope? what counts as success? | Enqueue for the Phase 3 interview. Never silently fill — even if a reasonable default exists. |

**For code-verifiable facts, use this inference order:**

1. **For Jira or Linear input — check `## Comments` first.** Product decisions already recorded by PM/stakeholders in comments are honored as authoritative (see [Comment-aware synthesis](#comment-aware-synthesis)). Walk comments chronologically; an explicit decision resolves and removes the gap. Ambiguous signals become recommended answers for Phase 3.
2. Consult `WIKI_CORE` (the 1–3 pages from Phase 0.2); every code-verifiable fact the wiki answers leaves the gap list.
3. Codebase grep — route each remaining code-verifiable gap by question type (table below).
4. Search each affected service page's `## Conventions & How-To` and `.claude/CLAUDE.md` for prescriptive context.
5. Read the files step 3 surfaced — never wider.
6. Inspect existing tickets or drafts for precedents.

Grep routing table (code-verifiable facts only — one word-boundary Grep per gap, test directories included; record each finding as `path:line`):

| Question class | Example | Grep |
|---|---|---|
| symbol_lookup | "Does `RateLimiter` exist?" | `\bRateLimiter\b` — a declaring file proves existence |
| relationship | "Who calls `AuthService.login`?" | `\blogin\b` outside the declaring file; keep the hits that invoke it |
| data_flow | "Does the request flow auth → users?" | the client, route or topic identifier `auth` uses to reach `users` |
| boundary | "Are `users` and `auth` in the same service?" | each path against `framework-config.json::stack_profile.services[].path` (longest-prefix match) |
| impact | "If we change `User`, what's affected?" | `\bUser\b` repo-wide; distinct importing files are the blast radius (factual answer to a code-verifiable question only; never an input to product scope or ticket sizing) |

Cache every result and reuse it instead of re-querying.

**Phase 2 output — two lists:**

- `resolvedFacts[]` — code-verifiable facts already answered; these ground recommendations in Phase 3.
- `productGaps[]` — product-judgment fields needing PM confirmation; these become Phase 3 questions.
- `dependencies[]` — blocking or related tickets / product capabilities **explicitly named** in the description or comments. Do not infer or interview for them; leave empty when none are stated (the Dependencies section is then omitted in Phase 7).

UI-specific handling must remain available: classify whether the work is UI-related (based on description and code context). If UI work is detected, add a product gap — "Is visual fidelity to Figma an acceptance requirement for this ticket?" — with a recommended answer of "yes" when a Figma URL is referenced.

### Phase 3: Sequential Product Interview

Interview the PM one question at a time, grounded in BDD thinking. Each question covers exactly one field from `productGaps[]`, is presented as a **multiple-choice** question (2–3 concrete behavioral options plus the mandatory Delegate option), carries a recommended answer (grounded in `resolvedFacts[]`, conventions, comments, description), is framed behaviorally (what should the system DO, what should a user EXPERIENCE), and waits for PM confirmation or override before the next.

**Run this interview with the [`grill-me`](../grill-me/SKILL.md) skill — it is the interview engine.** Apply its method: walk the decision tree one branch at a time; **explore before asking** (when `resolvedFacts[]` already answers a gap, present the finding as the answer instead of asking); **one question per turn**; every question carries a **recommended answer** with its reasoning; and **surface the dependency** each answer unblocks. This phase supplies the product scope — the `productGaps[]` and the topic sequence below — and the execution-context routing; `grill-me` supplies the questioning technique. Skip its infra/data-model/operability categories: create-sdd interviews product behavior only.

**Stop criterion:** every product-judgment field (`userStory`, `successCriteria`, `acceptanceCriteria`, `outOfScope`, `edgeCases`, `errorScenarios`) is PM-confirmed. Do NOT keep asking once all are complete. `stakeholders` is **not** an interview topic — populate it deterministically: Requester = the invoking user; Product Owner / End Users are carried from the source ticket's metadata when present, otherwise left `(open)`. Never interview for it and never silently invent names.

**Detect the execution context from the arguments and this exact command — never from a terminal probe.** A missing terminal does not mean no human: Claude Code runs every Bash command without one.

```bash
echo "QAF_ASK_USER_MCP_TOOL=${QAF_ASK_USER_MCP_TOOL:-UNSET}"
```

Route in this order:

- `--skip-questions` passed → **headless fallback** block, even when the MCP tool is set. The flag is the only no-ask signal.
- `QAF_ASK_USER_MCP_TOOL` non-empty (not `UNSET`) → **MCP autonomous** block.
- Otherwise → **interactive** block.

An ask channel that returns no usable answer (tool absent, error, empty, or EOF — an unattended caller that omitted `--skip-questions`) is never re-asked: finish every remaining field through the **headless fallback** block.

#### Interview topic sequence (dependency order)

Ask in this order, skipping any topic already resolved by `resolvedFacts[]` or PM-confirmed from comments. For each topic, provide the recommended answer with its evidence citation; for BDD, provide a full Given-When-Then draft the PM confirms, edits, or replaces.

**Topic 1 — Users & Role.** "Who are the primary users of this feature? What is their role or context?" Behavioral framing: "In what situation does a [role] need this behavior, and what are they trying to accomplish?" Recommend from existing user/role models in code, wiki, or conventions; cite evidence.

**Topic 2 — Core Behavior.** "What is the main behavior this feature should enable? Describe it as what a user should be able to do — not what will be built." Format: "[Actor] can [action] so that [outcome]." Distill from description, authoritative comments, and wiki evidence.

**Topic 3 — Scope (In / Out).** "Which behaviors are in scope for this increment? Which are explicitly out of scope or deferred?" Base on what exists (code-facts) vs. what is described as new. If the described behavior spans more than one distinct **user-facing capability**, ask: "This seems to cover [capability A] and [capability B]. Should they be separate tickets?" Judge this from the behaviors themselves — never from how many files or services a change would touch (code structure is not product scope).

**Topic 4 — Success Criteria & Metrics.** "How will we know this feature is successful? What should a user observe or measure that they cannot today?" NFR framing: express performance/security/scale requirements as measurable behavioral outcomes ("search results appear within 500 ms"), not technical constraints.

**Topic 5 — BDD Acceptance Scenarios.** Walk the main journeys one at a time, proposing a full Given-When-Then draft each time: happy path, edge case, error/failure path, and (if applicable) a permission scenario for a user without the required role. Continue until ≥3 scenarios (happy + edge + error) are confirmed. See [references/bdd-guide.md](references/bdd-guide.md) for scenario anatomy and content rules.

**Topic 6 — Edge & Error Behavior (residual).** "Are there remaining edge or error behaviors the scenarios haven't covered? For example [cite concrete patterns from conventions — concurrent access, empty states, maximum limits]." Recommend from validation patterns in the service page's `## Conventions & How-To` and existing error handling.

#### Question format (all routing blocks)

Every question the PM sees is multiple-choice: the 2–3 concrete behavioral options **plus** a final **"Delegate the decision to the developer"** option — 4 total at most, the ask channel's cap. The free-text **"Other"** is surfaced by the channel automatically and does NOT count against that cap.

You build **only** the 2–3 concrete options — the **recommended** one listed **first**, its label suffixed ` (Recommended)` (the MCP `options[]` schema has no separate recommended field, so the suffix is what keeps it visible). Do **not** rely on remembering to add the Delegate option: the MCP block appends it deterministically with `jq`, and the interactive block below carries it verbatim. (Headless never presents options — it records unanswered fields under `## Open Questions & Delegated Decisions` instead.)

The Delegate option is specific to **this** create-sdd PM interview — the PM defers a *product* decision to the developer who will build it. Never carry it into any other interview: when `grill-me` runs for planning (`create-implementation-plan`, `implement-ticket`), the developer is the interviewee, so a "delegate to the developer" option is meaningless there.

When the PM picks "Delegate the decision to the developer", do NOT re-ask or infer an answer: record the field under `## Open Questions & Delegated Decisions` (origin `delegated`, format in Phase 7) and move to the next topic. A delegated field is a valid terminal state — it is neither PM-confirmed nor an error.

#### Routing blocks

#### When QAF_ASK_USER_MCP_TOOL is set (autonomous execution — questions routed via MCP):

Load [references/batched-interview.md](references/batched-interview.md) before drafting any question: over MCP the interview runs in batched rounds, not one question at a time.

```bash
if [[ -n "${QAF_ASK_USER_MCP_TOOL:-}" ]]; then
  PAYLOAD=$(MCP_SKILL=create-sdd-ticket MCP_PHASE=phase-3-product-interview \
    bash "$MCP_AUQ_HOOKS/build-mcp-payload.sh")
  mkdir -p "$ARTIFACTS_DIR/decisions"
  jq -r '.invocation.batch_id' <<<"$PAYLOAD" > "$ARTIFACTS_DIR/decisions/sdd-batch.txt"
  # Build ONLY the 2–3 concrete options for each question in the round, recommended FIRST with a ' (Recommended)' suffix. Example (Topic 1):
  #   [{"id":"coreUserRole","question":"Who are the primary users of this feature?","recommended_answer":"Admin users — they manage the user list.","options":[{"label":"Admin users (Recommended)"},{"label":"All authenticated users"},{"label":"External API clients"}],"multi_select":false}]
  # Write the round as JSON through a quoted heredoc so the shell expands nothing.
  QUESTIONS_JSON=$(jq -c . <<'QAF_SDD_QUESTIONS'
<JSON array with every question of this round, per references/batched-interview.md; options[] = the 2–3 concrete choices only>
QAF_SDD_QUESTIONS
)
  # Append the Delegate option deterministically so it can never be dropped (create-sdd PM interview only). 'Other' is auto-surfaced by the channel.
  QUESTIONS_JSON=$(jq -c 'map(.options += [{"label":"Delegate the decision to the developer"}])' <<<"$QUESTIONS_JSON")
  "$QAF_ASK_USER_MCP_TOOL" "$(jq --argjson q "$QUESTIONS_JSON" '.questions=$q' <<<"$PAYLOAD")"
  # Send the whole round in this ONE call. After the answers return, run the conflict check in references/batched-interview.md; call again only for a follow-up round, building its payload with MCP_PARENT_BATCH_ID="$(cat "$ARTIFACTS_DIR/decisions/sdd-batch.txt")" and an incremented MCP_ATTEMPT.
fi
```

#### When QAF_ASK_USER_MCP_TOOL is unset and `--skip-questions` is absent — interactive execution

Present one question at a time and wait for the PM's reply before continuing. `(d) Delegate…` is always the last concrete option and `(e) Other` is always offered — every question, no exceptions. Example (Topic 1; adapt the question and (a)–(c) per topic):

```markdown
## Topic 1: Users & Role

**Question**: Who are the primary users of this feature?

**Options**:
(a) Admin users (Recommended)
(b) All authenticated users
(c) External API clients
(d) Delegate the decision to the developer
(e) Other — type your own answer

> Evidence for the recommended option: existing user model exposes an `admin` role (docs/llm-wiki/wiki/services/users.md#roles)

**Your answer**: ___
```

#### When `--skip-questions` is passed — headless fallback

Never prompt. For each unanswered product-judgment field, record an item under `## Open Questions & Delegated Decisions` (origin `headless-assumption`, format in Phase 7), using the recommended answer as the labeled working assumption. Seed the BDD scenarios (Phase 6) from those recommended answers so the ≥3-scenario minimum still holds, but tag each such scenario `(assumed)` and cross-list it under Open Questions & Delegated Decisions — never present an assumed scenario as PM-confirmed scope. The ticket is still generated — automation never hangs.

### Phase 4: Apply PM answers

Parse the PM's confirmed answers, apply them back into the canonical ticket fields, and re-run completeness validation: every required product-judgment field is either PM-confirmed, PM-delegated to the developer, or (headless) recorded under `## Open Questions & Delegated Decisions`. Ensure no unresolved placeholder content remains.

### Phase 5: Apply INVEST Criteria

Validate across all INVEST dimensions. "Small" is a PM judgment, not a code-boundary measurement.

- **Independent** — does not depend on another un-merged story.
- **Negotiable** — scope confirmed with the PM (Phase 3), not silently decided.
- **Valuable** — the user story states a clear business benefit.
- **Estimable** — enough behavioral detail to size (≥3 BDD scenarios; unambiguous acceptance criteria).
- **Small** — ask the PM: "Is this one coherent, independently-valuable behavior increment a team could deliver in a sprint?" If not, recommend a split **by user-facing capability**, not by code boundary (e.g. "This covers two distinct capabilities — [A] and [B] — which could ship independently. Recommend splitting."). Never cite file counts or service counts as the basis for a split.
- **Testable** — every acceptance criterion has a corresponding Given-When-Then scenario.

**Headless mode:** `Negotiable` and `Small` are defined by PM confirmation, which headless cannot obtain. Treat both as **provisionally** satisfied, record the open scope/sizing judgment under `## Open Questions & Delegated Decisions`, and still emit the ticket — mirroring the BDD-seeding carve-out. Never block emission on a PM confirmation headless cannot get.

### Phase 6: Generate BDD scenarios

Refine and complete the scenarios collected in Phase 3. All must be seeded from PM-confirmed answers — never silently derived from comments or inferred from code. **Headless exception:** with no PM to confirm, seed from the recommended answers instead, tag each scenario `(assumed)`, and cross-list them under `## Open Questions & Delegated Decisions` — this keeps the minimum coverage without presenting assumed scope as confirmed. Minimum coverage: ≥3 scenarios (1 happy path, ≥1 edge case, ≥1 error/failure path).

Follow [references/bdd-guide.md](references/bdd-guide.md) for scenario structure (Given/When/Then/And/But roles with WRONG/CORRECT examples), business-language content rules, titling, and the coverage checklist.

### Phase 7: Output ticket

- Format the completed ticket using [templates/sdd-ticket-template.md](templates/sdd-ticket-template.md). Emit **only** the sections in that template — no Technical Context, Architecture Decisions, or Implementation Notes.
- Include `## Open Questions & Delegated Decisions` as a first-class section whenever any field was PM-delegated to the developer or (headless) left unresolved. This section is the parseable contract `implement-ticket` consumes — emit each item exactly in this shape (keep the field labels verbatim):

  ```markdown
  - **[Topic/Field]** — *delegated* | *headless-assumption*
    - Question: [the behavioral question posed to the PM]
    - Options presented: [option A] · [option B] · [option C]
    - Recommended: [recommended answer] — Evidence: [citation]
  ```
- Include `Dependencies` only when Phase 2's `dependencies[]` is non-empty; omit the whole section otherwise — never render its placeholders as an empty section (that would trip the "no placeholders" gate).
- Apply the same omit-when-empty rule to every other optional section — `Metrics`, `Future Considerations`, `Data & Input Validation`, and `References`: fill it only when there is real content, and drop the line/section entirely when there is none. No `[...]` placeholder may survive into the emitted ticket.
- Save to the provided markdown path exactly; if markdown output is requested without a path, default to `.claude-temp/tickets/<ticket-id>/<ticket-id>.md`. Create parent directories as needed.
- When saving to Jira, follow the two Saving To Jira rules below — preserve priority, issue type, and project key when provided.
- When saving to Linear, load [references/linear-save-destination.md](references/linear-save-destination.md) before writing.
- Return the saved path or tracker identifier plus a short quality summary.

Before finalizing, run the [final quality checklist](references/quality-and-errors.md) and confirm: no required section missing, no placeholder markers, INVEST applied, BDD scenarios concrete and behavioral, no technical/architecture/implementation content, and the ticket is ready for `implement-ticket`'s planner to derive the "how".

#### Saving To Jira: update the source issue, never create a duplicate

Decide create-vs-update from the **input mode**, not from the save target:

- **Input was `--from-jira <KEY>`** → the SDD refines an existing issue. **Update that exact issue** with the Atlassian MCP issue-edit operation, targeting `<KEY>`. Do **NOT** call the issue-create operation in this mode — it creates a duplicate card and orphans the original. In this mode the `--save-to-jira` value **has no routing effect** whatever it is: whether it is a board/project URL, a ticket URL, or absent entirely, the write always targets `<KEY>` from `--from-jira`. A board/project URL is used only to confirm the destination project matches the source key's project; a ticket URL is **ignored for routing** (never update that second ticket); an absent value means "update in place" and the project-match confirmation is skipped. Never STOP over a save-target/source-project mismatch — the source `<KEY>` wins.
- **Input was `--from-input` or `--from-markdown`** (no source Jira key) → there is nothing to update. **Create** a new issue with the MCP issue-create operation in the project derived from `--save-to-jira <BOARD-URL>` (or `--project-key`).

Resolve the source key deterministically before deciding: `--from-jira` may be a bare key (`PROJ-123`) or a full URL — extract the `PROJ-123` issue key first. If the input was `--from-jira` but no issue key can be parsed, **STOP and report**; never silently fall back to creating a new issue.

#### Saving To Jira: the SDD body goes in the description, never a comment

The synthesized SDD **is** the issue's specification — it belongs in the `description` field:

- **Update mode** — write the full SDD markdown to the issue-edit operation's `description` field. It replaces the prior description in full.
- **Create mode** — write the full SDD markdown to the issue-create operation's `description` field.

Do **NOT** post the SDD body as a comment via the MCP comment-add operation. A comment is reserved for an optional one-line traceability note (e.g. `Description refined by /create-sdd-ticket`); the spec itself must always land in `description` so it remains the canonical, top-of-ticket source of truth. A comment-only write leaves the original description stale and is a defect, not an acceptable fallback. When updating, set `summary`, `priority`, issue type, and `labels` only where the SDD or the explicit flags provide them; do not blank fields the SDD does not set.

#### Saving To Linear: resolve and validate the destination first

The same create-vs-update rule applies: `--from-linear` input updates that exact issue, every other input creates and requires a `linear.app` team or project URL. The SDD body goes in the issue description, never a comment. Load [references/linear-save-destination.md](references/linear-save-destination.md) for URL validation, destination resolution, and post-write workspace verification before calling any Linear MCP write operation.

## Comment-aware synthesis

When the input was `--from-jira` or `--from-linear`, the ticket-context artifact's `## Description` is the **starting point** of the SDD, not the final word. The `## Comments` section carries the conversation that refined the requirement — the SDD must reflect that final state. Recorded PM/stakeholder decisions are honored, not re-litigated.

**Three buckets for comment handling:**

1. **Explicit recorded decisions → honored directly.** Comments carrying strong-decision markers (`Decision:` / `Approved:` / `confirmed:` / `confirmado:`) and not later contradicted are applied directly to the product field. Not re-asked in Phase 3.
2. **Ambiguous or partial signals → recommended answers for Phase 3.** The skill proposes the comment-derived reading as the recommended answer; the PM confirms or overrides. This replaces silent inference — the comment's weight is preserved, the silent adoption is not.
3. **Implementation or architecture content → dropped.** Implementation detail, architecture decisions, and technical constraints in comments are out of scope for the product spec; the `implement-ticket` planner re-derives the "how" from the same comments downstream.

A comment that names or renames the ticket subject also rewrites the SDD's `title` and inline references to the prior name.

**Precedence:** when two comments contradict each other on the same product point, or a comment contradicts the description, the **most recent comment wins**. Exception: an older comment with a strong-decision marker and no later explicit contradiction stands — a more recent comment adds rather than overrides.

**Output is the SDD only.** The body must NOT contain inline citations (`_(from comment #10042, …)_`), rename/renumber log lines, meta-narration about the synthesis, or any comment id / author / timestamp. Traceability lives in the tracker comment thread and the working artifact at `$ARTIFACTS_DIR/context/ticket-context.md`.

## Question policy

Ask about product and business behavior only — never implementation details, which belong to the executor. Product questions are bounded to: who the users are and what they need to accomplish; what behaviors the system should enable; what is in and out of scope; what observable outcomes confirm success; what happens in edge and error conditions; whether any NFRs exist as measurable behavioral outcomes.

Never ask what the gap classifier can answer as a code-verifiable fact — "does X exist?", "what does the current system do?", "which service owns Y?" all resolve via wiki / grep.

## Usage examples

```text
# Text → markdown
--from-input "Admin users report taking too long to find specific users in the 500+ user list. Add search filtering by name and email, similar to the existing product search." --save-to-markdown "./specs/user-search.md"

# Text → Jira
--from-input "Add user export feature for admins to download CSV reports" --save-to-jira "https://acme.atlassian.net/jira/software/projects/PROJ/boards/1" --project-key PROJ --priority High

# Jira → markdown
--from-jira "PROJ-100" --save-to-markdown "./specs/refined-PROJ-100.md"

# Linear → update same issue
--from-linear "ENG-100" --save-to-linear

# Markdown → Jira
--from-markdown "./specs/draft-feature.md" --save-to-jira "https://acme.atlassian.net/jira/software/projects/PROJ/boards/1" --project-key PROJ
```

## Reference

- [references/bdd-guide.md](references/bdd-guide.md) — Given-When-Then scenario anatomy, business-language content rules, coverage checklist.
- [references/ticket-structure.md](references/ticket-structure.md) — required fields and the canonical JSON shape behind the rendered template.
- [references/batched-interview.md](references/batched-interview.md): how Phase 3 runs over an MCP ask channel (batched rounds, follow-up only on conflict).
- [references/quality-and-errors.md](references/quality-and-errors.md) — the final Completeness / INVEST / BDD / Product-clarity checklist and standard failure responses.
- [templates/sdd-ticket-template.md](templates/sdd-ticket-template.md) — the lean product-only markdown output template.

## Integration Notes

- Each affected service page's `## Conventions & How-To` → `### Code Rules` (behavioral gotchas) and `### Testing` (edge/error-case framing only) — read in Phase 0.1; `### Multi-File Workflows` is deliberately not loaded (planner's *how*, not product behavior).
- `fetch-ticket-context` — **mandatory** in Phase 1 for `--from-jira` and `--from-linear`; produces the canonical artifact whose `## Description` + `## Comments` drive comment-aware synthesis.
- `grill-me` — the interview engine for Phase 3: create-sdd supplies the product topics and routing, `grill-me` supplies the one-question-at-a-time decision-tree method (explore-before-asking, recommended answer, surface dependency).
- `implement-ticket` — the resulting product spec is the input to its planner agent, which derives the "how" (files, architecture, integration points).
- LLM wiki: required in Phase 0.2 when available; soft-optional when missing.
