# Qase Adapter

Publishes canonical test cases to **Qase** via MCP. Creates a suite named after the ticket, then bulk-creates all test cases.

## Requirements

- Qase MCP (`mcp__qase__*`) configured in `.mcp.json` with a valid project token.

## Flag syntax

```
--to-qase [PROJECT-CODE]
```

- If `PROJECT-CODE` is omitted, list projects via `mcp__qase__list_projects` and ask the user to pick one.
- Use `--suite-id <ID>` to add cases to an existing suite instead of creating a new one.
- Use `--format classic` (default) or `--format gherkin` for step style.

## MCP tools

- `mcp__qase__create_suite` — creates a suite named after the source ticket (e.g. `"PROJ-124 - Feature name"`).
- `mcp__qase__bulk_create_cases` — bulk-creates all canonical cases under that suite.

## Field mapping (canonical → Qase)

| Canonical | Qase field |
|-----------|------------|
| `title` | `title` |
| `preconditions` | `preconditions` |
| `postconditions` | `postconditions` |
| `priority: "high"` | `priority: 1` |
| `priority: "medium"` | `priority: 2` |
| `priority: "low"` | `priority: 3` |
| `type: "functional"` | `type: 1` |
| `type: "security"` | `type: 4` |
| `type: "usability"` | `type: 5` |
| `type: "performance"` | `type: 6` |
| `type: "accessibility"` | `type: 8` |
| `type: "compatibility"` | `type: 9` |
| `steps[].action` | `steps[].action` |
| `steps[].expected_result` | `steps[].expected_result` |
| `tags` | `tags` |

> If the saved `customizations` declare a priority scale outside `1-3`, map to the nearest valid Qase value and report the conflict in the success summary.

## Phase 4 progress announcements

- Before `mcp__qase__create_suite`: `⏳ Creating suite in Qase...`
- Before `mcp__qase__bulk_create_cases`: `⏳ Publishing test cases to Qase...` (do not specify a number).

## Success report

```
✅ Created N test cases
   Adapter: Qase
   Project: <CODE> | Suite: "<title>" (ID: <suite_id>)
   Created test cases with IDs <first>–<last>
```

## References

- [Qase API — Create cases in bulk](https://developers.qase.io/reference/create-cases-in-bulk)
