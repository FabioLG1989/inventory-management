# CLAUDE.md

Factory Inventory Management System Demo with GitHub integration - Full-stack application with Vue 3 frontend, Python FastAPI backend, and in-memory mock data (no database).

> ⚠️ **This repository and any fork you create are PUBLIC.** Do not commit credentials, internal hostnames, or private registry URLs. The client uses **pnpm**. `client/.npmrc` pins the public npm registry (pnpm honors it) so the committed `client/pnpm-lock.yaml` never records a private registry; `client/package-lock.json` stays gitignored. Leave both in place and check `pnpm-lock.yaml` has no private registry URLs before committing.

## QAF First (Qubika Agentic Framework)

This project is initialized with QAF. QAF is the default way of working here.

1. **Check for a QAF way before every task.** Before starting any task, check whether a QAF skill or agent covers it (skills in `.claude/skills/`, agents in `.claude/agents/`) and use it when one fits. Examples:
   - New idea or feature request → `/create-sdd-ticket`
   - Implementing a ticket → `/implement-ticket` (planning only: `/create-implementation-plan`)
   - Reviewing a PR → `/pr-reviewer` (also runs automatically in CI on every PR); security → `/security-review`
   - Bugs and failures → `/troubleshoot`, `/report-bug`
   - Tests → `/generate-test-cases`, `/ui-testing`, `/requirement-coverage-gap-analysis`
   - Parallel work → `/start-task`; wiki upkeep → `/wiki-refresh`
2. **Always use the LLM Wiki, even without a matching QAF skill.** Before reading or changing code, load `docs/llm-wiki/CLAUDE.md` (router) → `docs/llm-wiki/wiki/index.md` → only the matching pages. Fall back to Grep/Read only when the wiki does not answer.
3. **Always follow QAF rules.** Apply `.claude/CLAUDE.md` (cheat-sheet and Project-Wide Rules), `docs/llm-wiki/wiki/conventions/project.md`, and the `## Conventions & How-To` section of `docs/llm-wiki/wiki/services/{id}.md` for the service you touch.
4. **Keep the wiki current.** After out-of-band changes outside `/implement-ticket`, run `/wiki-refresh`.

## Critical Tool Usage Rules

### Subagents
Use the Task tool with these specialized subagents for appropriate tasks:

- **vue-expert**: Use for Vue 3 frontend features, UI components, styling, and client-side functionality
  - Examples: Creating components, fixing reactivity issues, performance optimization, complex state management
  - **MANDATORY RULE: ANY time you need to create or significantly modify a .vue file, you MUST delegate to vue-expert**
- **code-reviewer**: Use after writing significant code to review quality and best practices
- **Explore**: Use for understanding codebase structure, searching for patterns, or answering questions about how components work
- **general-purpose**: Use for complex multi-step tasks or when other agents don't fit

### Skills
- **backend-api-test** skill: Use when writing or modifying tests in `tests/backend` directory with pytest and FastAPI TestClient

### GitHub
- **ALWAYS use the `gh` CLI** for ALL GitHub operations (PRs, issues, reviews, Actions runs, secrets, API calls via `gh api`)
  - Local branches: use `git checkout -b` / `git switch -c`
  - Do not use the GitHub MCP tools (`mcp__github__*`); no GitHub MCP server is configured
- **GitHub Actions** (`.github/workflows/`):
  - `claude-code-review.yml` runs the QAF `/pr-reviewer` skill on every PR open/push and posts one formal review via `gh api`
  - `claude.yml` runs Claude when someone writes `@claude` in an issue, PR comment or review; QAF skills, `gh`, `git`, `node`, `python3`, `pnpm`, `uv`, `curl`, the start/stop scripts and the Playwright MCP (headless Chromium) are allowed there, so it can start the app and check it in a browser
  - In CI, `gh` runs as `github-actions[bot]` with the workflow `GITHUB_TOKEN` (`gh api user` is not available); each run uploads Claude's execution log as an artifact for debugging
  - Workflow changes only take effect after they are merged to `main`

### MCP Tools
- **ALWAYS use Playwright MCP tools** (`mcp__playwright__*`) for browser testing
  - Test against: `http://localhost:3000` (frontend), `http://localhost:8001` (API)

## Stack
- **Frontend**: Vue 3 + Composition API + Vite (port 3000)
- **Backend**: Python FastAPI (port 8001)
- **Data**: JSON files in `server/data/` loaded via `server/mock_data.py`

## Quick Start

```bash
# Backend
cd server
uv run python main.py

# Frontend (needs pnpm: `corepack enable`)
cd client
pnpm install && pnpm run dev
```

## Key Patterns

**Filter System**: 4 filters (Time Period, Warehouse, Category, Order Status) apply to all data via query params
**Data Flow**: Vue filters → `client/src/api.js` → FastAPI → In-memory filtering → Pydantic validation → Computed properties
**Reactivity**: Raw data in refs (`allOrders`, `inventoryItems`), derived data in computed properties

## API Endpoints
- `GET /api/inventory` - Filters: warehouse, category
- `GET /api/orders` - Filters: warehouse, category, status, month
- `GET /api/dashboard/summary` - All filters
- `GET /api/demand`, `/api/backlog` - No filters
- `GET /api/spending/*` - Summary, monthly, categories, transactions

## Operational Memory
Known bugs, environment quirks and open gotchas live in `.claude/memory/operational.md`. The file is gitignored and never committed, because this repo is public.
- **Location:** use the copy in the main checkout, not in a worktree, so every worktree shares it. Find it with `"$(git rev-parse --path-format=absolute --git-common-dir)/../.claude/memory/operational.md"`.
- **Read it** before debugging or verifying a change, so you don't chase issues that are already known. One example is the `/api/tasks` 404 in the console.
- **Add an entry** when you find a bug or quirk you are not fixing in the current task. Use a short heading with **Found** (date and context), **Symptom**, **Cause** (file paths), **Impact** and **Status**.
- **When it's fixed,** delete the entry, or set its Status to fixed with the PR link.
- **What not to put here:** credentials, internal hostnames or personal data. Facts that belong in this CLAUDE.md or in code comments go there instead.

## Common Issues
1. Use unique keys in v-for (not `index`) - use `sku`, `month`, etc.
2. Validate dates before `.getMonth()` calls
3. Update Pydantic models when changing JSON data structure
4. Inventory filters don't support month (no time dimension)
5. Revenue goals: $800K/month single, $9.6M YTD all months

## File Locations
- Views: `client/src/views/*.vue`
- API Client: `client/src/api.js`
- Backend: `server/main.py`, `server/mock_data.py`
- Data: `server/data/*.json`
- Styles: `client/src/App.vue`

## Design System
- Colors: Slate/gray (#0f172a, #64748b, #e2e8f0)
- Status: green/blue/yellow/red
- Charts: Custom SVG, CSS Grid for layouts
- No emojis in UI
