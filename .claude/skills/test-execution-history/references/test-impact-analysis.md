# Test impact analysis — mapping rules and safety gates

`scripts/impact_analysis.py` decides whether a test run can be scoped to a git diff instead of
running the whole `--suite`, and if so, which test files to run. It never runs tests itself —
it only emits a decision (`scope: "full" | "impacted" | "none"`) plus, when scoped, the file list
and a recommended run command.

## Decision order

Each check runs in this order; the first one that fires wins and the rest are skipped:

| # | Check | Escalates to `full` unless… |
| - | ----- | --------------------------- |
| 1 | Current branch matches a protected-branch pattern | `--allow-scoped-on-protected-branch` |
| 2 | A changed file matches a core glob or core directory (lockfile, CI config, root config, env file, migration) | never — there is no override; narrow `--core-glob`/`coreGlobs` or `--core-dir-marker`/`coreDirMarkers` in the map file instead if one is too broad for a project |
| 3 | A changed source file maps to zero known test files ("unmapped") | `--allow-unmapped` |

If none of these fire, `scope` is `"impacted"` and `impactedTestFiles` lists every test file found.
If there were changes but every one of them is itself a test file already covered by check 3's
mapping, or `--allow-unmapped` let through changes with no mapped test at all, `scope` is `"none"`
— there is nothing new to run for this suite.

Default protected-branch patterns: `^(main|master|develop|development)$`, `^release/.*$`,
`^hotfix/.*$`. Override the whole list with `--protected-branch <regex...>` — it replaces, not
extends, the defaults.

A **detached HEAD** (`git rev-parse --abbrev-ref HEAD` prints the literal string `HEAD`, not a
branch name — common in CI checking out one specific commit) is checked before the pattern list
and treated as protected regardless of what the patterns say: there is no branch name to match
against at all, and the checked-out commit can just as easily be a protected branch's own tip as a
scratch build. Same `--allow-scoped-on-protected-branch` override applies.

The `--map-file` itself is always a core file too — editing the mapping rules is exactly the
moment to re-verify with a full run, not a change the rules should be trusted to score.

Default core globs (always additive to whatever a project defines): lockfiles
(`package-lock.json`, `pnpm-lock.yaml`, `yarn.lock`, `poetry.lock`, `Pipfile.lock`, `go.sum`,
`Gemfile.lock`, `composer.lock`), CI config (`.github/workflows/**`, `azure-pipelines.yml`,
`.gitlab-ci.yml`), root config (`package.json`, `pyproject.toml`, `tsconfig*.json`, `*.config.{js,ts,cjs,mjs}`,
`Dockerfile*`, `docker-compose*.y*ml`), and env files (`.env*`). These are a first pass, not a
guarantee — a project with its own shared/core directories should declare `coreGlobs` explicitly in
the map file rather than relying on this list.

**Core directories are matched separately, by path-segment membership, not a glob** — the default
list is just `migrations`. A glob's `*` has no path-separator awareness, so a naive
`**/migrations/**` entry in `coreGlobs` only matches when at least one directory precedes it
(`app/migrations/x.sql` matches, but a root-level `migrations/x.sql` — common for a single-app
Django/Alembic/Prisma layout — does not), which silently defeats the one check documented as having
no override for exactly the file it exists to catch. `--core-dir-marker`/`coreDirMarkers` check
instead whether the name is one of a changed file's actual path segments (`Path(f).parts`),
matching at any depth including the root, the same technique `test-data-strategy`'s
`scan_test_data.py` already uses for `fixtures`/`seeds`/etc. Add a project's own equivalents (Rails'
`db/migrate`, matched via the single segment `migrate`) with `--core-dir-marker <name...>` or the
map file's `coreDirMarkers`; a fixed-position directory that can only ever appear at the repo root
(`.github/workflows`) doesn't need this and stays a plain entry in `coreGlobs` instead.

## Mapping a changed file to a test file

Tried in order, first match(es) on disk win (a file can match more than one and all matches are
kept):

1. **The changed file is itself a test file** (matches the naming convention for its stack, e.g.
   `*.spec.ts`, `test_*.py`) — it maps to itself.
2. **Custom rules** from `--map-file`'s `rules` for this suite (see schema below) — a regex
   capture-group substitution, checked against the filesystem before being accepted.
