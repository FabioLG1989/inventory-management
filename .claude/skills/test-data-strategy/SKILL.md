---
name: test-data-strategy
version: 1.0.0
last-updated: 2026-09-14
description: Governance rules for the data that test cases and test code use — factories/builders over inline literals, fixture provenance, synthetic data over sampled-real data, per-environment isolation, and a hard no-PII rule — plus a scanner that checks test/fixture files against them. Distinct from pytest-patterns / e2e-test-architecture, which cover fixture *syntax*; this covers what data a fixture is allowed to hold. Use when asked to "test data strategy", "test data policy", "mask PII in tests", "synthetic test data", "anonymize fixtures", "factory pattern for test data", "is this test data safe to commit", or when generate-test-cases needs to decide what concrete values a generated test case should use.
argument-hint: 'scan --path <dir/file/glob...> [--fake-domains <domain...>] [--format json|markdown] [--fail-on-finding]'
allowed-tools: Bash, Read, Write, Glob, Grep
user-invocable: true
---

# Test Data Strategy Skill

Closes the "no test-data strategy for AI-generated data" gap: `/generate-test-cases` and the
test-writing skills in this group produce concrete data values (emails, names, IDs, fixture
files) with no enforced rule for what those values are allowed to be. This skill is that rule
set, plus `scripts/scan_test_data.py` to check it mechanically instead of trusting review alone.

## Contents

