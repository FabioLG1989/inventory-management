---
document_type: architecture
content_type: descriptive
summary: >-
  The repository is a two-service co-located layout — classified as `polyrepo`
  by the structure analyzer, but practically a single-repo with two sibling
  servic...
last_updated: '2026-11-12T18:59:25.000Z'
tags:
  - architecture
  - topology
  - javascript
  - vue
  - python
---
# Architecture

## Monorepo / Repository Shape

The repository is a two-service co-located layout — classified as `polyrepo` by the structure analyzer, but practically a single-repo with two sibling service directories sharing no workspace tooling. There is no pnpm/yarn workspace configuration, no root-level `package.json`, and no shared package between services. The two directories (`client/` and `server/`) are independent in terms of dependency management but are deployed and developed together.

| Workspace | Path | Language | Role |
|-----------|------|----------|------|
| client | `client/` | JavaScript | Vue 3 SPA frontend |
| server | `server/` | Python | FastAPI REST backend |

The repository root contains shell scripts under `scripts/` that start and stop both services concurrently. CI runs on GitHub Actions and is limited to Claude automation (see Automation & CI).

The co-location is intentional: the architecture decision record notes this arrangement keeps the two services accessible for workshop attendees without introducing pnpm/yarn workspace complexity.

## Service Inventory

| ID | Type | Language | Port | Role |
|----|------|----------|------|------|
| [[client]] | frontend | JavaScript | 3000 | Vue 3 SPA — renders inventory, orders, demand, and spending dashboards; sends filter query params to the server API |
| [[server]] | backend | Python | 8001 | FastAPI service — exposes filtered REST endpoints over in-memory JSON mock data for inventory, orders, demand, and spending |

## Service Communication

All inter-service communication is synchronous HTTP REST. The server exposes an API; the client consumes it. There is no message queue, no WebSocket, and no shared in-process communication.

| Source | Target | Protocol | Direction | Notes |
|--------|--------|----------|-----------|-------|
| client | server | REST (HTTP) | client → server | `client/src/api.js` builds axios GET requests with filter query params |
| server | client | REST (HTTP) | server → client | JSON responses validated by Pydantic response models before dispatch |

The client never exposes an API surface. CORS is configured via `CORSMiddleware` in `server/main.py`, allowing all origins, methods, and headers during development.

## External Integrations

(not determined by analysis)

## Authentication & Authorisation

(not determined by analysis)

## Request Lifecycle

### Server surface

The server request lifecycle proceeds through four steps, all located in `server/main.py`:

1. **CORS middleware** — `CORSMiddleware` is registered via `app.add_middleware`. All origins, methods, and headers are permitted during development.
2. **Route to handler** — FastAPI matches the incoming path (e.g., `GET /api/inventory`) and injects optional query parameters (`warehouse`, `category`) into the handler function `get_inventory`.
3. **Filter in-memory data** — `apply_filters` and `filter_by_month` are applied sequentially to Python lists loaded from JSON fixtures at startup by `server/mock_data.py`.
4. **Validate and serialize** — FastAPI validates the return value against the Pydantic `response_model` (e.g., `InventoryItem`) before writing the JSON response body. A fixture-to-model shape mismatch raises a 500 at response time, not request time.

### Client surface

The client request lifecycle proceeds through three steps:

1. **User interaction** — The user modifies a filter dropdown in a Vue view (e.g., `client/src/views/InventoryView.vue`). Reactive refs update immediately.
2. **API call** — The view calls an API helper (e.g., `getInventory` in `client/src/api.js`), which issues an axios GET request with the current filter values as query parameters.
3. **Store response** — The resolved axios response data is stored into a reactive ref. Computed properties derive display-ready values from that ref.

Filter state across all views is centralised in the `useFilters` composable (`client/src/composables/useFilters.js`), ensuring consistent query params are sent to every endpoint. See [[client]] for the full filter system detail.

## Data Architecture

All runtime data is static JSON loaded into process memory at server startup. `server/mock_data.py` reads every file under `server/data/` and exposes the contents as plain Python lists and dicts. There is no database, no ORM, no cache, and no persistence between restarts.

