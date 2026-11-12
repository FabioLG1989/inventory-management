<!--
Template sections (in order): User Story · Stakeholders · Success Criteria ·
Acceptance Criteria · Out of Scope · Edge Cases & Error Handling ·
Dependencies (if applicable) · Definition of Done · UI Testing (if applicable) ·
Open Questions & Delegated Decisions (if applicable) · References.
This comment is a scope-preview aid for partial reads; it does not render in the ticket.
-->

# [TICKET-ID]: [Concise Title]

## 📋 User Story

**As a** [user role/persona]
**I want** [goal/capability — described as observable behavior]
**So that** [business benefit/value]

---

## 👥 Stakeholders

| Role | Name | Responsibility |
|------|------|----------------|
| Requester | [Name] | Initial request, requirements validation |
| Product Owner | [Name] | Acceptance, prioritization |
| End Users | [Group/Role] | Primary beneficiaries |

---

## 🎯 Success Criteria

1. [Measurable behavioral outcome 1 — what users can observably do or see]
2. [Measurable behavioral outcome 2]
3. [Measurable behavioral outcome 3]

**Metrics** (if applicable): [How success will be measured — NFRs (latency, availability, security) are expressed here as measurable behavioral outcomes, e.g., "Search results appear within 500 ms" or "Unauthenticated users are redirected to login". Omit this line when there is no distinct metric beyond the success criteria above.]

---

## ✅ Acceptance Criteria

> BDD scenarios written in Gherkin. Each scenario covers exactly one behavior.
> Minimum coverage: one happy path + one edge case + one error/failure path.

### Scenario 1: [Business outcome — happy path]

```gherkin
Given [user or system state — in business language, no technical terms]
And [additional context if needed]
When [user action or system event — one action per When]
Then [observable outcome the user or stakeholder can verify]
And [additional observable outcome if needed]
```

### Scenario 2: [Business outcome — edge case]

```gherkin
Given [context]
When [action]
Then [outcome]
```

### Scenario 3: [Business outcome — error or failure path]

```gherkin
Given [context]
When [action]
Then [outcome — what the user sees or experiences, not the error code]
```

### Scenario 4: [Additional scenario if needed]

```gherkin
Given [context]
When [action]
Then [outcome]
```

---

## 🚫 Out of Scope

The following behaviors are explicitly NOT part of this increment:

1. [Behavior 1 — described as what the system will NOT do]
2. [Behavior 2]

**Future Considerations** (if applicable): [Behaviors that may be addressed in a follow-on increment. Omit this line when there are none.]

---

## ⚠️ Edge Cases & Error Handling

> Framed behaviorally: describe what the system DOES and what the user experiences — not how it is implemented.

### Edge Cases

1. **[Edge condition]**: [Expected system behavior — what the user observes]
2. **[Edge condition]**: [Expected system behavior]

### Error Scenarios

1. **[Error condition]**: [What the user sees / what the system does — no error codes or stack traces]
2. **[Error condition]**: [What the user sees / what the system does]

### Data & Input Validation (if applicable)

- [Validation rule expressed as behavior — e.g., "If the email field is empty, the form shows a required-field message and cannot be submitted". Omit this sub-section when the feature has no input to validate.]

---

## 📦 Dependencies (if applicable)

_Include this section only when the description or comments explicitly name a blocking or related ticket / product capability. Omit the whole section — heading included — when there are none._

### Blocking (must be complete before this ticket can start)

- [ ] [Feature, product capability, or ticket that must be ready first]

### Related

- [Ticket/initiative] — [Relationship description]

---

## 🎓 Definition of Done

> Product acceptance only — implementation quality gates belong to the executor.

- [ ] All acceptance criteria scenarios confirmed working by stakeholders
- [ ] Edge cases and error paths validated by the product owner
- [ ] Out-of-scope behaviors verified to not be present
- [ ] User-facing behavior matches the agreed acceptance criteria
- [ ] Stakeholders sign off on final implementation

---

## 🎨 UI Testing (if applicable)

**Visual fidelity to Figma**: [is / is not] an acceptance requirement for this ticket.

[If applicable — Figma URL: [link]]

---

## 📌 Open Questions & Delegated Decisions (if applicable)

> Decisions the PM delegated to the implementing developer, plus product-judgment fields left unresolved in headless mode. Never a silent decision — each item is resolved by the implementing agent's business-question wave before the plan is built. This section is the parseable contract `implement-ticket` consumes; keep the field labels verbatim.

- **[Topic/Field]** — *delegated* | *headless-assumption*
  - Question: [the behavioral question posed to the PM]
  - Options presented: [option A] · [option B] · [option C]
  - Recommended: [recommended answer] — Evidence: [citation]

---

## 🔗 References (if applicable)

- [Design mockups / Figma URL]
- [Related documentation]
- [External resources]

_Omit this whole section when there are no real links._

---

**Created**: [Date]
**Created By**: Claude (create-sdd-ticket skill)
**INVEST Validated**: [✅/❌]
**BDD Scenarios**: [Count]
**Priority**: [High/Medium/Low]
**Labels**: [label1, label2, label3]
