# Factory Inventory Management System

## Tech Stack

### client (JavaScript)
- **Vue** 3 · **pnpm** · **Vite**
- **Routing & HTTP**: vue-router, axios

### server (Python)
- **FastAPI** · **uv**
- **Runtime**: pydantic, uvicorn

## File Placement Guide

- **client** — Vue views under `client/src/views/{view}.vue` — full table: `docs/llm-wiki/wiki/services/client.md`
- **server** — FastAPI app in `server/main.py` with JSON fixtures co-located in `server/data/{entity}.json` loaded by `server/mock_data.py` — full table: `docs/llm-wiki/wiki/services/server.md`

## Directory Structure

```
project/
├── client/   Vue frontend
└── server/   FastAPI backend
```

## Essential Commands

| Command | Description | Source |
| ------- | ----------- | ------ |
| `./scripts/start.sh` | Dev-server launcher. | `scripts/start.sh` |
| `./scripts/stop.sh` | Environment reset. | `scripts/stop.sh` |
| `./scripts/start.sh` | From README.md § Quick Start | `README.md#quick-start` |
| `cd client && pnpm install` | Install client deps (pnpm; `corepack enable` if missing) | `client/package.json` |
| `cd client && pnpm run build` | Build (client) | `client/package.json` |

### Per-service commands (low-level)

> Prefer the wrapper above when present; these run a single service in isolation and may not start dependent services.

| Service | Start dev environment |
| ------- | --- |
| client | `cd client && pnpm run dev` |

> Essential commands only — the full command reference (every discovered command and variant) is documented in the project wiki.

## Services & Ports

| Service | Type | Port | Role |
| ------- | ---- | ---- | ---- |
| client | frontend | 3000 | Vue 3 SPA — renders inventory, orders, demand, spending dashboards; calls server API with filter params |
| server | backend | 8001 | FastAPI service — exposes filtered REST endpoints over in-memory JSON mock data for inventory, orders, demand, spending |

## Project-Wide Rules

- Repository and any fork is PUBLIC — do not commit credentials, internal hostnames, or private registry URLs.
- The client uses pnpm: `client/.npmrc` pins the public npm registry and `client/pnpm-lock.yaml` is committed; `client/package-lock.json` is gitignored — leave both in place and never commit a lockfile containing private registry URLs.
- Use the `gh` CLI for ALL GitHub operations (PRs, issues, reviews, Actions, `gh api`); create local branches with `git checkout -b`. Do not use GitHub MCP tools (`mcp__github__*`).
- PR reviews use the QAF `/pr-reviewer` skill, locally and in CI: `.github/workflows/claude-code-review.yml` runs it on every PR; `.github/workflows/claude.yml` answers `@claude` mentions with QAF skills enabled.
- Use Playwright MCP tools (`mcp__playwright__*`) for browser testing against `http://localhost:3000` and `http://localhost:8001`.
- Delegate any create/significant-modify of `.vue` files to the `vue-expert` subagent.
- Use the `backend-api-test` skill when writing or modifying tests under `tests/backend` (pytest + FastAPI TestClient).
- No emojis in UI.

## Project Conventions

Before writing or reviewing code in a service, read that service's prescriptive
rules — do not infer them from surrounding files alone:

- `docs/llm-wiki/wiki/services/{id}.md` → `## Conventions & How-To` — that service's coding, multi-file-workflow, and testing rules, with grounded examples.
- `docs/llm-wiki/wiki/conventions/project.md` → `## Project-Wide Rules` — rules that apply across the whole repository.

<!-- LLM_WIKI_START -->
## LLM Wiki
- Router (entry point): `docs/llm-wiki/CLAUDE.md` — decision table and tier discipline. **Read this first.**
- Index (summary catalog): `docs/llm-wiki/wiki/index.md` — one line per page; pick the 1–3 pages whose summaries match your question.
- Before broad code changes: load the router → match the index → read only the matched pages. Stop wikilink traversal at depth 2. Fall back to targeted Grep/Read on the source only if the wiki does not answer.
<!-- LLM_WIKI_END -->
