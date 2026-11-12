# Run mode

Sole owner of the run-mode decision: how it resolves, the scan and interview behind a `simple` verdict, and what `simple` removes. Phase 1 of `/implement-ticket` reads this file only on an unpinned run and never restates its rules; the persisted `run-config.json` shape, the in-place escalation edit and the delivery gates live in that phase. Flag polarity and the layered-default hierarchy live in `.claude/skills/implement-ticket/docs/FLAGS.md`.

Two modes. `standard` is the full pipeline — plan gate, implementer agents, full test operations. `simple` is inline execution: Phase 1 authors a contract-valid micro-plan and the orchestrator applies it itself, reduced only where the table below says so — never improvise a reduction.

## Resolution order — first match wins

1. `--full` → `standard`, `source: flag-full`. Skips the scan and the interview — nothing about the ticket can move a pinned mode. It also turns on every optional step of the run; the set is named in `.claude/skills/implement-ticket/docs/FLAGS.md`.
2. `--standard` → `standard`, `source: flag-standard`. Same pin, the same skip of the scan and the interview, and Phase 5's full test matrix — nothing else. `--full` wins when both are passed.
3. `--from-plan` → `standard`, `source: default`. The developer supplied the plan; the gate's job is to validate or normalize what they wrote, and that plan drives implementer dispatch. No scan, no interview.
4. Otherwise → the scan, then (interactive runs) the interview. An autonomous run (`--skip-questions` / `--autonomous`) scans the same way — confirm every candidate and settle or record every fork, since its settled findings bind the planner either way — and skips the interview. `simple` resolves two ways only: the developer confirmed it (`source: confirmed`), or an autonomous scan met the Verdict's autonomous bar (`source: judgement`). A run landing on `standard` records `source: judgement` when a rule or an answer decided it, `default` when the scan simply concluded so.

## The scan

Its product is an evidence table plus a fork list; the verdict and the interview's questions are read off them, never guessed from ticket prose. Build it from `$ARTIFACTS_DIR/context/ticket-context.md`:

| Field | How |
|---|---|
| `candidate_files` | the files the ticket implies — name them from its text, confirm each by Grep, Read the edit site |
| `services` | longest-prefix match of each candidate on `framework-config.json::stack_profile.services[].path` |
| `repos` | the `child_repos` entries in `.preflight-ok` containing those candidates |
| `structural` | the candidates that are structural (defined below) |
| `blast_radius` | per edited symbol, Grep its references repo-wide (word-boundary, test directories included) and Read each hit outside `candidate_files`; record each as `path:line` classed name-only, unchanged call, or reach under `## Scan Findings`. A symbol-less edit (constant, top-level statement, config): Grep the way the project's own imports reference the module (module path, package name or file basename) |
| `delegated_decisions` | count of items under the ticket's `## Open Questions & Delegated Decisions` |
| `forks` | the decisions an inline edit would otherwise pick silently — placement when more than one plausible site exists, the name or contract of any new public surface (a path, a key, a signature), the data source when more than one candidate holds the value, auth posture. Each fork carries the scan's recommended answer. When a fork is a field value in a file that is one of many registry/table siblings, Grep how existing siblings set it before recommending. Before listing a fork, Grep the tests: an existing test asserting the behavior in question settles it — record it as a read under `## Scan Findings`, not a fork |

Also read the wiki router (`docs/llm-wiki/CLAUDE.md`) and `docs/llm-wiki/wiki/index.md` inline — bounded context that grounds the candidates and the recommended answers. No page bodies and no delegation here; deep wiki reading belongs to the planner.

**What settles a fork.** The ticket is never evidence: its text, and any code it proposes, is the input under verification — a proposed snippet is one option among the others, checked like them. When an option mishandles some input, the smallest variant that handles it is an option too. Before settling a fork whose branches differ in runtime behavior, trace each option on the inputs the existing tests exercise: an option that fails or raises on one of them cannot be settled in its favor — calling the assertion stale is not evidence — and a fork no option survives is unresolved, as is one whose options edit the same lines when an assertion on their current output is all that rules an option out. A claim about how code handles an input that a settlement rests on is executed, not read, when the code runs in isolation (a regex, a pure function); record the probe in the finding.

