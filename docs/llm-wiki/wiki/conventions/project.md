---
document_type: conventions
content_type: prescriptive
summary: >-
  The single home for project-wide conventions — shared dependencies, tooling,
  quality gates, and service boundaries that recur across services, plus
  genuinely repo-wide rules; the per-service pages reference it.
last_updated: '2026-11-12T18:06:44.520Z'
tags:
  - conventions
  - project
---
# Project-Wide Conventions

This project standardises one enforced service boundary: [[client]] communicates with [[server]] exclusively through the server's published REST API. Direct in-process or filesystem coupling between the two services falls outside the boundary that the shared conventions govern.

Dependency management, shared tooling configuration, and quality-gate conventions (linting rules, test requirements, CI pipeline gates) are (not determined by analysis) at the project-wide level; consult [[client]] and [[server]] for the conventions in force within each service.

## Shared Topics

### Service Boundaries

- reach `server` through its published API (services: client, server)

## Project-Wide Rules

- Repository and any fork is PUBLIC — do not commit credentials, internal hostnames, or private registry URLs.
- The client uses pnpm: `client/.npmrc` pins the public npm registry and `client/pnpm-lock.yaml` is committed; `client/package-lock.json` is gitignored — leave both in place and never commit a lockfile containing private registry URLs.
- Use the `gh` CLI for ALL GitHub operations (PRs, issues, reviews, Actions, `gh api`); create local branches with `git checkout -b`. Do not use GitHub MCP tools (`mcp__github__*`).
- Use Playwright MCP tools (`mcp__playwright__*`) for browser testing against `http://localhost:3000` and `http://localhost:8001`.
- Delegate any create/significant-modify of `.vue` files to the `vue-expert` subagent.
- Use the `backend-api-test` skill when writing or modifying tests under `tests/backend` (pytest + FastAPI TestClient).
- No emojis in UI.
