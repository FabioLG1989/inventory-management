---
name: requirement-coverage-gap-analysis
version: 1.0.0
last-updated: 2026-09-14
description: Compare requirement-derived test scenarios (from a Jira ticket, spec, or a generate-test-cases batch) against an existing test suite — repo test files or a test management tool — to surface acceptance criteria and edge cases with no corresponding test. Distinct from jest-coverage-automation, which measures line/branch coverage of source code — this measures scenario coverage against a source-of-truth requirement, a different axis entirely. Use when asked to "find untested scenarios", "requirement coverage gap", "what acceptance criteria have no test", "are we missing test cases for TICKET-123", "gap analysis against existing tests", or before closing a ticket to confirm every AC has a corresponding test.
argument-hint: '--from-jira <KEY>|--from-markdown <path>|--from-text "<text>"  --against-suite <path/glob...>|--against-qase <CODE>|--against-testrail <ID>|--against-jira'
allowed-tools: Read, Write, Bash, Glob, Grep
user-invocable: true
---

# Requirement Coverage Gap Analysis Skill

Closes the "no requirement-to-coverage-gap analysis" gap: `/generate-test-cases`' Phase 3e
coverage checklist validates a freshly generated batch against itself — it has no visibility into
an existing suite, so it cannot tell a reviewer "these 3 acceptance criteria already have tests,
these 2 don't." This skill is that missing comparison: requirement-derived scenarios vs. what
already exists, not a generated batch vs. itself, and not code paths vs. source (that's
[jest-coverage-automation](../jest-coverage-automation/SKILL.md)).

## Contents

