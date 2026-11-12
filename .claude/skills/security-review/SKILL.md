---
name: security-review
version: 2.0.0
last-updated: 2026-05-14
description: Performs hybrid SAST + LLM-adjudicator security analysis across all detected languages, emitting per-repo SARIF 2.1.0, structured JSON, and a human-readable report. User-invocable standalone against a PR URL or working tree, or in multi-repo mode with --repos.
argument-hint: '[--pr-url <URL>] [--jira-key <KEY>] [--artifacts-dir <abs>] [--repos <abs1>,<abs2>,...] [--baseline <path>] [--aggregate]'
allowed-tools: Bash, Read, Write, Glob, Grep
user-invocable: true
disable-model-invocation: false
---

# Security Review

Input: $ARGUMENTS

Parse flags from the input above:
- `--pr-url <URL>` — GitHub PR URL providing diff context for LLM triage
- `--jira-key <KEY>` — Jira ticket key used for artifact path namespacing
- `--artifacts-dir <abs>` — absolute dir to write output under (`<dir>/security/...`); parsed into `$ARTIFACTS_DIR_FLAG`. Passed by `/implement-ticket`. When omitted, falls back to the relative default — see Artifact Paths.
- `--repos <abs1>,<abs2>,...` — comma-separated absolute paths; each is scanned independently
- `--baseline <path>` — JSON findings file; only new fingerprints appear in output
- `--aggregate` — after per-repo scans, run cross-repo aggregator agent

When `--repos` is absent, treat the current workspace root as the single target.
When `--jira-key` is absent, derive a slug from the PR URL or use `adhoc-<date>`.

## Artifact Paths

Resolve the base once: use `--artifacts-dir` (`$ARTIFACTS_DIR_FLAG`, absolute, passed by `/implement-ticket`) when given, else the prior relative default. Per repo, derive the output dir and scanner dir (`$REPO_BASENAME` is empty in single-repo, the repo basename in multi-repo):

```bash
ARTIFACTS_BASE="${ARTIFACTS_DIR_FLAG:-.claude-temp/artifacts/${JIRA_KEY}}"
ARTIFACTS_DIR="$ARTIFACTS_BASE/security${REPO_BASENAME:+/$REPO_BASENAME}"
SCANNER_OUT="$ARTIFACTS_DIR/scanner-outputs"; mkdir -p "$SCANNER_OUT"
```

**Single-repo** (`$ARTIFACTS_DIR` = `$ARTIFACTS_BASE/security`):
```
$ARTIFACTS_BASE/security/
  sarif.json
  security-results.json
  security-report.md
  scanner-outputs/
```

**Multi-repo (one entry per repo, `$ARTIFACTS_DIR` = `$ARTIFACTS_BASE/security/<repo-basename>`):**
```
$ARTIFACTS_BASE/security/<repo-basename>/
  (same files)
```

**Cross-repo summary (only with --aggregate):**
```
$ARTIFACTS_BASE/security/cross-repo-summary.json
$ARTIFACTS_BASE/security/cross-repo-summary.md
```

## Stack Detection Table

| Language | Detection Markers | Scanners |
|---|---|---|
| Python | `pyproject.toml`, `requirements*.txt`, `Pipfile.lock`, `poetry.lock`, `uv.lock` | bandit, pip-audit, semgrep |
| JS/TS | `package.json`, `package-lock.json`, `pnpm-lock.yaml`, `yarn.lock` | npm/pnpm audit, eslint-plugin-security, semgrep |
| Go | `go.mod` | gosec, govulncheck, osv-scanner |
| Rust | `Cargo.toml` | cargo-audit, cargo-deny, clippy |
| Java | `pom.xml`, `build.gradle`, `build.gradle.kts` | spotbugs + findsecbugs, OWASP dep-check, semgrep |
| Ruby | `Gemfile`, `Gemfile.lock` | brakeman, bundle-audit |
| PHP | `composer.json` | psalm-security, composer audit |
| .NET | `*.csproj`, `packages.lock.json` | security-code-scan, dotnet list package --vulnerable |
| C/C++ | `CMakeLists.txt`, `Makefile`, `*.h`, `*.c` | cppcheck, flawfinder |
| IaC | `Dockerfile`, `*.tf`, `k8s/*.yaml` | trivy, checkov |
| Universal | always | gitleaks, trufflehog, semgrep |

