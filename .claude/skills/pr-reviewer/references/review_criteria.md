# Review Criteria Rubric

Binary rubric for every specialist and the coordinator. Each finding passes the three lists below; the coordinator enforces "Never flag" as a hard filter.

## Severity Definitions

- **blocking** — must be fixed before merge: real bug, security vulnerability, broken contract, data-loss risk, failing test.
- **major** — should be fixed before merge: missing test for a new public API, uncaught error path on an external boundary, evidenced performance regression, unguarded external input.
- **minor** — optional improvement.

## Always Flag

| Issue | Minimum severity |
|---|---|
| SQL injection (string concatenation in a query) | blocking |
| Command injection (unescaped user input in shell exec) | blocking |
| Path traversal (user-controlled file path without sanitisation) | blocking |
| Hardcoded credential, API key, or secret | blocking |
| Authentication bypass (new endpoint without auth check) | blocking |
| Crash in a normal execution path (unhandled exception, null dereference) | blocking |
| Test suite invocation that fails on the diff as-is | blocking |
| Broken exported contract (changed function signature with no caller update) | blocking |
| Missing test for a new exported public API | major |
| Missing error handler on a network or database call in a public function | major |
| N+1 database query with concrete evidence in the diff | major |
| New dependency pinned to a version with a known CVE (cite the CVE) | major |
| Module or file placed where the build or test runner cannot discover it | major |

## Conditionally Flag

Only with concrete evidence in the diff; never speculate.

| Issue | Severity | Required evidence |
|---|---|---|
| Off-by-one error | major or blocking | Quote the lines; explain the incorrect boundary |
| Missing null guard | major | Show the value can be null at the call site |
| Performance regression | major | Quote the loop plus I/O call; estimate request-time impact |
| Readability that affects correctness | minor | Explain how the unclear name leads a caller to misuse the API |
| Convention violation | minor or major | Cite where the convention is established (wiki page or adjacent file) |
| Missing edge-case test | minor | Name the case; explain why it is reachable |
| Logging of sensitive data | minor | Quote the log statement; identify the sensitive field |

## Never Flag

- Style already enforced by the project linter
- Formatting (indentation, trailing whitespace, import order)
- Naming preferences that are not established project conventions
- Pre-existing issues in code this PR did not touch
- Speculative performance concerns without evidence in the diff
- "Could be cleaner" observations with no correctness impact
- A different language feature when the current one is correct
- Missing comments or docs on internal helpers (only exported public API)
- Commit message or PR description quality
- Test coverage for unchanged code paths

## Nit Cap

`findings.minor` holds at most **5** entries, the most impactful by affected surface (public API > service boundary > internal helper); `build-review.mjs` applies the cap in the judge's order. The excess becomes one `recommendations` string: "plus N additional minor observations not listed individually". Every `recommendations` entry is a single line covering one point; split multiple points into separate entries.

## Evidence

A finding cites a file this PR changed and a `codeSnippet` copied verbatim from the line it cites. Anchoring is the verifier's job — it re-reads every finding after you and drops what no longer matches — so never re-open a file to confirm a snippet is still there. Read files to establish that a defect is real, not to re-check a snippet. `references` holds only URLs quoted from this rubric or found in the repository, else `[]`.

## Finding schema

```typescript
interface Finding {
  id: string;                 // "<PREFIX>-001"
  category: string;
  severity: "blocking" | "major" | "minor";
  issue: string;              // one line
  file: string;               // relative to the repo root; never null
  line: number | null;        // null for file-level findings
  details: string;
  codeSnippet: string | null;
  fixInstructions: {
    action: "replace" | "add" | "delete" | "refactor";
    file: string;
    line?: number;
    insertAfterLine?: number; // omit rather than null
    oldCode?: string;
    newCode?: string;
    explanation: string;
  };
  testSuggestion: string | null;
  references: string[];
}
```
