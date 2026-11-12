---
name: wiki-refresh
version: 2.4.0
last-updated: 2026-10-06
description: AI-driven incremental refresh of docs/llm-wiki/. Use when the user says "/wiki-refresh", "refresh wiki", or "update wiki". Diffs against last-indexed commits (per-repo in multi-repo) in docs/llm-wiki/.state.json, asks an LLM to identify affected pages using index.md as the routing table, and surgically edits each. Conservative by design — high-level facts only. Multi-repo aware. Idempotent.
argument-hint: '[--dry-run] [--commit] [--ticket <ID>] [--artifacts-dir <path>]'
user-invokable: true
---

# Wiki Refresh

Input: $ARGUMENTS

Refresh `docs/llm-wiki/` pages whose **high-level** facts drifted since the last refresh. Default behaviour is write-only: page edits and `.state.json` are left uncommitted for ad-hoc runs. Pass `--commit` to commit the changes as `docs(wiki): refresh` (append `--ticket <ID>` for a per-ticket suffix). Pass `--dry-run` to see what would change without writing anything.

## Flags

Parse `$ARGUMENTS`:

- `--dry-run` — run phases 1–5 only; no writes, no commit. Wins over `--commit`.
- `--commit` — after phase 7, commit any changes under `docs/llm-wiki/**` (see phase 7 for message + multi-repo fallback).
- `--ticket <ID>` — only meaningful with `--commit`; appends ` for <ID>` to the commit message.
- `--artifacts-dir <path>` — anchors the Phase 0 preflight to the caller's run (marker reuse, see Phase 0); with `--commit`, when the wiki lives outside any git repo, the diff manifest + warning land under `<path>/wiki/` for the caller.

## Contract

- **What gets touched.** Existing `docs/llm-wiki/wiki/**/*.md` pages whose **high-level** facts an LLM judges to have drifted, plus `docs/llm-wiki/.state.json`, plus `docs/llm-wiki/wiki/index.md` when an updated page's `summary` / `tags` / `related` changed. Nothing else.
- **What never gets touched.** New page creation. If the diff suggests a new service deserves a wiki page, surface a one-line suggestion in the final summary — the user runs `/wiki-add-service <name>` separately.
- **All-or-nothing state advance.** `.state.json` is bumped to per-repo `HEAD`s only when every selected page update succeeded. On any failure, leave `.state.json` untouched so the next run retries from the same baseline.
- **Idempotent.** If `.state.json` is at HEAD everywhere, report "wiki is fresh" and finish successfully without spending tokens on AI calls.
- **Conservative.** "No change" is a successful outcome. The skill refuses to rewrite a page that still reads correctly. The high-level-only rule lives in the step-5 prompt; step 6 re-confirms per page before editing.

## Sequential phases

Execute these in order, starting at Phase 0. Do NOT skip ahead. Provider note: every "abort the skill" / "exit with failure" instruction below should be expressed however your runtime signals failure — exit non-zero in Claude Code, emit `failed` and STOP in Codex CLI. Every "finish successfully" instruction maps to exit 0 / emit `completed`. The semantics are identical.

### 0. Preflight (auto-bootstrap)

Run the deterministic preflight before any wiki work. It records the workspace topology and repo HEADs, checks for a framework update, and writes a success marker.

**With `--artifacts-dir <path>`** (a delegating caller mid-run — its own preflight just wrote `<path>/.preflight-ok`, and the only drift is the commit it just made):

```bash
cd "$(git rev-parse --show-toplevel)"
QAF_PREFLIGHT_ALLOW_HEAD_DRIFT=1 bash ".claude/scripts/ensure-context.sh" --artifacts-dir "<path>"
```

The env var lets marker reuse tolerate moved repo HEADs — every other reuse condition (marker <60 min fresh, no framework-update prompt pending) still holds, so this exits in ~1s. The marker's HEADs lag by one commit, which misleads nothing: page selection comes from git diffs.

**Without `--artifacts-dir`** (standalone invocation):

```bash
cd "$(git rev-parse --show-toplevel)"
bash ".claude/scripts/ensure-context.sh"
```

If `ensure-context.sh` exits non-zero, abort the skill and surface its output verbatim — the failure marker `<artifacts-dir>/.preflight-failed` carries `{reason, git_head, ran_at}`.

### 1. Read wiki state

Read `docs/llm-wiki/.state.json`. Expected shape:

```json
{
  "repos": { ".": "<sha>" },
  "last_refresh_at": "<iso>"
}
```

or, for multi-repo:

