# TestRail Adapter

Publishes canonical test cases to **TestRail**.

## Requirements

- TestRail MCP configured in `.mcp.json` (preferred), OR
- Fallback: write a CSV file the user can import via TestRail's CSV import feature.

## Flag syntax

```
--to-testrail [PROJECT-ID]
```

## MCP tool (when available)

- TestRail MCP `create_case` (one call per canonical case, attached to the chosen section/suite).

## Field mapping (canonical → TestRail)

| Canonical | TestRail field |
|-----------|---------------|
| `title` | `title` |
| `preconditions` | `custom_preconds` |
| `steps[].action` | `custom_steps_separated[].content` |
| `steps[].expected_result` | `custom_steps_separated[].expected` |
| `priority: "high"` | `priority_id: 4` (Must Test) |
| `priority: "medium"` | `priority_id: 3` (Medium) |
| `priority: "low"` | `priority_id: 2` (Low Priority) |
| `type: "functional"` | `type_id: 2` (Functionality) |
| `type: "performance"` | `type_id: 6` (Other) * |
| `type: "accessibility"` | `type_id: 6` (Other) * |
| `type: "security"` | `type_id: 6` (Other) * |
| `type: "usability"` | `type_id: 6` (Other) * |
| `type: "compatibility"` | `type_id: 6` (Other) * |

> **\* Custom case types recommended.** TestRail does not include Accessibility, Security, Usability, or Compatibility as default case types. If your TestRail admin has created custom types for these categories (**Administration > Customizations > Case Types**), replace the `type_id: 6` values above with the corresponding custom IDs. When custom types are not configured, all four fall back to `Other (6)`.

## Phase 4 progress announcements

- Before the create loop (MCP): `⏳ Publishing test cases to TestRail...`
- Before fallback CSV write: `⏳ TestRail MCP not configured — writing CSV-importable file to <path>...`

## Fallback behavior

If no TestRail MCP is configured:

```
⚠️  TestRail MCP not configured in .mcp.json.
   Falling back to CSV export → ./testrail-import.csv
   You can import this file via TestRail's CSV import feature.
```

Generate a CSV file with columns matching TestRail's import format (`Title`, `Preconditions`, `Steps`, `Expected Result`, `Priority`, `Type`), then exit with the fallback note in the success report.

## References

- [TestRail API — Add Case](https://support.testrail.com/hc/en-us/articles/7077292642580)
