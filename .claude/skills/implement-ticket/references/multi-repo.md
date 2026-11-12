# Multi-repo workspaces

Loaded by `/implement-ticket` in Phase 0 when `.preflight-ok` reports `workspace_mode: multi` — a parent folder containing N independent child git repos, each with its own remote. The SKILL body owns every phase; this file owns the three repo sets the phases name and the workspace-root rules. In `single` none of it applies: the one repo is a code repo, and every root rule below is `multi`-only.

## The three sets

- **`AFFECTED_REPOS`** — the repos the code change touches: the `child_repos` subset named in the plan's `## Affected Repositories`.
- **`DELIVERY_REPOS`** — `AFFECTED_REPOS` plus the workspace root when `git -C <root> rev-parse --git-dir` succeeds: it carries the Phase 7 cheat-sheet edit and the Phase 9 wiki commit, so Phase 8 acts on it too, and Phase 3 branches it only when `.gates.create_commit` is true — otherwise nothing is committed there. At the root only `docs/llm-wiki/` and `.claude/CLAUDE.md` are ever checked or staged; the rest of the parent folder is not QAF's concern.
- **PR set** (Phase 10) — `AFFECTED_REPOS` plus the workspace root when it is in `DELIVERY_REPOS` and `git -C <root> rev-list --count <base>..<branch>` ≥ 1 (`<base>` = its recorded `gh-merge-base`, else resolved as `repo-fanout-pr` Phase C step 2 does). Phase 10 sends the whole PR set through `/repo-fanout-pr`, whatever `len(PR set)` and whatever the mode.

## The workspace root never blocks delivery

A root step that fails never STOPs. Report `root changes left uncommitted on <root>:<current-branch> (<reason>)` and drop the root from `DELIVERY_REPOS`, so Phase 8 skips it, Phase 9 runs without `--commit`, and Phase 10 leaves it out:

- **Phase 0 — `dirty before run`**: a non-empty `git -C <root> status --porcelain -- docs/llm-wiki/ .claude/CLAUDE.md` or a failing `git -C <root> diff --cached --quiet` (the root commits take the whole index). The children's clean check in the SKILL body still STOPs.
- **Phase 3 — `branch failed`**: the create-or-switch step. The root is lenient under `--branch <name>`: not on `<name>` → create it there, or `git -C <root> switch <name>` when `git -C <root> rev-parse --verify --quiet refs/heads/<name>` succeeds.
- **Phase 8 or 9 — `commit failed`**: report it with the hook output and continue.

In Phase 10 the root carries wiki/docs only: without an `origin` remote it drops out of the PR set up front; a failed push or PR is recorded and skipped. Either way report `root commits left local on <root>:<branch> (<reason>)` — `no origin remote`, `push failed`, or `pr failed` — and continue: code PRs, their cross-links, and Phase 11 proceed. Phase 12 repeats every root line.
