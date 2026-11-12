---
name: repo-fanout-pr
version: 1.5.0
last-updated: 2026-10-15
description: Pushes and opens one PR per listed repo — a single repo, or child repos and, when it carries commits, the workspace root — on GitHub, GitLab or Azure DevOps, then cross-links the code PR bodies (the workspace-root PR links to them, never the reverse). Invoked by /implement-ticket Phase 10 and /apply-ticket-feedback for every PR set, one repo or many. Pass --no-commit when the caller has already committed (e.g., /implement-ticket Phase 8). Not for direct user use.
argument-hint: '--repos <abs-path>[,<abs-path>...] --branch <name> --ticket <ID> --artifacts-dir <path> [--base <branch>] [--body-append <abs-path>] [--skip-pr] [--no-commit]'
disable-model-invocation: true
---

# Repo Fanout PR

Input: $ARGUMENTS

Create one commit + push + PR per repo in `--repos` — one repo or many — then cross-link the code PR bodies so reviewers can navigate the change as a single logical unit. Returns a structured JSON result the caller consumes.

This skill is the PR path that `/implement-ticket` Phase 10 and `/apply-ticket-feedback` delegate to for every PR set. It is intentionally narrow: it owns commit/push/PR creation and cross-linking, nothing else. It does NOT run tests, refresh wiki, or modify the working tree beyond `git add` of files already changed by the implementer.

## Inputs

Parse `$ARGUMENTS` for these flags:

- `--repos <abs1>[,<abs2>,...]` — comma-separated absolute paths to each git repo to deliver: a single repo, or child repos plus the workspace root when it carries the wiki/cheat-sheet commits. Order is preserved in the output JSON.
- `--branch <name>` — feature branch name. Must already exist in every repo (Phase 3 created it).
- `--ticket <ID>` — ticket id, used in commit message and PR title.
- `--artifacts-dir <path>` — `$ARTIFACTS_DIR` from the orchestrator. Outputs land under `<artifacts-dir>/fanout/`.
- `--base <branch>` (optional) — base for every repo's PR; overrides the recorded fork point. Absent → Phase C step 2 resolves it per repo.
- `--body-append <abs-path>` (optional) — a markdown file the caller wrote (suspected pre-existing test failures, findings addressed, the original PR); its content goes verbatim into every PR body between `## Ticket` and `## Related PRs`.
- `--skip-pr` (optional) — commit locally in each repo and STOP. No push, no PR.
- `--no-commit` (optional) — skip Phase B (stage and commit). The caller has already produced the implementation commit in each repo (e.g., `/implement-ticket` Phase 8). Phase B becomes: use `git rev-parse HEAD` as `commit_sha`, derive `files_count` from `git diff --name-only <base>..<branch>`, and assert that the working tree is clean and the branch has at least one commit ahead of base. STOP otherwise.

The skill reads the canonical ticket context from `<artifacts-dir>/context/ticket-context.md` to build PR titles and bodies.

## Outputs

- `<artifacts-dir>/fanout/<repo-basename>/files.txt` — per-repo list of files staged.
- `<artifacts-dir>/fanout/<repo-basename>/pr-body.md` — per-repo PR body, after cross-link pass.
- `<artifacts-dir>/fanout/result.json` — the structured result returned to the caller. Schema:

```json
{
  "branch": "feature/PROJ-123-foo",
  "skipped": false,
  "repos": [
    {
      "path": "/abs/path/to/cm-ai-api",
      "name": "cm-ai-api",
      "remote": "thisisqubika/cm-ai-api",
      "base": "development",
      "commit_sha": "abc123…",
      "pr_url": "https://github.com/thisisqubika/cm-ai-api/pull/42",
      "files_count": 7
    }
  ]
}
```

Under `--skip-pr`, every entry has `pr_url: null` and `skipped: true` at the top level. The caller treats a code-repo failure as STOP.

## Phases

### Phase A — Validate inputs

- Assert `--repos`, `--branch`, `--ticket`, `--artifacts-dir` are all set; STOP with a clear error otherwise.
- Assert every path in `--repos` exists and contains `.git`; STOP otherwise.
- Classify: the workspace root is the `--repos` entry that is a parent directory of another entry (none in a single-repo or children-only set); every other entry is a code repo. Deliver the root after every code repo. Every later STOP or abort — the branch checkout below and Phases B and C — applies to code repos only; on the root, record `pr_url: null` plus an `errors[]` entry (repo path, failed step, stderr) and continue: it carries wiki/docs only and must never block the code PRs.
- For each repo, assert the current branch matches `--branch`. If not, switch with `git -C <repo> checkout <branch>` (created upstream by Phase 3).
- `mkdir -p <artifacts-dir>/fanout`.

### Phase B — Stage and commit per repo

When `--no-commit` is set, Phase B does NOT stage or commit. Instead, for each `<repo>` in `--repos`:

1. Resolve the base branch (Phase C step 2).
2. Assert the working tree is clean: `git -C <repo> status --porcelain` MUST be empty (on the workspace root: `git -C <root> status --porcelain -- docs/llm-wiki/ .claude/CLAUDE.md`, the only root paths QAF stages). If not, surface the porcelain output and STOP (the caller violated the contract by not committing all changes).
3. Assert the branch has at least one commit ahead of base: `git -C <repo> rev-list --count <base>..<branch>` MUST be ≥ 1. If 0, surface a clear error and STOP (nothing to push for this repo).
4. Capture `commit_sha = git -C <repo> rev-parse HEAD`.
5. Capture the file list `git -C <repo> diff --name-only <base>..<branch>` and write it to `<artifacts-dir>/fanout/<repo-basename>/files.txt`. `files_count` = line count.
6. Continue to Phase C with the captured `commit_sha` and `files_count`.

Otherwise (the default — `--no-commit` not set), for each `<repo>` in `--repos`, in input order:

1. Compute the file list from `git -C <repo> status --porcelain` — both modified and untracked (the workspace root: `-- docs/llm-wiki/ .claude/CLAUDE.md` only). Strip status prefixes; keep paths relative to `<repo>`.
2. If the list is empty, RECORD `files_count: 0`, `commit_sha: null` and continue (this repo has no changes; the caller likely shouldn't have included it, but we tolerate it).
3. Write the list to `<artifacts-dir>/fanout/<repo-basename>/files.txt`.
4. Stage the listed files only: `git -C <repo> add -- <file1> <file2> …`. Never `git add .` and never `git add -A`.
5. Build the commit message:

   ```
   <type>(<ticket>): <ticket short title>

   <ticket short body, ≤72 chars per line>

   Refs: <TICKET_ID>
   ```

   `<type>` is inferred per repo from the touched paths (heuristic: presence of `src/api/`, `src/entities/` → `feat` for backend; presence of `services/web-frontend/src/components/` → `feat`; tests-only diff → `test`; docs-only diff → `docs`). When in doubt, default to `feat`.
6. `git -C <repo> commit -m "<message>"`. Capture the resulting SHA via `git -C <repo> rev-parse HEAD`.

If commit fails for any repo (e.g., pre-commit hook failure), surface the hook output verbatim and STOP — do NOT proceed to other repos. The caller decides whether to retry. Earlier successful commits stay in their repos for the user to inspect.

### Phase C — Push and create PRs

Skipped entirely under `--skip-pr` (jump to Phase E with `skipped: true`).

For each `<repo>` with a non-null `commit_sha`:

1. Detect SCV and resolve coordinates from `git -C <repo> remote get-url origin`:
   - **GitHub** (`github.com` in URL): parse `<owner>/<name>` from SSH (`git@github.com:<owner>/<name>.git`) or HTTPS (`https://github.com/<owner>/<name>.git`). Strip trailing `.git`.
   - **Azure DevOps** (`dev.azure.com` or `visualstudio.com` in URL): parse `<org>`, `<project>`, `<repo-name>` from `https://dev.azure.com/<org>/<project>/_git/<repo-name>` or `https://<org>.visualstudio.com/<project>/_git/<repo-name>`.
   - **GitLab** (`gitlab` in URL): parse `<namespace>/<name>` from SSH or HTTPS forms. Strip trailing `.git`.
   - Unknown host: still run step 3 (push), then record `pr_url: null` plus an `errors[]` entry (`unsupported host <host> — branch pushed; open the PR manually`) and continue with the next repo.
2. Resolve the base branch — first hit wins:
   - `--base`.
   - The fork point `/implement-ticket` Phase 3 recorded: `git -C <repo> config branch.<branch>.gh-merge-base`.
   - Inferred from history: the HEAD reflog entry that created `<branch>` (`git -C <repo> log -g --format=%gs HEAD | grep ' to <branch>$' | tail -1` → `checkout: moving from <base> to <branch>`), else the remote branch whose merge-base with `<branch>` is nearest its tip.
   - The remote default branch: `git -C <repo> symbolic-ref --short refs/remotes/origin/HEAD` minus `origin/`, else `git -C <repo> remote show origin` → `HEAD branch`.

   Verify with `git -C <repo> ls-remote --heads origin <base>`; missing → STOP. When the base was not recorded, print `base for <repo>: <base> (inferred|remote-default)` — a guess is never silent.
3. Push: `git -C <repo> push -u origin <branch>`; non-zero exit → STOP with its stderr.
4. Build the initial PR body at `<artifacts-dir>/fanout/<repo-basename>/pr-body.md`:

   ```markdown
   ## Summary

   <one-paragraph summary derived from the ticket title + description>

   ## Scope of this PR

   This PR contains the **<repo-basename>** portion of <TICKET_ID>. Files touched in this repo:

   - <file1>
   - <file2>
   - …

   ## Test plan

   - [ ] <items derived from ticket acceptance criteria>

   ## Ticket

   <TICKET_ID> — see ticket-context.md (or the linked ticket if available)

   ## Related PRs

   _Will be populated after sibling PRs are created._
   ```

   With a single repo in `--repos`, drop the ` (<repo-basename>)` title suffix below and the "contains the … portion of" sentence (keep the file list). When `--body-append` is set, insert that file's content verbatim between `## Ticket` and `## Related PRs`.

5. Create the PR using the SCV detected in step 1:

   **GitHub:**
   ```
   gh -R <owner>/<name> pr create \
     --base <base> \
     --head <branch> \
     --title "<TICKET_ID>: <ticket short title> (<repo-basename>)" \
     --body-file <artifacts-dir>/fanout/<repo-basename>/pr-body.md
   ```

   **Azure DevOps:**
   ```
   az repos pr create \
     --repository <repo-name> \
     --org https://dev.azure.com/<org> \
     --project <project> \
     --source-branch <branch> \
     --target-branch <base> \
     --title "<TICKET_ID>: <ticket short title> (<repo-basename>)" \
     --description @<artifacts-dir>/fanout/<repo-basename>/pr-body.md \
     --open
   ```

   **GitLab:**
   ```
   glab mr create \
     --source-branch <branch> \
     --target-branch <base> \
     --title "<TICKET_ID>: <ticket short title> (<repo-basename>)" \
     --description "$(cat <artifacts-dir>/fanout/<repo-basename>/pr-body.md)"
   ```

6. Capture the returned URL.

If PR creation fails for a repo after a sibling PR already succeeded, do NOT auto-close the sibling. Record the failure in `result.json` (set `pr_url: null`, add a top-level `errors[]` entry with the repo path and stderr), and STOP. The caller surfaces the partial state to the user verbatim.

### Phase D — Cross-link pass

Once every code repo has a PR URL:

1. Build each PR's block from the code PRs only — a code PR lists its sibling code PRs; the root PR, when it exists, lists every code PR. The root PR itself is never listed: no code PR points at the wiki/cheat-sheet PR.

   ```markdown
   ## Related PRs

   - <repo-A-name>: <PR-A-URL>
   - <repo-B-name>: <PR-B-URL>
   - …
   ```

2. For each PR, rewrite `pr-body.md` replacing the `## Related PRs` placeholder section with its block; a code PR whose block is empty drops the section instead.
3. Update each PR body using the SCV detected in Phase C step 1:

   **GitHub:** `gh -R <owner>/<name> pr edit <number> --body-file <artifacts-dir>/fanout/<repo-basename>/pr-body.md`

   **Azure DevOps:** `az repos pr update --id <number> --org https://dev.azure.com/<org> --project <project> --description @<artifacts-dir>/fanout/<repo-basename>/pr-body.md`

   **GitLab:** `glab mr update <number> --description "$(cat <artifacts-dir>/fanout/<repo-basename>/pr-body.md)"`

   PR numbers are derived from the URL (last path segment after `pull/` or `merge_requests/`).

If the update fails for any PR, the PR itself still exists; record the failure in `result.json` under `errors[]` but do NOT STOP — cross-linking is best-effort. Surface the partial result to the caller.

### Phase E — Emit `result.json`

Write the structured result to `<artifacts-dir>/fanout/result.json`. Print the JSON to stdout so the caller can capture it. Exit 0 when every code repo has a PR (root-only `errors[]` entries still exit 0), exit 1 on partial success (a code repo failed), exit 2 on hard failure (Phase A or B aborted).

## Constraints

- Every git command is `git -C <repo>` with a path taken from `--repos`; never rely on cwd, never touch an unlisted repo.
- Never `git add .` / `git add -A` / `git commit -a`. Only stage the files reported by `git status --porcelain` for that specific repo.
- Never skip hooks. If a hook fails, surface and STOP.
- Never force-push.
- Never close or delete a PR programmatically — even on partial failure, leave PRs open for the user to triage.

## Prerequisites

- SCV CLI installed and authenticated: `gh` for GitHub, `az` (Azure CLI with `azure-devops` extension) for Azure DevOps, `glab` for GitLab. Only the CLI matching the detected remote is required.
- Each repo in `--repos` already has the feature branch `<branch>` checked out (created in Phase 3).
- Default mode: each repo has changes staged-or-unstaged in the working tree (the implementer's edits from Phase 4). `--no-commit` mode: each repo's working tree is clean (the workspace root: within `docs/llm-wiki/` and `.claude/CLAUDE.md`) and the branch is ahead of base — a child carries the `/implement-ticket` Phase 8 implementation commit; the workspace-root entry carries the Phase 8 cheat-sheet and/or Phase 9 wiki-refresh commits.
- `<artifacts-dir>` exists and is writable.