When a language is detected but its scanner is not installed, emit a `scanner-missing` finding with the recommended install command. Never fall back to generic checks silently.

## Pipeline

Run this pipeline for each target repo. Runs are independent and may proceed in parallel when multiple repos are given. Before Step 1, set `$REPO_PATH`/`$REPO_BASENAME` for the repo and run the Artifact Paths snippet to define `$ARTIFACTS_DIR` and `$SCANNER_OUT` (always under the workspace-root base, never inside `$REPO_PATH`).

---

### Step 1 — Detect Stack

```bash
python3 ".claude/skills/030-quality-assurance/security-review/scripts/detect_stack.py" \
  --repo-path "$REPO_PATH" \
  --out-dir "$SCANNER_OUT" \
  --config-dir ".claude"
```

The script emits `$SCANNER_OUT/stack.json`:
```json
{ "languages": ["python", "typescript"], "lockfiles": ["pyproject.toml", "package-lock.json"] }
```

Read `framework-config.json` from `$REPO_PATH/.claude/framework-config.json` if it exists; prefer its `by_service` language map over the local detection result (Phase 1 analyzer is authoritative).

---

### Step 2 — Run Scanners (parallel, language-aware)

Run all applicable scanner scripts in parallel based on the detected language list.

**Secrets (always):**
```bash
bash ".claude/skills/030-quality-assurance/security-review/scripts/run_secrets.sh" \
  --repo-path "$REPO_PATH" \
  --out-dir "$SCANNER_OUT" \
  ${BASELINE:+--baseline "$BASELINE"}
```

**SAST (language-dispatched):**
```bash
python3 ".claude/skills/030-quality-assurance/security-review/scripts/run_sast.py" \
  --repo-path "$REPO_PATH" \
  --out-dir "$SCANNER_OUT" \
  --languages "$(jq -r '.languages | join(",")' "$SCANNER_OUT/stack.json")"
```

**Dependency audit:**
```bash
python3 ".claude/skills/030-quality-assurance/security-review/scripts/run_deps.py" \
  --repo-path "$REPO_PATH" \
  --out-dir "$SCANNER_OUT" \
  --languages "$(jq -r '.languages | join(",")' "$SCANNER_OUT/stack.json")"
```

**IaC (when Dockerfile/tf/k8s found):**
```bash
bash ".claude/skills/030-quality-assurance/security-review/scripts/run_iac.sh" \
  --repo-path "$REPO_PATH" \
  --out-dir "$SCANNER_OUT"
```

Each script writes SARIF 2.1.0 files under `$SCANNER_OUT/`. Execution continues even if an individual scanner exits non-zero; failures are captured as `scanner-missing` findings in the SARIF output.

---

### Step 3 — Consolidate SARIF

```bash
python3 ".claude/skills/030-quality-assurance/security-review/scripts/consolidate_sarif.py" \
  --sarif-dir "$SCANNER_OUT" \
  --out "$ARTIFACTS_DIR/sarif.json" \
  ${BASELINE:+--baseline "$BASELINE"}
```

This step:
- Merges all per-tool SARIF files into one SARIF 2.1.0 document
- Deduplicates by `fingerprints.primaryLocation`
- Applies suppressions: `# nosec`, `# noqa: S`, `// nosem`, `gitleaks:allow`, `.gitleaks.toml`, `.semgrepignore`
- When `--baseline` is provided, removes findings whose fingerprint already exists in the baseline; only new fingerprints remain

---

### Step 4 — LLM Triage (per-CWE specialist agents)

Normalize findings to the intermediate schema first:

```bash
python3 ".claude/skills/030-quality-assurance/security-review/scripts/normalize_findings.py" \
  --sarif "$ARTIFACTS_DIR/sarif.json" \
  --out "$ARTIFACTS_DIR/normalized-findings.json"
```

Group findings by OWASP category (use `tags` in SARIF `rule.properties`). For each non-empty group, invoke the corresponding specialist agent as a sub-agent:

| Group | Agent |
|---|---|
| Access Control / SSRF | `agents/triage-A01-broken-access.md` |
| Security Misconfiguration | `agents/triage-A02-config.md` |
| Supply Chain / Dependencies | `agents/triage-A03-supply-chain.md` |
| Cryptographic Failures | `agents/triage-A04-crypto.md` |
| Injection | `agents/triage-A05-injection.md` |
| Insecure Design | `agents/triage-A06-insecure-design.md` |
| Authentication Failures | `agents/triage-A07-authn.md` |
| Integrity Failures | `agents/triage-A08-integrity.md` |
| Logging / Monitoring | `agents/triage-A09-logging.md` |
| Unhandled Exceptions | `agents/triage-A10-exceptions.md` |
| Secrets | `agents/triage-secrets.md` |
| Deserialization | `agents/triage-deserialization.md` |

Each specialist agent receives:
- The relevant subset of `normalized-findings.json`
- The PR diff (when `--pr-url` provided): `Grep` the diff for the affected files
- Access to `Read`, `Grep` tools to verify cited `file:line` references

Each specialist returns a JSON array of triaged findings with `classification: "TP" | "FP" | "uncertain"` and a revised `severity`.

**LLM must not invent CVE IDs.** Only CVE IDs present in the scanner SARIF output may appear in the triage output. Any finding citing an ID absent from the SARIF input must be flagged as invalid and discarded.

Merge all specialist outputs into `$ARTIFACTS_DIR/triaged-findings.json`.

---

### Step 5 — Devil's Advocate Critic

Invoke `agents/devils-advocate-critic.md` only for findings with `severity: "HIGH"` or `severity: "CRITICAL"` in the triaged output.

The critic runs exactly one round. It receives the high-severity findings and must produce at least one alternate hypothesis per finding (e.g., "this route is protected by middleware not visible in the diff"). Findings the critic marks as `"verdict": "likely-FP"` are downgraded to `uncertain`; the final report notes the critic's reasoning.

---

### Step 6 — Fix Suggester

For all findings with `classification: "TP"` invoke `agents/fix-suggester.md`.

The fix suggester:
- Reads the relevant source file via `Read` to confirm the line still exists
- Emits a `suggestion` block (diff-style) when the fix is fewer than 6 lines
- Emits a `plan` block (prose steps) for larger refactors
- Never suggests a fix it cannot verify exists in the file

---

### Step 7 — Emit Outputs

**Normalize final findings to SecurityResults JSON:**

```bash
python3 ".claude/skills/030-quality-assurance/security-review/scripts/normalize_findings.py" \
  --triaged "$ARTIFACTS_DIR/triaged-findings.json" \
  --sarif "$ARTIFACTS_DIR/sarif.json" \
  --repo-path "$REPO_PATH" \
  --jira-key "$JIRA_KEY" \
  --out "$ARTIFACTS_DIR/security-results.json"
```

**Write human-readable report:**

Use the `Write` tool to produce `$ARTIFACTS_DIR/security-report.md` containing:
- Executive summary (counts by severity, overall status)
- Scanner versions table
- Per-finding sections with `file:line`, severity, classification, fix suggestion or plan
- OWASP compliance table
- Recommendations and next steps

**Validate SARIF (optional, non-blocking):**
```bash
npx @microsoft/sarif-multitool validate "$ARTIFACTS_DIR/sarif.json" 2>/dev/null || true
```

---

### Step 8 — Cross-Repo Aggregator (--aggregate only)

When `--aggregate` is set and more than one repo was scanned, invoke `agents/cross-repo-aggregator.md`. Resolve `$ARTIFACTS_BASE` (see Artifact Paths) — same base the per-repo scans used.

The aggregator reads all per-repo `security-results.json` files (under `$ARTIFACTS_BASE/security/*/`) and produces:
- `cross-repo-summary.json` — structured summary (schema below)
- `cross-repo-summary.md` — human-readable version

Both files are written to `$ARTIFACTS_BASE/security/`.

---

## SecurityResults JSON Schema

