# Execution-history schema

## Storage layout

```
<history-dir>/<suite>.jsonl
```

- `<history-dir>` defaults to `.qa/test-history/` at the target project's root (override with `--history-dir`).
- One file per logical `<suite>` (e.g. `unit.jsonl`, `e2e.jsonl`, `backend-api.jsonl`) so unrelated suites never share a trend window.
- **JSON Lines**: one run record per line, append-only. `record_run.py` prunes each file down to the newest `--retain` lines (default **15**, matching `trends.py`'s default `--last 15`) after every append, so the file self-bounds and stays diffable. Raise `--retain` on both scripts together if a project wants a longer memory — they don't have to match, but a `--last` bigger than `--retain` just silently returns fewer runs than asked.
- Commit the directory to the repo (small, text, no secrets) so trends survive across machines and CI runners, or point `--history-dir` at a persistent CI cache/artifact path if the team prefers not to commit it. Either way, do not `.gitignore` it silently — that silently reintroduces the "no persistence" gap this skill closes.
- **Concurrent writers**: `record_run.py` and `ci_sync.py` hold an exclusive `flock` on a sibling `<suite>.jsonl.lock` file around their own append-then-prune sequence, so parallel CI jobs recording the same suite queue instead of clobbering each other's runs. POSIX only — on Windows (no `fcntl`) the lock is a no-op and concurrent writes to the same suite can still silently drop a run.

## Run record

One line of `<suite>.jsonl`, written by `scripts/record_run.py`:

```json
{
  "schemaVersion": "1",
  "runId": "54ba8732a7a4",
  "suite": "unit",
  "timestamp": "2026-08-27T14:13:15.765111+00:00",
  "commit": "a1b2c3d",
  "branch": "main",
  "ci": true,
  "label": "gh-run-42",
  "source": "junit-xml",
  "totals": { "total": 3, "passed": 2, "failed": 1, "skipped": 0, "errors": 0 },
  "durationSeconds": 10.0,
  "testCases": [
    { "name": "test_one", "classname": "pkg.A", "status": "passed", "durationSeconds": 2.0 },
    { "name": "test_two", "classname": "pkg.A", "status": "failed", "durationSeconds": 3.0 }
  ],
  "scope": "full",
  "impactedFiles": [],
  "baseRef": null
}
```

| Field | Type | Notes |
| --- | --- | --- |
| `schemaVersion` | string | Bump when the shape changes; `trends.py` should tolerate unknown older versions gracefully. |
| `runId` | string | 12-char hex, generated per recorded run. Not a test-runner concept — purely a history-file key. |
| `suite` | string | Matches the filename stem; lets one project keep independent trends per test type. |
| `timestamp` | string | UTC ISO-8601, when the run was recorded (not necessarily when it executed). |
| `commit` / `branch` | string \| null | Auto-detected via `git rev-parse` at record time when not passed explicitly; `null` outside a git repo. |
| `ci` | boolean | Set with `--ci` to distinguish CI-sourced runs from local dev runs when eyeballing the file. |
| `label` | string \| null | Free text — CI job id, environment name, whatever the caller finds useful. |
| `source` | `"junit-xml"` \| `"generic"` \| `"ci-junit"` \| `"ci-status"` | Which input mode produced this record. The first two come from `record_run.py` (see `SKILL.md`); the `ci-*` values come from `scripts/ci_sync.py` — see below. |
| `provider` | `"github"` \| `"azure"` \| absent | Only present on `ci_sync.py` records. |
| `ciRunId` | string \| absent | The CI platform's own run id (GitHub `databaseId`, Azure `id`). Only present on `ci_sync.py` records — this is the dedup key `ci_sync.py` uses to avoid re-syncing a run it already wrote. |
| `ciRunUrl` | string \| null \| absent | Link to the run on the CI platform, when the provider exposes one (GitHub does; Azure DevOps CLI does not, hence `null`). |
| `totals` | object | `total`, `passed`, `failed`, `skipped`, `errors` — always present, `errors` folded separately from `failed` (JUnit distinguishes `<error>` from `<failure>`). |
| `durationSeconds` | number | Sum of per-testsuite `time` attributes (JUnit mode) or `--duration-seconds` (generic mode). |
| `testCases` | array | Empty in generic mode (no per-test granularity available). In JUnit mode, one entry per `<testcase>` across all merged report files — this is what flaky-test and per-test duration analysis in `trends.py` reads. |
| `scope` | `"full"` \| `"impacted"` | `"full"` unless `record_run.py --scope impacted` was passed — set when the run only executed the subset `scripts/impact_analysis.py` selected for a diff (see [Test impact analysis](../SKILL.md#test-impact-analysis)). Defaults to `"full"` for every record written before this field existed, which is the correct read for them (they were whole-suite runs). |
| `impactedFiles` | array \| absent | Only present when `scope` is `"impacted"` — the test file(s) `impact_analysis.py` selected and that this run actually executed, from `--impacted-files`. |
| `baseRef` | string \| null \| absent | Only present when `scope` is `"impacted"` — the git ref `impact_analysis.py` diffed against (`--base-ref`), for reproducing what the diff was. |

### Test-case entry

| Field | Type | Notes |
| --- | --- | --- |
| `name` | string | JUnit `testcase/@name`. |
| `classname` | string | JUnit `testcase/@classname`; may be empty for runners that don't set it. |
| `status` | `"passed"` \| `"failed"` \| `"skipped"` \| `"error"` | `trends.py` groups `failed` and `error` together as "not passed" for flip/flake detection. |
| `durationSeconds` | number | JUnit `testcase/@time`. |

Tests are identified across runs by `"<classname>::<name>"` (see `_test_key` in `scripts/trends.py`). If a test is renamed or moved between classes, history treats it as a new test — this is a known, accepted limitation rather than an attempt at fuzzy matching. The same key can also collide *within* one run when `--junit` merges multiple files (two different tests across files sharing a classname+name — `record_run.py` warns when this happens); `trends.py` collapses same-run duplicates to a single worst status before any trend math runs, so they read as one test, not a false flip.

## Multiple JUnit files per run

`record_run.py --junit` accepts multiple paths/globs (e.g. a monorepo emitting one XML per package). All matched files are merged into a single run record: totals are summed, `testCases` are concatenated, and `durationSeconds` is the sum across files. This keeps one run record per CI invocation instead of one per package, which is what the trend math in `references/trend-metrics.md` assumes.
