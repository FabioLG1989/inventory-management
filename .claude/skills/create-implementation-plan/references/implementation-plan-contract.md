# Implementation Plan Contract

Defines the implementation-plan artifact: the `planner` agent writes plans that conform to it, and `implement-ticket` validates a plan against it before executing.

## Canonical Artifact Path

`$ARTIFACTS_DIR/plans/implementation-plan.md`, where `$ARTIFACTS_DIR` is `<workspace-root>/.claude-temp/tickets/<TICKET_ID>/artifacts/`, resolved by the calling skill.

## Required And Optional Sections

| Section | Status |
|---|---|
| `# Implementation Plan` (title) | expected |
| `## Plan Tier` | optional — one value: `simple` or `standard`; absent means `standard` |
| `## Summary` | expected |
| `## Wiki Evidence` | **REQUIRED** |
| `## Source Evidence` | **REQUIRED** |
| `## Impact Analysis` | expected |
| `## Implementation Steps` | expected — target files must be named somewhere in the plan |
| `## Risk Assessment` | expected |
| `## Testing Strategy` | **REQUIRED** |
| `## Recommended Implementers` | **REQUIRED** — non-empty ordered list |
| `## Cross-Stack Contract` | **REQUIRED when `## Recommended Implementers` has 2+ entries** — the interface one entry provides and another consumes, or the literal `None — entries are independent`; not validation-gated: a multi-entry plan missing it dispatches sequentially |
| `## Affected Repositories` | **REQUIRED in `multi` workspace mode**; omit in `single` mode |
| `## Assumptions And Open Questions` | expected — interactive planning surfaces these to the developer; autonomous runs record auto-resolved questions here, including any business decision the business wave auto-resolved |

**REQUIRED** sections are validation-gated: the executor refuses a plan that lacks them (see Validation Rules below). **Expected** sections are part of the canonical shape the `planner` agent always emits, but a hand-written plan missing them is normalized rather than rejected.

### Plan Tier (micro-plans)

A plan may carry a `## Plan Tier` section holding one value: `simple` or `standard`; an absent section means `standard`. At `simple` the plan is a micro-plan: the evidence sections may be single-bullet direct-verification entries ("verified by direct Read of `<file>` (lines N–M)"; "Grep for `<text>` matched only the target files"), `## Implementation Steps` pins the exact edit (`<file>:<line>`), and `## Testing Strategy` must name its exact verification command. The Validation Rules below are unchanged and apply in full — brevity is licensed, absence is not.

A micro-plan is written by the executor's own run-mode phase, from the scan and interview that judged the tier — the planning skill is not invoked at `simple` and authors no micro-plans. A plan failing a Validation Rule at that tier means the verdict was wrong, and the executor escalates the run rather than executing an invalid plan.

## Section Shapes

Plans use these sections in this shape. Preserve it so downstream parsing and human review remain stable.

`## Impact Analysis` and `## Risk Assessment` orient a reviewer; they are not the deliverable. Only what applies, one line per bullet, no paragraphs; `## Implementation Steps` is what gets executed.

```markdown
# Implementation Plan

## Summary

Brief summary of what needs to be done.

## Wiki Evidence

Cite every wiki page you drew a fact from. A claim the plan hinges on MUST be verified by a Grep or `Read` of the source before use; record that verification under Source Evidence below.

- `<wiki page path>`: key facts used
- Conventions consulted (PRESCRIPTIVE — rules, examples, checklists; cited when load-bearing, and only when `index.md` lists the page — absent pages go under wiki gaps, never hunted): each affected service page's `## Conventions & How-To` (`docs/llm-wiki/wiki/services/<id>.md`) and `docs/llm-wiki/wiki/conventions/project.md`
- Claims taken from the wiki without further verification:
- Wiki gaps that required a source check:

## Source Evidence

One bullet per load-bearing claim: the Grep or Read that verified it and the `path:line` it resolved to.

- `<claim>` — Grep `<pattern>` / Read `<file>` → `path:line`: what it proved or failed to prove beyond the wiki

## Impact Analysis

- Affected services/modules:
- Callers/imports/dependencies:
- Related tests:
- Blast radius:
- Potential breaking changes:

## Implementation Steps

1. Step title
   - What:
   - Where:
   - How:
   - Patterns to follow:
   - Tests:

## Risk Assessment

- Overall risk:
- Risks:
- Mitigations:
- Rollback strategy:

## Testing Strategy

- Unit tests:
- Integration tests:
- E2E/manual checks:
- Commands to run:

A bucket the developer declined during the plan interview reads `None — user-confirmed`; a bucket whose kind has no detected infrastructure in the affected services (`stack_profile.services[].testing`) reads `None — no detected infrastructure`. Only a recorded developer decision writes the first marker — the interview loop on resolution, or the planner folding in a test-scope entry from `ticket-context.md`'s `## Directions Confirmed`; never planner inference (a `--skip-questions` run has no developer in the loop). The second is evidence-based and either may write it. Declining `e2e` rewrites only the e2e portion of `E2E/manual checks:` — its manual and visual checks stay. `Commands to run:` stays non-empty — the scoped regression command — even when every bucket is declined. Each of its lines ends with the planner's probe result, `— resolves` or `— unresolved: <reason>`.

## Recommended Implementers

Non-empty ordered list, one entry per unique language bucket derived from `framework-config.json::stack_profile.services` (longest-prefix file→service match, dedupe by `language`). Every entry's agent is `implementer-generic`, which serves every language; each entry names the service IDs it covers, its scoped files, and a one-line rationale. The executor dispatches entries in the listed order, or all at once when their scoped files are pairwise disjoint and `## Cross-Stack Contract` is present — pinning an interface, or declaring `None — entries are independent`; a multi-entry plan missing the section dispatches sequentially.

1. `implementer-generic` — services: `<service-id>[, <service-id>...]`
   - `<path/to/file>`
   - `<path/to/file>`
   - rationale: <why this position in the order>

(Repeat the block once per bucket. Single-stack tickets produce a list of length 1.)

## Cross-Stack Contract

- Provider: entry <n> — Consumer: entry <m>
- <exact interface: endpoint/path, params, request/response fields, types>
- (no inter-entry dependency: this section's whole body is `None — entries are independent`)

## Assumptions And Open Questions

- Assumptions:
- Open questions:
```

### Verification command probes

Probe each scoped command once without installing, using its supported list, dry-run or collect-only mode or checking the runner's prerequisites. `command -v` alone is not readiness. Suffix each line `— resolves` or `— unresolved: <reason>`. Missing dependencies do not invalidate the plan: retain the regression command for executor setup. Planned targets and inconclusive probes do not establish unavailability.

### Affected Repositories — multi-repo workspaces only

Maps each touched repo (a `child_repos` path from the preflight marker) to its files, so commit and PR creation fan out per repo; implementer dispatch stays per language bucket.

```markdown
## Affected Repositories

- `/abs/path/repo-a`: services/api/src/foo.ts, services/api/src/foo.test.ts
- `/abs/path/repo-b`: apps/web/src/bar.tsx
```

## Validation Rules

The executor enforces these before executing any plan; the producer asserts them before returning one. A plan that fails any rule is not executor-ready.

1. The plan file exists at the canonical artifact path.
2. The plan contains `## Wiki Evidence` and `## Source Evidence` sections, citing the wiki paths and the `path:line` checks actually made.
3. The plan contains a `## Testing Strategy` section, and target files to create/modify are named.
4. The plan contains a `## Recommended Implementers` section that is a non-empty ordered list where **every entry's agent is `implementer-generic`**, and each entry names the service IDs it covers (derived from `framework-config.json::stack_profile.services`) and its scoped files.
5. In `multi` workspace mode, the plan contains an `## Affected Repositories` section mapping each touched `child_repos` path to its files. `single` mode may omit it — `AFFECTED_REPOS` is then the one workspace repo.
6. `## Testing Strategy` names scoped checks; it never prescribes a whole-repo or whole-suite run as a mandatory local gate — suite-wide sweeps belong to CI or the executor's `--full`. Its commands must not modify tracked files: formatters and linters run in check/diff mode (never the writing form), and every lint, format or write-capable command targets the plan's named files, never a directory — a directory surfaces pre-existing findings in files the ticket never touches, and an explicit path bypasses the tool's own excludes, so it can rewrite files the project deliberately skips. Keep setup separate: never bootstrap hooks or install dependencies as a verification command. `pre-commit` and husky-style hooks are commit-time gates. Each `Commands to run:` line carries that probe result per `### Verification command probes`; the executor prepares the environment, the planner never does.
7. An existing test assertion or test case that cannot survive the change is replaced with the new expected value, never deleted, loosened, or skipped. The one exception is a ticket that explicitly names the test, or the exact behavior or input the assertion covers, for removal; that the new code raises on the assertion's input is never one.
8. When the ticket body proposes code, the plan records a source verification of it — adopted, corrected, or rejected, with the evidence.
9. A decision the plan defers to a human lives under `- Open questions:` — never as a risk mitigation or step note ("escalate before merge" is not a mitigation). An autonomous run never leaves a known failure path (a branch that crashes or loses data) open: the steps take the non-crashing branch and record the choice under `- Assumptions:`.
10. Every implementation step is executable by an unattended agent: none requires a human action, a manual runtime observation, or an interactive session as a precondition. A manual check belongs under `## Testing Strategy` → `E2E/manual checks:`; a premise the planner could not verify is an `- Assumptions:` entry naming the value assumed, never a step that blocks until someone verifies it.