```json
{
  "repos": {
    "cm-ai-api": "<sha>",
    "cm-delivery-tool": "<sha>"
  },
  "last_refresh_at": "<iso>"
}
```

If the file does not exist → abort the skill: `wiki not initialized — run /initialize-project first`.

### 2. Enumerate repos at HEAD

Read the workspace shape from the marker Phase 0 wrote (`<artifacts-dir>/.preflight-ok`, default `.claude-temp/preflight/.preflight-ok`): `workspace_mode` is `multi` when the root, a git repo or not, has no `.gitmodules` and at least one top-level child git repo (the framework dir never counts); `child_repos` lists those children as absolute paths.

- **Single-repo** (`single`). Map: `{ ".": <current HEAD> }` via `git -C "$PROJECT_PATH" rev-parse HEAD`.
- **Multi-repo** (`multi`). Map each `child_repos` entry by basename: `git -C "<child>" rev-parse HEAD`. The root's own HEAD is not tracked — it holds only the wiki and config.

For any repo listed but missing from `repos` in `.state.json`, treat it as **new**: record its current HEAD into `repos` for the eventual state write, and skip its diff this run.

### 3. Build evidence pack per repo

For each repo where `repos[<repo>]` from `.state.json` exists and differs from current HEAD, run:

```bash
git -C "<repo-path>" log --oneline <recorded-commit>..HEAD
git -C "<repo-path>" diff --stat <recorded-commit>..HEAD
git -C "<repo-path>" diff --name-only <recorded-commit>..HEAD
```

For the top 3–5 largest-diff files (by `+/-` line count from `--stat`), also capture the first ~50 lines of their hunks via `git -C "<repo-path>" diff <recorded-commit>..HEAD -- <file>` and truncate.

If **every** repo's recorded commit equals current HEAD, report `wiki is fresh — no changes since last refresh` and finish successfully. Do NOT write `.state.json` (no-op). Do NOT commit.

### 3.5 Include external-doc evidence

After building the per-repo git evidence pack in Phase 3, load any external documents staged by `/wiki-ingest-external-docs` that have not yet been reflected in the wiki.

For each repo being processed in this run:

1. Check if `docs/llm-wiki/raw/external/manifest.json` exists inside that repo's wiki tree. If it does not exist, skip this step for that repo.
2. Read the manifest. Load all entries whose `ingested_at` timestamp is after `last_refresh_at` from `.state.json`. These are documents staged since the last refresh.
3. Append them to the evidence pack under the key `external_docs`:

   ```json
   {
     "external_docs": [
       {
         "path": "docs/llm-wiki/raw/external/<hash>-<slug>.md",
         "source_uri": "...",
         "subject_keywords": ["auth", "sessions"],
         "describes_service": "payments",
         "describes_files": [],
         "authoritativeness": "vendor-doc",
         "source_of_truth": false,
         "content_sha256": "..."
       }
     ]
   }
   ```

4. Additionally, check `docs/llm-wiki/global/raw/external/manifest.json` once per refresh run (not per-repo). Apply the same `ingested_at > last_refresh_at` filter using the minimum `last_refresh_at` across all repos in `.state.json`. Append matching global entries to the shared `external_docs` array.

If no manifest files exist, or no entries pass the timestamp filter, set `external_docs: []` and continue normally.

### 4. Read the routing table

Read `docs/llm-wiki/wiki/index.md` verbatim. It is the LLM's routing table — one line per page with summary / document_type / tags / related inline.

### 5. Identify affected pages

Assemble a single prompt containing, in order:

1. The wiki index (`index.md` content).
2. For each repo with changes: a section like `=== Commits (<repo-name>) ===` (commit subjects from step 3), `=== git diff --stat ===` (stat output), `=== Changed files ===` (file list), `=== Sampled hunks ===` (the truncated hunks).
3. If `external_docs` from Phase 3.5 is non-empty: a section `=== External Documents ===` listing each entry with its `path`, `subject_keywords`, `describes_service`, and `authoritativeness`. For each entry with `authoritativeness: rfc` or `source_of_truth: true`, read the first 200 lines of the file at `path` and include as a subsection. For other authoritativeness levels, include only the manifest metadata (not file content) to bound token cost.
4. The **conservatism rule** (verbatim):

   > **Descriptive sections** (everything except `## Conventions & How-To`) document **high-level architecture only**. Mark a page `update` ONLY when the diff changes a fact at that abstraction level: the existence or role of a service, its tech stack or version pin, its ports, its public API surface, its cross-cutting infrastructure (db / auth / queue / storage / LLM clients), its top-level directory layout, its authentication or authorization model, its deployment target, or another fact the page already records at that altitude. Mark `skip` for: implementation refactors, internal renames, new private helpers, new tests, bug fixes that don't change the public contract, formatting / style changes, dependency bumps that don't move a documented version pin, and any change confined to function bodies. When in doubt, prefer `skip` — a wiki page that already reads correctly should not be rewritten. "No change" is a successful outcome.
   >
   > **The service page's `## Conventions & How-To` section is prescriptive** and follows a separate rubric: mark the service page `update` when the diff changes a *rule for how new code in that service should be written* — a new or changed gotcha, a new validation library or where validation runs, a new required cross-file step (add-endpoint / add-entity checklist), a changed test command or fixture rule, a new security / boundary / error-envelope rule. A grounded WRONG/CORRECT example may be added or corrected. If a service page has no `## Conventions & How-To` section yet (it predates this section) and the diff shows a groundable rule, adding the section IS allowed — this is the one case where creating a new section is correct. Do not add generic stack-obvious advice; every rule must be grounded in the service's code.

