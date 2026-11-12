---
name: owasp-security-testing
version: 1.0.0
last-updated: 2026-06-10
description: >
  Generates and executes OWASP-aligned security test cases against a running web, API, or mobile application.
  Only invoke when the user explicitly mentions "owasp", "OWASP", or a specific OWASP category (e.g. "A01", "A03", "owasp top 10").
  Do NOT trigger for general security, auth, or injection mentions — use /security-review for those.
argument-hint: '--target <url|service> [--scope web|api|mobile|all] [--owasp <A01,A02,...>] [--to-qase <CODE>|--to-markdown <path>] [--dry-run]'
allowed-tools: Read, Write, Bash, Glob, Grep, Edit, Task
user-invocable: true
disable-model-invocation: true
---

# OWASP Security Testing Skill

Generates and executes OWASP-aligned security test cases against a running application by mapping its attack surface and producing concrete, independently-executable test cases covering the applicable OWASP Top 10 categories.

## Contents

- [Purpose](#purpose)
- [Prerequisites](#prerequisites)
- [Arguments](#arguments)
- [OWASP Top 10 Coverage](#owasp-top-10-coverage)
- [Workflow](#workflow)
- [Output Adapters](#output-adapters)
- [Platform-Specific Notes](#platform-specific-notes)
- [Error Handling](#error-handling)
- [References](#references)

---

## Purpose

### What This Skill Does

Probes a **running application** for exploitable runtime security vulnerabilities by:

1. Mapping the application's attack surface (endpoints, roles, input fields, auth mechanism)
2. Generating concrete test cases for each applicable OWASP Top 10 category
3. Publishing the test cases to a test management tool or a local markdown file

### Comparison with `/security-review`

| Dimension | `/owasp-security-testing` (this skill) | `/security-review` |
|-----------|----------------------------------------|--------------------|
| What it tests | Running application behavior | Source code and dependency graph |
| When to run | Against a non-production deployed environment (dev, staging) you are authorized to test | During a PR review before deployment |
| Finds | Auth bypass, IDOR, injection in live requests, session mismanagement | Hardcoded secrets, insecure code patterns, known CVEs in dependencies |
| Output | Executable test cases (QA test suite) | SARIF findings + triage report |
| Requires | Running target URL + credentials | Source repository access |
| Complements | A06 Vulnerable Components testing (defer to `/security-review`) | Runtime behavior verification |

These skills are complementary, not overlapping. Run `/security-review` on the PR, run `/owasp-security-testing` against the deployed build.

---

## Prerequisites

- A running application URL reachable from the machine running this skill
- Auth credentials for at least one test user account with standard permissions
- Auth credentials for a second test user account with equal permissions (required for IDOR testing)
- Auth credentials for an admin or elevated-role account when privilege escalation tests are in scope
- Any available API documentation: Swagger/OpenAPI spec URL or file path, Postman collection, or inline route list
- The application's known user roles and their intended access boundaries

If any prerequisite is absent, the skill announces what is missing and which OWASP categories will have reduced coverage as a result.

---

## Arguments

Parse flags from `$ARGUMENTS`:

- `--target <url|service>` — target base URL (`https://api.example.com`) or named service identifier; **required**
- `--scope web|api|mobile|all` — testing surface (default: auto-detect from target)
- `--owasp <A01,A02,...>` — comma-separated OWASP category codes to test (default: all applicable categories given the scope)
- `--to-qase <CODE>` — publish test cases to Qase project; loads `../generate-test-cases/adapters/qase.md`
- `--to-markdown <path>` — write test cases to a local markdown file; loads `../generate-test-cases/adapters/markdown.md`
- `--dry-run` — generate the attack surface map and test case descriptions only. Skips the Phase 0 authorization gate (nothing needs authorizing) and disables the live discovery probing fallback in Phase 1. No traffic is ever sent to the target. (default: off)

When `--target` is absent, print usage and stop:

```
Usage: /owasp-security-testing
         --target <url|service>
         [--scope web|api|mobile|all]
         [--owasp <A01,A02,...>]
         [--to-qase <CODE>] | [--to-markdown <path>]
         [--dry-run]
```

---

## OWASP Top 10 Coverage

| Category | What This Skill Tests | Defer to `/security-review` |
|----------|----------------------|------------------------------|
| A01 Broken Access Control | IDOR probes, forced browsing, missing authorization checks, privilege escalation requests, CORS misconfiguration via header probes | Static access control pattern review in source |
| A02 Cryptographic Failures | Sensitive data in response bodies and URLs, unencrypted cookie flags, weak TLS via redirect behavior | Hardcoded keys, weak algorithm invocations in source |
| A03 Injection | SQL injection via input fields, XSS stored/reflected probes, command injection in filename/path fields, NoSQL injection | Static sink tracing and data flow analysis in source |
| A04 Insecure Design | Rate limiting bypass attempts, workflow step skipping, business logic abuse (e.g., applying a discount twice) | Architectural design flaw review |
| A05 Security Misconfiguration | Security response headers, error message verbosity, unnecessary HTTP methods, default credentials | IaC misconfiguration, framework defaults in source |
| A06 Vulnerable Components | Not in scope — defer entirely | Dependency audit, CVE scan |
| A07 Auth & Session Management | Session fixation, token reuse after logout, brute-force threshold, concurrent session behavior, password complexity bypass | Hardcoded credentials, JWT misconfiguration in source |
| A08 Software & Data Integrity | Not in scope — defer entirely | Deserialization sinks, CI/CD integrity, SRI |
| A09 Logging & Monitoring Failures | Verifying sensitive actions produce audit responses (API-detectable), PII in log-reflected responses | Sensitive variable names in log calls in source |
| A10 SSRF | URL input fields sending server-side requests, webhook URL parameters, import-from-URL features | Static URL sink tracing |

---

## Workflow

**Agent invocation.** The phases below delegate to the files under `agents/`. Spawn each one with
`Task` when it is available. When it is not (Codex CLI has no `Task` tool), read the agent file and
follow it inline in the current turn — the inputs, outputs and ordering are identical either way.
Never skip an agent because `Task` is unavailable.

### Phase 0: Parse Arguments, Authorization Gate, and Announce

Parse all arguments.

If `--dry-run` was passed, skip straight to the summary block below — no attack traffic is ever
sent under `--dry-run`, so there is nothing to authorize.

Otherwise, before doing anything else, obtain authorization.

**Detect the execution context by running this exact bash command and reading its literal output.
Do NOT infer either value from prior context — run the check.**

```bash
echo "QAF_ASK_USER_MCP_TOOL=${QAF_ASK_USER_MCP_TOOL:-UNSET}"
echo "STDIN_TTY=$([[ -t 0 ]] && echo yes || echo no)"
```

Route on both lines of output:

- `QAF_ASK_USER_MCP_TOOL` non-empty (not `UNSET`) → **MCP** block, regardless of `STDIN_TTY`.
- `UNSET` and `STDIN_TTY=yes` → **interactive** block.
- `UNSET` and `STDIN_TTY=no` → **headless abort** block — fail closed. Live attack traffic never
  goes out without an explicit, recorded authorization.

**When `QAF_ASK_USER_MCP_TOOL` is set** — route the gate through MCP so the confirmation is
recorded by the engineer's configured backend, not typed into a transcript:

```bash
if [[ -n "${QAF_ASK_USER_MCP_TOOL:-}" ]]; then
  PAYLOAD=$(MCP_SKILL=owasp-security-testing MCP_PHASE=phase-0-authorization \
    bash "$MCP_AUQ_HOOKS/build-mcp-payload.sh")
  QUESTIONS_JSON='[{
    "question": "Authorize active security probing (SQLi, IDOR, brute-force, SSRF) against <resolved --target value>? Confirm you have explicit written authorization, the target is NOT production (or you have written prod-test approval), and test data is seeded.",
    "header": "Authorization",
    "multiSelect": false,
    "options": [
      {"label": "No — abort", "description": "Do not send any probe."},
      {"label": "Yes — I confirm all four conditions", "description": "Written authorization held; non-production or approved; seeded data; real HTTP requests understood."}
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
⚠️  OWASP Security Testing — Authorization Required

This skill sends active security probes (SQLi, IDOR, brute-force, SSRF) to the target.
Running against a production environment or a system you do not own or have explicit
written authorization to test is illegal and will cause real harm.

Target: <resolved --target value>

Confirm ALL of the following before proceeding:
  [ ] I have explicit written authorization to security-test this target
  [ ] This is NOT a production environment (or I have written prod-test approval)
  [ ] Test data is seeded — no real user data will be modified or exfiltrated
  [ ] I understand this skill sends real HTTP requests to the target

Type YES to continue, or anything else to abort.
```

If the user does not type `YES` (case-insensitive), stop immediately.

**When `QAF_ASK_USER_MCP_TOOL` is unset and stdin is NOT a terminal (`[[ ! -t 0 ]]`)** — fail
closed. There is no way to obtain an explicit, recorded authorization, so abort before any request
is sent:

```
✗ OWASP Security Testing — Authorization Required, Cannot Confirm

This skill sends live attack traffic (SQLi, IDOR, brute-force, SSRF) to the target and requires
explicit authorization before any request goes out. No terminal is attached to answer the
YES/abort prompt, and QAF_ASK_USER_MCP_TOOL is not configured to obtain authorization
programmatically.

Aborting — no traffic was sent.

To proceed, either:
  - Run this skill interactively so the authorization prompt can be answered, or
  - Configure QAF_ASK_USER_MCP_TOOL so authorization can be obtained programmatically, or
  - Pass --dry-run to generate the attack plan and test case descriptions without sending traffic.
```

Stop immediately.

On every path, an unconfirmed gate means: do not invoke any agent and do not send any request.

Print a summary after confirmation (or immediately, under `--dry-run`):

```
Target:  https://api.example.com
Scope:   api
OWASP:   A01, A02, A03, A05, A07, A10
Output:  Qase → project MYPROJ
```

Announce which categories are excluded and why (e.g., "A06 deferred to /security-review", "A04 skipped — no scope=web or scope=api flag detected").

### Phase 1: Attack Surface Discovery (Planner Agent)

Invoke `agents/planner.md` as a sub-agent. Pass:
- `--target` value
- `--scope` value (resolved or detected)
- Any API docs or Swagger URL provided
- `--dry-run` value (whether the flag was passed)

The planner produces a structured attack surface map (JSON) covering:
- All discovered endpoints with HTTP method and auth requirement
- Auth mechanism in use (cookie, JWT, OAuth, API key)
- Known user roles and their access boundaries
- Input surfaces: form fields, query params, path params, file upload endpoints, redirect/callback URL params
- Sensitivity classification per endpoint (public, user-scoped, admin-only)
- Applicable OWASP categories given what was discovered

Under `--dry-run`, the planner never sends live discovery probes to the target (see
[`agents/planner.md`](./agents/planner.md) "Attack Surface Discovery") — it relies only on
`framework-config.json` and any provided spec/docs, and reports discovery as incomplete when
neither is available.

Print a summary after the planner completes:

```
⏳ Mapping attack surface...
✓ Discovered 34 endpoints across 6 resource groups
  Auth:   JWT (Bearer)
  Roles:  guest, member, admin
  OWASP categories applicable: A01, A02, A03, A05, A07, A10
```

### Phase 2: Generate Security Test Cases (Implementer Agent)

Invoke `agents/implementer.md` as a sub-agent. Pass the attack surface map from Phase 1 and the filtered OWASP category list.

The implementer generates concrete test cases in the [canonical format](../generate-test-cases/SKILL.md#canonical-test-case-format) defined by the `generate-test-cases` skill. Every test case must have:
- `type: "security"`
- Tags including the OWASP category code (e.g., `"owasp-a01"`) and the affected resource group
- Specific preconditions naming exact user roles and required data
- Step-by-step HTTP actions with headers, method, URL, and body where relevant
- Observable expected result that does not require source code access to verify

Progress announcement:

```
⏳ Generating security test cases for A01 (Broken Access Control)...
⏳ Generating security test cases for A03 (Injection)...
...
✓ Generated security test cases across N OWASP categories
```

### Phase 3: Output via Adapter

This phase never sends traffic to `--target` — it only publishes the test case descriptions
generated in Phase 2, so it runs unchanged under `--dry-run`.

When `--to-qase <CODE>` is specified, load `../generate-test-cases/adapters/qase.md` and follow its Phase 4 instructions to publish all generated test cases.

When `--to-markdown <path>` is specified, load `../generate-test-cases/adapters/markdown.md` and write to the given path.

When neither flag is given, display a formatted inline summary of all generated test cases, grouped by OWASP category.

After publishing, emit the success report from the selected adapter.

---

## Output Adapters

This skill reuses the adapter files from `../generate-test-cases/adapters/` — there is no duplication of adapter logic here.

| Flag | Adapter file | Description |
|------|-------------|-------------|
| `--to-qase <CODE>` | [`../generate-test-cases/adapters/qase.md`](../generate-test-cases/adapters/qase.md) | Publishes to Qase via MCP |
| `--to-markdown <path>` | [`../generate-test-cases/adapters/markdown.md`](../generate-test-cases/adapters/markdown.md) | Writes to a local markdown file |

To add a new output destination, add the adapter file under `../generate-test-cases/adapters/` following the instructions in the `generate-test-cases` skill. No changes to this skill are required.

---

## Platform-Specific Notes

### Web (`--scope web`)

- Use Playwright-based test steps when the target is a browser-rendered UI
- Reference the project's Playwright config via `playwright.config.ts` or `playwright.config.js` for base URL and browser selection
- Test XSS via stored and reflected vectors through visible input fields (comments, profile names, search boxes)
- Test forced browsing by constructing URLs to resources belonging to other users rather than navigating through the UI
- Security headers are checked via a direct `GET` on the root URL and on authenticated pages

### API (`--scope api`)

- Use HTTP client test steps (curl-style: method, URL, headers, body, expected status)
- If a Swagger/OpenAPI spec is available, use it as the canonical endpoint list; supplement with crawled routes
- IDOR tests use path parameter substitution (replacing `/users/123/orders/456` with IDs from another authenticated user)
- Injection probes target JSON body fields, query string parameters, and path segments

### Mobile (`--scope mobile`)

- Auth flow tests use Appium or Detox steps referencing the mobile platform detected from the project config
- Token storage tests verify that tokens are not stored in plaintext in `SharedPreferences` (Android) or `NSUserDefaults` (iOS)
- Deep link parameter injection tests probe URL-scheme handlers for IDOR and injection vectors
- Certificate pinning bypass is noted as a manual prerequisite where detected; the skill generates test cases against the API layer directly

---

## Error Handling

| Condition | Behavior |
|-----------|----------|
| `--target` absent | Print usage and stop |
| Target URL unreachable | Announce failure, stop, prompt engineer to verify the target is running |
| Swagger/OpenAPI spec not found | Continue with crawled endpoints; note reduced coverage in Phase 0 summary |
| No second user account provided | Skip IDOR test cases; note in Phase 0 summary |
| No admin account provided | Skip privilege escalation cases; note in Phase 0 summary |
| OWASP code in `--owasp` not recognized | Print the unknown code and the valid range (A01–A10), then stop |
| Adapter MCP unavailable for `--to-qase` | Fall back to `--to-markdown` behavior using a generated path; announce the fallback |
| `--dry-run` passed with no `framework-config.json` or spec available | Planner skips live discovery probing; reports attack-surface discovery as incomplete in `coverage_gaps` instead of probing the target |

---

## References

- Canonical test case format: [`../generate-test-cases/SKILL.md#canonical-test-case-format`](../generate-test-cases/SKILL.md#canonical-test-case-format)
- Output adapters: [`../generate-test-cases/adapters/`](../generate-test-cases/adapters/)
- OWASP category quick reference: [`references/owasp-categories.md`](./references/owasp-categories.md)
- Attack surface planner agent: [`agents/planner.md`](./agents/planner.md)
- Test case generator agent: [`agents/implementer.md`](./agents/implementer.md)
- OWASP Top 10 2021 (the edition this skill's categories and links follow): https://owasp.org/Top10/
- OWASP Testing Guide v4.2: https://owasp.org/www-project-web-security-testing-guide/
