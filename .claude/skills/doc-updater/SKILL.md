---
name: doc-updater
description: "Update CLAUDE.md — the cheat-sheet of tech stack, file placement, essential commands, services and ports — when a code change alters one of those facts. Use after implementing a ticket; conventions and descriptive docs belong to /wiki-refresh, preflight state to ensure-context.sh."
version: 3.0.0
---

# Documentation Updater Skill

## Responsibilities and non-responsibilities

### In scope

This skill updates exactly one target — nothing else:

1. `.claude/CLAUDE.md` (CLAUDE.md / AGENTS.md) — the project **cheat-sheet** (tech stack, file-placement guide, directory structure, essential commands, services & ports).

### Out of scope (and why)

| What | Why not here | Where instead |
|------|-------------|---------------|
| Per-service prescriptive conventions — coding rules, WRONG/CORRECT gotchas, multi-file change checklists, testing rules for a specific service | Per-service prescriptive content lives on each service page, not in the cheat-sheet. | `/wiki-refresh` maintains each service page's `## Conventions & How-To` (`docs/llm-wiki/wiki/services/<id>.md`) |
| Repo-wide prescriptive rules — commit/branch/PR flow, test-tree location, CI-breaking gates | Repo-wide rules live on the conventions wiki page, not the cheat-sheet. | `/wiki-refresh` maintains `docs/llm-wiki/wiki/conventions/project.md` → `## Project-Wide Rules` |
| `docs/llm-wiki/**` (descriptive) | Descriptive content — system shape, service inventory, flows. Belongs in the wiki. | `/wiki-refresh` (invoked automatically in `/implement-ticket` Phase 9 Wiki Refresh) |
| Preflight state — marker, workspace topology, framework-update check | Written by pre-flight tooling, not by a documentation pass. | `ensure-context.sh` preflight |
| README files | READMEs are discoverable human documentation handled during ticket implementation, not by this skill. | Implementer agent during `/implement-ticket` Phase 4 |

**Cheat-sheet vs. everything else (load-bearing):**

- `CLAUDE.md` carries the **cheat-sheet** (file placement rules, commands, tech stack, services & ports — the "where / what command / what stack" reference every session reads at startup), maintained here. Repo-wide rules are not maintained in this file — they live on `docs/llm-wiki/wiki/conventions/project.md`; never add a `## Project-Wide Rules` block here.
- **Per-service prescriptive** rules (how to write code in a service — code rules, workflows, testing) live in each service page's `## Conventions & How-To` (`docs/llm-wiki/wiki/services/<id>.md`), maintained by `/wiki-refresh`.
- **Descriptive** facts (what the system IS — service shape, request flows, integrations) live in the rest of the wiki, maintained by `/wiki-refresh`.

If a change you would document is a per-service prescriptive rule ("ALWAYS wrap order writes in a transaction", "adding an entity now also requires registering it") or descriptive ("the system uses RabbitMQ"), it does NOT belong in the cheat-sheet — invoke `/wiki-refresh` instead. A genuinely repo-wide rule (commit format, branch/PR flow, test-tree location, CI-breaking gate) also goes to `/wiki-refresh`, which writes it to `docs/llm-wiki/wiki/conventions/project.md`.

---

## CRITICAL: Role prompt for this agent

```
CRITICAL: This agent updates the CLAUDE.md cheat-sheet ONLY.

FORBIDDEN:
- Editing any file under docs/llm-wiki/**
- Adding prescriptive rules or descriptive narrative to CLAUDE.md
- Editing README.md or any documentation that is not the single in-scope target
- Bumping version numbers in package.json / pyproject.toml / Cargo.toml / go.mod / etc.

If a proposed change is prescriptive or descriptive, refuse it and tell the caller to invoke /wiki-refresh instead.
```

---

## Qualification rubric

A change qualifies for a cheat-sheet update **only if** it alters one of the cheat-sheet's own facts:

**(a)** A **new technology** enters the stack — a new framework/library/language/runtime, or a new database/service in the container/compose config.

