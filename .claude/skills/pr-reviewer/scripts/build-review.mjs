#!/usr/bin/env node
/**
 * Deterministic tail of the pr-reviewer pipeline: assembles review-results.json
 * from the judge's adjudication and the specialists' findings, verifies every
 * finding against the PR's changed files and builds the GitHub review payload
 * (review.json).
 *
 * The judge decides — which findings survive, at what severity, merged from
 * which duplicates — and writes only those rulings to adjudication.json. The
 * finding bodies stay in findings/<role>.json and are copied from there, so
 * the judge never re-emits them. The envelope (PR metadata, iteration,
 * timestamp) comes from pr.json and the review dir.
 *
 * The orchestrator passes only paths it derived itself. A PR-controlled `file`
 * is allowlisted against pr.json and read through `fs`, never through a shell.
 *
 * Pure Node builtins so it runs in any user project where Node is present.
 *
 * Usage: node build-review.mjs --review-dir <dir> [--repo <path>] [--repo-path <path>] [--jira-key <key>] [--viewer <login>] [--body-only] [--approve] [--quick]
 *
 * `--repo` is the tree the findings are verified against (the PR head);
 * `--repo-path` is the checkout recorded as `repository.path` and defaults to
 * `--repo`. `--jira-key` defaults to `pr-<number>`.
 *
 * A clean PR is posted as a COMMENT that states the intended approval unless
 * `--approve` is given: an unattended run never submits a formal approval on
 * its own.
 *
 * With `--quick` (the pr-reviewer run skipped its judge), or when no
 * specialist filed a finding, adjudication.json is not read and every filed
 * finding is kept as filed; otherwise a missing adjudication is fatal.
 *
 * Without `--repo` the checkout could not be anchored to the PR head: nothing
 * is read from disk, every finding is body-only, `nextSteps.action` is
 * MANUAL_REVIEW and the event is never APPROVE. The same holds when the
 * adjudication leaves specialist findings unaccounted for, and when the
 * findings that failed verification change the verdict: an empty
 * adjudication and a tree that drifted from the PR head both look like a
 * clean PR, so the run defers to a human.
 * Dropped findings are always listed in review-results.json and in the body.
 */
import { readdirSync, readFileSync, writeFileSync } from "node:fs";
import { join, resolve, sep } from "node:path";

const NIT_CAP = 5;

const MAX_ITERATIONS = 3;

const DEEP_SCAN_ID = "SEC-DEEP-SCAN";

const SEVERITIES = ["blocking", "major", "minor"];

const VERDICT = {
  CHANGES_REQUESTED: {
    action: "TRIGGER_FIX_ITERATION",
    event: "REQUEST_CHANGES",
  },
  COMMENTED: { action: "APPROVE", event: "COMMENT" },
  APPROVED: { action: "APPROVE", event: "APPROVE" },
};

function arg(flag) {
  const i = process.argv.indexOf(flag);
  return i >= 0 ? process.argv[i + 1] : undefined;
}

function fail(message) {
  console.error(`build-review: ${message}`);
  process.exit(1);
}

function readJson(path) {
  try {
    return JSON.parse(readFileSync(path, "utf-8"));
  } catch (error) {
    return fail(`cannot read ${path}: ${error.message}`);
  }
}

function readText(path) {
  try {
    return readFileSync(path, "utf-8");
  } catch {
    return "";
  }
}

/**
 * Every specialist finding keyed by id, read from findings/<role>.json. A
 * duplicate id is fatal: the judge's rulings would be ambiguous.
 */
function loadFindings(dir) {
  const folder = join(dir, "findings");
  let names;
  try {
    names = readdirSync(folder)
      .filter((n) => n.endsWith(".json"))
      .sort();
  } catch (error) {
    return fail(`cannot read ${folder}: ${error.message}`);
  }
  const byId = new Map();
  for (const name of names) {
    const list = readJson(join(folder, name));
    if (!Array.isArray(list))
      fail(`${join(folder, name)} must be a JSON array of findings`);
    for (const finding of list) {
      const id = String(finding.id);
      if (byId.has(id))
        fail(
          `finding id "${id}" appears in both ${byId.get(id).source} and ${name}`,
        );
      byId.set(id, { finding, source: name });
    }
  }
  return byId;
}

