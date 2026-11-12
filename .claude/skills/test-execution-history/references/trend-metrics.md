# Trend metrics — formulas and thresholds

`scripts/trends.py` reads the last `--last N` runs (default 15, matching `record_run.py`'s default `--retain`) for a suite and computes everything below. All thresholds are CLI flags with the defaults listed here — tune them per project rather than editing the script.

## Window split

Runs are split into two halves to compare "now" against "just before now":

- `half = max(1, N // 2)`
- `recent half` = the newest `half` runs
- `prior half` = the `half` runs immediately before that (empty if `N <= half`, i.e. fewer than 2 runs — trend fields then report `"insufficient-data"` instead of guessing)

This is a simple moving comparison, not a linear regression — it stays cheap, stack-agnostic, and easy to reason about with as few as 2-4 runs, which is what a new suite will have.

## Pass-rate trend

For each run, `passRate = passed / total * 100` (`0` if `total == 0`).

```
deltaPp = mean(passRate over recent half) - mean(passRate over prior half)
```

- `deltaPp > --pass-rate-threshold-pp` (default `1.0`) → `"improving"`
- `deltaPp < -threshold` → `"degrading"`
- otherwise → `"stable"`

## Duration trend

```
percentChange = (mean(duration, recent half) - mean(duration, prior half)) / mean(duration, prior half) * 100
```

- `percentChange > --duration-threshold-pct` (default `10.0`) → `"slower"`
- `percentChange < -threshold` → `"faster"`
- otherwise → `"stable"`

### Regression flag (separate from the trend direction)

The trend direction compares two small windows and can be noisy on 2-4 runs. `durationTrend.regression` is a stricter, single-run check meant for gating (e.g. failing a CI step):

```
baselineMean = mean(durationSeconds over every run except the latest)
regression = latestRun.durationSeconds > baselineMean * (1 + --regression-threshold)
```

Default `--regression-threshold` is `0.20` (20% slower than the historical baseline). Raise it for suites with naturally high run-to-run variance (e.g. E2E suites hitting a shared staging environment); lower it for tightly-controlled unit suites where a 5-10% jump is already suspicious.

## Flaky-test detection

For every test seen across the analyzed window, build its chronological status sequence (`passed` / `failed` / `error`; `skipped` occurrences are dropped from the sequence rather than treated as a state):

```
flipCount = number of adjacent pairs (a, b) in the sequence where (a == "passed") != (b == "passed")
```

A test is reported as flaky when `flipCount >= 1` and it appeared in at least 2 of the analyzed runs. `failed` and `error` are both treated as "not passed" for this purpose — the distinction still shows up per-run in `totals.errors` vs `totals.failed`.

If a classname::name key appears more than once within one run (two different tests across merged `--junit` files sharing a name), it's collapsed to a single status — the worst of error/failed > passed > skipped — before this sequence is built, so a same-run duplicate never reads as an extra flip between "runs" that never happened.

Runs recorded by `scripts/ci_sync.py` with `source: "ci-status"` have an empty `testCases` (no per-test data available from CI run status alone), so they never contribute to this list — a suite synced entirely in `ci-status` mode will always report zero flaky tests here even if it visibly flips between green and red across runs. That flip still shows up in `passRateTrend` and in the raw `totals` per run; it's a real signal, just not a per-test one. Sync with `--junit-artifact-pattern`/`--junit-artifact-name` (`source: "ci-junit"`) to get per-test flaky detection from CI-only suites.

The same partial-visibility caveat applies to runs recorded with `scope: "impacted"` (see [Test impact analysis](../SKILL.md#test-impact-analysis)): a test not selected for that run simply has no status entry for it in that run, exactly as if the run predated the test — it does not read as a flip and does not get counted against that test's `occurrences`. This is the correct behavior (an unrun test isn't evidence of anything), but it does mean a window with many `impacted` runs sees fewer `occurrences` per test overall, so a genuinely flaky test that impact analysis rarely selects can take longer to cross the `flipCount >= 1` / `occurrences >= 2` bar than it would under `scope: "full"` runs.

`passRateTrend` and `durationTrend`, unlike flaky detection, read each run's `totals` at face value — and an `impacted` run's `totals` describe only the subset that ran, not the whole suite. A 3-test impacted run at 100% and a 500-test full run at 98% are not the same signal, so a window mixing both scopes can swing on scope alone rather than on a real pass-rate or duration change. Treat a trend computed over a mixed-scope window as indicative, not conclusive — filter `runs` to one `scope` first (or record impacted runs to a distinct suite name, e.g. `unit-impacted`) when a project needs a clean comparison.

This catches the common flaky pattern (intermittent pass/fail) but will also flag a test that failed once and was then legitimately fixed — that's expected: a `flipCount` of `1` with `lastStatus: "passed"` reads very differently from one with `lastStatus: "failed"`, and both `newlyFailing`/`newlyFixed` (below) already separate the "just changed" case out explicitly.

## Newly failing / newly fixed

Pure diff between the two most recent runs only (not the whole window):

- `newlyFailing`: status is `failed`/`error` in the latest run AND was not `failed`/`error` in the previous run.
- `newlyFixed`: status is `passed` in the latest run AND was `failed`/`error` in the previous run.

## Slowest tests

`topSlowestLatestRun` (default top 5, `--top-slowest`) is simply the latest run's `testCases` sorted by `durationSeconds` descending — a duration-regression pointer for the run you'd actually act on right now, independent of the aggregate trend above.

## Why halves-comparison instead of a full regression

A least-squares trend line needs enough points to be stable and is easy to over-interpret on a fresh suite with 3-5 runs. The halves comparison degrades gracefully (returns `"insufficient-data"` instead of a misleading slope), needs no extra dependency (`statistics.fmean` is stdlib), and mirrors the "regression flag" the agent and CI gates actually care about. If a suite accumulates a long, low-noise history and finer-grained trend detection becomes worth the complexity, that's a deliberate follow-up — not something to bolt onto this script silently.