| Store | Technology | Port | Owned By | Notes |
|-------|------------|------|----------|-------|
| Fixture files | JSON on disk | n/a | server | Read once at startup into memory; never written at runtime |
| In-memory data | Python list/dict | n/a | server | Filtered per-request by `apply_filters` / `filter_by_month` in `server/main.py` |

Schema management: none. When the shape of a fixture in `server/data/` changes, the corresponding Pydantic response model in `server/main.py` must change in lockstep. A mismatch is not caught at startup — it raises a validation error at response serialisation time, producing a 500 for the affected endpoint.

Revenue goal constants (`$800K/month` for single-month views, `$9.6M` year-to-date for all-months views) are computed on the client side against the aggregated figures returned by `GET /api/dashboard/summary`. They are not stored in any data fixture.

Migration tooling: none — the in-memory fixture design eliminates the concept of migrations entirely.

## Deployment Topology

(not determined by analysis)

No deploy targets, Dockerfile, container registry references, or cloud provider configuration were discovered in the repository. The project is a workshop demo; deployment beyond local development is not represented.

## Local Development

The full local stack is started with a single wrapper script:

```bash
./scripts/start.sh
# Backend:  http://localhost:8001
# Frontend: http://localhost:3000
# API Docs: http://localhost:8001/docs
```

`scripts/stop.sh` resets the environment (kills both servers).

Manual startup for each service in isolation:

**Backend (`server/`, port 8001):**
```bash
cd server
uv venv && uv sync
uv run python main.py
```

**Frontend (`client/`, port 3000):**
```bash
cd client
pnpm install
pnpm run dev
```

Runtime version pins: (not determined by analysis). Consult `server/pyproject.toml` and `client/package.json` for the enforced Python and Node version constraints.

There are no emulators, no local database containers, and no message broker to start — the server reads JSON fixtures from disk into memory on launch.

## Automation & CI

The primary automation interface is two shell scripts at the repository root:

| Script | Purpose | Source |
|--------|---------|--------|
| `scripts/start.sh` | Starts both the backend and frontend dev servers concurrently | `scripts/start.sh` |
| `scripts/stop.sh` | Stops both servers and resets the environment | `scripts/stop.sh` |

There is no Makefile, Justfile, or Taskfile. The software version control host is GitHub, and CI is GitHub Actions under `.github/workflows/`. There is no build or test pipeline; both workflows run Claude Code via `anthropics/claude-code-action`:

| Workflow | Trigger | What it does | Source |
|----------|---------|--------------|--------|
| Claude Code Review | PR opened / pushed / reopened | Runs the QAF `/pr-reviewer` skill and posts one formal review via `gh api` | `.github/workflows/claude-code-review.yml` |
| Claude Code | `@claude` in an issue, PR comment or review | Runs Claude with QAF skills and `gh`, `git`, `node`, `python3`, `pnpm`, `uv`, `curl` allowed; installs headless Chromium for the Playwright MCP so it can check the running app | `.github/workflows/claude.yml` |

Build commands per service:

| Service | Command | Source |
|---------|---------|--------|
| client | `cd client && pnpm run build` | `client/package.json` |
| server | `cd server && uv build` | `server/pyproject.toml` |

## Coupling Hotspots

The structure analyzer identified four high-coupling hubs and no bridges:

- `client/src/composables/useFilters.js` (module, score 10)
- `client/src/composables/useAuth.js` (module, score 10)
- `client/src/composables/useI18n.js` (module, score 10)
- `client/src/api.js` (module, score 8)

All four hubs are in the client service. `useFilters.js` is the central filter-state composable consumed by every view that calls the server API — changes to filter shape ripple through all views and all API calls simultaneously. `useAuth.js` and `useI18n.js` are similarly cross-cutting composables shared across the view layer. `client/src/api.js` is the sole HTTP client wrapper; every view that fetches data imports from it, making it the single point of change for any API contract update.

There are no bridge nodes detected between client and server at the module level — the HTTP boundary is the only coupling point between the two services.