/**
 * Owner and name from the PR URL (`https://HOST/OWNER/REPO/pull/N`).
 */
function repoRef(pr, path) {
  const m = /^https?:\/\/[^/]+\/([^/]+)\/([^/]+)\/pull\//.exec(pr.url ?? "");
  return { owner: m?.[1] ?? "", name: m?.[2] ?? "", path };
}

/**
 * One past the highest iteration-<N>.json in the review dir, or 1.
 */
function nextIteration(dir) {
  let max = 0;
  for (const name of readdirSync(dir)) {
    const m = /^iteration-(\d+)\.json$/.exec(name);
    if (m) max = Math.max(max, Number(m[1]));
  }
  return max + 1;
}

/**
 * Resolves the judge's rulings into full findings. A kept entry copies the
 * specialist's finding, takes the judge's severity, issue and details when
 * given, and gathers `references` from the duplicates merged into it. Ids the
 * judge did not rule on, ruled on twice, or that no specialist filed are
 * reported under recommendations rather than lost silently, and returned as
 * `lost` so the verdict defers to a human instead of reading an
 * under-delivering adjudication as a clean PR. SEC-DEEP-SCAN never becomes a
 * finding: it asks for the standalone security review.
 */
function adjudicate(rulings, sources, prUrl) {
  const seen = new Set();
  const unknown = [];
  const twice = [];
  const claim = (raw) => {
    const id = String(raw);
    if (!sources.has(id)) {
      unknown.push(id);
      return null;
    }
    if (seen.has(id)) {
      twice.push(id);
      return null;
    }
    seen.add(id);
    return sources.get(id).finding;
  };

  const findings = [];
  for (const kept of rulings.keep ?? []) {
    const base = claim(kept.id);
    if (!base || String(kept.id) === DEEP_SCAN_ID) continue;
    const merged = (kept.mergedFrom ?? []).map(claim).filter(Boolean);
    const finding = { ...base, references: [...(base.references ?? [])] };
    if (kept.severity !== undefined) finding.severity = kept.severity;
    if (typeof kept.issue === "string") finding.issue = kept.issue;
    if (typeof kept.details === "string") finding.details = kept.details;
    for (const m of merged) {
      for (const ref of m.references ?? [])
        if (!finding.references.includes(ref)) finding.references.push(ref);
    }
    findings.push(finding);
  }
  for (const dropped of rulings.drop ?? []) claim(dropped.id);

  const missed = [...sources.keys()].filter(
    (id) => !seen.has(id) && id !== DEEP_SCAN_ID,
  );
  const notes = [];
  if (sources.has(DEEP_SCAN_ID))
    notes.push(`Run /security-review --pr-url ${prUrl}`);
  if (unknown.length)
    notes.push(
      `${unknown.length} adjudicated ids match no specialist finding and were ignored: ${unknown.join(", ")}`,
    );
  if (twice.length)
    notes.push(
      `${twice.length} findings adjudicated more than once, the first ruling stands: ${twice.join(", ")}`,
    );
  if (missed.length)
    notes.push(
      `${missed.length} specialist findings the judge did not rule on were dropped: ${missed.join(", ")}`,
    );
  return { findings, notes, lost: [...missed, ...unknown, ...twice] };
}

/**
 * The review-results envelope from pr.json and the review dir, with the
 * judge's recommendations followed by the adjudication notes. Buckets,
 * counts, status and nextSteps are filled by recompute().
 */
function assemble(dir, pr, rulings, sources, jiraKey, repoPath) {
  const iteration = nextIteration(dir);
  const linesChanged = (pr.additions ?? 0) + (pr.deletions ?? 0);
  const { findings, notes, lost } = adjudicate(rulings, sources, pr.url);
  const results = {
    jiraKey: jiraKey ?? `pr-${pr.number}`,
    prUrl: pr.url,
    prNumber: pr.number,
    reviewIteration: iteration,
    timestamp: new Date().toISOString(),
    repository: repoRef(pr, repoPath),
    prMetadata: {
      commitSha: pr.headRefOid,
      baseRef: pr.baseRefName,
      headRef: pr.headRefName,
      linesChanged,
      filesChanged: pr.changedFiles ?? 0,
    },
    metrics: { filesReviewed: pr.changedFiles ?? 0, linesChanged },
    recommendations: [...(rulings.recommendations ?? []).map(String), ...notes],
    nextSteps: { maxIterations: MAX_ITERATIONS, currentIteration: iteration },
  };
  return { results, findings, lost };
}

