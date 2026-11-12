# Usage Examples

End-to-end invocations of `/generate-test-cases` for each input + adapter combination, plus interactive flows.

## Jira → Qase (classic steps)
```bash
/generate-test-cases --from-jira PROJ-123 --to-qase MYPROJ
```
Fetches PROJ-123, generates canonical test cases, loads `adapters/qase.md`, maps to Qase fields, creates suite + bulk-creates cases.

## Jira → Qase (gherkin, existing suite)
```bash
/generate-test-cases --from-jira PROJ-125 --to-qase MYPROJ --format gherkin --suite-id 5
```

## Jira → Jira subtasks
```bash
/generate-test-cases --from-jira PROJ-122 --to-jira
```
Loads `adapters/jira.md` and creates one Subtask per canonical test case under PROJ-122.

## Jira → Markdown
```bash
/generate-test-cases --from-jira PROJ-124 --to-markdown ./test-cases/wishlist-tests.md
```

## Free text → Qase
```bash
/generate-test-cases \
  --from-text "Users can select a currency and all prices update immediately" \
  --to-qase MYPROJ
```

## Jira → TestRail (MCP configured)
```bash
/generate-test-cases --from-jira PROJ-123 --to-testrail 12
```

## Jira → Xray
```bash
/generate-test-cases --from-jira PROJ-123 --to-xray
```

## First run in a new project (interactive format confirmation)

First invocation in a project where `generate-test-cases.json` does not yet exist. Phase 2 shows the default and asks the user.

```bash
$ /generate-test-cases --from-jira PROJ-123 --to-markdown ./cases.md

✓ Loaded: PROJ-123 — User Authentication
  Source: Jira (Story)
  Labels: auth, security
  Other data: Checklist items found: 8
  Output adapter: Markdown → ./cases.md

📋 No format config found for this project. This is the default:

  • Title convention: "Feature | Scenario"
  • Fields: title, preconditions, steps[], postconditions, priority, type, tags
  • Priority scale: high | medium | low
  • Type scale: functional | security | usability | accessibility | performance | compatibility
      (for regression/smoke/sanity suite membership, use tags — not the type field)
  • Step style: classic

Use this default, or describe your customizations?
  - Reply "default" / "ok" / "yes" to accept as-is.
  - Or describe changes in plain text.

> Titles follow Module > Feature > Scenario. Priority scale 1-5.

✓ Saved format config to generate-test-cases.json
  Style: classic
  Customizations: Titles follow Module > Feature > Scenario. Priority scale 1-5.

[... Phase 3 + Phase 4 run normally ...]
```

After this run, `generate-test-cases.json` exists at project root and will be used silently on subsequent runs.

## Subsequent run in a project with saved config

Same project after the first run. Phase 2 reads the existing config and proceeds without asking.

```bash
$ /generate-test-cases --from-jira PROJ-124 --to-qase MYPROJ

✓ Loaded: PROJ-124 — Password Reset
  Source: Jira (Story)
  ...

✓ Using saved format config (generate-test-cases.json)
  Style: classic
  Customizations: Titles follow Module > Feature > Scenario. Priority scale 1-5.

[... Phase 3 + Phase 4 run normally, applying the saved customizations ...]
```
