---
document_type: service
content_type: descriptive
summary: >-
  The server is a Python FastAPI service running on port 8001 that exposes
  filtered REST endpoints over in-memory mock data. It serves as the sole
  backend for ...
last_updated: '2026-11-12T18:06:44.520Z'
tags:
  - service
  - python
  - backend
  - fastapi
service_id: server
---
# Service: server

## Purpose

The server is a Python FastAPI service running on port 8001 that exposes filtered REST endpoints over in-memory mock data. It serves as the sole backend for the [[client]], providing JSON responses for inventory, orders, demand, backlog, and spending domains. There is no database — all data lives in process memory, loaded at startup from JSON fixtures.

## Overview

The server is built on FastAPI with Pydantic for response validation and uvicorn as the ASGI runtime, managed via `uv`. Its data layer is intentionally thin: `server/mock_data.py` reads every JSON file under `server/data/` at import time and exposes them as plain Python lists and dicts; `server/main.py` holds all route handlers, Pydantic response models, and the CORS middleware configuration. No ORM, no migration tooling, and no persistence between restarts.

A typical request flows from the [[client]] through CORS middleware, is dispatched by FastAPI to a handler in `server/main.py`, filtered in-process by `apply_filters` and `filter_by_month` against the module-level in-memory collections, then validated against a Pydantic response model before being serialized to JSON. The full set of endpoints, their parameters, and response shapes is captured in the Facts and API & Contracts tables on this page.

Four query-parameter filters (time period, warehouse, category, order status) apply across the inventory, orders, and dashboard summary endpoints, with two constraints: the inventory endpoints carry no time dimension so the `month` filter is a no-op there, and the demand/backlog endpoints accept no filters at all. Spending resources are split into discrete sub-endpoints (summary, monthly, categories, transactions) rather than being parameterized. CORS is configured to allow all origins, methods, and headers, reflecting the demo nature of the service — see Notable Patterns on this page for details.

Revenue goal constants ($800K/month for single-month views, $9.6M year-to-date for all-months views) are UI-side computations in [[client]] against figures returned by the dashboard summary endpoint; the server itself carries no goal logic.

## Facts

| Fact | Value |
| --- | --- |
| Type | backend |
| Language | python |
| Path | server |
| Package manager | uv |
| Manifest | server/pyproject.toml |
| Frameworks | FastAPI |
| Port | 8001 |

## File Placement

| Artefact | Location | Example |
| --- | --- | --- |
| FastAPI app / REST router | `server/main.py` | `server/main.py` |
| Mock data loader | `server/mock_data.py` | `server/mock_data.py` |
| Data generator script | `server/generate_data.py` | `server/generate_data.py` |
| JSON data fixture | `server/data/{entity}.json` | `server/data/orders.json` |

## API & Contracts

- Protocols: rest
- Exposes an API: yes
- Consumed by: [[client]]

| Step | Where | Note |
| --- | --- | --- |
| Add CORS middleware | `server/main.py:app` | CORSMiddleware added via app.add_middleware; allows all origins, methods, headers during development. |
| Route to handler function | `server/main.py:get_inventory` | FastAPI matches GET /api/inventory and injects optional query params (warehouse, category). |
| Filter in-memory data | `server/main.py:apply_filters` | apply_filters and filter_by_month applied sequentially to in-memory Python lists loaded at startup. |
| Validate and serialize response | `server/main.py:InventoryItem` | FastAPI validates return value against the Pydantic response_model before sending JSON response. |

## Configuration

| Setting | Value |
| --- | --- |
| Dev port | 8001 |

## Dependencies

| Group | Packages |
| --- | --- |
| production | `fastapi`, `pydantic`, `uvicorn` |

## Testing

Representative tests:

- `tests/backend/conftest.py` — FastAPI TestClient fixture setup
- `tests/backend/test_inventory.py` — TestInventoryEndpoints.test_get_inventory_by_warehouse

Tests live in tests/backend/ and are run with pytest (config at tests/pytest.ini). There are no frontend tests — the client has no test framework installed. The only fixture infrastructure is conftest.py at tests/backend/; it wires FastAPI's synchronous TestClient and provides shared sample data fixtures (sample_inventory_item, sample_order). Tests are grouped in classes named Test<Domain>Endpoints. The pattern is: call an endpoint via client.get/post, assert HTTP status, deserialize response.json(), assert structure and filter semantics. No mocking — the in-memory data loaded at import time serves as the test dataset, so tests are integration-style against real (mock) data.

## Conventions & How-To

### Code Rules

- Keep all route handlers and Pydantic response models in `server/main.py`. Do not split them into separate modules unless the file grows to a scale that makes a single file unworkable — the current architecture is intentionally flat.
- When a JSON fixture in `server/data/{entity}.json` changes shape, update the corresponding Pydantic model in `server/main.py` in the same commit. A shape mismatch raises a validation error at response time (not request time), causing 500s that are hard to trace after the fact.
- Do not add auth, sessions, rate limiting, or persistent storage. The service is a demo surface deliberately kept thin.

### Multi-File Workflows

- Adding a new data domain requires touching three files in lockstep: the JSON fixture under `server/data/`, the loader in `server/mock_data.py`, and the route handler plus Pydantic model in `server/main.py`.
- If fixture data is generated rather than hand-authored, use or extend `generate_data.py` and commit the generated fixture — do not generate at runtime.

### Testing

- Tests live in `tests/backend/` and are run with pytest (config at `tests/pytest.ini`). Use the `backend-api-test` skill when writing or modifying these tests per [[conventions/project]].
- All tests receive a `client` fixture from `tests/backend/conftest.py` that wires FastAPI's synchronous `TestClient` against the live `app` object. Do not mock the in-memory data — the collections loaded at import time serve as the test dataset, keeping tests integration-style against real (mock) data.
- Group tests in classes named `Test<Domain>Endpoints`. The pattern is: call an endpoint via `client.get`/`client.post`, assert HTTP status code, deserialize `response.json()`, assert structure and filter semantics (e.g., every returned item satisfies the applied filter predicate).

### API & Contracts

- Filter parameters are optional query strings; handlers must tolerate their absence without error.
- The `month` filter is accepted but ignored by inventory endpoints — do not add time-dimension filtering to inventory without also adding a time field to the inventory fixtures and Pydantic model.
- Demand and backlog endpoints accept no filter parameters; do not add filter logic to those handlers.

### Boundaries & Dependencies

- The only consumer of this service is [[client]]. There are no other callers, no external service calls outbound, and no event pipeline. Keep the dependency surface flat.
- For rules on reaching this service from outside (e.g., how the client should call the API), see [[conventions/project]].

Project-wide rules live in [[conventions/project]].
