---
name: report-bug
version: 1.14.0
last-updated: 2026-10-28
description: Turn a failing test, a manual QA finding, free-form text, or a loosely-written ticket into a structured, tool-agnostic bug report and publish it to Qase, Jira, Linear, or a markdown file — or run the Playwright, Detox or Appium suites itself and report what fails. Use when asked to "file a bug", "report a defect", "log this failure as a bug", "run the e2e tests and report failures", or "reportar un bug".
argument-hint: '--from-text "<description>" | --from-failure <path> | --from-run <path|id> | --from-ticket <KEY> | --run [<path>]  [--to-qase [CODE]] [--to-jira] [--to-linear [TEAM|URL]] [--to-markdown [PATH]]  [--retries <N>]'
allowed-tools: Read, Write, Bash, Glob, Grep, Edit
disable-model-invocation: true
---

# Report Bug Skill

Turns evidence of a failure — a failing test, a manual QA finding, free-form text, or a loosely-written ticket — into a structured, ready-to-file bug report and publishes it via an output adapter.

## Contents

- [Purpose](#purpose)
- [Prerequisites](#prerequisites)
- [Input Modes](#input-modes)
- [Output Adapters](#output-adapters)
- [Workflow](#workflow)
- [Canonical Bug Format](#canonical-bug-format)
- [Output Formatting](#output-formatting)
- [Quality Checks](#quality-checks)
- [Adding a New Output Adapter](#adding-a-new-output-adapter)
- [Error Handling](#error-handling)
- [Best Practices](#best-practices)
- [Integration with Other Skills](#integration-with-other-skills)
- [References](#references)

---

## Purpose

Automates turning evidence of a failure into a bug report that a developer can act on without a round trip back to QA:

1. **Loads the evidence** — a failing test run, a manual finding, free text, or an existing ticket — or runs the Playwright, Detox or Appium suites to get one
2. **Gathers supporting evidence** — retries a flaky-looking failure, replays it against the base tree to check for regression, surfaces likely duplicates
3. **Generates a canonical bug report** — tool-agnostic, with severity, priority, repro steps, expected/actual result, and every field a developer needs to act without asking a follow-up question
4. **Publishes via an output adapter** — each `--to-*` flag maps the canonical report onto the target tool's API

**Principle**: the value of this skill is report *quality*, not issue creation. A bad bug report costs 2-3 round trips between QA and dev — every field in the canonical format exists to prevent one of those round trips. This skill never classifies a failure as PRODUCT BUG vs TEST DEFECT vs ENVIRONMENT — that judgment call stays with the human filing the report; the skill only gathers the evidence that judgment call needs.

---

## Prerequisites

**Common**: Claude Code with MCP support, plus at least one input source:
- A local failure artifact for `--from-failure` (Playwright HTML/JSON report, Vitest/Jest JSON report, Detox mobile E2E JSON report, WebdriverIO/Appium JSON report, JUnit XML from any runner, manual QA finding file)
- A run directory or CI run ID for `--from-run`
- **Atlassian MCP** for `--from-ticket` — see [MCP tool resolution](#mcp-tool-resolution)
- Free-form text inline for `--from-text`
- For `--run`, the project's own Playwright, Detox or Appium suite — plus an emulator, simulator or device for a mobile suite, which the skill boots itself when the config names one

**Adapter-specific**: each adapter has its own MCPs/permissions — see the corresponding file under `adapters/`, loaded only when its `--to-*` flag is used.

### MCP tool resolution

This skill and its adapters name MCP tools by operation only (`getJiraIssue`, `save_issue`, `qase_defect_upsert`, …). The full tool name carries a server prefix that depends on how the server was connected — project-scoped (`claude mcp add`), a claude.ai connector (`mcp__claude_ai_<Name>__…`), or a plugin. Never assume one.

Resolve each server's prefix once per run, before its first call: search the live tool list for its probe operation (in Claude Code, `ToolSearch` with that name loads it) and take the prefix of the tool whose name ends in `__<probe>`. Call every other operation of that server with the same prefix. When more than one server matches, prefer the project-scoped one. When none matches, stop with that server's missing-MCP error — do not guess a name.

| Server | Probe | Project-scoped prefix | Missing-MCP error |
|---|---|---|---|
| Atlassian | `getJiraIssue` | `mcp__atlassian__` | "No Atlassian MCP" in [Error Handling](#error-handling) |
| Linear | `save_issue` | `mcp__linear__` | [linear.md → Errors](./adapters/linear.md#errors) |
| Qase | `qase_defect_upsert` | `mcp__qase__` | [qase.md → Errors](./adapters/qase.md#errors) |

**Optional**: `framework-config.json` at the project root — used to resolve `suspected_area` from the discovered service/component map. When absent, `suspected_area` is inferred from file paths in the evidence and marked best-effort.

---

## Input Modes

### `--from-text "<description>"`
Free-form description of a bug. Infer whatever fields the text supports; ask for the rest (see [Phase 3](#phase-3-resolve-missing-required-fields)).
```bash
/report-bug --from-text "Clicking 'Remove' on a wishlist item removes the wrong item when the list has more than 10 items" --to-jira
```

### `--from-failure <PATH>`
Path to a single failing QA-automation run's output or a manual QA finding file (markdown/text). Extracts title from the test/finding name, steps from the test body or finding narrative, and expected/actual from the assertion diff.

**Format matters for evidence richness.** Prefer a JSON report. Playwright's JSON reporter carries the failure text plus `attachments[]` (screenshot, video, `trace.zip`); JUnit XML carries only text, because Playwright's JUnit output never records attachments. Vitest/Jest JSON reports carry failure text only (Node, nothing to screenshot). Detox runs on Jest, so its `--json` report has the same `testResults[]` shape — only the framework label and evidence profile differ. WebdriverIO's JSON report (Appium included) carries failure text only; its screenshots and device logs come from the files a failure hook writes beside it.

**Supported inputs**: QA automation (E2E/Playwright, mobile E2E/Detox, and mobile E2E/Appium through WebdriverIO's JSON report), unit-test JSON reports (Vitest/Jest, via their built-in JSON reporters), and JUnit XML from any runner (Appium suites in Java or Python included) — plus manual QA findings. A test-report shape this skill doesn't recognize (see the sniff order in [Extracting failures](#extracting-failures-from-a-json-test-report)) is not yet a supported input — file it as free text via `--from-text`, or extend [Extracting failures from a JSON test report](#extracting-failures-from-a-json-test-report) when that shape needs supporting.
```bash
/report-bug --from-failure ./test-results/checkout.spec.ts-report.json --to-qase MYPROJ
```

### `--from-run <PATH|RUN-ID>`
Batch mode over a full QA-automation run (a Playwright HTML report directory, or a CI run ID resolvable via the project's CI integration). Produces one bug candidate per distinct failure, deduplicates candidates that share the same failing assertion + file, then asks the user which candidates to file (default: all, after the duplicate-lookup step in [Phase 2](#phase-2-evidence-gathering) removes ones already filed).
```bash
/report-bug --from-run ./playwright-report --to-qase MYPROJ
```

### `--run [<path>]`
Runs the project's Playwright, Detox and Appium suites (WebdriverIO, or a Java/Python suite that writes JUnit XML) — or only the spec file or folder at `<path>` — then reports what fails exactly as `--from-run` does. It boots the emulator or simulator a mobile suite needs, writes every report under `.claude-temp/report-bug/run/` so the project's own reports stay untouched, and stops with `✅ … nothing to report` when everything passes. Read [references/run-tests.md](references/run-tests.md) before running anything.
```bash
/report-bug --run --to-jira
/report-bug --run mobile/specs/checkout.e2e.ts --to-markdown
```

### `--from-ticket <KEY>`
Fetch a ticket via the Atlassian `getJiraIssue` tool (see [MCP tool resolution](#mcp-tool-resolution)) that already describes a bug in unstructured prose, and normalize it into the canonical format — useful when a bug was filed loosely and needs restructuring before it is actionable, or before re-filing it in a different tool.
```bash
/report-bug --from-ticket PROJ-456 --to-markdown ./bugs/PROJ-456.md
```

**Combining sources**: `--from-ticket` or `--from-run` may be combined with `--from-failure` when the failure artifact is the evidence for a ticket that only describes symptoms — the ticket supplies `linked_ticket` and narrative context, the failure artifact supplies repro steps and evidence.

---

## Output Adapters

Each `--to-*` flag selects an adapter that translates the canonical bug format into the target tool's payload. Generation and evidence gathering are shared — only the adapter changes.

**Adapter details live in separate files under `adapters/` and are loaded on-demand.** Phase 5 reads only the file for the selected `--to-*` flag.

| Flag | Adapter file | Description | Duplicate lookup |
|------|-------------|-------------|-------------------|
| `--to-qase [CODE]` | [`adapters/qase.md`](./adapters/qase.md) | Creates a defect in Qase via MCP. | Yes |
| `--to-jira` | [`adapters/jira.md`](./adapters/jira.md) | Creates a Bug issue in Jira via MCP. | Yes |
| `--to-linear [TEAM\|URL]` | [`adapters/linear.md`](./adapters/linear.md) | Creates a `Bug`-labeled issue in Linear via MCP (OAuth). | Yes |
| `--to-markdown [PATH]` | [`adapters/markdown.md`](./adapters/markdown.md) | Writes one markdown file per bug (default folder `bug-reports/`). No MCP needed. | No (no store to search) |

**Display only** (no `--to-*` flag): prints the formatted canonical report in the conversation for review before publishing. No adapter file is loaded, no duplicate lookup runs — until the user picks destination(s) in the Phase 4 ask.

**Several `--to-*` flags can be combined** (e.g. `--to-jira --to-linear`) — the same bug is then published to every named destination.

**Never assume the destination.** The only valid sources for where a bug gets published are `--to-*` flags the user typed in this invocation, or an explicit answer to the Phase 4 destination question. Not a tool used earlier in the conversation, not the adapter most recently added or tested, not the only MCP that happens to be connected, not a suggestion you made yourself that the user didn't explicitly confirm. A reply that answers only *which* bugs to file ("all", "1 and 3") does not answer *where* — ask again.

There is no `--to-github` adapter (GitHub Issues) — do not build one ad hoc; add it following [Adding a New Output Adapter](#adding-a-new-output-adapter).

---

## Workflow

### Phase 0: Parse Arguments

Parse all arguments before doing anything else.

**If a `--from-*` flag is present, use it as given — skip auto-detection below and go straight to Phase 1. `--run` first runs the suites per [references/run-tests.md](references/run-tests.md), then continues as `--from-run`.**

**If no `--from-*` flag is present, auto-detect the input source yourself before asking the user or falling back to the usage message.** Do not just print usage the moment a flag is missing — check the working directory first:

1. **Look for a recent test run.** Search the output folders the project's test configs name (`outputDir`/`outputFile` in `playwright.config.*`, `vitest.config.*`, Jest's config, the Jest config a Detox config (`.detoxrc`, `.detoxrc.*`, `detox.config.*`, `package.json`'s `"detox"` key) points to, or the reporters' `outputDir` and the Appium service's `logPath` in `wdio.conf.*`), plus the defaults `test-results/`, `playwright-report/`, `e2e/`, and Maven/Gradle's `target/surefire-reports/`, `build/test-results/`; a multi-package repo can have several. A report is recent only if it is newer than `git log -1 --format=%ct` and a few hours old at most. Sniff every `.json` and `.xml` candidate (see [Extracting failures](#extracting-failures-from-a-json-test-report)) and silently skip one with an unsupported shape. Prefer JSON over HTML/JUnit. Exactly one recent, shape-valid report with failures is your `--from-failure` (one failure) or `--from-run` (several) candidate.
2. **Use the IDE/conversation context to disambiguate, not to invent.** If a spec/test file is open in the IDE or was just discussed, and a same-run report references that file, use it to narrow an ambiguous multi-report result to the matching test — but a file being open is never by itself evidence of a failure; it only breaks a tie between multiple candidate reports.
3. **Look for a ticket key.** If the user's message or the recent conversation names a ticket key (e.g. `PROJ-123`, `QAF-45`), treat it as a `--from-ticket` candidate.
4. **When detection is unambiguous, announce it and proceed — do not stop to ask for confirmation.** One recent report (or one report set, for `--from-run`), optionally narrowed by step 2/3, is enough to act on directly; asking "use this? [y/n]" for a single unambiguous candidate is exactly the kind of question this auto-detection exists to avoid. Announce what was picked, formatted as a heading + a compact table (this is the first block of the conversation reply — see [Output Formatting](#output-formatting) for the full visual spec this and every later block follows), and move straight into Phase 1:
   ```
   ## 🔎 Input Source Detection

   **Auto-detected:** recent Playwright run, 1 failure

   | | |
   |---|---|
   | Source | `test-results/cart.spec.ts-report.json` |
   | Framework | Playwright (E2E) |
   | Failure | "adds item to cart" (failed) |
   | Mode | `--from-failure` |
   ```
   The `Framework` row is `Playwright (E2E)`, `Detox (mobile E2E)`, `Appium (mobile E2E)`, `WebdriverIO (E2E)`, or `Vitest (unit)`/`Jest (unit)` per the shape sniff above — always show it, since the report shape and the project's Detox config/`wdio.conf.*`/`playwright.config.ts`/`vitest.config.ts` presence drive different Phase 2 replay commands and Phase 1 evidence handling. For a `--from-run` batch, add `Run time` and `Failures` rows (count + the spec files involved) instead of a single `Failure` row — see the worked example in [Output Formatting](#output-formatting).

   If new information later contradicts the pick (e.g. the report turns out unreadable), fall back to step 5 at that point rather than mid-guessing.
5. **Only ask when detection is genuinely ambiguous or empty** — multiple candidates with no signal (step 2/3) to tell them apart, or nothing runnable found at all. This is the sole case where you involve the user before proceeding:
   ```
   Usage: /report-bug
            --from-text "<text>" | --from-failure <path> | --from-run <path|id> | --from-ticket <KEY> | --run [<path>]
            [--to-qase [CODE]] [--to-jira] [--to-linear [TEAM|URL]] [--to-markdown [PATH]]  (combinable)
            [--retries <N>]
   ```

**When the user says they ran tests but no report for that run exists, read what's on disk — never run the suite yourself without `--run`.** The skill works from the report the user's own run wrote. If it's missing, explain which cause applies, so they can re-run it the right way — and offer `/report-bug --run`, which runs the suites and reads their reports itself:
- **Wrong directory.** A same-named script at the repo root may target different packages than the suite that failed. Run the suite from the folder that owns it.
- **Run from the IDE** (VS Code test explorer / Playwright or Vitest extension). These use their own reporters and skip the config's JSON reporter, so nothing is written to disk.
- **Wiped by Playwright.** Playwright empties its `outputDir` (default `test-results/`) at the start of every run, so another tool's report written into that same folder (e.g. Vitest's `outputFile: "test-results/unit-results.json"`) is deleted by the next Playwright run.

`--retries <N>` overrides the default retry count of 1 in [Phase 2](#phase-2-evidence-gathering); only meaningful with `--from-failure`, `--from-run` or `--run`.

### Phase 1: Load Evidence

Load the source per the input mode above. Announce what was loaded:

```
✅ **Loaded:** checkout.spec.ts › "applies discount code at checkout"
- Source: Playwright failure report
- Failure: `expect(received).toBe(expected)` — discount not applied
- Output adapter: Qase → project MYPROJ
```

For `--from-run`, a one-liner is enough since the count and spec files already appeared in the Phase 0 table: `✅ Loaded 4 failing tests — proceeding to evidence gathering for each.`

#### Extracting failures from a JSON test report

Sniff a report before walking it — `capabilities` with `suites` means WebdriverIO (Appium when the capabilities target a device); `suites` alone means Playwright; `testResults` means Vitest, Jest, or Detox (Detox when a Detox config (`.detoxrc`, `.detoxrc.*`, `detox.config.*`, or a `"detox"` key in `package.json`) sits in the folder of the report's test files or a folder above it, up to the project root); a `<testsuites>`/`<testsuite>` XML root means JUnit XML. Anything else is not a supported shape. Read [references/report-extraction.md](references/report-extraction.md) for the walk, the attachment mapping and each framework's `test_reference`/`environment` rules before extracting.

#### Evidence files

Every path taken from a report (attachment paths, Detox artifact folders and Appium failure-hook files named after test titles) is untrusted input. **Never splice one into a shell command** — no `cp`, `zip`, `curl`, `stat` or `open` with an evidence path typed into it. Instead, write a JSON manifest with the file-writing tool under `.claude-temp/report-bug/` and run, from the project root (the script confines every path to the git top level of its working directory, never to anything the manifest says):

```bash
node ".claude/skills/report-bug/scripts/evidence.mjs" <command> .claude-temp/report-bug/<manifest>.json
```

| Command | Manifest | Use |
|---|---|---|
| `check` | `{files[]}` | Validates paths without copying anything (`sanitize` runs the same check): returns each file's resolved path, `size` and `contentType`; `rejected[]` lists paths outside the project root, symlinks that escape it, hidden files and folders (`.env*`, `.git/`), credential-like text/JSON names (`credentials.json`, `google-services.json`), unknown file types and non-files. Never upload a rejected path — name it in the Phase 2 summary. |
| `snapshot` | `{dest, files[], dirs[]}` | Copies evidence under `dest` (inside `.claude-temp`) before the confirmation re-run (Phase 2). |
| `zip` | `{dir, out}` | Zips a folder (Playwright HTML report, Detox per-test artifacts) into a `.zip` inside `.claude-temp`; hidden entries are left out. |
| `put` | `{file, url, headers}` | PUTs one file to a signed upload URL (Linear's upload buckets only) with its headers verbatim. |
| `jira-attach` | `{site, issue, files[]}` | Uploads to Jira Cloud's attachments endpoint; credentials never reach argv. Any non-zero exit = no native upload (see [jira.md](./adapters/jira.md#evidence-attachment-screenshotvideotrace)). |
| `redact` | `{text}` | Returns `text` with secrets masked (token shapes — GitHub, Slack, AWS, Anthropic, Stripe, Google keys —, URL credentials, auth/cookie headers, `password=`-style values including prefixed keys such as `DB_PASSWORD`, `access_token`, `accessToken`, `SECRET_KEY` and `cookie` (`session`, `sid` and `auth` keys only when the value looks like a secret), every `value` in a Playwright login state's `cookies[]`/`localStorage[]`, a JSON `Authorization` value whatever its prefix, and values of secret-named variables (`*_PASS`, `*_KEY`, `*_SK`, `*TOKEN*`, …) in the environment or the project's `.env*` files (subfolders included) when the value looks like a secret — plain words, integers, URLs without credentials, existing file paths and shell variables such as `PWD` stay readable) and `redactions[]` — mandatory before publishing, see [Phase 4](#phase-4-generate-the-canonical-bug-report). |
| `sanitize` | `{files[]}` | Before every upload: redacts a copy of each text file (logs, JSON, markdown, HTML — including the zip an HTML report embeds as base64) and rebuilds each `.zip` (Playwright `trace.zip`, zipped reports — they carry headers and cookies) with its entries redacted. Upload each entry's `upload`, never the original `path`; media files come back unchanged, and a file that can't be fully sanitized (archives nested too deep) is rejected. |

`put` and `jira-attach` report a failed upload per file (`ok: false`, plus `error` on a transport failure) and keep going: retry only those files, never the whole batch.

**No `zip`/`unzip` on the machine** (stock Windows, slim CI images): `zip` exits 1 with `zip is not installed…`, and `sanitize` puts each file it would have to unpack (`trace.zip`, a zipped report, an HTML report that embeds its data as a zip) in `rejected[]` with `missingTool`. Upload everything that did come back (screenshots, videos, redacted logs), skip the full-report zip, and in the evidence comment list each skipped archive's original path with: `Not attached: <zip|unzip> is not installed, so this file could not be redacted. Check it for secrets before attaching it by hand.`

### Phase 2: Evidence Gathering

Only applies to `--from-failure`, `--from-run` and `--run` (a failure that can actually be re-executed). Skip this phase entirely for `--from-text` and `--from-ticket` — there is no runnable test to retry or replay.

1. **Confirm the failure.**
   - First `snapshot` the loaded report and every evidence file/folder to `.claude-temp/report-bug/evidence/` (see [Evidence files](#evidence-files)) and use the copies from then on — a re-run rewrites the report and Playwright empties its `outputDir`.
   - Re-run just that one test once (`--retries <N>` for more): `npx playwright test '<file>' -g '<test title>' --project '<project>'` (`--project` with the failing result's `projectName`, when the report has one), `npx vitest run '<file>' -t '<test name>'`, `npx jest '<file>' -t '<test name>'`, `npx detox test --configuration <configuration> '<file>' -t '<test name>'` (the file is positional: Detox hands flags it doesn't know to Jest, where `-f` means `--onlyFailures` and selects nothing), `npx wdio run <wdio.conf> --spec '<file>' --jasmineOpts.grep '<test name>'` (`--mochaOpts.grep` for Mocha), and for a JUnit-only Java/Python suite `mvn test -Dtest='<Class>#<method>'`, `gradle test --rerun --tests '<Class>.<method>'` or `pytest '<file>::<test>'`. Prefer the project's wrapper script when it forwards args and handles device lifecycle (e.g. `npm run test:e2e -- '<file>' -t '<test name>'`).
   - **`-g`/`-t`/`--jasmineOpts.grep`/`--mochaOpts.grep` take a regular expression, and Detox also passes `-t` through a shell that escapes only spaces — so replace every character other than letters, digits and spaces with `.` and single-quote the result** (`applies 10% discount (VIP)` → `'applies 10. discount .VIP.'`). Never pass the raw title or backslash escapes; the title is report text.
   - Every other value taken from the report — `<file>`, `<project>`, `<Class>`, `<method>`, `<test>` — is single-quoted too, and used only when it holds nothing but letters, digits, spaces and `_ . / : - [ ] # ,`. Otherwise drop that part of the selector (`pytest '<file>'` for `'<file>::<test>'`, `mvn test -Dtest='<Class>'` for `'<Class>#<method>'`) and let the count check below decide; when even `<file>` fails, skip the re-run: `Could not re-run: the report names this test with characters that are unsafe in a command.`
   - An Appium run needs a booted simulator/emulator or a connected device, and a Detox debug build a running Metro bundler: start them first rather than letting the run hang, and keep them up until the whole batch is confirmed. WebdriverIO's Appium service starts the Appium server itself, never the device. Detox boots the emulator its `.detoxrc` names by itself.
   - A Detox run on Android that fails with `response not received` could not query an emulator that was already running — one the user started, possibly mid-session: ask ([How to ask](#phase-3-resolve-missing-required-fields)) before touching it, naming its serial and AVD (`adb -s <serial> shell getprop ro.boot.qemu.avd_name` — not `adb emu avd name`, which goes through the same emulator console that just failed and prints nothing; with several, the one matching `.detoxrc`'s `avdName`), with **Restart it** / **Stop**. Restart it → `adb -s <serial> emu kill`, then run again; Detox leaves the emulator it booted running and hits the same error on the next run, so a Restart it answer covers every later Detox run of this batch (confirmation re-runs and the regression replay) — kill the emulator before each one without asking again; Stop, or headless → stop with `❌ Close the <AVD> emulator and run again — Detox can't use one that was already running.`
   - Add observation-only flags so the run doesn't overwrite the project's reports (`--reporter=line`, `--reporter=json`, `--outputFile=...`, `--output=<scratch dir>`), then record the command **without** them as `test_reference.rerun_command` — what selects the file/test (and Detox's `--configuration`) plus whatever the wrapper bakes in. For WebdriverIO, `--reporters json --logLevel error` replaces the config's reporters for the re-run and prints the JSON report after a `"json" Reporter:` line, leaving the project's report files alone.
   - **Check that exactly one test ran before reading the result.** Take the count from the run's JSON report (Playwright: `stats.expected + stats.unexpected + stats.flaky`; Vitest/Jest/Detox: `numTotalTests - numPendingTests - numTodoTests`; WebdriverIO/Appium: `state.passed + state.failed` summed over the run's files; JUnit XML: `tests - skipped`), never from the exit code alone — a title that selects nothing exits non-zero on Playwright and 0 on Vitest and WebdriverIO. Zero or several tests ran → leave `reproducibility` unset and say so in the Phase 2 summary: `Could not re-run: the test title selected <n> tests.`
   - If it passes on the confirmation run, record `reproducibility: "intermittent"` and surface it:
   ```
   ⚠️  Passed on the confirmation run — this looks flaky.
      Filing it as a bug is still your call, but consider fixing the flake instead.
   ```
   Do not auto-file a flaky result and do not auto-skip it — the decision to file stays with the user; the skill only surfaces the signal. If it fails the confirmation run too (or all `--retries N` attempts), record `reproducibility: "always"`.

2. **Replay for regression.** Re-run the same test against the base branch to determine whether the failure pre-exists the current branch. This step is **mandatory via a disposable worktree** — never via `git stash`/`checkout` on the primary tree, and never skipped in place of that:
   - `git worktree add <tmp-dir> <base-ref>` once per batch, run each candidate's single test there, then `git worktree remove <tmp-dir>` after the last one (add `--force` if the run left artifacts behind). The primary tree and the developer's branch are never touched — a crash or interruption mid-run leaves at most an orphaned directory to clean up manually, never uncommitted work at risk.
   - If `git worktree add` itself fails (disk space, permissions, an unclean worktree registry), do not fall back to mutating the primary tree. Stop this step, record `regression.is_regression: null` with a note that verification could not run, and continue to Phase 3 — a bug report with an unverified regression field is safe; a working tree damaged by a failed stash/restore is not.
   - If the application source itself is not tracked in git (never committed, or ignored), `<base-ref>` has nothing to replay against: skip the worktree and record `regression.is_regression: null`.
   - **A fresh worktree has no installed dependencies or ignored local config.** Bring the primary tree's dependency folders over instead of reinstalling: a symlink is enough for most runners (`node_modules` for Playwright, Vitest, Jest or WebdriverIO), but React Native's Metro bundler doesn't follow a symlinked `node_modules`, so for a Detox or React Native app copy it with a copy-on-write clone (`cp -c -R` on macOS, `cp -R --reflink=auto` on Linux) — near-instant and no extra disk on APFS/Btrfs/XFS. Also copy the ignored files the native build reads, such as `android/local.properties`.
   - **Build the app under test inside the worktree** when the suite runs a compiled binary (Detox's `binaryPath`, an Appium `app` capability pointing at a file the project builds): run the build there (`npx detox build --configuration <configuration>`, or the project's build command) once per batch, before the first replay — every candidate replays against the same `<base-ref>`. Running the primary tree's binary from the worktree replays the current code, not `<base-ref>`'s. When the build fails, record `regression.is_regression: null` for every candidate of the batch and name the build error in the Phase 2 summary.
   - **If the worktree is created but the test harness itself is missing there** (`tests/`, `playwright.config.ts`, `package.json` etc. are untracked/new and were never committed, so a checkout of `<base-ref>` doesn't have them) — this is common early in a project before the E2E suite's own scaffolding has been committed. Do not treat this as an "is_regression: null" case by default: copy the untracked harness files (dependencies as in the bullet above, never a full reinstall) from the primary tree into the worktree before running, so the *same test code* executes against the *base-ref's* application source. This is valid because the thing under test for regression purposes is the application source (e.g. `js/app.js`), not the test harness — as long as the harness itself is unchanged between the two runs, swapping only the SUT is exactly what "replay against base" means. Remove the copied files along with the worktree when done. Only fall back to `regression.is_regression: null` if the harness can't even run this way (e.g. its own dependencies changed incompatibly between base and current).

   `/implement-ticket`'s testing phase deliberately does not attempt this kind of verification itself — it only classifies a failure as suspected pre-existing without mutating the tree, and reports that classification as unverified. This step is where the actual verification happens, whenever `report-bug` runs against that failure. Record `regression.is_regression` and, when resolvable, `regression.last_known_good` (the last commit/tag where the test passed, if cheaply discoverable — otherwise leave `null`, do not spend an unbounded bisect on it).

3. **Surface duplicates.** If `--to-qase`, `--to-jira`, or `--to-linear` is set, run that adapter's duplicate-lookup step (see the adapter file) before publishing. Search with 2-4 keywords from the draft title, each reduced to letters and digits only (`[A-Za-z0-9]`) — never splice the raw title into a query string (QQL, JQL). Show up to 5 candidate matches with links; ask the user to proceed, link the new evidence to an existing one instead, or abort. Skip for `--to-markdown` and display-only (no store to search).

   **Duplicates are only compared within the same platform/test type** — the `[UI]`/`[Mobile]`/`[BE]` tag from [Canonical Bug Format](#canonical-bug-format) (i.e. Playwright vs. Playwright, Detox vs. Detox, Appium vs. Appium, Vitest/Jest vs. Vitest/Jest). Detox and Appium both tag `[Mobile]` but are different frameworks: within `[Mobile]`, also compare the ticket's `Failing Test` → `Framework:` line. A `[Mobile]` bug is checked only against existing `[Mobile]` tickets, a `[BE]` unit-test bug only against `[BE]` tickets, a `[UI]` Playwright bug only against `[UI]` tickets. The same defect found by another framework or on another platform is **not** a duplicate: the user may want a ticket per framework (each has to be retested there) or the same ticket in several tools. So:
   - Drop cross-platform/cross-framework matches **silently** — don't list them as candidates, don't explain why they were excluded, don't mention them in the cards, the evidence summary, or the final message.
   - Tell a ticket's platform from its title tag; for an older ticket without one, from its `Failing Test` → `Framework:` line. Only if neither exists, show it as a candidate and let the human decide.
   - When no same-platform candidate remains, just proceed — no "no duplicates found" narration beyond the adapter's `⏳` line.
   - **Only the tool's live state counts.** A ticket created earlier in this session that the lookup no longer finds was most likely deleted on purpose. Don't mention it, ask about it, or investigate why it's gone. Check only the bug being filed now: if the lookup finds no same-platform match, proceed.

4. **Summarize before moving on.** Once all candidates (one for `--from-failure`, N for `--from-run`) have been through steps 1-3, print one consolidated summary block — not a repeat per candidate — before Phase 3/4:
   ```
   ## 🧪 Evidence Gathering

   - ✅ **Confirmed** — 4 failures re-run once, all reproduced
   - ✅ **Regression check** — replayed against base `HEAD` (`88b125a`) in a disposable git worktree
   - ⚠️ **Snag found & fixed** — <only include this line if something like a stale dev-server port or a flaky confirmation happened; state what it was and how it was handled, e.g. "a stale http.server on :8765 was making the worktree serve the main tree's files instead of its own — killed it and re-ran">
   - 📭 **Publishing** — no `--to-*` flag was given, so this is a display-only preview; nothing has been filed anywhere
   ```
   Swap the last bullet for `📤 **Publishing** — to <adapter> project <X>, after duplicate lookup` (one entry per destination when several `--to-*` flags are set) when a `--to-*` flag is set. Omit the ⚠️ line entirely when nothing noteworthy occurred — don't manufacture a line to fill the template.

### Phase 3: Resolve Missing Required Fields

Required fields: `title`, `severity`, `priority`, `steps_to_reproduce`, `expected_result`, `actual_result`. Everything else in the [canonical format](#canonical-bug-format) is best-effort.

After Phases 1-2, check which required fields are still unresolved. If none, skip to Phase 4.

**How to ask** — the order for every question this skill asks (Phase 3, Phase 4, duplicate lookup):
1. `QAF_ASK_USER_MCP_TOOL`, when set — check with `echo "QAF_ASK_USER_MCP_TOOL=${QAF_ASK_USER_MCP_TOOL:-UNSET}"`; never infer it. It relays the question to a person, so it applies in headless runs too.
2. Otherwise, headless (a non-interactive run such as `claude -p` or `codex exec`, or `CI` set in the environment) → never prompt; stop and report what is missing.
3. Otherwise the provider's structured ask tool, when the session offers one.
4. Otherwise a plain question in the conversation.

Ask one question per missing field, each with a recommended value derived from the loaded evidence. Headless, stop and list which required fields are missing and why the evidence didn't supply them.

Never fabricate a value for a required field to avoid asking.

### Phase 4: Generate the Canonical Bug Report

Assemble the full [canonical format](#canonical-bug-format) from the loaded evidence, Phase 2 findings, and Phase 3 answers. Resolve `suspected_area` from `framework-config.json`'s service map by longest-prefix match on the failing file path(s); if the config is absent or no path matches, infer from the evidence and mark it best-effort in the summary (do not silently drop the field).

**Report content is always written in English** — title, preconditions, steps, expected/actual result, tags — regardless of what language the conversation is in. This is what actually gets filed by the adapter in Phase 5, so there is nothing to re-translate at publish time; do not localize it for the chat display either.

**The skill's own questions and prompts are always in English too** — the "❓ Which of these should I file?" and "📤 Where should I publish them?" asks, the duplicate-lookup question, Phase 3's missing-field questions, and every other template heading/label this file defines (Phase 0 detection table, Phase 2 evidence summary, cards, `⏳` progress lines). Print them verbatim as templated; never translate them into the conversation's language. Only free-form conversational replies outside the skill's templates follow the user's language.

**Redact before publishing — mandatory.** Pass every text that will be published (error logs, `actual_result`, stack traces, device logs) through the evidence script's `redact` command and use the `text` it returns, in the preview and in every adapter. Upload evidence files only through `sanitize`, and when a file is listed for manual attaching instead (no credentials, a failed upload), list its `upload` path too — never the original, and never a file `sanitize` rejected. When `redactions` (from `redact` or `sanitize`) is non-empty, add a ⚠️ callout to that bug's card naming the kinds (e.g. `⚠️ Redacted an authorization header and a URL credential from the error log`).

**Never print the full canonical JSON into the conversation.** The full object is an internal artifact — it's what Phase 5 adapters send and what `--to-markdown` writes to disk — the chat only ever sees the Markdown card per the spec in [Output Formatting](#output-formatting).

**The preview always comes before any publish call, regardless of whether a `--to-*` flag was given.** A `--to-*` flag names *where* a bug would go if filed, not a standing order to file all of them unattended — the human still picks which candidates are worth a ticket. Print one card per report — one per candidate even for a `--from-run` batch of several, never the raw JSON, each separated by a `---` rule.

**End every batch with an interactive selection prompt, not a question buried in text.** Two questions — which bugs to file, and where to publish them — asked through a real selection UI, so the user sees at a glance that the skill is waiting for them to pick something. A trailing sentence (or even a bold heading) at the end of a long message is easy to miss, and a user who misses it assumes the run is finished.

**Which UI to use** — the [How to ask](#phase-3-resolve-missing-required-fields) order: `QAF_ASK_USER_MCP_TOOL`; otherwise headless stops after the preview and says nothing was filed; otherwise the provider's ask tool, then the text fallback below.

**Ask them one at a time, in consecutive ask calls — never both in one call.** First Question 1; wait for the answer; if it is `Select Bugs to Report`, ask the bug checklist next; then Question 2. If the answer to Question 1 is `None — just reviewing`, don't ask anything else — stop there (nothing is filed). Text in English verbatim:

| | Question 1 (`multiSelect: false`) | Question 2 (`multiSelect: true`) |
|---|---|---|
| `header` | `Bugs to file` | `Publish to` |
| `question` | `Which of these bugs should I file?` | `Where should I publish them? (you can pick more than one)` |
| `options` | Exactly three, in this order, whatever the batch size: `Report All Bugs` (description `File all N bugs`), `None — just reviewing`, `Select Bugs to Report` (description `Pick specific bugs from a checklist`). | One per destination whose adapter exists — `Qase`, `Jira`, `Linear`, `Markdown file` — with the resolved project/team/path in the description (e.g. `Linear — team ENG`, `Markdown file — bug-reports/`) when known from `.mcp.json`, the adapter's default, or a single visible team/project; otherwise leave it for that adapter's flag-syntax rules once chosen. |

**Bug checklist** (only after `Select Bugs to Report`): list every bug, `multiSelect: true`, in groups of 3 per question — label `Bug N`, description = the card's title — plus a `None of these` option, header `Bugs N-M`, question `Which of bugs N–M should I file?`. Up to 4 questions per call (12 bugs); for more, repeat the call with the next groups until every bug has been shown. If nothing was selected across all groups, stop — nothing is filed.

**The destination question is mandatory whenever no `--to-*` flag was given** — never pick a destination yourself (see [Never assume the destination](#output-adapters)). When the invocation already had `--to-*` flag(s), skip Question 2 and print them just above Question 1 instead (`📤 Destination(s): Jira KAN, Linear ENG — from your flags`) so the user can still correct it via "Other". If an answer covers only which bugs and not where (e.g. typed free text), ask where before publishing anything.

**Destinations are multi-select, never single-choice.** A bug may have to go to several tools at once (e.g. Jira for the dev team and Linear for another team). Never use a radio-button / single-choice prompt for Question 2 (`multiSelect: true`, and the equivalent option on `QAF_ASK_USER_MCP_TOOL`).

**Text fallback** (no ask tool, a person in the conversation) — same one-at-a-time order: print the first block, wait for the reply; on **select**, print a checklist of every bug (`- [ ] Bug N — <title>`) and ask for the numbers; then print the second block (skip it if the answer was "none"). Each is its own `###` heading after a `---` rule, never folded into regular prose:
```
---

### ❓ Which of these should I file?

Reply **all**, **none**, or **select** to pick specific bugs.

### 📤 Where should I publish them?

You can pick **more than one** (e.g. "Jira and Linear"):
- [ ] Qase — project `<CODE>`
- [ ] Jira — project `<KEY>`
- [ ] Linear — team `<KEY>`
- [ ] Markdown file — `bug-reports/`
```
(The two blocks above are shown in separate messages — the second only after the first is answered.)

Do not proceed to Phase 5 until **both** questions are answered.

### Phase 5: Publish via Adapter

Once the user has answered which candidate(s) to file and where, and only for those, **load the matching adapter file** — repeat steps 1-5 once per chosen destination (each destination runs its own duplicate lookup; a bug can be a duplicate in one tool and new in another):

1. Read `adapters/<name>.md` (relative to this skill directory).
2. Run its duplicate-lookup step if not already done in Phase 2 — still a real pause: show the candidates, ask the user to proceed, link to an existing one instead, or abort, before creating anything.
3. Apply its field mapping table to transform the canonical report into the tool's payload.
4. Make the MCP/API calls in the order specified, for each selected candidate.
5. Use the progress announcements from the adapter file (`⏳ ...`) while each call is in flight — these are transient status lines, not the report itself.
6. Once every selected candidate has been published (or explicitly skipped as a duplicate), print **one consolidated block**: the same per-bug card already shown in the Phase 4 preview, now carrying the extra `Ticket` row with the created ID and link (see the adapter's success-report section for exactly what goes in that row). A reviewer should be able to read this block alone and know what got filed without opening the tool. **Nothing goes after it** except the adapter's short evidence lines — no side notes about excluded duplicates, how the regression check was done, wrapper-script quirks, or emulator/server cleanup; anything worth flagging belongs in the Phase 2 summary, before the user decides. If the user wants to tweak wording afterward, that happens by editing the ticket directly, not by re-running this skill.

With several destinations, the consolidated block still has one card per bug, with one `Ticket` line per destination (e.g. `✅ [KAN-12](...) · ✅ [ENG-7](...)`); a failure in one destination doesn't roll back or block the others — report it on that line and follow that adapter's error template.

If no `--to-*` flag, skip adapter loading entirely once the user confirms "none, just reviewing" — the Phase 4 preview already served as the display output, and Phase 5 never runs.

**If the publish call itself fails** (permission denied, invalid project/board, rate limit, network error, disk write failure) — never report success and never silently drop the report. Print the exact underlying error the tool/filesystem returned, then re-print the full canonical report from Phase 4 in full so none of the evidence-gathering work is lost, and suggest either retrying or falling back to `--to-markdown [PATH]` to save it locally instead. See each adapter's `## Errors` section for the specific message per failure mode.

---

## Canonical Bug Format

Phase 4 builds one tool-agnostic JSON object per bug; every adapter consumes it. Read [references/canonical-format.md](references/canonical-format.md) for the schema, the `[BUG] [UI|Mobile|BE] Area | …` title rule and the severity/priority scales.

## Output Formatting

Every block printed to the conversation is Markdown: Phase 0's detection table, Phase 2's summary and one card per bug. Read [references/output-formatting.md](references/output-formatting.md) for the card template, the emoji legend and the `Ticket` row values.

## Quality Checks

Before finalizing (end of Phase 4, before Phase 5 publishing):

**Per report:**
- [ ] Title starts with `[BUG] `, followed by a `[UI]`/`[Mobile]`/`[BE]` platform tag, and names the area and the broken behavior — not just "bug" or "error"
- [ ] Every step in `steps_to_reproduce` is one atomic, observable action, and the **last** step names what is being checked, not just a neutral action — "Verify the subtotal updates to unit price × quantity" tells the reader what correct behavior looks like; "Read the subtotal shown" doesn't, and forces them to already know the bug to know what to look for
- [ ] `expected_result` and `actual_result` are both concrete and distinguishable from each other, and `expected_result` states the underlying rule/behavior, not just the specific value it happens to produce this time — "the subtotal should always equal unit price × quantity" is a report a developer can act on anywhere in the code; "$36.00" alone forces them to reverse-engineer why before they can even judge whether the fix is right
- [ ] `severity` and `priority` are both set with independent rationale
- [ ] `reproducibility` reflects the actual retry outcome from Phase 2, not a guess
- [ ] `regression` reflects the actual replay outcome from Phase 2, not a guess
- [ ] At least one evidence entry when the input mode produced one (a failure report always has a stack trace or diff to attach)
- [ ] `suspected_area` populated or explicitly marked best-effort
- [ ] `test_reference` populated (framework, test name, file, and the exact rerun command from Phase 2's confirmation run) for a `--from-failure`/`--from-run` candidate — explicitly all-`null` only for `--from-text`/`--from-ticket`, never silently omitted

**Adapter output:**
- [ ] Duplicate lookup ran (or was explicitly skipped for markdown/display-only) and its result is in the success report
- [ ] Field mapping applied per the loaded `adapters/<tool>.md`
- [ ] MCP calls returned a successful ID (or the markdown file was written)

---

## Adding a New Output Adapter

Create `adapters/<toolname>.md` (don't edit this skill) with sections: requirements, flag syntax, duplicate-lookup step (or explicit "not applicable"), MCP/API calls, field mapping table, Phase 5 progress announcements, success report, errors/fallbacks, references. Add a row to the [Output Adapters](#output-adapters) table and update the `argument-hint`. Phases 1-4 do not change — the canonical format is stable.

---

## Error Handling

Adapter-specific errors live in each `adapters/*.md`. Common errors:

| Error | Message |
|------|---------|
| Missing input source | `❌ No input source specified. Use: --from-text "<text>", --from-failure <path>, --from-run <path\|id>, or --from-ticket <KEY>` |
| Failure artifact not found | `❌ Could not read failure artifact at <path>. Check the path and that the test run produced a report.` |
| Ticket not found | `❌ Could not fetch <KEY> from Jira. Check the ticket key and Atlassian MCP configuration.` |
| No Atlassian MCP | `❌ No Atlassian MCP server is connected. Connect the Atlassian connector in claude.ai (Settings → Connectors), or run: claude mcp add --transport sse --scope project atlassian https://mcp.atlassian.com/v1/sse — then /mcp → atlassian → Authenticate.` |
| Required fields missing, headless context | `❌ Missing required field(s): <list>. Cannot prompt in a non-interactive, non-MCP context. Re-run with --from-text to supply them directly, or in an interactive session.` |
| Adapter publish call failed | `❌ Failed to create the bug in <adapter>: <underlying error>. Nothing was filed. The report below is unchanged — retry, or re-run with --to-markdown [PATH] to save it locally instead.` (followed by the full canonical report, reprinted in full) |
| Regression replay's worktree could not be created (see Phase 2) | `⚠️  Could not verify regression: git worktree add failed (<underlying error>). Filing without regression data.` — record `regression.is_regression: null` and continue to Phase 3; the primary working tree was never touched. |

---

## Best Practices

- **Never skip evidence gathering for a runnable failure** — filing a bug without the retry/replay/duplicate steps produces exactly the low-quality report this skill exists to prevent.
- **Report quality over speed** — a report a developer can act on without asking a follow-up question is the only success criterion that matters.
- **Prefer `--to-markdown` first** when unsure which tool should own the bug — review locally before publishing to a shared tool.
- **Don't auto-file flaky results** — surface them, let the human decide.
- **Always capture the returned ID/URL** from the adapter and echo it in the success report.

---

## Integration with Other Skills

- **`/implement-ticket`** — its testing phase classifies a failing test as suspected pre-existing without verifying or filing anything for it; that classification is only recorded for the final report and the PR body. A developer reading "N suspected pre-existing failures" there can run `/report-bug --from-failure` themselves, at a moment of their choosing, against a tree in a known state — this skill does not wire into that phase automatically.
- **`/generate-test-cases`** — the two skills are architectural mirrors (evidence → canonical format → adapter) but serve opposite directions: `generate-test-cases` documents what should be tested, `report-bug` documents what already failed. A test case executed by a human or by `/playwright-e2e-automation` (web) or `/mobile-e2e-automation-architecture` (Detox/Appium) that fails is exactly the kind of manual/QA-automation finding `--from-failure` expects.
- **`/troubleshoot`** — troubleshoot is for fast, in-conversation root-cause debugging; once root cause is understood and the issue needs to be tracked as a ticket rather than fixed inline, hand off to `/report-bug`.

---

## References

- **Input**: Atlassian MCP `getJiraIssue` (markdown response) for `--from-ticket`, resolved per [MCP tool resolution](#mcp-tool-resolution); [references/run-tests.md](references/run-tests.md) for `--run`; [references/report-extraction.md](references/report-extraction.md) for every test-report shape.
- **Output adapters**: [`adapters/`](./adapters/) — one file per tool, loaded on-demand by Phase 5.
- **Related skills**: [`/generate-test-cases`](../generate-test-cases/SKILL.md), [`/implement-ticket`](../../020-development-workflow/implement-ticket/SKILL.md), [`/troubleshoot`](../../070-infrastructure/troubleshoot/SKILL.claude.md).