5. The instruction: "Using `index.md` as the routing table and the conservatism rule above, identify which wiki pages need updating based on the diffs and any external documents listed above. For each external document in `external_docs`, use its `subject_keywords` and `describes_service` fields to route it to the most relevant wiki page — consult `index.md` to match. Weight external evidence by its `authoritativeness`: `rfc` and `source_of_truth: true` entries should trigger updates when they contradict or extend a page's current content; `meeting-note` entries are advisory only and should not trigger an update unless the page has no other information on the subject. Return strict JSON:

   ```json
   {
     "affected": [
       { "page": "wiki/<path>.md", "action": "update", "reason": "<one line tying the diff to a high-level fact the page records>" },
       { "page": "wiki/<path>.md", "action": "skip", "reason": "<one line — typically 'internal refactor, no public-contract change' or similar>" }
     ],
     "suggestions": ["<one-line suggestion strings>"]
   }
   ```

   `affected` lists every page whose summary you considered relevant (with `action: update` or `action: skip` and a one-line reason). `suggestions` lists potential new services / new major areas that don't have a wiki page yet — these are advisory only, not actionable here."

Send the prompt to yourself (you ARE the LLM) and produce the JSON. If the first attempt is malformed, retry once with a stricter prompt; if still malformed, abort the skill.

### 6. Update each affected page

For each entry with `action: "update"`:

1. Read the current page at `docs/llm-wiki/<page>`.
2. **Downgrade guard (section-aware).** Re-confirm which section the diff belongs in. For a **descriptive** section: does the page discuss the area at the page's own altitude? If it is silent on that area (e.g., the diff introduced a new internal helper for an existing service whose page only documents the service's role/ports/API surface), downgrade the action to `skip`, record `"downgraded_to_skip": "<reason>"`, and do not invent descriptive sections. For a change that is a **prescriptive rule** (per the second conservatism rubric), route it to the service page's `## Conventions & How-To` section — updating an existing sub-heading, or adding the section when the page predates it and the rule is groundable. A genuinely repo-wide rule goes to `docs/llm-wiki/wiki/conventions/project.md` → `## Project-Wide Rules` (add the section if the page lacks it), not to a service page's `## Conventions & How-To`.
3. Otherwise, when the diff introduced symbols the page does not already name, Grep each one (word-boundary) and Read only its declaring file for context.
4. If the page update is triggered by an `external_docs` entry (from Phase 3.5): read the full content of the staged file at the entry's `path`. Absorb only its descriptive, high-level claims — same conservatism rule applies. When citing the external source in the page, use a markdown link pointing to the staged file (e.g., `[vendor-auth-spec](../raw/external/<hash>-<slug>.md)`). Do not cite the original `source_uri` (it may be ephemeral). Weight the external evidence by its `authoritativeness` field.
5. Use your file-edit primitive to surgically patch sections that drifted. **Preserve every sentence whose factual content is still accurate.** Goal: minimal diff against the previous version.
6. Update frontmatter `last_updated` to the current ISO timestamp. Frontmatter `summary` / `tags` / `related` only change when the page's overall identity actually shifted (a new framework adopted, a service's role inverted) — not on every routine update.
7. If `summary` / `tags` / `related` legitimately changed in step 6, surgically patch the corresponding line in `docs/llm-wiki/wiki/index.md` so the index stays in sync. Body-only edits skip the index touch.

For each entry with `action: "skip"`, do nothing — but remember the reason for the summary print.

If any page update fails (edit error, file missing, etc.), do NOT proceed to step 7. Surface the error and abort the skill so the next run retries from the same baseline.

### 7. Write `.state.json` (and optionally commit)

