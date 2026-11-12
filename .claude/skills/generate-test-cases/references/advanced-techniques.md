# Advanced Test Design Techniques

Situational techniques applied during Phase 3b. Each one fires only when its trigger condition
holds — read this file when at least one applies, and skip the techniques whose trigger does not
match the ticket.

These techniques produce **test cases a human or downstream tool will execute**. Three of them
overlap with dedicated skills that actively probe a running system. Each section below names its
escalation target — surface it to the user whenever the ticket needs verified runtime behavior
rather than documented cases, and do not stop at the inline cases in that situation.

## Contents

- [Cross-Endpoint Consistency](#cross-endpoint-consistency) — resource reachable via multiple endpoints
- [Security Test Generation](#security-test-generation) — authentication, authorization, or user data
- [Accessibility Test Generation](#accessibility-test-generation) — UI components, forms, modals
- [Performance Test Generation](#performance-test-generation) — SLA, throughput, lists, or data at scale

---

## Cross-Endpoint Consistency

**Trigger**: the feature creates or modifies a resource reachable via multiple endpoints (create,
read-by-id, list, search, related entities).

Verify:

1. Data written through one endpoint matches every read path.
2. Mutations are reflected immediately across all materialization points.
3. Deletions propagate correctly so no endpoint returns a ghost record.
4. Expected side effects on adjacent resources are observable from their own endpoints.

Generate one case per distinct read path.

**Escalate to** `/api-contract-testing` when the resource has an OpenAPI/Swagger spec — it validates every read path against the schema automatically and detects breaking changes between spec versions.

---

## Security Test Generation

**Trigger**: the feature involves authentication, authorization, or user data.

Generate:

1. Request with missing, expired, or structurally invalid auth token → expect 401 or 403, never
   200 or 500.
2. Valid auth token scoped to a different user attempting to access the target resource → expect
   403 or 404 (IDOR probe).
3. Response body audit — sensitive fields (passwords, raw tokens, internal DB IDs, stack traces)
   must not appear in any response.
4. Error responses must not leak file paths, DB schema, or framework version strings.
5. User-controlled string fields submitted with `<script>alert(1)</script>` or a SQL fragment →
   must be rejected or returned escaped, never reflected or executed.

Tag cases with `type: "security"`.

**Escalate to** `/owasp-security-testing` when a running target is available — it executes active
OWASP Top 10 probes (IDOR, injection, auth bypass, brute force) against the live app instead of
documenting cases. Use `/security-review` instead for static analysis of the source and dependencies.

---

## Accessibility Test Generation

**Trigger**: the feature introduces or modifies UI components, forms, modals, or interactive
elements.

Generate:

1. All images and icons have meaningful alt text or `aria-hidden`.
2. All interactive elements are keyboard reachable and operable without a mouse.
3. Form fields have visible, associated labels (not placeholder-only).
4. Error messages are linked to their fields via `aria-describedby`.
5. Modal dialogs trap focus and return it to the trigger on close.
6. Color is not the sole means of conveying information.

Tag cases with `type: "accessibility"`.

**Escalate to** `/accessibility-testing` for executable coverage — it generates axe-core + Playwright
tests for WCAG 2.1 A/AA, keyboard navigation, ARIA correctness, and focus management.

---

## Performance Test Generation

**Trigger**: the ticket mentions SLA, response time, or throughput targets, or the feature handles
lists, search, bulk operations, or data at scale.

Generate:

1. Page or endpoint responds within the stated SLA under normal conditions.
2. List and search endpoints paginate correctly and do not degrade with large datasets.
3. Bulk or batch operations complete within an acceptable time window.
4. The feature remains responsive under the expected concurrent-user load.

Tag cases with `type: "performance"`.

**Suggest** `/performance-testing` to the engineer when the ticket states an SLA or throughput
target — it generates runnable k6 or Artillery scripts with embedded thresholds, baseline
comparison, and CI integration. Do not invoke it automatically: it sends real load traffic to
`--target` and requires the engineer to confirm authorization at its own Phase 0 gate, so the
engineer must run it themselves.
