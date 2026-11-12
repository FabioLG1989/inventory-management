# Jira Subtask Adapter

Creates each canonical test case as a **Subtask** under the source Jira ticket.

## Requirements

- Atlassian MCP configured in `.mcp.json`.
- Input source MUST be `--from-jira` — subtasks need a parent issue key.

## Flag syntax

```
--to-jira
```

No project, suite, or identifier needed — the parent is the source ticket.

## MCP tool

- `mcp__claude_ai_Atlassian__createJiraIssue` with `issueTypeName: "Subtask"` and `parent` set to the source ticket key.

## Field mapping (canonical → Jira Subtask)

| Canonical | Jira field |
|-----------|------------|
| `title` | `summary` |
| `preconditions` + `steps` + `postconditions` | `description` (formatted markdown: Preconditions section, Steps table, Postconditions section) |
| `priority: "high"` | `additional_fields.priority.name: "High"` |
| `priority: "medium"` | `additional_fields.priority.name: "Medium"` |
| `priority: "low"` | `additional_fields.priority.name: "Low"` |
| `tags` | `additional_fields.labels` |

### Description template

```markdown
## Preconditions
<preconditions>

## Steps
| # | Action | Expected Result |
|---|--------|-----------------|
| 1 | ... | ... |

## Postconditions
<postconditions>
```

## Phase 4 progress announcements

- Before the create-subtask loop: `⏳ Creating Jira subtasks...`
- Loop one call per case; collect returned issue keys for the success report.

## Success report

```
✅ Created N Jira subtasks under <PARENT-KEY>
   Adapter: Jira (Subtask)
   Created keys: <KEY-1>, <KEY-2>, ...
```

## Errors

- If input is not `--from-jira`: abort with
  `❌ --to-jira requires --from-jira (subtasks need a parent ticket key).`

## References

- [Atlassian REST — Create issue](https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issues/#api-rest-api-3-issue-post)
