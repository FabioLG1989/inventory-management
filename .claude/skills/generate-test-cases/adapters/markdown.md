# Markdown Adapter

Writes all canonical test cases to a local markdown file with a table of contents. No MCP required.

## Requirements

- Write access to the target directory.

## Flag syntax

```
--to-markdown <PATH>
```

## Field mapping (canonical → Markdown)

| Canonical | Markdown section |
|-----------|-----------------|
| `title` | `### TC-N: <title>` heading |
| `priority` + `type` + `tags` | metadata line: `**Priority**: high | **Type**: functional | **Tags**: ...` |
| `preconditions` | `**Preconditions**` bullet list |
| `steps` | `**Steps**` table with `#`, `Action`, `Expected Result` columns |
| `postconditions` | `**Postconditions**` paragraph |

## File template

```markdown
# Test Cases — <Source title>

## Table of Contents
- [TC-1: ...](#tc-1-...)
- [TC-2: ...](#tc-2-...)

---

### TC-1: <title>
**Priority**: high | **Type**: functional | **Tags**: tag-a, tag-b

**Preconditions**
- ...

**Steps**

| # | Action | Expected Result |
|---|--------|-----------------|
| 1 | ... | ... |

**Postconditions**
...
```

For `--format gherkin`, replace the Steps table with a fenced gherkin code block per case.

## Phase 4 progress announcements

- Before the write: `⏳ Writing test cases to <path>...`

## Success report

```
✅ Wrote N test cases to <path>
   Adapter: Markdown
```