/**
 * Whether the patch is a `git format-patch` series rather than one unified
 * diff. A series repeats every file once per commit that touched it, with
 * line numbers relative to that commit, so `diffLines` keeps only the last
 * occurrence and would anchor against the wrong lines. Produced by `gh pr
 * diff --patch`, which §Fetch must not pass; a series anchors nothing and
 * defers to a human rather than posting comments on lines it cannot trust.
 */
function isPatchSeries(patch) {
  return /^From [0-9a-f]{40} /m.test(patch);
}

/**
 * New-side line numbers each file exposes in the diff (added and context
 * lines), keyed by path. Only those lines accept an inline review comment.
 */
function diffLines(patch) {
  const out = new Map();
  let lines = null;
  let line = -1;
  for (const raw of patch.split("\n")) {
    const header = /^diff --git a\/.* b\/(.*)$/.exec(raw);
    if (header) {
      lines = new Set();
      out.set(header[1], lines);
      line = -1;
      continue;
    }
    const hunk = /^@@ -\d+(?:,\d+)? \+(\d+)/.exec(raw);
    if (hunk) {
      line = Number(hunk[1]);
      continue;
    }
    if (!lines || line < 0 || raw.startsWith("-") || raw.startsWith("\\"))
      continue;
    lines.add(line);
    line += 1;
  }
  return out;
}

/**
 * Lines of a file under `root`, or null when the path escapes the root or the
 * file cannot be read. Cached per path.
 */
function fileLines(cache, root, file) {
  if (cache.has(file)) return cache.get(file);
  const abs = resolve(root, file);
  let lines = null;
  if (abs.startsWith(root + sep)) {
    try {
      lines = readFileSync(abs, "utf-8").split("\n");
    } catch {
      lines = null;
    }
  }
  cache.set(file, lines);
  return lines;
}

function snippetHead(f) {
  return String(f.codeSnippet ?? "")
    .split("\n")[0]
    .trim();
}

function where(f) {
  return f.line === null || f.line === undefined
    ? f.file
    : `${f.file}:${f.line}`;
}

/**
 * Line of `lines` holding `want` closest to `line`, or null when no line
 * holds it. The cited line wins any tie, so a correct citation never moves.
 */
function nearestLine(lines, want, line) {
  let best = null;
  for (let i = 0; i < (lines?.length ?? 0); i += 1) {
    if (!lines[i].includes(want)) continue;
    if (best === null || Math.abs(i + 1 - line) < Math.abs(best - line)) {
      best = i + 1;
    }
  }
  return best;
}

/**
 * Keeps a finding when its file is in the PR and, given a repo to read and a
 * snippet to match, that snippet's first line is somewhere in the file,
 * re-anchoring `line` to the occurrence nearest the citation. Agents cite a
 * line they never opened, so an off-by-a-few citation is a misplaced comment
 * rather than a wrong finding; only a snippet absent from the whole file is
 * dropped. A finding re-anchored off the diff degrades to body-only, and a
 * finding without a snippet cannot be checked, so it too stays body-only.
 */
function verify(findings, files, root, cache) {
  return findings.filter((f) => {
    if (!files.has(f.file)) return false;
    const want = snippetHead(f);
    if (!root || f.line === null || f.line === undefined || !want) return true;
    const found = nearestLine(fileLines(cache, root, f.file), want, f.line);
    if (found !== null) f.line = found;
    return found !== null;
  });
}

function statusOf(findings) {
  if (findings.some((f) => f.severity !== "minor")) return "CHANGES_REQUESTED";
  return findings.length ? "COMMENTED" : "APPROVED";
}

/**
 * Why the survivors cannot stand as the verdict, or null when they can: no
 * checkout to read, specialist findings the adjudication did not account
 * for, findings that failed verification that would have changed the
 * verdict, or a diff no line can be anchored against. An empty adjudication
 * and a tree drifted from the PR head both look like a clean PR, so either
 * defers to a human.
 */
