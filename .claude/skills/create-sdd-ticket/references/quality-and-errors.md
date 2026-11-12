# Quality checklists and error handling

The final validation gate (Phase 7) and the standard failure responses. Consulted before finalizing and when an input, gap-resolution, INVEST, or output step fails.

## Contents

- Final quality checklist
- Error handling patterns

## Final quality checklist

### Completeness

- [ ] user story includes who, what (as observable behavior), and why
- [ ] all main product sections are present
- [ ] no `[NEEDS_CLARIFICATION]` or placeholder markers remain
- [ ] Open Questions & Delegated Decisions block present (in the parseable per-item format) if any product field was PM-delegated to the developer or unresolved in headless mode

### INVEST

- [ ] Independent — does not depend on another un-merged story
- [ ] Negotiable — scope confirmed with PM, not silently decided (headless: provisionally satisfied, recorded under Open Questions & Delegated Decisions)
- [ ] Valuable — user story states a clear business benefit
- [ ] Estimable — ≥3 BDD scenarios provide enough behavioral detail to size; acceptance criteria are unambiguous
- [ ] Small — PM confirmed one coherent, independently-valuable behavior increment, or a split recommendation was provided by user-facing capability (headless: provisionally satisfied, recorded under Open Questions & Delegated Decisions)
- [ ] Testable — every acceptance criterion has a Given-When-Then scenario

### BDD

- [ ] at least 3 scenarios exist
- [ ] all scenarios use Given-When-Then (and And/But where needed)
- [ ] scenarios use concrete examples and business language
- [ ] happy path, edge case, and error/failure path are all covered
- [ ] scenario titles state business outcomes, not test-case identifiers
- [ ] no HTTP methods, status codes, class names, or database terms in scenarios
- [ ] each scenario covers exactly one behavior (atomic)

### Product Clarity

- [ ] the whole ticket reads in plain, simple English for a non-technical reader — concise and concrete, no jargon, implementation terms, or filler
- [ ] no Technical Context, Architecture Decisions, or Implementation Notes present
- [ ] edge cases and error scenarios are framed as observable behavior ("what the user sees")
- [ ] out-of-scope behaviors are explicitly listed
- [ ] success criteria are measurable from the user's perspective
- [ ] NFRs (if any) appear as measurable behavioral outcomes in Success Criteria

## Error handling patterns

### Input source unavailable

Report which input could not be loaded and why: Jira ticket not found, markdown path missing or unreadable, empty plain-text description.

### Gap detection could not resolve all code facts

Summarize how many gaps were found, how many auto-resolved (code-verifiable facts), how many require PM confirmation (product judgment — these become Phase 3 questions), and which searches were attempted.

### INVEST validation failed

If the ticket is too large, do not silently continue. Provide the failure reason and a capability-based split recommendation.

```markdown
⚠️ INVEST Validation: Small criterion — PM review needed

This ticket appears to cover two distinct user-facing capabilities:
1. Searching users by name and email (user-facing search behavior)
2. Exporting filtered results to CSV (user-facing export behavior)

Recommendation: split into two tickets by capability, each independently valuable and shippable.
```

### Jira output unavailable

If Jira creation fails, recommend saving to the user-requested markdown path or, if none was provided, falling back to `.claude-temp/tickets/`.

```markdown
❌ Jira output unavailable

Fallback:
.claude-temp/tickets/DRAFT-20260415-143022/DRAFT-20260415-143022.md

Options:

1. Save to markdown now
2. Re-run later when Jira access is available
3. Copy the generated content into Jira manually
```