Persist what the scan established into `$ARTIFACTS_DIR/context/ticket-context.md` under `## Scan Findings`: one line per candidate — confirmed ones as `path:line` and the fact it settled, the rest marked `unconfirmed`. No file contents; the planner reads its own evidence. A settled entry is confirmed scope downstream, like `## Directions Confirmed`.

For each placement fork, record the alternatives, selected option, and deciding evidence under `## Scan Findings`, including forks settled during the scan.

**Structural** — a dependency manifest, a lock file, a runtime or toolchain pin, a build-system file, a test-runner config, a CI/CD or container/deploy file, or a database schema or migration file. Judge by what the file does, not by whether you recognize its name. Exception, Phase 7's doc gate only: a new migration file in an existing migrations directory that adds no dependency, command, or directory cannot change the cheat-sheet — it stays structural for the scan but does not trigger doc maintenance.

### When to stop

There is no call quota; there is a stopping rule. Additional reads do not by themselves imply `standard`.

- Stop the moment a hard rule fires — including candidate confirmation: the verdict is `standard` already, and every further call is spent buying an answer you hold. Remaining candidates go to `## Scan Findings` as `unconfirmed`.
- Continue focused reads or probes when they can resolve a specific remaining question about placement, behavior, impact, or verification and the investigation is narrowing that decision. A bounded placement fork may be settled by an existing test or decisive source evidence regardless of the number of reads needed; apply the evidence checks under **What settles a fork**.
- Stop once the evidence needed for the verdict is complete. Do not keep reading merely to increase confidence in an already settled finding.
- Choose `standard` when investigation expands into broader design or coordination, stops narrowing the decision, or leaves a consequential question unresolved.

All hard rules and Verdict criteria still apply; focused investigation does not waive them. A settled fork stays recorded under `## Scan Findings`.

### Hard rules — any one forces `standard`

Reads, not judgements; each has one correct answer, and the interview never overrides one — structural files, multiple services, multiple repos, and unconfirmable candidates are objective reads, not gray areas:

- `structural` is non-empty.
- `services` has more than one entry.
- `repos` has more than one entry.
- No candidate file could be confirmed. Absence of evidence is never evidence of simplicity — a ticket whose symbols nothing matches reads as small precisely because nothing came back.
- `forks` has more than 4 entries: that much ambiguity is not a simple change. Skip the interview's fork questions; delegated-decision items still reach the developer through the plan gate's business wave.

### The interview

