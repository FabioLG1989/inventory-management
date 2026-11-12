# Framework Registration & Sync

How a newly-drafted skill gets registered in the framework and synced to projects. Run these steps after writing the SKILL.md draft and before testing.

## Contents

- Step 1: Create the skill directory in the framework
- Step 2: Validate frontmatter compliance
- Step 3: Register in `skills/skills.config.json`
- Step 4: Run the sync
- Step 5: Validate the sync
- Real-world examples

Skills created through this framework follow a **framework-first** approach: the skill lives in the framework source tree, gets registered in the config, and is synced to the project's `.claude/skills/`. This makes the skill PR-able and shareable across all projects using the framework.

## Step 1: Create the skill directory in the framework

Choose the appropriate Johnny Decimal category:

| Prefix | Category |
|--------|----------|
| `010-foundation` | Core workflow skills (always copied) |
| `020-development-workflow` | Development process skills |
| `030-quality-assurance` | Testing, quality, and review |
| `040-integrations` | External tools (Jira, GitHub, Notion) |
| `050-language-frameworks` | Language and framework patterns |
| `060-documentation` | Documentation and diagrams |
| `070-infrastructure` | DevOps and containers |
| `080-cloud-platforms` | Cloud services (AWS, GCP, Firebase) |

Create the directory and write the SKILL.md there — never directly in `.claude/`:

```bash
mkdir -p skills/{NNN-category}/{skill-name}
# Write SKILL.md to skills/{NNN-category}/{skill-name}/SKILL.md
```

If the skill needs bundled resources, create subdirectories as needed (`scripts/`, `references/`, `assets/`).

## Step 2: Validate frontmatter compliance

Before registering, verify the SKILL.md against the framework spec. Read these documents and apply them:

- **`docs/reference/SKILLS_SPEC.md`** — Canonical frontmatter schema, archetypes, validation rules
- **`website/docs/guides/adding-skills.md`** — Registration procedure
- **`docs/reference/templates/SKILL_TEMPLATE_WORKFLOW.md`** — Starter template for workflow/orchestration skills
- **`docs/reference/templates/SKILL_TEMPLATE_REFERENCE.md`** — Starter template for reference/mastery skills

Ensure the frontmatter includes all required fields:

```yaml
---
name: skill-name              # kebab-case, must match directory name
description: >                # 20-500 chars, include "Use when..." phrases
  What the skill does. Use when [specific contexts].
version: 1.0.0
category: category-name       # kebab-case
keywords: [keyword1, keyword2]
allowed-tools:                # only tools actually used
  - Read
  - Write
last_updated: YYYY-MM-DD
---
```

Verify: archetype is consistent (Workflow or Reference, not mixed), single H1 heading, code blocks have language tags, no name/directory mismatch, no hardcoded credentials.

## Step 3: Register in `skills/skills.config.json`

Read the current `skills/skills.config.json` and add a new entry to the `skills` array. Ask the user whether the skill should use `trigger_mode: "always"` (copied to every project) or `"triggered"` (copied only when specific technologies are detected). If triggered, ask what the triggers should be.

```json
{
  "name": "skill-name",
  "path": "NNN-category/skill-name",
  "description": "Concise description of what the skill provides",
  "trigger_mode": "always"
}
```

For triggered skills, also include `triggers`. Set `is_linkable_to_agents: true` with `compatible_languages` only for a pattern reference the implementer agent should be able to `Read` while coding in those languages; it is then listed by path and `description` in the implementer of any project with a matching language. Leave both out for workflow skills (anything that orchestrates, opens PRs, or spawns agents):

```json
{
  "name": "skill-name",
  "path": "050-language-frameworks/skill-name",
  "description": "Concise description",
  "trigger_mode": "triggered",
  "triggers": ["technology-name"],
  "compatible_languages": ["typescript", "javascript"],
  "is_linkable_to_agents": true
}
```

After writing, validate the JSON:

```bash
jq empty skills/skills.config.json && echo "✓ Valid JSON" || echo "✗ Invalid JSON"
```

## Step 4: Run the sync

Sync the skill from the framework to the project's `.claude/skills/`:

```bash
./scripts/sync-framework-resources.sh
```

For `"always"` skills, this copies the skill to every initialized project. For `"triggered"` skills, the sync only copies when the project's stack profile matches one of the skill's triggers — this is correct behavior, not an error.

## Step 5: Validate the sync

Run the validation script to confirm everything landed correctly:

```bash
bash skills/020-development-workflow/skill-creator/scripts/validate-skill-sync.sh \
  "<skill-name>" "<framework-path>" "<project-path>"
```

The script checks that the framework source exists, the skill is registered, `skills.config.json` is valid JSON, the skill was synced to `.claude/skills/`, and the content matches. If any check fails, it provides troubleshooting guidance.

If the skill uses `trigger_mode: "triggered"` and the current project's stack doesn't match, a warning (not failure) is expected — the skill will sync to projects that do match.

## Real-world examples

Study these existing skills for patterns:
- **Workflow**: `skills/020-development-workflow/create-sdd-ticket/SKILL.md`
- **Reference**: `skills/050-language-frameworks/react-frontend/SKILL.md`
