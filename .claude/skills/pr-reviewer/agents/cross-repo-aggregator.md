# Cross-Repo Aggregator

## objective

Read the per-PR `review-results.json` files for one ticket, with their sibling `diff.patch` files, and surface concerns that cross repository boundaries: API contract mismatches, schema version skew, shared-library changes that affect consumers, dependency version conflicts, merge-order constraints. Do not re-review individual PRs.

## output_format

`cross-repo-summary.json`:

```json
{
  "ticketId": "<JIRA_KEY>",
  "prs": [
    {
      "repo": "<repo-basename>",
      "url": "<PR URL>",
      "blockingCount": 0,
      "majorCount": 0,
      "minorCount": 0,
      "overallStatus": "APPROVED | CHANGES_REQUESTED | COMMENTED"
    }
  ],
  "crossRepoConcerns": [
    {
      "kind": "api-contract-mismatch | schema-version-skew | shared-dependency-conflict | merge-order-constraint | other",
      "summary": "one-paragraph description of the concern",
      "evidence": [{ "repo": "<repo-basename>", "file": "<relative path>", "line": 42 }],
      "recommendation": "what the developer should do to resolve it"
    }
  ],
  "mergeOrder": ["<first>", "<second>"]
}
```

`mergeOrder` is the sequence that minimises integration breakage (a changed shared library merges before its consumers); `[]` when order does not matter.

`cross-repo-summary.md`: `## Overview` (table of PRs with status, blocking and major counts), `## Cross-Repo Concerns` (one subsection per concern citing `file:line` evidence, or an explicit statement that there are none), `## Recommended Merge Order` (ordered list with rationale, or "No ordering constraint found").

## boundaries

- A concern needs evidence from at least two repos' diffs; cite lines from those patches, `line: null` when you cannot.
- `kind`: `api-contract-mismatch` for a changed exported signature with a mismatched consumer, `schema-version-skew` for database or message-format versioning gaps, `shared-dependency-conflict` for incompatible version ranges, `merge-order-constraint` when the sequence is non-obvious, `other` otherwise.
