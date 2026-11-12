# Xray for Jira Adapter

Creates Xray Test issues in Jira (requires the Xray plugin in the target project).

## Requirements

- Atlassian MCP configured in `.mcp.json`.
- Xray plugin installed and enabled in the target Jira project.

## Flag syntax

```
--to-xray
```

## MCP tool

- `mcp__claude_ai_Atlassian__createJiraIssue` with `issueTypeName: "Test"` and Xray custom fields populated.

## Field mapping (canonical → Xray / Jira)

| Canonical | Xray/Jira field |
|-----------|----------------|
| `title` | `summary` |
| `steps` (classic) | `customfield_xray_steps` (step-by-step structure) |
| `steps` (gherkin) | `customfield_xray_gherkin` (Gherkin scenario text) |
| `preconditions` | `customfield_xray_precondition` |
| `priority: "high"` | `priority.name: "High"` |
| `priority: "medium"` | `priority.name: "Medium"` |
| `priority: "low"` | `priority.name: "Low"` |
| `tags` | `labels` |

> Custom field IDs (`customfield_xray_*`) are project-specific. Resolve them at runtime via the Atlassian MCP `getJiraIssueTypeMetaWithFields` call against the `Test` issue type, or rely on the project's pre-configured field aliases.

## Phase 4 progress announcements

- Before the create-test loop: `⏳ Creating Xray test issues in Jira...`

## Success report

```
✅ Created N Xray test issues
   Adapter: Xray
   Created keys: <KEY-1>, <KEY-2>, ...
```

## References

- [Xray for Jira — Test issue type](https://docs.getxray.app/display/XRAY/Test)