On success only:

1. Write `docs/llm-wiki/.state.json` with every repo's entry set to its current HEAD and `last_refresh_at` set to now.

   ```json
   {
     "repos": { "<repo-id>": "<HEAD-sha>" },
     "last_refresh_at": "<iso>"
   }
   ```

2. **If `--commit` was passed** and any file under `docs/llm-wiki/**` was modified (pages and/or `.state.json` and/or `index.md`):
   - Locate the git repo that contains `docs/llm-wiki/`. Walk up from `docs/llm-wiki/` looking for `.git/`.
   - **If found**:
     - Stage only the changed paths under `docs/llm-wiki/**` (explicit list from `git status --porcelain -- docs/llm-wiki/`). Never `git add .` / `-A`.
     - Commit message: `docs(wiki): refresh` by default; `docs(wiki): refresh for <TICKET-ID>` when `--ticket <ID>` was passed.
     - `git -C <wiki-repo> commit -m "<message>"`. Do not skip hooks. If the commit fails (e.g. pre-commit hook failure), surface the hook output verbatim and finish with the `commit-failed` outcome — leave `.state.json` written so a manual retry can commit without re-running the LLM.
   - **If not found** (the root is outside git, or a standalone run against a wiki folder outside any git repo):
     - **If `--artifacts-dir <path>` was passed**: write the full diff of `docs/llm-wiki/**` to `<path>/wiki/wiki-diff.md` and a one-line warning to `<path>/wiki/wiki-warning.txt` (suggested text: `Wiki was refreshed but lives outside any git repo — review docs/llm-wiki/ changes manually.`). Do not commit.
     - **If `--artifacts-dir` was NOT passed**: surface the same one-line warning. Do not commit. Leave the changes in the working tree.

If `--commit` was NOT passed, do nothing further — leave the changes in the working tree for the caller to inspect.

### 8. Summary

Report:

- **Updated:** list of pages updated.
- **Skipped:** list of pages whose summaries matched but the LLM judged no update needed (with reasons). Include any step-6 downgrades with the `downgraded_to_skip` reason.
- **External docs:** count of `external_docs` entries included in this run's evidence pack (e.g., `external_docs: 3 staged documents included`). List the filenames. If zero, omit this line.
- **Suggestions:** one-line items from step 5's `suggestions` array. For each, append `Run /wiki-add-service <name> to create a new service-doc page.` only when the suggestion clearly names a service-shaped area.
- **Commit:** when `--commit` produced a commit, report the repo, branch, SHA and message; when its pre-commit hook failed, report `commit-failed` with the hook output. When it produced an artifact-only fallback, point at the manifest path.
- **Dry-run note** if `--dry-run` was passed.

## `--dry-run`

When `--dry-run` is in `$ARGUMENTS`:

- Run phases 1–5 exactly as above.
- **Skip phase 6** (no page edits, no index edits).
- **Skip phase 7** (no `.state.json` write, no commit).
- Phase 8 summary explicitly notes "(dry-run — no changes made)".

`--dry-run` always wins over `--commit`.

## Failure modes

- `ensure-context.sh` (Phase 0) exits non-zero → abort, surface its output verbatim. The `<artifacts-dir>/.preflight-failed` marker carries the reason.
- `.state.json` missing → abort with message `wiki not initialized — run /initialize-project first`.
- Malformed LLM JSON after one retry → abort, surface the malformed response for debugging.
- Page update fails (edit error, file missing) → abort, do NOT advance `.state.json`. Next run retries from the same baseline.
- `--commit` and the wiki repo's pre-commit hook fails → abort, surface hook output, leave `.state.json` written so a manual `git commit` can finish the job.

## Why this design

- **Conservatism is the goal.** The hardcoded high-level rule in step 5 plus the per-page downgrade guard in step 6 push the LLM toward "no change" whenever the diff is implementation noise. A wiki that reads correctly should not be rewritten.
- **AI-judged matching** uses `index.md` as a routing table — one mechanism handles service docs, ARCHITECTURE.md, and any future cross-cutting page without rigid frontmatter mapping.
- **Surgical edits** preserve hand-tweaked prose. The page is not regenerated from scratch.
- **Per-repo state** is the only way multi-repo workspaces can track wiki freshness — the parent's HEAD doesn't move when children advance.
- **All-or-nothing state advance** means a partial failure never silently desyncs the wiki from the codebase.
- **Skill-owned commit** means `/implement-ticket` Phase 9 doesn't need to know how to stage `docs/llm-wiki/**`; the skill produces a clean follow-up commit after the implementation commit lands in Phase 8.
