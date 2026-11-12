# Canonical ticket structure

The mental model for completeness checks. The rendered markdown output follows [`../templates/sdd-ticket-template.md`](../templates/sdd-ticket-template.md); this file is the field-level contract behind it.

## Contents

- Required fields
- Canonical JSON shape

## Required fields

Include, when applicable:

- title and user story (role, observable goal, business benefit)
- stakeholders
- success criteria and metrics (NFRs expressed as measurable behavioral outcomes)
- acceptance criteria with BDD scenarios (≥3, covering happy / edge / error)
- out of scope and future considerations
- edge cases and error scenarios (framed as observable behavior)
- input and data validation rules (framed as behavior)
- feature and product dependencies
- definition of done (product-acceptance only)
- UI testing note (Figma fidelity acceptance requirement, yes/no)
- references
- open questions & delegated decisions (when the PM delegated a decision to the developer, or headless mode left product fields unresolved)
- metadata: INVEST validated, BDD scenario count, priority, labels

## Canonical JSON shape

```json
{
  "id": "PROJ-123 or DRAFT-YYYYMMDD-HHMMSS",
  "source": "jira | linear | markdown | input",
  "title": "Concise ticket title",
  "userStory": {
    "role": "user persona",
    "goal": "desired capability — described as observable behavior",
    "benefit": "business value"
  },
  "stakeholders": [
    {
      "role": "Product Owner",
      "name": "Jane Doe",
      "responsibility": "Acceptance, prioritization"
    }
  ],
  "successCriteria": ["Measurable behavioral outcome 1", "Measurable behavioral outcome 2"],
  "metrics": "How success will be measured — NFRs expressed as measurable outcomes here",
  "acceptanceCriteria": [
    {
      "scenario": "Administrator exports full user list successfully",
      "given": "the user is logged in as an administrator",
      "and_given": ["there are 500 registered users in the system"],
      "when": "the administrator clicks Export CSV",
      "then": "a CSV file containing all 500 user records is downloaded",
      "and_then": []
    }
  ],
  "outOfScope": ["Behavior explicitly not included"],
  "futureConsiderations": "Behaviors that may be addressed in a follow-on increment",
  "edgeCases": [
    {
      "case": "Edge condition description",
      "behavior": "What the user observes — not how the system handles it internally"
    }
  ],
  "errorScenarios": [
    {
      "error": "Error condition",
      "userExperience": "What the user sees — message, redirect, or state change"
    }
  ],
  "validationRules": ["Validation rule expressed as behavior"],
  "dependencies": {
    "blocking": ["PROJ-122"],
    "related": ["PROJ-100 - Related feature"]
  },
  "definitionOfDone": {
    "productAcceptance": [
      "All acceptance criteria scenarios confirmed by stakeholders",
      "Edge cases and error paths validated by product owner"
    ]
  },
  "uiTestingNote": "Visual fidelity to Figma is / is not an acceptance requirement",
  "figmaUrl": "https://figma.com/...",
  "openQuestionsAndDelegatedDecisions": [
    {
      "field": "Topic or field name",
      "origin": "delegated | headless-assumption",
      "question": "The behavioral question posed to the PM",
      "optionsPresented": ["option A", "option B", "option C"],
      "recommended": "recommended answer",
      "evidence": "citation — wiki page, code fact, comment reference"
    }
  ],
  "references": ["Design mockups URL"],
  "metadata": {
    "createdAt": "2026-04-15T10:00:00Z",
    "investValidated": true,
    "bddScenarioCount": 5,
    "priority": "High",
    "labels": ["sdd", "authentication"]
  }
}
```