function unverifiedReason(root, produced, survivors, lost, seriesPatch) {
  if (!root) return "checkout not anchored to the PR head, findings unverified";
  if (seriesPatch) {
    return "diff.patch is a commit series, not a unified diff; inline anchors unreliable";
  }
  if (lost.length) {
    return `${lost.length} specialist findings unaccounted for in adjudication`;
  }
  if (statusOf(produced) !== statusOf(survivors)) {
    return `${produced.length - survivors.length} of ${produced.length} findings failed verification, changing the verdict`;
  }
  return null;
}

/**
 * Rewrites buckets, metrics, summary, status and nextSteps from the survivors.
 * `unverified` names why they cannot stand as the verdict; null when they can.
 */
function recompute(results, survivors, unverified) {
  const findings = { blocking: [], major: [], minor: [] };
  for (const f of survivors) findings[f.severity].push(f);
  const overflow = findings.minor.splice(NIT_CAP);
  if (overflow.length) {
    results.recommendations = [
      ...(results.recommendations ?? []),
      `plus ${overflow.length} additional minor observations not listed individually`,
    ];
  }
  const { blocking, major, minor } = findings;
  const status = statusOf(survivors);
  const summary = `${blocking.length} blocking, ${major.length} major, ${minor.length} minor`;
  results.findings = findings;
  results.summary = summary;
  results.overallStatus = status;
  results.metrics = {
    ...results.metrics,
    totalFindings: blocking.length + major.length + minor.length,
    blockingCount: blocking.length,
    majorCount: major.length,
    minorCount: minor.length,
  };
  results.nextSteps = {
    ...results.nextSteps,
    action: unverified ? "MANUAL_REVIEW" : VERDICT[status].action,
    reason: unverified
      ? `${summary}; ${unverified}`
      : `${summary} after verification`,
  };
  return status;
}

function bodyLine(f) {
  return `- **[${f.severity}] ${f.id}** \`${where(f)}\` — ${f.issue}. ${f.fixInstructions?.explanation ?? ""}`.trimEnd();
}

/**
 * One inline review comment for a finding, or null when it has no snippet or
 * its lines are not in the diff. Spans the snippet when every spanned line is
 * in the diff; carries a suggestion only when `oldCode` matches the commented
 * lines exactly.
 */
function inlineComment(f, diff, lines) {
  const inDiff = diff.get(f.file);
  if (!snippetHead(f) || !inDiff?.has(f.line)) return null;
  const span = String(f.codeSnippet ?? "").split("\n").length;
  const end = f.line + span - 1;
  const ranged =
    span > 1 &&
    Array.from({ length: span }, (_, i) => f.line + i).every((n) =>
      inDiff.has(n),
    );
  const last = ranged ? end : f.line;
  let body = `**[${f.severity}] ${f.id}: ${f.issue}**\n\n${f.details}\n\nFix: ${f.fixInstructions?.explanation ?? ""}`;
  const fix = f.fixInstructions ?? {};
  const commented = lines?.slice(f.line - 1, last).join("\n");
  if (
    fix.action === "replace" &&
    typeof fix.oldCode === "string" &&
    fix.oldCode === commented
  ) {
    body += `\n\n\`\`\`suggestion\n${fix.newCode ?? ""}\n\`\`\``;
  }
  const comment = { path: f.file, line: last, side: "RIGHT", body };
  if (ranged)
    Object.assign(comment, { start_line: f.line, start_side: "RIGHT" });
  return comment;
}

/**
 * Line that opens the review body when the posted event does not speak for
 * itself: a self-review, a run that needs manual review, or a clean PR posted
 * as a comment because `--approve` was not given. Null otherwise.
 */
function preamble(selfReview, trueEvent, event, nextSteps) {
  if (selfReview && trueEvent !== "COMMENT") {
    return `Intended verdict: ${trueEvent} (posted as a comment: this account authored the PR)`;
  }
  if (nextSteps.action === "MANUAL_REVIEW")
    return `Manual review required: ${nextSteps.reason}`;
  if (trueEvent === "APPROVE" && event === "COMMENT") {
    return "Intended verdict: APPROVE (posted as a comment: pass --approve for a formal approval)";
  }
  return null;
}