- [When to Use vs Other Skills](#when-to-use-vs-other-skills)
- [Workflow](#workflow)
- [Gap report format](#gap-report-format)
- [Offering to fill the gaps](#offering-to-fill-the-gaps)
- [References](#references)

## When to Use vs Other Skills

| Question | Skill |
|----------|-------|
| "What test cases should this ticket have?" (nothing exists yet) | [`/generate-test-cases`](../generate-test-cases/SKILL.md) |
| "Which of this ticket's acceptance criteria already have a test, and which don't?" | `/requirement-coverage-gap-analysis` (this skill) |
| "What % of source lines/branches does the suite execute?" | [`/jest-coverage-automation`](../jest-coverage-automation/SKILL.md) |
| "Is this suite getting flakier / slower over time?" | [`/test-execution-history`](../test-execution-history/SKILL.md) |
| "Is the data these tests use safe to commit?" | [`/test-data-strategy`](../test-data-strategy/SKILL.md) |

A requirement can be 100% scenario-covered by this skill's measure while source coverage is low
(the tests exist but don't exercise every branch), or vice versa (high line coverage from tests
that never assert the specific behavior an AC describes). The two numbers answer different
questions — report them separately, never blend them into one "coverage" figure.

## Workflow

### 1. Extract requirement scenarios

Reuse `/generate-test-cases`' own Phase 3a (identify test areas) and Phase 3b (apply test design
techniques — equivalence partitioning, BVA, negative testing, error guessing, and the conditional
techniques) from [generate-test-cases/SKILL.md](../generate-test-cases/SKILL.md#3a-identify-test-areas).
The output here is lighter than a full test case, though: a flat scenario list, not
generate-test-cases' canonical format —

```json
{"scenarios": [
  {"id": "S1", "text": "Rejects login with an expired session token", "category": "negative"},
  {"id": "S2", "text": "Locks the account after 5 failed attempts", "category": "security"}
]}
```

— because the only thing this skill needs per scenario is enough text to match against an
existing test title; preconditions/steps/priority only matter once a gap is confirmed and someone
is writing the actual test case (at that point, hand the ❌ list to `/generate-test-cases`, see
[Offering to fill the gaps](#offering-to-fill-the-gaps)).

### 2. Inventory the existing suite

**Repo test files** (`--against-suite <path/glob...>`):

```bash
python3 ".claude/skills/requirement-coverage-gap-analysis/scripts/inventory_tests.py" \
  --path src tests --format json --output inventory.json
```

Stack-agnostic via regex over common test-naming conventions — see
[references/extraction-patterns.md](references/extraction-patterns.md) for exactly what each
stack's pattern catches and misses. Read that before trusting a thin result for a language it
warns about. `node_modules/`, `.venv/`, `venv/`, `dist/`, `build/`, `.git/`, `target/`, and
`vendor/` are always pruned from the walk (`--exclude-dir <name...>` to add more) — a vendored
dependency's own test suite is not this project's inventory.

Regression tests for the extractor itself: `scripts/test_inventory_tests.py`
(`python3 -m unittest test_inventory_tests -v` from the `scripts/` directory) — stdlib `unittest`,
no dependencies, one case per stack plus the directory-exclusion behavior above.

**Test management tool** (`--against-qase <CODE>` / `--against-testrail <ID>` / `--against-jira`):
list existing cases via the same MCP calls `/generate-test-cases`' adapters already use
(`adapters/qase.md`, `adapters/testrail.md`, `adapters/jira.md`) — read-only, listing titles only,
never creating anything at this step. Shape the result into the same
`{"tests": [{"file", "line", "title", "framework"}]}` form `inventory_tests.py` produces (`file`
can be the tool's case ID/URL, `line` omitted or `0`) so the next step is identical either way.

### 3. Prefilter, then adjudicate

```bash
python3 ".claude/skills/requirement-coverage-gap-analysis/scripts/match_scenarios.py" \
  --scenarios scenarios.json --inventory inventory.json --format json
```

Scores every scenario against every inventory title (string-similarity + token overlap, no
network, no AST — see the script's own docstring for the formula) and bands each scenario:

- **`auto-covered`** (score ≥ 0.72 default) — provisional. Spot-check a sample rather than
  re-reading every one; a generic title ("should return 200") can score high against an unrelated
  scenario by accident.
- **`needs-review`** (0.35–0.72 default) — read both texts and decide: `Covered`, `Partial`, or
  `Gap`. This band is the actual work of this skill; do not skip it by rounding to whichever
  neighboring band is more convenient.
- **`likely-gap`** (< 0.35 default) — provisional absence. Confirm there truly is no test for it
  under a different phrasing before reporting it as a gap; the prefilter only compares text, not
  meaning.

Never report the prefilter's bands as the final verdict without the `needs-review` read — that
band existing at all is what makes this different from a keyword search.

**The `@DisplayName`/`[Description]` title limitation (see [extraction-patterns.md](references/extraction-patterns.md))
is not just cosmetic here — it changes the band.** A JUnit test titled only by its bare method name
scores far lower against prose than the same test would with its `@DisplayName` text: measured on
one real pair, `shouldRejectExpiredCard` scored 0.246 (`likely-gap`) against the scenario "User
cannot check out with an expired card," while the same requirement against a descriptive title
scored 1.000 (`auto-covered`). A `likely-gap` verdict for a stack whose extractor emits bare method
names is weaker evidence of an actual gap than the same verdict from Jest/RSpec titles — read the
`needs-review` band more generously for those stacks rather than trusting the band cutoffs at face
value.

Malformed entries (a scenario with no `text`, an inventory item with no `title` — expected when
`--scenarios` comes from agent-generated ticket prose) are skipped and reported, not fatal — see
`_validate_scenarios`/`_validate_inventory` in the script.

Regression tests: `scripts/test_match_scenarios.py`
(`python3 -m unittest test_match_scenarios -v` from the `scripts/` directory) — stdlib `unittest`,
no dependencies.

## Gap report format

```markdown
## Requirement coverage — <ticket/source> vs <suite/tool>

N/M scenarios covered (X%), Y gaps, Z partial — <headline: e.g. "all negative-path scenarios for
the retry logic are uncovered">

| Scenario | Category | Status | Matched existing test | Action |
|---|---|---|---|---|
| Rejects login with an expired session token | negative | ✅ Covered | `auth.spec.ts:14` | — |
| Locks the account after 5 failed attempts | security | ❌ Gap | — | Generate a test case |
| Session persists across a page refresh | functional | ⚠️ Partial | `auth.spec.ts:22` (checks login only, not refresh) | Extend existing test or add a new one |
```

Cite the specific matched test for every `Covered`/`Partial` row — a status with no citation is
not verifiable and should read as `needs-review`, not `Covered`.

## Offering to fill the gaps

A gap report is analysis, not a deliverable that writes new test cases on its own. When gaps
exist, **offer** to hand the ❌ list to `/generate-test-cases --from-text "<gap scenarios>"` —
never invoke it automatically. This mirrors `test-execution-history`'s "ask before generating a
report" rule: the gap report itself (markdown/JSON to the conversation) is fine to produce
unprompted since it answers what was asked; turning it into new test cases is a second, larger
action the user should explicitly choose.

## References

- [Extraction patterns](references/extraction-patterns.md) — per-stack regex rules, what each catches and misses
- [generate-test-cases](../generate-test-cases/SKILL.md) — scenario-identification techniques (3a/3b) this skill reuses; also where a confirmed gap gets filled
- [jest-coverage-automation](../jest-coverage-automation/SKILL.md) — the source-code-coverage question this skill does not answer
- [test-data-strategy](../test-data-strategy/SKILL.md) — governance for any data values in a newly generated test case that fills a confirmed gap
