---
document_type: service
content_type: descriptive
summary: >-
  The client is a Vue 3 single-page application running on port 3000 that
  renders the operator-facing dashboards: inventory, orders, demand forecasting,
  backlo...
last_updated: '2026-11-12T18:06:44.520Z'
tags:
  - service
  - javascript
  - frontend
  - vue
service_id: client
---
# Service: client

## Purpose

The client is a Vue 3 single-page application running on port 3000 that renders the operator-facing dashboards: inventory, orders, demand forecasting, backlog, and spending analytics. It is the sole consumer of the [[server]] API, translating user filter selections into parameterized HTTP requests and projecting the returned JSON into reactive display data.

## Overview

The application is built with Vue 3 Composition API and bundled by Vite. Route-level screens live in `client/src/views/`, reusable widgets in `client/src/components/`, the HTTP layer in `client/src/api.js`, cross-cutting state hooks in `client/src/composables/`, and translation bundles in `client/src/locales/`. Global styling is declared in `client/src/App.vue`.

A typical request begins when a user adjusts one of the four shared filter controls (time period, warehouse, category, order status). The changed values flow into reactive refs, which trigger calls through `client/src/api.js`. That module uses `axios` to issue HTTP GET requests to [[server]], serializing the active filters as query parameters. The returned JSON is stored in raw refs (`allOrders`, `inventoryItems`, and so on); computed properties then derive every view-specific projection from those refs — the Vue reactivity graph is the data model, not a separate store.

The Facts, API & Contracts, and Notable Patterns tables on this page enumerate the endpoints, filter semantics, and framework versions. Two per-endpoint caveats worth knowing before reading those tables: inventory routes carry no time dimension (the `month` filter is silently ignored by [[server]]), and demand/backlog endpoints accept no filters at all.

## Facts

| Fact | Value |
| --- | --- |
| Type | frontend |
| Language | javascript |
| Path | client |
| Package manager | pnpm |
| Manifest | client/package.json |
| Frameworks | Vue 3; UI: Vite |
| Port | 3000 |

## File Placement

| Artefact | Location | Example |
| --- | --- | --- |
| Vue view | `client/src/views/{view}.vue` | `client/src/views/Dashboard.vue` |
| Vue component | `client/src/components/{Component}.vue` | `client/src/components/FilterBar.vue` |
| API client | `client/src/api.js` | `client/src/api.js` |
| Vue composable | `client/src/composables/{useName}.js` | `client/src/composables/useFilters.js` |
| i18n locale | `client/src/locales/{lang}.js` | `client/src/locales/en.js` |
| Utility module | `client/src/utils/{name}.js` | `client/src/utils/currency.js` |
| App entry | `client/src/main.js` | `client/src/main.js` |
| Vite config | `client/vite.config.js` | `client/vite.config.js` |

## API & Contracts

- Protocols: rest

| Step | Where | Note |
| --- | --- | --- |
| User interacts with Vue view | `client/src/views/InventoryView.vue:InventoryView` | User changes filter dropdowns; reactive refs update. |
| Call API helper | `client/src/api.js:getInventory` | axios GET request built with current filter query params. |
| Receive and store response | `client/src/api.js:getInventory` | Resolved axios response data stored into reactive ref for computed properties to derive display data. |

## Configuration

| Setting | Value |
| --- | --- |
| Dev port | 3000 |

## Dependencies

| Group | Packages |
| --- | --- |
| production | `axios`, `vue`, `vue-router` |

## Testing

No automated tests yet — candidate for a new test suite.

## Conventions & How-To

### Code Rules

- Use stable domain identifiers (`sku`, `month`, `id`) as `v-for` keys — never array index — because computed arrays can reorder and index-keyed vnodes will produce subtle rendering bugs.
- Validate date values before calling `.getMonth()` or any other `Date` method; the mock data can include strings that do not parse cleanly.
- Store raw API responses in refs and derive display data through `computed` properties; do not manipulate source-of-truth refs directly inside template event handlers.
- Raw refs holding server response arrays should be named after the domain entity (`allOrders`, `inventoryItems`); derived/filtered values should be named to reflect the transformation (`filteredOrders`, `lowStockItems`).

### Multi-File Workflows

- Any new view requires a `.vue` file under `client/src/views/` and a corresponding route entry; check `client/src/router/` when adding a view so the route is registered.
- Filter state that must survive across views belongs in a composable under `client/src/composables/`, not duplicated per-view.
- See [[conventions/project]] for the rule on delegating `.vue` file creation and significant modification to the `vue-expert` subagent.

### Observability & Ops

- The dev server runs on port 3000; the backend is expected at port 8001. Both ports are fixed — do not parameterize them without updating the Playwright test targets documented on [[conventions/project]].
- Build the client with `cd client && pnpm run build`; use `./scripts/start.sh` to launch both services together for local development.

### Boundaries & Dependencies

- The client must reach [[server]] only through the HTTP API via `client/src/api.js`; no direct import of server-side modules is permitted. See [[conventions/project]] for the canonical statement of this boundary rule.
- Do not introduce a Pinia/Vuex store for demo-scoped state; the refs-plus-computed pattern is intentional and keeps the reactivity graph as the single source of truth.

Project-wide rules live in [[conventions/project]].
