# BDD scenario authoring guide

How to write the Given-When-Then acceptance scenarios this skill produces. Consulted from Phase 6.

## Contents

- Scenario structure
- Scenario titles
- Content rules
- Coverage checklist

## Scenario structure

Each clause has a defined role. Write in business language throughout — no HTTP methods, status codes, class names, table names, or field identifiers.

**Given** — preconditions and system state.
- ✅ `Given the user is logged in as an administrator`
- ❌ `Given auth.isAdmin === true`
- ✅ `Given there are 500 registered users in the system`
- ❌ `Given User.count() returns 500`

**When** — the user action or system event that triggers the behavior. One action per When; two actions means two scenarios.
- ✅ `When the administrator clicks "Export CSV"`
- ❌ `When the administrator calls POST /api/v1/export`
- ✅ `When the session token expires`
- ❌ `When the JWT TTL field is past expiry`

**Then** — the observable outcome the user or a stakeholder can verify. Must be visible or measurable at the product level, never internal state.
- ✅ `Then a CSV file containing all 500 user records is downloaded`
- ❌ `Then status 200 is returned with Content-Type: text/csv`
- ✅ `Then the user sees a "Session expired" message and is redirected to the login page`
- ❌ `Then the session record is deleted from the sessions table`

**And** — chains additional Given, When, or Then clauses without repeating the keyword.

**But** — a negative Then clause ("the system does X, but NOT Y").
- ✅ `But no email notification is sent to the user`

## Scenario titles

State the business outcome, not a test identifier.
- ✅ `Scenario: Administrator exports full user list successfully`
- ❌ `Scenario: Test case 1` / `Scenario: Happy path`

## Content rules

- Business domain language — no HTTP methods, status codes, class names, table names, or field identifiers.
- Concrete values — `a user with the Admin role` not `a valid user`; `a report older than 90 days` not `an expired report`; `5 failed login attempts` not `too many attempts`.
- One behavior per scenario — a scenario that tests two behaviors is two scenarios.
- Atomic and independently executable — each scenario runs without depending on state set by another.
- State the WHAT, not the HOW — `Then the report is no longer visible` not `Then the record is soft-deleted in the database`.

## Coverage checklist

Minimum ≥3 scenarios: one happy path, one or more edge cases, one or more error/failure paths. Confirm before finalizing:

- [ ] Happy path: the primary use case with all conditions met
- [ ] Alternative success: a valid but non-primary path (optional field not filled, different role, pre-existing data)
- [ ] Boundary / edge case: a condition at the limit of the accepted range (empty list, single item, maximum allowed count)
- [ ] Invalid input: user provides missing or malformed data — what do they see?
- [ ] System failure: an external dependency or system resource is unavailable — what is the observable behavior?
- [ ] Permission / access control (if applicable): a user without the required role attempts the action

**Seeding rule:** every scenario must be seeded from a PM-confirmed Phase 3 answer. Sweep the confirmed answers for test-relevant behaviors; each confirmed edge or error behavior seeds at least one scenario. Never derive new product scope from comments — comments may inform recommended answers in Phase 3, but scenario content comes only from PM-confirmed fields. **Headless exception:** when running without a PM (`--skip-questions`, or the ask channel returned no usable answer), seed from the recommended answers instead, tag each such scenario `(assumed)`, and cross-list it under `## Open Questions & Delegated Decisions` — so the minimum coverage holds without presenting assumed scope as confirmed.