**(b)** A **file-placement or structure rule** changes — a new directory layout, file-naming convention, module-organisation pattern, or path alias a developer must know before creating new files.

**(c)** An **essential command** changes — package-manager scripts, Makefile targets, or other development-workflow commands.

**(d)** **Services & ports** change — services added/removed, port mappings changed.

Anything else is either prescriptive (→ `/wiki-refresh`), descriptive (→ `/wiki-refresh`), or one-off implementation detail (→ no update).

**Do NOT update if:**

- Changes are simple bug fixes
- Changes add new endpoints (endpoints must not be listed)
- Changes add new entities (entity fields must not be listed)
- Changes are implementation details discoverable by reading code
- The candidate update is a prescriptive rule or descriptive fact (→ `/wiki-refresh`)

---

## When to Use

Invoke `/doc-updater` after implementing a ticket (Phase 7 of implement-ticket), after significant code changes, or when the tech stack, file-placement conventions, essential commands, or services/ports change.

---

## Inputs

This skill expects to be called from implement-ticket Phase 7 with:

1. **Changed files list**: From `git diff --name-only`
2. **Implementation summary**: Brief description of changes
3. **Ticket ID**: For tracking purposes

---

## Workflow

Run the five phases below in order. This skill is invoked inline by the caller — **do not create tasks or todos; the calling skill owns progress tracking.**

### Phase 0: Read Current Cheat-Sheet

```bash
echo "=== Current CLAUDE.md ==="
cat .claude/CLAUDE.md
```

### Phase 1: Analyze Changed Files

Read and categorize all changed files:

```bash
for file in $CHANGED_FILES; do
  echo "=== $file ==="
  cat "$file"
done
```

Categorize changes:

- Backend code (controllers, services, guards, middleware)
- Frontend code (components, pages, hooks)
- Configuration (package.json, docker-compose.yml, tsconfig.json)
- Infrastructure (Dockerfile, scripts, CI/CD)

### Phase 2: Detect Cheat-Sheet Impact

Decide whether `CLAUDE.md` needs an update. Apply the qualification rubric above — if none of clause (a)–(d) is satisfied, do not update.

**`CLAUDE.md` — update when:**

- **New technology**: new framework/library in package.json, new language, new database/service in docker-compose.yml
- **File placement changes**: new directory structure, file naming convention, or module-organisation pattern
- **Common commands changed**: package.json scripts, Makefile targets, or new development-workflow commands
- **Architecture changes**: monorepo structure modified, new path aliases, backend/frontend organisation changed
- **Services & ports changed**: docker-compose services added/removed, port mappings changed

If the change introduces a per-service prescriptive rule (a gotcha, a multi-file checklist, a testing rule) or a descriptive fact (a new integration, a shifted service boundary), do **not** edit the cheat-sheet — note it for `/wiki-refresh`, which owns each service page's `## Conventions & How-To` and the descriptive pages. A genuinely repo-wide rule likewise goes to `/wiki-refresh` (the `docs/llm-wiki/wiki/conventions/project.md` page).

### Phase 3: Generate Update Plan

Generate a JSON structure with your analysis:

```json
{
  "ticketId": "<ticket-id>",
  "changesDetected": {
    "claudeMd": {
      "updateNeeded": false,
      "sections": [],
      "reason": "<rubric clause (a-d) satisfied, or 'no clause satisfied'>"
    }
  },
  "deferredToWikiRefresh": "<prescriptive/descriptive facts that belong in /wiki-refresh, or empty>",
  "updates": {
    "claudeMd": []
  }
}
```

### Phase 4: Apply Updates

For each update in the plan, use the Edit tool against `.claude/CLAUDE.md` and verify the edit succeeded:

```
Edit({
  file_path: '.claude/CLAUDE.md',
  old_string: update.before,
  new_string: update.after,
})
```

**Update strategy — keep every section concise and reference-only:**