```typescript
interface SecurityResults {
  jiraKey: string;
  timestamp: string;                    // ISO 8601
  languages: string[];                  // detected languages
  overallStatus: 'PASS' | 'FAIL';
  summary: string;

  repository: {
    owner: string;                      // git remote owner or ""
    name: string;                       // repo basename
    path: string;                       // absolute path
  };

  sarifPath: string;                    // relative to artifact dir
  scannerVersions: { [tool: string]: string };

  findings: {
    blocking: SecurityFinding[];
    major: SecurityFinding[];
    minor: SecurityFinding[];
  };

  metrics: {
    totalFindings: number;
    blockingCount: number;
    majorCount: number;
    minorCount: number;
    secretsFound: number;
    filesScanned: number;
    linesScanned: number;
  };

  scannerResults: { [scannerName: string]: ScannerSummary };

  owaspCompliance: {
    [owaspCategory: string]: 'PASS' | 'WARN' | 'CRITICAL' | 'REVIEW';
  };

  recommendations: string[];

  nextSteps: {
    action: 'PASS' | 'TRIGGER_REVIEW_LOOP';
    reason: string;
    blockingIssueIds?: string[];
  };
}

interface SecurityFinding {
  id: string;
  ruleId: string;                       // SARIF ruleId
  cweId: string;                        // e.g. "CWE-89"
  category: string;                     // OWASP category
  severity: 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW' | 'NOTE';
  classification: 'TP' | 'FP' | 'uncertain';
  issue: string;
  file: string;
  line: number | null;
  details: string;
  codeSnippet: string | null;
  sarifFingerprint: string;
  fixInstructions: FixInstruction | null;
  testSuggestion: string | null;
  references: string[];
}

interface FixInstruction {
  action: 'replace' | 'add' | 'delete' | 'refactor';
  file: string;
  line?: number;
  insertAfterLine?: number;
  oldCode?: string;
  newCode?: string;
  explanation: string;
}

interface ScannerSummary {
  tool: string;
  version: string;
  issuesFound: number;
  scanCompleted: boolean;
  error?: string;
}
```

## Cross-Repo Summary Schema

```json
{
  "ticketId": "PROJ-123",
  "repos": [
    {
      "repo": "my-service",
      "path": "/abs/path",
      "blockingCount": 2,
      "majorCount": 4,
      "minorCount": 1,
      "overallStatus": "FAIL",
      "sarifPath": "<workspace-root>/.claude-temp/artifacts/PROJ-123/security/my-service/sarif.json"
    }
  ],
  "crossCuttingConcerns": [
    {
      "kind": "shared-dep-cve",
      "summary": "CVE-2024-1234 affects lodash in 3 repos",
      "evidence": ["repo-a/package.json", "repo-b/package.json"]
    }
  ],
  "dependencyOrder": ["shared-lib", "consumer-a", "consumer-b"]
}
```

## SARIF Emission Rules

- Level mapping: `CRITICAL` → `error`; `HIGH` → `error`; `MEDIUM` → `warning`; `LOW` → `note`
- Each result must have `fingerprints.primaryLocation` for baseline diff
- Suppressed findings must appear with `suppressions[].kind: "inSource"` and `state: "accepted"`
- Scanner tool metadata (name, version, informationUri) populates SARIF `tool.driver`
- SARIF version must be `"2.1.0"` with schema URI `https://json.schemastore.org/sarif-2.1.0.json`

## False-Positive Policy

1. Scanners produce candidates (ground truth source data)
2. LLM triage classifies each as TP / FP / uncertain using file-verified evidence
3. Devil's advocate critic challenges HIGH+ findings once
4. FP-classified findings are excluded from blocking/major counts but retained in the SARIF with `suppressions[].kind: "externalSuppression"`
5. `uncertain` findings appear in the report with a `REVIEW` tag but do not block the pipeline

## Failure Modes and Recovery

| Failure | Behaviour |
|---|---|
| Scanner binary missing | Emit `scanner-missing` finding listing `install:` command; continue |
| Scanner exits non-zero | Capture stderr in `scanner-outputs/<tool>.stderr`; continue |
| LLM triage agent times out | Mark all findings in the group as `uncertain`; continue |
| SARIF consolidation fails | Abort with non-zero exit; log to stderr |
| Baseline file not readable | Warn and continue without baseline diff |

## Installing Scanners

For a fresh machine, run once:
```bash
bash ".claude/skills/030-quality-assurance/security-review/scripts/install_scanners.sh"
```

This script is idempotent (safe to re-run) and uses `brew` on macOS or `apt` on Linux with `cargo install` fallbacks.

## References

- OWASP Top 10 2025: `references/owasp-top-10-2025.md`
- SARIF 2.1.0 spec: https://docs.oasis-open.org/sarif/sarif/v2.1.0/sarif-v2.1.0.html
- Semgrep rules registry: https://semgrep.dev/r
- OSV schema: https://ossf.github.io/osv-schema/
