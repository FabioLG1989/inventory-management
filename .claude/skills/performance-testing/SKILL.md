---
name: performance-testing
version: 1.0.0
last-updated: 2026-06-10
description: >
  Load, stress, and soak testing for web applications and APIs. Generates k6 scripts (primary) or
  Artillery configs (fallback) for smoke, load, stress, spike, and soak scenarios. Establishes
  performance baselines, defines pass/fail thresholds, and integrates with CI pipelines.
  Use when asked to load test, performance test, stress test, or establish SLA thresholds.
  Triggers on: performance testing, load test, stress test, soak test, k6, artillery, locust,
  throughput, latency, SLA, p95, p99, VU, virtual users.
argument-hint: '--target <url> [--tool k6|artillery] [--scenario smoke|load|stress|soak|spike] [--vus <n>] [--duration <t>] [--dry-run]'
allowed-tools: Read, Write, Bash, Glob, Grep, Edit, Task
user-invocable: true
disable-model-invocation: true
---

# Performance Testing Skill

Generates executable performance test scripts, establishes measurable SLA thresholds, and produces CI-ready pipelines for any HTTP API or web application.

## Contents

- [Purpose](#purpose)
- [Prerequisites](#prerequisites)
- [Arguments](#arguments)
- [Tool Selection](#tool-selection)
- [Scenario Types](#scenario-types)
- [Default Thresholds](#default-thresholds)
- [Workflow](#workflow)
- [Canonical Script Structures](#canonical-script-structures)
- [Baseline Comparison](#baseline-comparison)
- [CI Integration](#ci-integration)
- [Error Handling](#error-handling)
- [Best Practices](#best-practices)
- [References](#references)

---

## Purpose

Automates the full performance testing lifecycle:

1. **Discovers testable endpoints and user journeys** — reads OpenAPI specs, crawls the target, or accepts an explicit endpoints file
2. **Generates scenario scripts** — produces k6 JavaScript or Artillery YAML files for every requested scenario type
3. **Establishes thresholds** — embeds pass/fail SLA criteria directly in scripts so CI can gate on them
4. **Runs and reports** — executes tests when the tool is available and produces a human-readable summary
5. **Detects regressions** — compares results against a stored baseline when provided

**Principle**: Scripts must be executable with a single command and zero file edits. All variable configuration (base URL, auth token, VU counts, duration) flows through environment variables. Credentials are never hardcoded.

---

## Prerequisites

- A running target application reachable at `--target <url>`
- **k6** installed (`k6` in PATH or listed in `package.json` devDependencies) — or **Artillery** (`artillery` in PATH or devDependencies) as fallback
- If neither tool is detected: the skill generates scripts and install instructions; it does not abort

**Optional**:
- OpenAPI/Swagger spec (auto-discovered at `/openapi.json`, `/swagger.json`, or `--spec <path>`)
- `--endpoints <file>` — JSON file listing endpoints to test
- `--baseline <file>` — previous k6 `summary.json` for regression comparison
- `--thresholds <file>` — custom thresholds JSON to override defaults

---

## Arguments

| Argument | Description | Default |
|----------|-------------|---------|
| `--target <url>` | Base URL of the application under test. **Required.** | — |
| `--tool k6\|artillery` | Testing tool to use. Auto-detected when absent. | Auto-detect |
| `--scenario <types>` | Comma-separated scenario types to generate. | `smoke,load` |
| `--vus <n>` | Peak virtual user count for load scenario. | `50` |
| `--duration <t>` | Hold duration in minutes for load/soak. | `10` |
| `--endpoints <file>` | JSON file listing endpoints (method, path, body schema). | Auto-discover |
| `--baseline <file>` | Previous k6 `summary.json` for regression detection. | None |
| `--thresholds <file>` | Custom thresholds JSON overriding defaults. | None |
| `--spec <path>` | Path or URL to OpenAPI spec (auto-discovered if absent). | Auto-discover |
| `--out <dir>` | Output directory for generated scripts. | `performance/` |
| `--dry-run` | Generate scripts only — Phase 3 never runs, so no load traffic is sent. Phase 1 still issues a few discovery requests to `--target`, so the Phase 0 gate still applies (its prompt says discovery-only). | Off |

---

## Tool Selection

**k6** is the primary tool. It offers native JS scripting, rich CLI output, built-in threshold enforcement, and first-class CI integration.

**Artillery** is the fallback for teams that already use it or need built-in Playwright integration for browser-level load testing.

Auto-detection order:

1. `--tool` flag — use exactly what is specified
2. `k6` present in `package.json` devDependencies → use k6
3. `k6` available in PATH → use k6
4. `artillery` present in `package.json` devDependencies → use Artillery
5. `artillery` available in PATH → use Artillery
6. Neither detected → generate k6 scripts, print install instructions, skip execution

Announce the selected tool as part of Phase 0, after the authorization gate is confirmed:

```
⚙  Tool: k6 (detected in PATH)
   Target: https://staging.example.com
   Scenarios: smoke, load
   Output: performance/
```

---

## Scenario Types

| Scenario | Purpose | Default Profile |
|----------|---------|----------------|
| `smoke` | Verify nothing is broken under minimal load | 1–3 VUs, 2 min |
| `load` | Validate normal expected traffic | Ramp to `--vus`, hold `--duration` min, ramp down |
| `stress` | Find the breaking point | Step-function: 25 → 50 → 100 → 200 → 400 VUs, 2 min each |
| `spike` | Validate sudden traffic surge handling | Rapid ramp to 10× normal VUs, 1 min hold, immediate drop |
| `soak` | Detect memory leaks and degradation over time | Moderate VUs (20% of peak), 60–240 min |

See [`references/scenario-profiles.md`](./references/scenario-profiles.md) for detailed parameter guidance and when to use each type.

---

## Default Thresholds

Applied to every generated script unless overridden with `--thresholds <file>`:

```javascript
thresholds: {
  http_req_duration: ['p(95)<500', 'p(99)<1000'],
  http_req_failed:   ['rate<0.01'],
  errors:            ['rate<0.01'],
  http_reqs:         ['rate><expectedRps>'],  // load and spike only, from the plan
}
// stress omits the thresholds block entirely; smoke and soak omit the http_reqs floor
```

**Interpretation:**
- `p(95)<500` — 95th percentile response time under 500 ms
- `p(99)<1000` — 99th percentile response time under 1 s
- `rate<0.01` — fewer than 1% of requests fail (`http_req_failed`), and fewer than 1% of `check()` assertions fail (`errors`)
- `rate><expectedRps>` — throughput floor, **derived by the planner** from VU count, requests per iteration and think time; never a fixed number. Emitted for `load` and `spike` only: at the defaults smoke runs at 1–3 VUs and soak at 20% of `--vus` with 2–3 s think time, so no floor is reachable there. k6 only — Artillery's `ensure` block carries no throughput key.

`stress.k6.js` carries **no** thresholds at all: it deliberately climbs past saturation, so any gate fails by design. Metrics are still collected for the report.

To override thresholds project-wide, create `performance/thresholds.json` and pass it via `--thresholds`:

```json
{
  "http_req_duration": ["p(95)<200", "p(99)<500"],
  "http_req_failed": ["rate<0.005"],
  "http_reqs": ["rate>200"]
}
```

---

## Workflow

**Agent invocation.** The phases below delegate to the files under `agents/`. Spawn each one with
`Task` when it is available. When it is not (Codex CLI has no `Task` tool), read the agent file and
follow it inline in the current turn — the inputs, outputs and ordering are identical either way.
Never skip an agent because `Task` is unavailable.

### Phase 0: Parse Arguments, Authorization Gate, and Announce Plan

Parse all arguments before doing anything else. Print usage if `--target` is missing.

```
Usage: /performance-testing
         --target <url>
         [--tool k6|artillery]
         [--scenario smoke|load|stress|soak|spike]
         [--vus <n>] [--duration <t>]
         [--endpoints <file>] [--baseline <file>]
         [--thresholds <file>] [--spec <path>] [--out <dir>] [--dry-run]
```

Before generating or running anything, obtain authorization to contact the resolved `--target`.
Under `--dry-run`, substitute "a few discovery requests (spec lookup, target crawl)" for "real,
sustained load traffic" in every prompt below — Phase 3 never runs under `--dry-run`, so only
Phase 1's discovery requests need authorizing.

**Detect the execution context by running this exact bash command and reading its literal output.
Do NOT infer either value from prior context — run the check.**

```bash
echo "QAF_ASK_USER_MCP_TOOL=${QAF_ASK_USER_MCP_TOOL:-UNSET}"
echo "STDIN_TTY=$([[ -t 0 ]] && echo yes || echo no)"
```

Route on both lines: non-`UNSET` → **MCP** block regardless of `STDIN_TTY`; `UNSET`+`yes` →
**interactive** block; `UNSET`+`no` → **headless abort** block, fail closed.

**When `QAF_ASK_USER_MCP_TOOL` is set** — route the gate through MCP so the confirmation is
recorded by the engineer's configured backend, not typed into a transcript:

```bash
if [[ -n "${QAF_ASK_USER_MCP_TOOL:-}" ]]; then
  PAYLOAD=$(MCP_SKILL=performance-testing MCP_PHASE=phase-0-authorization \
    bash "$MCP_AUQ_HOOKS/build-mcp-payload.sh")
  QUESTIONS_JSON='[{
    "question": "Send real, sustained load traffic to <resolved --target value>? Confirm you own this environment or are explicitly authorized to load-test it, and that it is NOT production (or you hold written approval for production load testing).",
    "header": "Authorization",
    "multiSelect": false,
    "options": [
      {"label": "No — abort", "description": "Do not send any traffic."},
      {"label": "Yes — I confirm both conditions", "description": "Authorized to load-test this target; non-production, or approved for production load testing."}
    ]
  }]'
  "$QAF_ASK_USER_MCP_TOOL" "$(jq --argjson q "$QUESTIONS_JSON" '.questions=$q' <<<"$PAYLOAD")"
fi
```

Proceed **only** on the explicit affirmative option. Any other answer, a timeout, or an MCP error
aborts — never treat a missing or unparseable response as consent.

**When `QAF_ASK_USER_MCP_TOOL` is unset and stdin is a terminal (`[[ -t 0 ]]`)** — fall back to
provider-native prompting:

```
⚠️  Performance Testing — Authorization Required

This skill sends real, sustained load traffic (potentially hundreds of virtual users) to the
target. Running it against production or a system you do not own or have explicit authorization
to load-test can degrade or take the service down for real users.

Target: <resolved --target value>

Confirm ALL of the following before proceeding:
  [ ] I own this target or have explicit authorization to load-test it
  [ ] This is NOT a production environment (or I hold written approval for production load testing)
  [ ] I understand this skill sends real, sustained HTTP traffic — not simulated requests

Type YES to continue, or anything else to abort.
```

If the user does not type `YES` (case-insensitive), stop immediately.

**When `QAF_ASK_USER_MCP_TOOL` is unset and stdin is NOT a terminal (`[[ ! -t 0 ]]`)** — fail
closed. There is no way to obtain an explicit, recorded authorization, so abort before any request
is sent:

```
✗ Performance Testing — Authorization Required, Cannot Confirm

This skill sends real HTTP requests to the target (discovery requests under --dry-run, sustained
load otherwise) and requires explicit authorization first. No terminal is attached to answer the
YES/abort prompt, and QAF_ASK_USER_MCP_TOOL is not configured to obtain authorization
programmatically.

Aborting — no traffic was sent. Run interactively, or configure QAF_ASK_USER_MCP_TOOL, to proceed.
```

Stop immediately.

On every path, an unconfirmed gate means: do not invoke any agent and do not send any request.

After confirmation, announce:

```
⚙  Tool: k6 (detected in PATH)
   Target: https://staging.example.com
   Scenarios: smoke, load
   Peak VUs: 50 | Hold: 10 min
   Output: performance/
```

### Phase 1: Endpoint Discovery (Planner Agent)

Invoke **`agents/planner.md`** to map testable endpoints and define critical user journeys.

The planner:
- Reads the OpenAPI spec if available (at `--spec`, `/openapi.json`, `/swagger.json`, or `<target>/docs`)
- Falls back to the `--endpoints` file if provided
- Falls back to crawling the target root for observable link structure
- Identifies critical paths: authentication flow, primary data read, primary data write, high-frequency endpoints
- Recommends VU counts and duration adjustments based on the number of distinct journeys

Output: a test plan JSON at `performance/.test-plan.json` (ephemeral, not committed).

Progress announcement:
```
⏳ Discovering endpoints and mapping user journeys...
✓ Discovered 3 critical user journeys across 8 endpoints
```

### Phase 2: Script Generation (Implementer Agent)

Invoke **`agents/implementer.md`** with the test plan.

The implementer:
- Generates one script file per requested scenario type under `--out` (default `performance/`)
- Embeds all journeys from the test plan in each script
- Parameterizes base URL and auth token via environment variables
- Applies thresholds from `--thresholds` file or defaults
- Generates `performance/README.md` with run instructions, environment variable reference, and results interpretation guide

Progress announcement:
```
⏳ Generating k6 scripts for: smoke, load...
✓ Generated: performance/smoke.k6.js
✓ Generated: performance/load.k6.js
✓ Generated: performance/README.md
```

### Phase 3: Estimate, Confirm, and Run

If `--dry-run` was passed, stop here — scripts were already written in Phase 2 and no traffic is
sent:

```
✓ Scripts generated in performance/. Skipping execution (--dry-run).
```

Otherwise, before running anything, sum the estimated wall-clock duration of the resolved
scenario list using the stage table in
[`agents/implementer.md`](./agents/implementer.md) ("Stage configurations per scenario"):

| Scenario | Formula | At defaults |
|----------|---------|--------------|
| smoke | 2 min, fixed | 2 min |
| load | 2 (ramp up) + `--duration` (hold) + 2 (ramp down) | 14 min |
| stress | 2 min × number of stages in `vuRecommendations.stress.stages` | 10 min |
| spike | 10 s + 1 min + 10 s, fixed | ~1.5 min |
| soak | 2 (ramp up) + `vuRecommendations.soak.durationMin` (hold) + 2 (ramp down) | 64 min (240-min release sign-off soak: 244 min) |

Print the total, e.g.:

```
⏱  Estimated run time: smoke (2m) + load (14m) = 16 min
```

Require an explicit confirmation — through the same `QAF_ASK_USER_MCP_TOOL` gate or typed-`YES`
fallback used in Phase 0 — whenever the estimated total exceeds 15 minutes, or the resolved
scenario list includes `stress`, `spike`, or `soak`. This confirmation is required even when Phase
0 was already confirmed, because the concrete scenario list and total were not known until now.
Any other answer, a timeout, or an MCP error aborts before a single request is sent.

If the selected tool is available in PATH and the run was confirmed (or did not require
confirmation):

```
⏳ Running smoke test (estimated: 2 min)...
```

Execute each scenario in order from fastest to slowest: smoke → load → stress → spike → soak.

After each run:
- Print the k6/Artillery summary inline
- If `--baseline` was provided, run baseline comparison (see [Baseline Comparison](#baseline-comparison))
- k6 writes results JSON via `--summary-export` to `performance/results/<scenario>-summary.json` (Artillery via `--output` to the same path)

If the tool is not available:
```
⚠  k6 not found in PATH. Scripts generated but not executed.
   Install: https://grafana.com/docs/k6/latest/set-up/install-k6/
   Run manually: BASE_URL=https://staging.example.com k6 run --summary-export=performance/results/smoke-summary.json performance/smoke.k6.js
```

Final summary:

```
✅ Performance test complete
   Scenarios run: smoke, load
   Smoke:  p95=142ms  p99=287ms  errors=0.0%  rps=12
   Load:   p95=318ms  p99=610ms  errors=0.2%  rps=94
   Thresholds: ALL PASSED
   Results: performance/results/
```

---

## Canonical Script Structures

See [`references/canonical-script-structures.md`](./references/canonical-script-structures.md) for the full k6 and Artillery script templates and their key conventions.

---

## Baseline Comparison

When `--baseline <file>` is provided, Phase 3 loads the previous `<scenario>-summary.json` (produced by `--summary-export`) and compares:

| Metric | Warning threshold | Failure threshold |
|--------|------------------|-------------------|
| p95 response time | >10% worse | >25% worse |
| p99 response time | >10% worse | >25% worse |
| Error rate | >10% worse | >25% worse |
| Throughput (rps) | >10% lower | >25% lower |

Report format after each run:

```
📊 Baseline comparison (vs performance/results/baseline.json)
   p95:        318ms → 342ms  (+7.5%)  ✓ within threshold
   p99:        610ms → 820ms  (+34.4%) ✗ REGRESSION — exceeds 25% limit
   Error rate: 0.2%  → 0.2%   (0.0%)   ✓ no change
   Throughput: 94rps → 91rps  (-3.2%)  ✓ within threshold
```

The exit code is non-zero when any failure threshold is exceeded, enabling CI gates.

To update the baseline after a validated improvement:
```bash
cp performance/results/load-summary.json performance/results/baseline.json
```

---

## CI Integration

### GitHub Actions — k6

```yaml
- name: Run k6 load test
  uses: grafana/k6-action@v0.3.0
  with:
    filename: performance/load.k6.js
    flags: --summary-export=performance/results/load-summary.json
  env:
    BASE_URL: ${{ secrets.STAGING_URL }}
    AUTH_TOKEN: ${{ secrets.TEST_USER_TOKEN }}
```

Add `grafana/k6-action` to a `performance` job that runs after deployment to staging. Gate the job on the `deploy-staging` job completing successfully.

### GitHub Actions — Artillery

```yaml
- name: Run Artillery load test
  run: npx artillery run performance/load.artillery.yml --output performance/results/load-${{ github.run_id }}.json
  env:
    BASE_URL: ${{ secrets.STAGING_URL }}
    AUTH_TOKEN: ${{ secrets.TEST_USER_TOKEN }}

- name: Generate Artillery report
  run: npx artillery report performance/results/load-${{ github.run_id }}.json
```

### Baseline gating

```yaml
- name: Compare against baseline
  run: |
    node performance/compare-baseline.js \
      --current performance/results/load-${{ github.run_id }}.json \
      --baseline performance/results/baseline.json
```

The `compare-baseline.js` script is generated by the implementer agent when `--baseline` is provided at skill invocation time.

---

## Error Handling

| Error | Message |
|-------|---------|
| Missing `--target` | `❌ --target <url> is required. Specify the base URL of the application to test.` |
| Target unreachable | `❌ Cannot reach <url>. Verify the application is running and the URL is correct.` |
| No endpoints found | `⚠  No endpoints discovered. Pass --endpoints <file> or --spec <path> to specify them manually.` |
| Tool not in PATH | `⚠  <tool> not found. Scripts generated. Install: <url>` |
| Baseline file missing | `❌ Baseline file <path> not found. Run without --baseline first to generate results.` |
| Threshold exceeded | `✗ THRESHOLD EXCEEDED: <metric> <actual> exceeds limit <limit>. Exit code: 1.` |

---

## Best Practices

- **Smoke before load** — always run smoke first to confirm the target is healthy before applying load
- **Environment variables for everything** — base URL, auth token, dataset size; zero hardcoded values in scripts
- **Realistic think time** — always include `sleep()` between requests; absence of think time produces unrealistic saturation; see [`references/scenario-profiles.md`](./references/scenario-profiles.md) for per-scenario guidance
- **Authenticated endpoints** — acquire tokens in the k6 `setup()` function and pass them to `default()` via the returned object; never hardcode tokens
- **Isolate test data** — use a dedicated test user or a seeded dataset that does not interfere with production records
- **Commit baselines** — commit `performance/results/baseline.json` after a validated release so regressions are caught automatically
- **Soak tests in separate pipelines** — soak tests run for 60–240 min; gate them on a scheduled workflow, not on every PR
- **Check for N+1 patterns** — a rising p99 under moderate constant load (not spike) often indicates an N+1 query; see [`references/scenario-profiles.md`](./references/scenario-profiles.md) for detection guidance

---

## Integration with Other Skills

- After **`/implement-ticket`** — run smoke and load tests before merging to confirm no performance regression
- Pairs with **`/generate-test-cases`** — add `type: performance` test cases citing specific thresholds from the generated scripts
- Pairs with **`/api-contract-testing`** — share the endpoint list; contract tests verify shape, performance tests verify timing

---

## References

- **Planner agent**: [`agents/planner.md`](./agents/planner.md)
- **Implementer agent**: [`agents/implementer.md`](./agents/implementer.md)
- **Scenario profiles**: [`references/scenario-profiles.md`](./references/scenario-profiles.md)
- **Canonical script structures**: [`references/canonical-script-structures.md`](./references/canonical-script-structures.md)
- **k6 docs**: https://grafana.com/docs/k6/latest/
- **Artillery docs**: https://www.artillery.io/docs
- **k6 GitHub Action**: https://github.com/grafana/k6-action
