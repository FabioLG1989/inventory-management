---
name: pr-reviewer
version: 5.5.1
last-updated: 2026-10-02
description: Reviews a GitHub pull request with five parallel specialist subagents and a coordinator-judge that plays devil's advocate, verifies every finding deterministically, then submits one formal GitHub review (REQUEST_CHANGES / COMMENT / APPROVE) with inline comments via gh api. Invoked by /implement-ticket once per PR URL (with --quick for a simple run: bug-logic and security specialists, no judge); also user-invocable. Single- and multi-repo.
allowed-tools: Bash, Read, Write, Grep, Glob, Task
argument-hint: '[--pr-url <URL>] [--jira-key <KEY>] [--mode automated|manual] [--approve] [--artifacts-dir <abs>] [--repos <abs1>,<abs2>,...] [--aggregate] [--quick]'
user-invocable: true
disable-model-invocation: false
---

# PR Reviewer

Input: $ARGUMENTS

- `--pr-url <URL>` — GitHub PR to review (required unless `--aggregate`)
- `--jira-key <KEY>` — ticket key for artifact namespacing
- `--mode automated|manual` — automated posts the review; manual stops so you can edit `review.json` and posts it on your go-ahead (default: automated)
- `--approve` — post a formal `APPROVE` when the review is clean; without it a clean PR is posted as a `COMMENT` that states the intended verdict (default: off)
- `--quick` — two specialists (`specialist-bug-logic`, `specialist-security-style`), no judge; `/implement-ticket` passes it for a `simple` run
- `--artifacts-dir <abs>` — absolute artifact root (`$ARTIFACTS_DIR_FLAG`), passed by `/implement-ticket`; output goes under `<abs>/pr/...`
- `--repos <abs1>,<abs2>,...` — repo roots in multi-repo mode
- `--aggregate` — skip the review; run the cross-repo aggregator over this ticket's per-PR results

Read `.claude/skills/pr-reviewer/references/pipeline.md` now — it owns variables, fetch, artifacts, `review-results.json`, `review.json`, verification and posting. Nothing below restates it.

## Roles

Every role is a prompt under `.claude/skills/pr-reviewer/agents/`. Run a role by spawning a subagent with your runtime's subagent tool (`Task(subagent_type: "general-purpose")` in Claude Code, `spawn_agent` in Codex CLI) whose prompt is the role's instructions; tell it not to spawn subagents of its own, and wait for its result. When no subagent tool is available, run the role yourself: read its file, adopt its objective, output_format and boundaries, write its output file, then return to the orchestrator persona.

## Artifact paths

```bash
ARTIFACTS_BASE="${ARTIFACTS_DIR_FLAG:-.claude-temp/artifacts/${JIRA_KEY}}"
REVIEW_DIR="$ARTIFACTS_BASE/pr${REPO_BASENAME:+/$REPO_BASENAME}/review"
```

Single-repo: `$ARTIFACTS_BASE/pr/review/`. Multi-repo: `$ARTIFACTS_BASE/pr/<repo-basename>/review/` per PR, then `$ARTIFACTS_BASE/pr/cross-repo-summary.{json,md}` from `--aggregate`. Each `--pr-url` invocation is independent; `--artifacts-dir` keeps every tree at the workspace root even when `--repos` points at a child repo.

## Pipeline

1. **Gate and fetch** — pipeline §Rerun gate, §Fetch.
2. **Context** — pipeline §Context.
3. **Specialists** — in one turn, spawn the five roles in parallel (`--quick`: only `specialist-bug-logic` and `specialist-security-style`), each with pipeline §Specialist prompt and its role substituted: `specialist-bug-logic`, `specialist-security-style`, `specialist-tests`, `specialist-performance`, `specialist-conventions`. Wait for all. Without a subagent tool, run them one at a time in that order.
4. **Judge** — one subagent for `coordinator-judge.md` with the §Judge inputs; it challenges blocking and single-source major findings and writes `$REVIEW_DIR/adjudication.json`. Skip it under `--quick`, or when every specialist returned `0 findings` — §Build rules keep-all in its place.
5. **Build** — one `node` command (§Build) assembles `review-results.json` from the rulings, verifies the findings and writes `$REVIEW_DIR/review.json`; pass `--approve` and `--quick` through when given.
6. **Post** — automated mode:
   ```bash
   gh api -X POST "repos/$OWNER_REPO/pulls/$PR_NUMBER/reviews" --input "$REVIEW_DIR/review.json" > "$REVIEW_DIR/posted.json"
   ```
   Retries and manual mode: §Post.

## Aggregate mode (--aggregate)

Resolve `$ARTIFACTS_BASE` and collect the per-PR `review-results.json` files (§Aggregate). With two or more, run one subagent for `cross-repo-aggregator.md` to write `$ARTIFACTS_BASE/pr/cross-repo-summary.json` and `.md`.