function main() {
  const dir = arg("--review-dir");
  if (!dir) fail("--review-dir is required");
  const repo = arg("--repo");
  const root = repo ? resolve(repo) : null;
  const viewer = arg("--viewer");
  const approve = process.argv.includes("--approve");

  const pr = readJson(join(dir, "pr.json"));
  const sources = loadFindings(dir);
  const rulings =
    process.argv.includes("--quick") || sources.size === 0
      ? { keep: [...sources.keys()].map((id) => ({ id })), drop: [] }
      : readJson(join(dir, "adjudication.json"));
  const { results, findings: all, lost } = assemble(
    dir,
    pr,
    rulings,
    sources,
    arg("--jira-key"),
    arg("--repo-path") ?? repo ?? "",
  );
  const patch = readText(join(dir, "diff.patch"));
  const seriesPatch = isPatchSeries(patch);
  const diff = diffLines(patch);
  const bodyOnly =
    process.argv.includes("--body-only") || !root || seriesPatch;
  const existing = new Set(
    readText(join(dir, "existing-comments.txt")).split("\n").filter(Boolean),
  );
  const files = new Set((pr.files ?? []).map((f) => f.path));
  const cache = new Map();

  for (const f of all) {
    f.severity = String(f.severity).trim().toLowerCase();
    if (!SEVERITIES.includes(f.severity)) {
      fail(
        `unknown severity "${f.severity}" on ${f.id}; expected blocking, major or minor`,
      );
    }
  }
  const survivors = verify(all, files, root, cache);
  const dropped = all.filter((f) => !survivors.includes(f));
  if (dropped.length) {
    results.recommendations = [
      ...(results.recommendations ?? []),
      `${dropped.length} of ${all.length} findings dropped in verification (file not in the PR, or its snippet is gone from the file): ${dropped.map((f) => `${f.id} (${f.severity}) ${where(f)}`).join(", ")}`,
    ];
  }
  const unverified = unverifiedReason(root, all, survivors, lost, seriesPatch);
  const status = recompute(results, survivors, unverified);
  writeFileSync(
    join(dir, "review-results.json"),
    `${JSON.stringify(results, null, 2)}\n`,
  );
  const kept = SEVERITIES.flatMap((k) => results.findings[k]);

  const comments = [];
  const unanchored = [];
  const stillOpen = [];
  for (const f of kept) {
    if (existing.has(`${f.file}:${f.line}`)) {
      stillOpen.push(f);
      continue;
    }
    const comment = bodyOnly
      ? null
      : inlineComment(f, diff, fileLines(cache, root, f.file));
    if (comment) comments.push(comment);
    else unanchored.push(f);
  }

  const trueEvent = VERDICT[status].event;
  const selfReview = Boolean(viewer) && viewer === pr.author?.login;
  const formalApproval = approve && !unverified && !selfReview;
  const event =
    selfReview || (trueEvent === "APPROVE" && !formalApproval)
      ? "COMMENT"
      : trueEvent;
  const sections = [`## Review: ${event} — ${results.summary}`];
  const opening = preamble(selfReview, trueEvent, event, results.nextSteps);
  if (opening) sections.unshift(opening);
  if (unanchored.length)
    sections.push(
      ["### Not anchored to a diff line", ...unanchored.map(bodyLine)].join(
        "\n",
      ),
    );
  if (stillOpen.length)
    sections.push(["### Still open", ...stillOpen.map(bodyLine)].join("\n"));
  const recommendations = (results.recommendations ?? []).map((r) =>
    r.replace(/\s*\n\s*/g, " "),
  );
  if (recommendations.length) {
    sections.push(
      ["### Recommendations", ...recommendations.map((r) => `- ${r}`)].join(
        "\n",
      ),
    );
  }

  const review = {
    commit_id: pr.headRefOid,
    event,
    body: sections.join("\n\n"),
    comments,
  };
  writeFileSync(
    join(dir, "review.json"),
    `${JSON.stringify(review, null, 2)}\n`,
  );
  console.log(
    `event=${event} blocking=${results.metrics.blockingCount} major=${results.metrics.majorCount} minor=${results.metrics.minorCount} inline=${comments.length} body_only=${unanchored.length} still_open=${stillOpen.length} dropped=${dropped.length}`,
  );
}

main();
