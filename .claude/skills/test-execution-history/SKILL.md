---
name: test-execution-history
version: 1.3.0
last-updated: 2026-09-14
description: Persist every test run into a per-suite execution history (last 15 runs) and compute pass/fail trends, duration trends, and flaky-test detection — either from local runs or synced directly from GitHub Actions / Azure Pipelines run history. Scope a run to a git diff instead of running an entire suite, with safety gates that refuse to scope on protected branches, on core-file changes, or when a changed file maps to no known test. Can render a PDF trend report, but only when the user explicitly asks for one — never generate a report unhanded. Use when asked to "track test history", "test trends", "are tests getting flaky", "is the suite getting slower", "persist test results", "last N runs", "PDF test report", "flakiness over time", "sync CI history", "only run tests affected by this diff", "test impact analysis", "scope tests to changed files", or when a CI/local test run should be recorded for future trend analysis.
argument-hint: 'record --suite <name> --junit <path...> [--scope full|impacted --impacted-files <path...> --base-ref <ref>] | ci-sync --provider github|azure --suite <name> --workflow <name>|--pipeline-id <id> | trends --suite <name> [--last 15] [--format json|markdown|pdf --output <path>] | impact --suite <name> --base <ref> [--head <ref>] [--map-file <path>] [--format json|markdown]'
allowed-tools: Bash, Read, Write, Glob, Grep, AskUserQuestion
user-invocable: true
---

# Test Execution History Skill

