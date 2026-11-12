# Canonical Bug Format

Tool-agnostic internal format produced by Phase 4. Every adapter consumes this; never write tool-specific fields before Phase 5.

**`title` always starts with `[BUG] `, followed by a platform/layer tag, then `Area | ...`** — e.g. `[BUG] [UI] Cart | Subtotal ignores quantity for a repeated item`. Every adapter's title/summary field inherits this since none of them rewrite `title`, so it needs setting only once, here in Phase 4.

**The platform/layer tag is derived from `test_reference.framework`** (or from context for `--from-text`/`--from-ticket`, where there's no framework to derive it from — infer it from the description, or ask if it's genuinely ambiguous):

| `test_reference.framework` | Tag |
|---|---|
| `Playwright` | `[UI]` |
| `Detox` / `Appium` | `[Mobile]` |
| `WebdriverIO` | `[UI]` |
| `Vitest` / `Jest` | `[BE]` |
| `null` (`--from-text`/`--from-ticket`) | Infer from context, or omit if truly unclear |

This is a default, framework-based heuristic, not a strict classification — a Vitest/Jest suite that's actually testing UI components (e.g. React Testing Library) is still front-end code even though it inherits `[BE]` by this table; override the tag when what the test actually exercises doesn't match its framework's usual role. The tag lets a reviewer tell platforms apart at a glance when the same defect is filed once per framework.

```json
{
  "title": "[BUG] [UI|Mobile|BE] Area | Broken behavior under condition",
  "severity": "blocker | critical | major | minor | trivial",
  "priority": "urgent | high | medium | low",
  "environment": {
    "app_version": "commit SHA, tag, or build number",
    "os": "e.g. macOS 15 / Ubuntu 22.04 — for a Detox or Appium candidate, the mobile OS/device instead (e.g. 'Android 14 (Pixel_7_API_34 emulator)'); for a Vitest/Jest unit-test candidate, the host OS isn't meaningful at all — use this field for the runtime instead, e.g. 'Node/jsdom unit test'",
    "browser": "e.g. Chrome 128 (null if not a browser bug — a Detox/Appium mobile E2E or a unit-test candidate)",
    "env": "local | staging | production",
    "service": "affected service/component name, if known"
  },
  "preconditions": "Exact system state before reproducing. Be specific.",
  "steps_to_reproduce": [
    { "step": 1, "action": "One atomic action" }
  ],
  "expected_result": "The correct behavior in plain terms, not just a bare value — state the rule, not only the number it produces",
  "actual_result": "What actually happened",
  "reproducibility": "always | intermittent | once",
  "regression": {
    "is_regression": "true | false | null (null when the worktree replay in Phase 2 could not run — see Error Handling)",
    "last_known_good": "commit SHA / tag / date, or null if not determined"
  },
  "suspected_area": ["service-or-component-name"],
  "evidence": [
    { "type": "screenshot | log | stack_trace | video | trace | test_report", "path": "relative or absolute path" }
  ],
  "test_reference": {
    "framework": "Playwright | WebdriverIO | Appium | Vitest | Jest | Detox | JUnit runner name | null (null for --from-text/--from-ticket, or a report shape this skill doesn't recognize)",
    "test_name": "full test name, describe/suite path included (e.g. Playwright's title, or Vitest/Jest's ancestorTitles + title) — or null",
    "file": "relative path to the test file, or null",
    "rerun_command": "the exact CLI command to run just this test locally — the same one used for Phase 2's confirmation re-run, verbatim — or null when there is no runnable test"
  },
  "linked_test_case": "test case ID/URL, or null",
  "linked_ticket": "ticket key, or null",
  "tags": ["feature-name", "service-name"]
}
```

**Severity vs. priority — never conflate them:**
- **Severity** = technical impact. `blocker`: system unusable / data loss. `critical`: core feature broken, no workaround. `major`: feature broken, workaround exists. `minor`: cosmetic or edge-case. `trivial`: typo-level.
- **Priority** = business urgency. `urgent`: fix before anything else ships. `high`: fix this sprint. `medium`: fix when convenient. `low`: backlog.

A `blocker`-severity bug can be `low` priority (e.g. a crash in a deprecated, unused feature) and a `trivial`-severity bug can be `urgent` priority (e.g. a typo in a customer-facing legal disclaimer).