3. **Co-location convention** — `foo.ts` → `foo.spec.ts` / `foo.test.ts` in the same directory
   (and the equivalent per-stack templates: `test_foo.py`/`foo_test.py`, `foo_test.go`,
   `foo_spec.rb`, `fooTest.java`, `fooTests.cs`, `fooTest.php`).
4. **Mirror convention** — a file under a `src/`, `lib/`, or `app/` directory is also looked for
   at the same relative path under a sibling `test/`, `tests/`, or `__tests__/` directory, with
   the co-location templates re-applied there too.

A candidate only counts if the file actually exists — the script never invents a path. A changed
file that matches none of the above is "unmapped" (decision check 3).

## Map-file schema (`.qa/test-impact-map.json`, override with `--map-file`)

```json
{
  "suites": {
    "unit": {
      "rules": [
        { "sourcePattern": "^src/(.+)\\.ts$", "testPattern": "src/\\1.spec.ts" }
      ],
      "coreGlobs": ["src/shared/**", "src/config/**"],
      "coreDirMarkers": ["migrate"],
      "runCommandTemplate": "npx jest {testFiles}"
    },
    "backend-api": {
      "rules": [
        { "sourcePattern": "^app/(.+)\\.py$", "testPattern": "tests/\\1_test.py" }
      ],
      "runCommandTemplate": "pytest {testFiles}"
    }
  }
}
```

Every field is optional and per-suite — a suite absent from the file falls back to the built-in
co-location/mirror conventions only. `runCommandTemplate`'s `{testFiles}` is replaced with the
space-joined impacted file list, each path already shell-quoted (`shlex.quote`) — a changed path
containing a space, `;`, backtick, or `$(...)` cannot turn the recommended command into something
other than a file list. Commit this file — it is small, stable, and lets a project's actual layout
override the generic heuristics once, instead of every invocation re-guessing it.

## Stronger impact signal via importer Grep

Filesystem-convention mapping only catches changes to a file and its own test — it cannot see
"file A changed, and files B and C import A and have no test file of their own that colocates
with A". For that transitive case, have the calling agent Grep the way the project's own imports
reference each changed file (module path, package name or file basename; word-boundary, test
directories included), then pass the changed files plus every importing file in with
`--changed-files <path...>` — this replaces `git diff` with that list as the changed-file set, and
the mapping in step 3 above runs over it so each importer pulls in its own tests. Core-glob and
protected-branch checks (1–2) still run against that list.

## Integration with recorded history

A scoped run is still worth recording — trend and flaky data over years of `scope: "impacted"`
runs is far better than no history at all for a suite too large to run in full on every change.
Record it with the scope metadata so it reads correctly later:

```bash
python3 ".claude/skills/test-execution-history/scripts/record_run.py" \
  --suite unit --junit reports/junit.xml \
  --scope impacted --impacted-files src/foo.spec.ts src/bar.spec.ts --base-ref origin/main
```

See [references/history-schema.md](history-schema.md) for the `scope`/`impactedFiles`/`baseRef`
fields this writes, and [references/trend-metrics.md](trend-metrics.md#flaky-test-detection) for
how mixed `full`/`impacted` history affects trend and flaky-test math — read that before trusting
a trend computed over a window that mixes both.

## Limitations

- **No import resolution** — this is a stdlib-only script; see [Stronger impact signal](#stronger-impact-signal-via-importer-grep) above for the transitive case.
- **Renamed/moved files** break co-location and mirror matching the same way a renamed test breaks
  `trends.py`'s `classname::name` identity (see [history-schema.md](history-schema.md)) — a rename
  reads as an unmapped source file plus an unrelated new test file, which correctly escalates to
  `scope: "full"` rather than silently missing coverage.
- **`git diff` semantics**: with `--head` omitted, the diff is against the working tree (including
  staged and unstaged edits) plus untracked new files — the common "what changed since I branched"
  local-dev case. With `--head` given, it's a pure `base...head` merge-base diff and untracked
  local files are not considered (there usually are none worth considering when diffing two refs).
- **This script never runs anything** — it is read-only over the filesystem and `git`. Executing
  `recommendedCommand` and recording the result are separate, deliberate steps.