Closes the "no execution-history access" gap: this skill persists the last 15 runs of any test suite (any language, any runner) and turns that history into pass/fail trends, duration trends, and flaky-test detection — without a database, without a hosted dashboard, and without assuming a specific test runner. It also closes the follow-on gap where agents can read live CI/pipeline status via `gh`/`az` but have no surface for how that status trends over time: `scripts/ci_sync.py` (see [Syncing history from CI](#syncing-history-from-ci)) turns GitHub Actions / Azure Pipelines run history into the same trend-ready data, for suites that only ever run in CI. It also closes the "no test-impact analysis" gap: `scripts/impact_analysis.py` (see [Test impact analysis](#test-impact-analysis)) scopes a run to a git diff instead of defaulting to run-everything, with safety gates that fall back to a full run whenever the mapping can't be trusted.

## Contents

- [Overview](#overview)
- [Storage](#storage)
- [Workflow](#workflow)
- [Ask before generating a report](#ask-before-generating-a-report)
- [Emitting JUnit XML per stack](#emitting-junit-xml-per-stack)
- [Generic mode (no JUnit XML available)](#generic-mode-no-junit-xml-available)
- [Test impact analysis](#test-impact-analysis)
- [Syncing history from CI](#syncing-history-from-ci)
- [Trend analysis](#trend-analysis)
- [PDF report format](#pdf-report-format)
- [Trend Analyst agent](#trend-analyst-agent)
- [References](#references)

## Overview

Four scripts, no dependencies beyond the Python standard library (`ci_sync.py` also shells out to whichever of `gh`/`az` the caller already has authenticated):

1. **`scripts/impact_analysis.py`** — before running anything, decide whether this run can be scoped to a git diff and, if so, which test files to run. Refuses to scope (falls back to `full`) on protected branches, core-file changes, or unmapped source files — see [Test impact analysis](#test-impact-analysis).
2. **`scripts/record_run.py`** — after a test run finishes, appends one normalized run record (pass/fail/skip/error totals, duration, and per-test results) to that suite's history file. Stack-agnostic via JUnit XML, which nearly every runner can emit.
3. **`scripts/ci_sync.py`** — pulls recent completed runs from GitHub Actions or Azure Pipelines and appends the ones not already recorded, using the same history file and record shape as `record_run.py`. For suites that only ever execute in CI (nobody calls `record_run.py` there), this is what gives them a trend history at all.
4. **`scripts/trends.py`** — reads the last 15 runs from that history and reports pass-rate trend, duration trend (with a stricter regression flag), flaky tests, newly-failing/newly-fixed tests since the previous run, and the slowest tests in the latest run. Can render that as JSON, markdown, or a **PDF report** — see [Ask before generating a report](#ask-before-generating-a-report) before ever invoking the PDF path.

All four are plain CLIs — invoke them directly with Bash, or from CI, or after a local test run.

## Storage

```
.qa/test-history/<suite>.jsonl
```

One JSON-Lines file per logical suite (`unit`, `e2e`, `backend-api`, ...), pruned to the newest **15** runs (`--retain`, default `15`) on every write — enough history for a meaningful trend without letting the file grow unbounded. Full schema: [references/history-schema.md](references/history-schema.md).

## Workflow

```bash
# 0. Optional: decide whether this run can be scoped to a diff instead of
#    running the whole suite — see [Test impact analysis](#test-impact-analysis).
#    Skip straight to step 1 for a normal full run.
python3 ".claude/skills/test-execution-history/scripts/impact_analysis.py" \
  --suite unit --base origin/main --format markdown

# 1. Run tests, producing a JUnit XML report (see cheat-sheet below) — either
#    the whole suite, or only the files step 0 selected
npx jest --reporters=jest-junit

# 2. Record the run — add --scope impacted --impacted-files <path...> --base-ref <ref>
#    if step 0 was used and its scope was "impacted"
python3 ".claude/skills/test-execution-history/scripts/record_run.py" \
  --suite unit \
  --junit reports/junit.xml \
  --ci

# 3. Get trends over the last 15 runs (JSON/markdown — always fine to run automatically)
python3 ".claude/skills/test-execution-history/scripts/trends.py" --suite unit --last 15 --format markdown

# 4. A PDF report is a separate, opt-in step — see below. Do not run it unasked.
```

`record_run.py` auto-detects `--commit`/`--branch` via `git rev-parse` when the caller doesn't pass them, and accepts multiple `--junit` paths/globs to merge a monorepo's per-package reports into one run record.

## Ask before generating a report

**Recording a run (step 2) and pulling JSON/markdown trends (step 3) are safe to do automatically** — they're cheap, local, and don't produce a deliverable for anyone else.

**Generating the PDF report is not automatic.** It's a deliverable the user may want to share, attach to a ticket, or hand to someone else — so before ever running `trends.py --format pdf`, gate on the engineer's answer following the project's MCP-first prompt routing, never a bare `AskUserQuestion` call:

```bash
if [[ -n "${QAF_ASK_USER_MCP_TOOL:-}" ]]; then
  QUESTIONS_JSON="<single-question array: 'I have <N> recorded runs for the <suite> suite. Generate a PDF test-history report?'; options[] = Yes / No>"
  PAYLOAD=$(MCP_SKILL=test-execution-history MCP_PHASE=pdf-report-gate \
    bash "$MCP_AUQ_HOOKS/build-mcp-payload.sh")
  "$QAF_ASK_USER_MCP_TOOL" "$(jq --argjson q "$QUESTIONS_JSON" '.questions=$q' <<<"$PAYLOAD")"
elif [[ -t 0 ]]; then
  : # interactive — ask via AskUserQuestion: "I have <N> recorded runs for the <suite> suite. Would you like a PDF test-history report generated?"
else
  echo "PDF report skipped: no interactive channel available (headless/CI)" >&2
fi
```

Only proceed to the PDF step on an explicit yes from the MCP tool or `AskUserQuestion`. Every other outcome — an explicit no, `QAF_ASK_USER_MCP_TOOL` unset with no TTY (headless/CI — exactly where `ci_sync.py` runs unattended), or a channel that returns nothing usable — skips the PDF step without asking again; the run must never block waiting on it. If the user just asked for "the trends" or "how are the tests doing" without mentioning a report/document/PDF, answer with the JSON/markdown summary (or the Trend Analyst agent's narrative) and still run this gate before turning that into a PDF. This rule also applies inside `agents/trend-analyst.md` — it must not be invoked to produce a report proactively after every recorded run.

## Emitting JUnit XML per stack

JUnit XML is the closest thing to a universal test-result format — use whichever of these matches the detected stack (see the project's stack profile / `framework-config.json` rather than guessing):

| Runner | Flag / package |
| --- | --- |
| Jest | `jest-junit` reporter (`--reporters=jest-junit`) |
| pytest | `pytest --junitxml=report.xml` |
| PHPUnit | `phpunit --log-junit report.xml` |
| Go | `gotestsum --junitfile report.xml` |
| .NET | `dotnet test --logger "junit;LogFilePath=report.xml"` (JunitXml.TestLogger package) |
| Maven Surefire | native (`target/surefire-reports/*.xml`) |
| Playwright | `reporter: [['junit', { outputFile: 'report.xml' }]]` in config |
| Mocha | `mocha-junit-reporter` |
| RSpec | `rspec_junit_formatter` |

Pass every produced file (or a glob) to `--junit`; `record_run.py` merges them into one run.

## Generic mode (no JUnit XML available)

When nothing in the stack can emit JUnit XML, skip `--junit` and pass counts directly — this loses per-test granularity (no flaky-test detection, no per-test slowest list for that run) but still gets pass-rate and duration trends:

```bash
python3 ".claude/skills/test-execution-history/scripts/record_run.py" \
  --suite legacy-suite \
  --total 42 --passed 40 --failed 2 --duration-seconds 87.3
```

## Test impact analysis

Closes the "no test-impact analysis" gap: the default for this skill (and most CI setups) is
run-everything on every change. `scripts/impact_analysis.py` scopes a run to what a git diff
actually touched, so a suite too slow to run in full on every commit still gets exercised
precisely, with a safety-first design — it defaults to recommending a full run whenever it isn't
confident the scoping is safe, rather than defaulting to under-testing:

```bash
python3 ".claude/skills/test-execution-history/scripts/impact_analysis.py" \
  --suite unit --base origin/main --format markdown
```

It refuses to scope down (`scope: "full"`) when:
- the current branch is protected (`main`, `master`, `develop`/`development`, `release/*`, `hotfix/*` by default);
- a changed file matches a core glob (lockfile, CI config, root config, env file) or a core directory at any depth (migration);
- a changed source file maps to no known test file ("unmapped").

Otherwise it returns `scope: "impacted"` with the test file(s) to run and a `recommendedCommand`
built from `--map-file`'s per-suite `runCommandTemplate`, if one is configured. Full mapping
algorithm, the `.qa/test-impact-map.json` schema, and how to get a stronger transitive-impact
signal by Grepping importers instead of filesystem-convention guessing: [references/test-impact-analysis.md](references/test-impact-analysis.md).

Never run the recommended command automatically without telling the user which files were
selected and why — a scoped run is a judgment call the human should be able to see and override,
not a silent substitution for the suite they asked to run.

Record whichever run actually executes — full or impacted — using `record_run.py`'s `--scope`,
`--impacted-files`, and `--base-ref` flags (see [Workflow](#workflow) step 2) so trend and
flaky-test history stay accurate; [references/trend-metrics.md](references/trend-metrics.md#flaky-test-detection)
explains how mixed-scope history should be read.

Regression tests for the mapping/safety-gate logic: `scripts/test_impact_analysis.py`
(`python3 -m unittest test_impact_analysis -v` from the `scripts/` directory) — stdlib `unittest`
against real scratch git repos, no dependencies.

## Syncing history from CI

Reading live CI status ad hoc (`gh run list`, `gh pr checks`, `az pipelines runs list`) answers "is the last run green" but leaves no trend — this is the gap `scripts/ci_sync.py` closes for suites that only ever run in CI. It fetches recently completed runs and appends the ones not already recorded (deduped by the CI platform's own run id) into the same `.qa/test-history/<suite>.jsonl` used above, so **every** trend below (pass-rate, duration, flaky) works for CI-synced history exactly like it does for locally-recorded runs. Safe to run automatically — same rule as `record_run.py`/`trends.py`'s JSON/markdown output, no report is produced.

```bash
# GitHub Actions — coarse mode: one pass/fail point per run, from the run's conclusion
python3 ".claude/skills/test-execution-history/scripts/ci_sync.py" --provider github --suite unit \
  --workflow CI --repo my-org/my-repo --branch main

# GitHub Actions — full mode: downloads a published JUnit artifact for per-test/flaky detection
python3 ".claude/skills/test-execution-history/scripts/ci_sync.py" --provider github --suite unit \
  --workflow CI --repo my-org/my-repo --branch main \
  --junit-artifact-pattern "test-results-*"

# Azure Pipelines — coarse mode
python3 ".claude/skills/test-execution-history/scripts/ci_sync.py" --provider azure --suite unit \
  --pipeline-id 42 --branch main

# Azure Pipelines — full mode (artifact must be published by the pipeline's own PublishBuildArtifacts/PublishPipelineArtifact step)
python3 ".claude/skills/test-execution-history/scripts/ci_sync.py" --provider azure --suite unit \
  --pipeline-id 42 --branch main --junit-artifact-name test-results
```

Without a JUnit artifact, each CI run becomes one `totals: {"total": 1, ...}` data point (`source: "ci-status"`) — enough for pass-rate/duration trend and run-level flakiness, but not per-test flaky-test detection (see [references/trend-metrics.md](references/trend-metrics.md)). Point `--junit-artifact-pattern`/`--junit-artifact-name` at whatever the workflow/pipeline already publishes to get full per-test history (`source: "ci-junit"`) instead. Keep `--limit` at or below `--retain` (default 15 for both) so a sync never tries to re-insert a run that already aged out of the file.

## Trend analysis

```bash
python3 ".claude/skills/test-execution-history/scripts/trends.py" --suite unit --last 15
```

Reports (JSON by default, `--format markdown` for a human-readable version, `--format pdf --output <path>` for the report deliverable — see [Ask before generating a report](#ask-before-generating-a-report) before using `pdf`. Full field-by-field walkthrough in [references/trend-metrics.md](references/trend-metrics.md)):

- **Pass-rate trend** — recent-vs-prior window mean, `improving` / `degrading` / `stable`
- **Duration trend** — recent-vs-prior window mean, plus a stricter single-run `regression` flag against the historical baseline (default: >20% slower)
- **Flaky tests** — tests that flipped pass/fail at least once in the window, ranked by flip count
- **Newly failing / newly fixed** — diff against the immediately-previous run
- **Slowest tests** — top N in the latest run

All thresholds are CLI flags (`--regression-threshold`, `--pass-rate-threshold-pp`, `--duration-threshold-pct`) — tune per suite rather than hardcoding assumptions about "normal" variance.

## PDF report format

```bash
python3 ".claude/skills/test-execution-history/scripts/trends.py" --suite unit --last 15 --format pdf --output test-history-report.pdf
```

- `--output` is **required** for `--format pdf` — PDF is binary and cannot be printed to stdout like `json`/`markdown` can.
- The writer emits raw PDF 1.4 objects directly (catalog, pages, a built-in Helvetica font, text-only content streams) — **no third-party library**, nothing to `pip install` on any of the 6000+ machines this framework runs on. It word-wraps and paginates automatically; there is no page limit.
- Content mirrors the markdown report exactly (same `_report_sections` data in `trends.py` renders both formats), so nothing is PDF-only or markdown-only.
- This is a text report, not a charting library — no charts/sparklines. If a project later needs visual trend charts, that's a deliberate follow-up, not something to bolt onto this writer silently.
- Text is encoded as `cp1252` (Helvetica/`WinAnsiEncoding`), the built-in PDF font's native charset. A suite or test name with characters outside it (CJK, Cyrillic, emoji) renders as `?` in the PDF with no warning — the JSON/markdown reports are unaffected.
- **Never run this without the user's explicit go-ahead** — see the next section.

## Trend Analyst agent

For a narrative summary instead of raw JSON/markdown tables (e.g. to post as a PR comment or Slack message, or as the prose that goes into the PDF), hand the `trends.py` output to [agents/trend-analyst.md](agents/trend-analyst.md). It interprets the numbers — verdict, what regressed, which flaky tests to look at first — without re-deriving anything the script already computed. Same rule applies: it produces output on request, not proactively after every recorded run.

## References

- [History schema](references/history-schema.md) — run-record and test-case shape, storage/retention rules
- [Trend metrics](references/trend-metrics.md) — exact formulas and thresholds behind every computed field
- [Test impact analysis](references/test-impact-analysis.md) — mapping algorithm, safety-gate rules, map-file schema
- [Trend Analyst agent](agents/trend-analyst.md) — narrative synthesis over `trends.py` output