- [The five rules](#the-five-rules)
- [Scanning test/fixture files](#scanning-testfixture-files)
- [Applying this during test-case generation](#applying-this-during-test-case-generation)
- [Where fixture syntax lives instead](#where-fixture-syntax-lives-instead)
- [CI gating](#ci-gating)
- [References](#references)

## The five rules

### 1. No real PII, ever

Never a real name, email, phone number, government ID, payment card, address, or auth
credential — not a teammate's, not a customer's, not one copied from a bug report "just for this
test," not one sampled from a production export. The exact forms this is checked against (safe
email domains, safe phone/SSN ranges, safe card numbers) are in
[references/pii-patterns.md](references/pii-patterns.md); when in doubt, prefer an obviously-fake
value over a plausible-real one, even if the scanner wouldn't catch the plausible one.

### 2. Factories/builders over inline literals

A concrete entity used by more than one test should come from a factory function/builder with
sensible defaults and explicit overrides — not the same object literal copy-pasted across files.
Duplication is the leading indicator this rule is being skipped:
[scan_test_data.py](#scanning-testfixture-files) flags any literal value hardcoded identically in
3+ files as a hint to extract one. Mechanics (fixture scope, factory-fixture syntax, builder
patterns per stack) live in the language/framework skills — see
[Where fixture syntax lives instead](#where-fixture-syntax-lives-instead).

### 3. Fixture provenance

Every static fixture file (`fixtures/`, `seeds/`, `__fixtures__/`) should say where its data came
from — a `// generated` / `# synthetic` comment, a `_provenance`/`_meta` key, or a reference to the
factory/faker call that built it. Without this, a `.json` fixture is indistinguishable from a real
data export someone dropped in "temporarily." Checked by
[scan_test_data.py](#scanning-testfixture-files)'s `fixture-missing-provenance` finding.

### 4. Environment isolation

Tests must never point at a shared staging or production data store by default — resolve the
target through a project-specific environment variable, the same pattern already used elsewhere in
this framework (`qa-camunda`'s `CAMUNDA_REST_BASE`, `playwright-e2e-automation`'s `APP_BASE_URL` in
its `.env.example`), never a hardcoded host. Prefer a test-owned database/schema/namespace seeded
and torn down by the test itself; for parallel runs, one per worker. A fixture file is not exempt
from this — a "seed data" fixture that only works against one shared environment's IDs is a hidden
coupling, not a fixture.

### 5. Synthetic, deterministic generation

When a scenario needs data with realistic shape (names, addresses, amounts), generate it
deterministically — a seeded faker-style generator, or a fixed factory default — rather than
inventing ad hoc literals or, worse, sampling real records. Determinism matters as much as
realism: a fixture whose values change between runs turns a flaky-looking failure into a
debugging session about the fixture instead of the code under test. The same applies to
time-dependent values — freeze or inject time, never bake in a wall-clock-relative literal.

## Scanning test/fixture files

```bash
python3 ".claude/skills/test-data-strategy/scripts/scan_test_data.py" \
  --path src tests fixtures --format markdown
```

Reports five finding categories — `pii-suspect-email`, `pii-suspect-phone`, `pii-suspect-ssn`,
`pii-suspect-card`, `fixture-missing-provenance`, `duplicated-literal-suggest-factory` — each with
file:line and the exact rule it failed. This is a regex/heuristic scan, not an AST — it has no
network access, needs nothing installed, and is honest about what it can't see (real names,
runtime-assembled values, encoded PII): see
[references/pii-patterns.md#what-this-scanner-does-not-catch](references/pii-patterns.md#what-this-scanner-does-not-catch).
A clean report is evidence, not proof.

`--fail-on-finding` exits `1` only when a `pii-suspect-*` finding exists — a missing-provenance or
duplicated-literal finding is advisory and never fails a gate on its own.

`node_modules/`, `.venv/`, `venv/`, `dist/`, `build/`, `.git/`, `target/`, and `vendor/` are always
pruned from the walk — a vendored dependency's own `fixtures/` directory is not this project's test
data, regardless of how deep `--path` is pointed. Add more with `--exclude-dir <name...>`
(additive to the defaults, not a replacement).

Regression tests for the scanner itself: `scripts/test_scan_test_data.py`
(`python3 -m unittest test_scan_test_data -v` from the `scripts/` directory) — stdlib `unittest`,
no dependencies, covers the false-positive and directory-exclusion cases above by name.

## Applying this during test-case generation

`/generate-test-cases` (Phase 3d/3e) writes concrete values into `preconditions` and `steps` —
"user with email X", "order total $Y". Those values are test data and this skill's rules apply to
them the same as to code: use an `example.com`-style email, a `555-01XX` phone, an obviously
placeholder name, never a value that reads as a real person or account. When a generated batch
will be handed off for implementation (e.g. via `--format e2e-flow` into
`/playwright-e2e-automation`), run `scan_test_data.py` over the resulting spec files once they
exist, the same as any other test code.

## Where fixture syntax lives instead

This skill is the *governance* layer — what a fixture is allowed to contain and why. The
*mechanics* of writing one are stack-specific and stay where they already are: fixture scopes and
factory-fixture patterns in [pytest-patterns](../pytest-patterns/SKILL.md#fixtures), Playwright's
`fixtures/index.ts` pattern in
[e2e-test-architecture/references/helpers-and-fixtures.md](../e2e-test-architecture/references/helpers-and-fixtures.md).
Read the relevant one for *how*; read this skill for *what data is allowed in it*.

## CI gating

```yaml
- name: Test-data governance scan
  run: |
    python3 ".claude/skills/test-data-strategy/scripts/scan_test_data.py" \
      --path src tests fixtures --fail-on-finding --format markdown
```

Safe to run automatically and unattended (read-only, no deliverable, no user-facing report) —
unlike `test-execution-history`'s PDF report, there is no "ask before generating" gate here.

## References

- [PII patterns](references/pii-patterns.md) — exact detection rules, why each threshold was chosen, safe-placeholder cheat sheet, and what the scanner can't see
- [Fixture mechanics — pytest](../pytest-patterns/SKILL.md#fixtures)
- [Fixture mechanics — Playwright](../e2e-test-architecture/references/helpers-and-fixtures.md)
- [generate-test-cases](../generate-test-cases/SKILL.md) — where AI-generated data values originate