Autonomous runs skip it and write nothing under `## Directions Confirmed` — that section holds a developer's answers only. Every fork goes under `## Scan Findings` with its answer, and stays in `run-config.json::scan.forks`: a preference fork (naming, or placement between options that behave identically at runtime) takes the scan's recommendation; a fork whose branches differ in runtime behavior — fixing the code that mishandles an input versus normalizing or guarding it upstream always does — is settled only by evidence (an existing test's assertion, or a source read that decides it); one no evidence settles is recorded as `unresolved fork:` for the planner. Otherwise it fires when no hard rule fired and either the strict criteria below hold (interactively, confirmation is what admits `simple`) or `forks`/`delegated_decisions` is non-empty (those answers shape the plan either way).

ONE batched round of questions to the developer. Present every item as multiple-choice, its recommended answer listed first and suffixed ` (Recommended)`:

- each delegated-decision item, using its SDD `Options presented`;
- each fork, using the scan's recommended answer;
- when the strict criteria hold, the mode question: "Simple — apply the edit directly (Recommended)" vs "Standard — full planning pipeline".

Cap each round at 4 items, ranked by consequence: the mode question, then delegated decisions, then forks by blast radius. ONE call, except when the mode question is on the table and the batch overflows — `simple` has no plan gate to catch a dropped item, so ask the remainder in ONE more call. Still overflowing after two calls → resolve `standard`; the rest reach the developer at the plan gate. An ask that returns no answer (no developer reachable) resolves `standard`.

Persist every answer into `$ARTIFACTS_DIR/context/ticket-context.md` before resolving the verdict: delegated-decision items under `## Delegated Decisions Resolved` (`Q: … → Decided: …`), fork and mode answers under `## Directions Confirmed`. Both sections are confirmed scope downstream — the plan gate's business wave and the planner never re-ask them.

Interactively, entering `simple` REQUIRES the developer's confirmation: no confirmation resolves `standard` — never silent `simple`. Autonomously, the Verdict's evidence bar stands in for it, and the `Run mode:` line names the source.

### Verdict

Strict criteria — all must hold for `simple` to be on the table:

- at most two files carry a behavior change — test files and docstring- or comment-only edits do not count toward it;
- the change is mechanical (text, a constant, copy, style, a self-contained addition) so its entire behavior is the edited lines;
- `blast_radius` reaches nothing outside those files. An outside reference is not reach when `## Scan Findings` records its `path:line` as *name-only* (an import, re-export, registration or type reference that never runs the edited lines) or *unchanged call* (a call through a kept signature whose result changes only on the input the ticket reports broken, with no existing test asserting the old result on that input); any other is reach. A test asserts the old result when it would fail on that input once the change lands — for a reported configuration (database backend, platform, locale, runtime version, flag), under that configuration, not the local suite's; record it by `path:line` as reach;
- a scoped verification command and its target are grounded in repository scripts, configuration or scoped test additions. Probe readiness per `### Verification command probes` in `.claude/skills/create-implementation-plan/references/implementation-plan-contract.md`; record the probe under `## Scan Findings`, and its result suffixes the micro-plan's `Commands to run:` line. Missing dependencies or unbuilt local extensions do not force `standard`: Phase 3 prepares the environment. An unexplained command or target is uncertainty and resolves `standard`.

- **Interactive**: `simple` when the criteria hold and the developer confirmed it. Declined or unasked → `standard`.
- **Autonomous**: `simple` only when every criterion holds, `delegated_decisions` is 0, and every fork is settled — a preference fork by the scan's recommendation, any other by an existing test's assertion, a decisive source read, or an executed probe; any `unresolved fork:` resolves `standard`. The verification command must be grounded; environment readiness does not decide the mode.
- `standard` — everything else. Uncertainty is not a tie; it resolves here.

Push toward `standard` when the change breaks shared or public API surface (renaming, removing, or retyping an existing field; changing an existing signature's parameters — a purely additive field or endpoint is not), touches auth, permissions, money, or data migrations, edits a file many others depend on, or describes behavior changes rather than a localized edit.

Every unreadable file, unparseable section, and missing field resolves to `standard`. Work is removed only when something positively established the change is routine — and the developer confirmed it, or an autonomous scan met the bar above.

## What `simple` removes

A phase absent from this table runs identically in both modes.

| Phase | `simple` |
|---|---|
| 2 Obtain Plan | not invoked at all — Phase 1 authored the micro-plan, so Phase 2 only validates it against the contract |
| 4 Implementation | no implementer agent: apply the micro-plan directly and assert the diff equals the scoped set. Any surprise escalates `mode` to `standard` in place (Phase 1's edit) and re-enters through implementer dispatch |
| 5 Testing | ONLY the micro-plan's named verification command plus the command catalog's lint operation (`standard` runs the catalog's single `run_tests` entry covering the change, or — with none — the detected runner scoped to the change; the whole-repo sweep and the full matrix require the `--full` or `--standard` flag). A code or verification-plan failure escalates and the standard fix loop takes over; environment unavailability records `untested` without escalation or another setup attempt |
| 11 Review Loop | `/pr-reviewer --quick`: two specialists (`specialist-bug-logic`, `specialist-security-style`), no judge; deterministic verification and posting unchanged |

The security specialist survives `--quick` deliberately: a small diff is exactly where an injected vulnerability hides best, and `simple` is the author's smallest possible size call. Only the fan-out the judge exists to reconcile is cut.
