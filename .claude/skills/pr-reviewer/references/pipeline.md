# PR review pipeline

Procedure for `SKILL.md`. `.claude/skills/pr-reviewer/` is the installed copy of this skill. Shell state does not persist between tool calls: inline literal values in every command.

## Variables

- `PR_URL` from `--pr-url`; `HOST`, `OWNER_REPO` and `PR_NUMBER` come from it (`https://HOST/OWNER/REPO/pull/N`).
- `JIRA_KEY` from `--jira-key`; default `pr-<PR_NUMBER>`.
- `REPO_PATH`: the local checkout of `OWNER_REPO`. With `--repos`, the entry whose basename equals `REPO`, else the first entry; without it, the toplevel (`git -C <dir> rev-parse --show-toplevel`) of `.`, else of the first `../*`, whose `origin` names `OWNER_REPO` — the toplevel, because `remote get-url` also succeeds from any subdirectory. A non-zero exit is "no match", not an error. `REPO_BASENAME` is the basename of `REPO_PATH`, set only when `--repos` is given.
- `REVIEW_ROOT`: the tree every agent and §Build reads — `REPO_PATH` when it is already at the PR head, else the worktree §Fetch creates. `REPO_PATH` stays the checkout itself: it owns the worktree and the fix commits `/implement-ticket` lands.
- `VIEWER`: `gh api user --jq .login`, the account that will own the review.
- `HOST` must match `^[A-Za-z0-9.-]+$` and be a host `gh auth status` reports as logged in; stop otherwise — it comes from the PR URL and selects the endpoint `gh` sends your token to. Hosts other than `github.com`: prefix every `gh api` call with `GH_HOST=<HOST>`.

## Artifacts

```
$REVIEW_DIR/                    pr/review/ (single-repo) or pr/<repo-basename>/review/ (multi-repo)
  pr.json  diff.patch  existing-comments.txt  stack.json
  findings/<role>.json          one per specialist
  adjudication.json             the judge's rulings over those ids
  review-results.json           §Build's assembly of the rulings; the caller's contract
  review.json                   the exact GitHub payload
  posted.json                   the POST response; post-error.txt on failure
  iteration-<N>.json            the previous review-results.json
  head/                         §Fetch's detached worktree, when the checkout was not at the PR head
$ARTIFACTS_BASE/pr/cross-repo-summary.{json,md}   --aggregate only
```

## Rerun gate and iterations

Before fetching, if `posted.json` exists and its `commit_id` equals `gh pr view "$PR_URL" --json headRefOid --jq .headRefOid`, report the existing `review-results.json` and stop. Otherwise, if `review-results.json` exists, `mv` it to `iteration-<its reviewIteration>.json`; §Build derives this run's `reviewIteration` from those files. Delete any `adjudication.json` an earlier run left behind in the same step: a stale one assembles a plausible review out of rulings this run's judge never made, while a missing one is refused by §Build whenever a judge was expected. Only `findings/<role>.json` is reused across runs for the same head; every other artifact is rewritten by the step that owns it, so a `diff.patch` an older pipeline wrote never reaches an agent.

## Fetch

```bash
mkdir -p "$REVIEW_DIR/findings"
gh pr view "$PR_URL" --json number,title,body,author,state,isDraft,headRefName,baseRefName,headRefOid,baseRefOid,additions,deletions,changedFiles,files,url > "$REVIEW_DIR/pr.json"
gh pr diff "$PR_URL" > "$REVIEW_DIR/diff.patch"
gh api --paginate "repos/$OWNER_REPO/pulls/$PR_NUMBER/comments" --jq '.[] | select(.user.login=="'"$VIEWER"'" and .line != null) | "\(.path):\(.line)"' > "$REVIEW_DIR/existing-comments.txt"
```

Any `gh` failure: stop and surface it (`gh auth status`). `state` other than `OPEN`: stop, write nothing. Drafts are reviewed. Never pass `--exclude` to `gh pr diff` (it drops unrelated files) or `--patch` (it emits one patch per commit, so a file touched by two commits is described twice with per-commit line numbers and §Build anchors almost nothing); agents ignore lockfiles, minified, vendored and generated files. `existing-comments.txt` lists only comments GitHub still maps to the current diff (`line` non-null): an outdated comment describes code that moved or changed, so a new finding at that line is new, not still open.