- **Tech Stack** — add new language/framework; bump versions only on a major change
- **File Placement Guide** — add new file-type patterns / structure changes; verify every path exists with Glob
- **Essential Commands** — reflect package.json script / Makefile changes; keep grouped by category
- **Directory Structure / Path Aliases** — reflect monorepo-structure or path-alias changes; structure only
- **Services & Ports** — reflect docker-compose service / port-mapping changes

If a fact you would add is prescriptive or descriptive, stop — it belongs in the wiki, not the cheat-sheet. Note it under `deferredToWikiRefresh` and invoke `/wiki-refresh` instead.

### Phase 5: Verify Updates

Read the updated file to confirm correctness:

```bash
echo "=== Updated CLAUDE.md ==="
cat .claude/CLAUDE.md
```

Confirm the result against the Success Criteria below.

---

## Completion

When all phases are done, emit a one-line summary to the caller — either `doc-updater: updated CLAUDE.md` or `doc-updater: no cheat-sheet changes needed` when the rubric gated the target — and return control. This step **always runs, including the no-change case**: emitting the summary is a successful return to the caller, not the end of the run — the calling skill continues with its next phase. Do not create tasks or todos; the calling skill owns progress tracking.

---

## Success Criteria

Your documentation update is successful if:

- Only the `CLAUDE.md` cheat-sheet was touched; no skill body, no wiki file, no README, no package-manifest version field
- Only necessary sections are updated; existing structure and formatting preserved
- No exhaustive lists added (no endpoint lists, entity-field lists, or similar inventories)
- All referenced paths exist in the codebase (verified with Glob)
- Every change satisfies at least one rubric clause (a–d)
- No prescriptive rule or descriptive prose leaked into the cheat-sheet (those go to `/wiki-refresh`)
- `CLAUDE.md` remains a scannable cheat-sheet (aim ≤ 250 lines)

---

## Example Outputs

### Example 1: No Updates Needed

```json
{
  "ticketId": "PROJ-123",
  "changesDetected": {
    "claudeMd": {
      "updateNeeded": false,
      "sections": [],
      "reason": "Changes are implementation details; no stack / file-placement / command / services change"
    }
  },
  "deferredToWikiRefresh": "New transaction-wrapping gotcha is a per-service prescriptive rule — belongs in that service page's ## Conventions & How-To via /wiki-refresh",
  "updates": { "claudeMd": [] }
}
```

→ Then report `doc-updater: no cheat-sheet changes needed` and **return control to the caller. This is a successful result, NOT the end of the run — `/implement-ticket` continues to its Phase 9 Wiki Refresh (which refreshes `docs/llm-wiki/`).**

### Example 2: New Technology + New Command (rubric clauses a and c)

```json
{
  "ticketId": "PROJ-789",
  "changesDetected": {
    "claudeMd": {
      "updateNeeded": true,
      "sections": ["Tech Stack", "Essential Commands"],
      "reason": "Rubric (a): Redis added as a new service. Rubric (c): new `pnpm queue:dev` command."
    }
  },
  "deferredToWikiRefresh": "Queue-consumer request flow is descriptive — belongs in the wiki via /wiki-refresh",
  "updates": {
    "claudeMd": [
      {
        "section": "Tech Stack",
        "action": "add",
        "before": "- PostgreSQL 15",
        "after": "- PostgreSQL 15\n- Redis 7 (queue + cache)",
        "justification": "Rubric (a): new service in the stack"
      }
    ]
  }
}
```

→ Apply the edits above, then report `doc-updater: updated CLAUDE.md` and return control to the caller.

---

## Integration with implement-ticket

This skill is invoked from `implement-ticket` Phase 7. The caller derives the changed-file list and ticket ID, then invokes the skill:

```bash
CHANGED_FILES=$(git diff --name-only origin/main...HEAD)
echo "Changed files: $CHANGED_FILES"
echo "Ticket ID: $TICKET_ID"
```

The skill detects changed files via git, analyzes each against the qualification rubric, updates only the `CLAUDE.md` cheat-sheet when a clause is satisfied, defers prescriptive/descriptive facts to `/wiki-refresh`, and returns a one-line completion summary (see Completion).
