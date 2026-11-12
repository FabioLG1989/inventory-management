# Format Config — `generate-test-cases.json`

This file documents the per-project format contract used by Phase 2 of the `generate-test-cases` skill. It is loaded on-demand when Phase 2 needs the full first-run flow, schema, or instructions to change a saved config.

The format contract resolves: title convention, field set, priority scale, type scale, and step style — everything Phase 3 must follow when generating canonical test cases. The answer is persisted per project so the user is only asked once.

---

## Ownership

- **Skill code** lives at `.claude/skills/generate-test-cases/` (framework-managed, updated by framework sync). Do NOT edit per-project config there.
- **Project config** lives at `generate-test-cases.json` in the **project root** (user data, versioned in the project's own git, same convention as `ui-visual-testing.json`).
- This file is NOT created by `/initialize-project`. It is written on the first run of `/generate-test-cases` in a project.

To share format preferences across a team, commit `generate-test-cases.json` to the project repo — new clones inherit it and skip the first-run prompt.

---

## Phase 2 flow

### 2a. Config file lookup

Look for `generate-test-cases.json` at the project root.

- **Exists** → returning-run flow (2b).
- **Missing** → first-run flow (2c).

### 2b. Returning-run flow (config present)

Read the file and print:

```
✓ Using saved format config (generate-test-cases.json)
  Style: <classic | gherkin>
  Customizations: <first 120 chars of customizations, or "none">
```

Pass `style` and `customizations` forward to Phase 3. Phase 3 applies them on top of the canonical default when generating. Do NOT ask the user anything.

### 2c. First-run flow (config missing)

Show the default format as a readable preview — NOT raw JSON:

```
📋 No format config found for this project. This is the default:

  • Title convention: "Feature | Scenario"
  • Fields: title, preconditions, steps[], postconditions, priority, type, tags
  • Priority scale: high (critical path) | medium (secondary flow) | low (polish)
  • Type scale: functional | security | usability | accessibility | performance | compatibility
      (for regression/smoke/sanity suite membership, use tags — not the type field)
  • Step style: classic (action + expected_result per step) — override with --format gherkin for Given-When-Then

Use this default, or describe your customizations?
  - Reply "default" / "ok" / "yes" to accept as-is.
  - Or describe changes in plain text. Examples:
      "Titles follow Module > Feature > Scenario."
      "Add a test_data field. Priority scale 1-5 where 1 is critical."
      "Use gherkin always. Tags must include the target environment."
```

Wait for the user's answer, then:

- **Accepted** → write `generate-test-cases.json` with `customizations: ""` and `style` from `--format` if provided, else `"classic"`.
- **Customized** → write `generate-test-cases.json` with the user's reply stored verbatim in `customizations`. If the reply contains an explicit style switch ("use gherkin" / "classic"), reflect it in `style`.

Print confirmation:

```
✓ Saved format config to generate-test-cases.json
  Style: <style>
  Customizations: <truncated or "none">
```

Then proceed to Phase 3.

### 2d. Config file schema

```json
{
  "version": "1.0",
  "format": {
    "style": "classic",
    "customizations": "Free-text description of custom rules applied during test case generation. Empty string means use the canonical default as-is."
  },
  "updatedAt": "2026-04-23T10:00:00Z"
}
```

- `style`: `"classic"` or `"gherkin"`. Controls step shape (action/expected_result table vs Given-When-Then).
- `customizations`: natural-language text. Claude interprets it during Phase 3. There is no schema validation — adapter conflicts surface at publish time (Phase 4 reports them and maps to the nearest valid value).
- `updatedAt`: ISO-8601 timestamp, useful for debugging and audit.

---

## Changing the Saved Format

### Re-ask the interactive prompt

Delete the file. The next `/generate-test-cases` run detects it missing and re-runs 2c.

```bash
rm generate-test-cases.json
```

### Tweak without re-asking

Edit `customizations` directly. The text is applied verbatim by Phase 3 — phrase it as natural-language rules.

```json
{
  "version": "1.0",
  "format": {
    "style": "classic",
    "customizations": "Titles follow Module > Feature > Scenario. Always include a test_data field in every case. Priority scale 1-5 (1 is critical, 5 is cosmetic)."
  },
  "updatedAt": "2026-04-23T10:00:00Z"
}
```

### Share across a team

Commit `generate-test-cases.json` to git. New team members inherit the config and skip the first-run prompt.

### Temporary overrides

There is no flag to override the saved config for a single run in v1.x. Workaround: rename/move the file before running, run with the desired answer, restore the original file. A `--format-spec` override flag may be added in a future version if usage demands it.

### Validation caveats

`customizations` is free-form. If a customization conflicts with a target adapter (e.g., declares "priority scale 1-5" but publishes to Qase, which only accepts 1-3), Phase 4 reports the conflict in its summary and maps to the nearest valid value. Phase 2 does not reject customizations.