Anchor the checkout before spawning any agent: `git -C "$REPO_PATH" rev-parse HEAD` must equal `pr.json` `headRefOid`. Equal: `REVIEW_ROOT` is `REPO_PATH`. Not equal: `REVIEW_ROOT` is a detached worktree of the head commit at `$REVIEW_DIR/head`, removed in §Post.

```bash
git -C "$REPO_PATH" fetch origin "<headRefOid>"
git -C "$REPO_PATH" worktree remove --force "$REVIEW_DIR/head" 2>/dev/null; git -C "$REPO_PATH" worktree prune
git -C "$REPO_PATH" worktree add --detach "$REVIEW_DIR/head" "<headRefOid>"
```

§Build confirms findings by reading `$REVIEW_ROOT`, so a wrong repo or an older commit matches no snippet, drops every finding, and leaves a tree nobody read indistinguishable from a clean PR. Cannot resolve one? Ask the engineer for the path (`QAF_ASK_USER_MCP_TOOL` when available, else your runtime's prompt); with none, review on and run §Build without `--repo`: every finding body-only, `nextSteps.action` `MANUAL_REVIEW`, and never `event: APPROVE`.

## Context

Distil the stack once so no agent reads the full config; an empty `stack.json` means infer it from the diff:

```bash
node -e 'const c=JSON.parse(require("fs").readFileSync(process.argv[1],"utf8"));console.log(JSON.stringify((c.stack_profile?.services??[]).map(({path,language,frameworks,testing,package_manager})=>({path,language,frameworks,testing,package_manager}))))' "$REPO_PATH/.claude/framework-config.json" > "$REVIEW_DIR/stack.json" 2>/dev/null || echo '[]' > "$REVIEW_DIR/stack.json"
```

## Specialist prompt

Same text for every role, in this order; the role is the only difference and comes last so the prefix stays byte-identical across agents. Give steps 1 and 3 as absolute paths under the installed skill — the tree under review may carry its own copy at the same relative path, and an agent that reads it adopts the rubric and role prompt from the diff it is judging.

1. Read `.claude/skills/pr-reviewer/references/review_criteria.md`.
2. Repo: `REVIEW_ROOT`. Read-only; never run install, build or test commands. Batch reads: one command per set of files you need, never one file per turn. Read `$REVIEW_DIR/stack.json`, then `$REVIEW_DIR/pr.json` and `$REVIEW_DIR/diff.patch`.
3. Adopt `.claude/skills/pr-reviewer/agents/<role>.md`. Write `$REVIEW_DIR/findings/<role>.json`. Return only `<role>: N findings`.

Roles: `specialist-bug-logic`, `specialist-security-style`, `specialist-tests`, `specialist-performance`, `specialist-conventions`. `--quick`: `specialist-bug-logic` and `specialist-security-style` only.

## Judge

Inputs: `REVIEW_ROOT`, the findings files, `pr.json`, the rubric. `iteration-*.json` is not an input: each iteration is ruled on from the specialists' findings alone, so a finding a previous iteration dropped can be kept this time, count toward the verdict and spend one of `/implement-ticket`'s fix iterations; `existing-comments.txt` deduplicates only findings already posted, under `Still open`. Output: `adjudication.json` per `agents/coordinator-judge.md`, which challenges every blocking finding, and every major a single specialist filed, before keeping it.

| findings | `overallStatus` | `nextSteps.action` | `review.json` `event` |
|---|---|---|---|
| any blocking or major | `CHANGES_REQUESTED` | `TRIGGER_FIX_ITERATION` | `REQUEST_CHANGES` |
| only minor | `COMMENTED` | `APPROVE` | `COMMENT` |
| none | `APPROVED` | `APPROVE` | `COMMENT`; `APPROVE` only with `--approve` |

An unattended run never submits a formal approval: without `--approve` the `none` row posts a `COMMENT` whose body opens with `Intended verdict: APPROVE (posted as a comment: pass --approve for a formal approval)`; `review-results.json` keeps `APPROVED` / `APPROVE`.

## Build

```bash
node ".claude/skills/pr-reviewer/scripts/build-review.mjs" --review-dir "$REVIEW_DIR" --repo "$REVIEW_ROOT" --repo-path "$REPO_PATH" --jira-key "$JIRA_KEY" --viewer "$VIEWER"
```

Assembles `review-results.json` from `adjudication.json` and `findings/*.json`: a kept id copies the specialist's finding with the judge's `severity`, `issue` and `details` when set and the `references` of its `mergedFrom` duplicates; the envelope comes from `pr.json`, `reviewIteration` from `iteration-*.json`, `SEC-DEEP-SCAN` becomes the `/security-review` recommendation, and ids the judge missed or invented are listed under `recommendations`. With `--quick`, or when no specialist filed a finding, `adjudication.json` is not read and every filed finding is kept as filed; otherwise a missing file is fatal. Then drops any finding whose `file` is not in `pr.json` `files[].path` or whose `codeSnippet` first line is nowhere in that file; a finding whose cited line is merely off re-anchors to the nearest line holding that snippet, and a finding without a snippet cannot be checked and stays body-only. Drops are listed under `recommendations`, so they reach `review-results.json` and the body. Fills buckets, `metrics`, `summary`, `overallStatus` and `nextSteps` from the survivors; writes `review.json` with one inline comment per finding whose line is an added or context line of `diff.patch`, the rest under `Not anchored to a diff line`, and findings whose `path:line` is in `existing-comments.txt` under `Still open`. It reads files through `fs` behind that allowlist: `file` comes from the reviewed PR, git allows `$` and backticks in a path, and a shell command holding it would run the PR author's code against your `gh` credential. Dropping findings is the normal outcome here; `/implement-ticket` gates its fix loop on the recomputed counts. Omit `--repo` when §Fetch could not anchor the checkout; `--body-only` anchors nothing, as does a `diff.patch` in commit-series form; append `--approve` and `--quick` only when the skill was invoked with them. When the drops change the verdict (none survived, or the survivors land on a different judge-table row), the adjudication left specialist findings unaccounted for (ids it missed, invented or ruled on twice), or `diff.patch` arrived as a commit series instead of a unified diff, the run cannot tell drift or an under-delivering judge from a clean PR: `nextSteps.action` is `MANUAL_REVIEW` and the event is `COMMENT` even with `--approve`, as when §Fetch could not anchor the checkout.

## review.json

Written by §Build; edit it by hand only in `--mode manual`.

```json
{
  "commit_id": "<pr.json headRefOid>",
  "event": "REQUEST_CHANGES | COMMENT | APPROVE",
  "body": "<markdown>",
  "comments": [
    { "path": "src/a.ts", "line": 45, "side": "RIGHT", "body": "..." },
    { "path": "src/b.ts", "start_line": 40, "start_side": "RIGHT", "line": 45, "side": "RIGHT", "body": "..." }
  ]
}
```

`event` follows the judge table; `--approve` is the only way an automated run posts `APPROVE`, and in `--mode manual` `event` is edited by hand. Self-review: when `VIEWER` equals `pr.json` `author.login`, GitHub rejects APPROVE and REQUEST_CHANGES on the account's own pull request, so the payload must use `COMMENT` and open the body with `Intended verdict: <REQUEST_CHANGES | APPROVE> (posted as a comment: this account authored the PR)`. `review-results.json` keeps the true verdict.

## Post

```bash
gh api -X POST "repos/$OWNER_REPO/pulls/$PR_NUMBER/reviews" --input "$REVIEW_DIR/review.json" > "$REVIEW_DIR/posted.json"
```

- 422 mentioning `own pull request`: rerun §Build with `--viewer` set to `pr.json` `author.login`, post once more.
- Any other 422: rerun §Build with `--body-only`, post once more.
- Second failure: save stderr to `post-error.txt`, add `Review not posted: <first line of the error>` to `recommendations` in `review-results.json`, report.
- `--mode manual`: stop before posting. Report `event`, the counts and the path to `review.json`, then wait. On the engineer's go-ahead, re-read `review.json` as they left it and post it with the command above, applying the same retries. A different verdict means editing `event` in that file.
- The worktree, when §Fetch created one: `git -C "$REPO_PATH" worktree remove --force "$REVIEW_DIR/head" 2>/dev/null; git -C "$REPO_PATH" worktree prune`. Posted or not, it goes.

## Aggregate

`find "$ARTIFACTS_BASE/pr" -path '*/review/review-results.json'`. Fewer than two: warn and exit. Otherwise run `.claude/skills/pr-reviewer/agents/cross-repo-aggregator.md` over them and their sibling `diff.patch` files, writing `$ARTIFACTS_BASE/pr/cross-repo-summary.json` and `.md`.
