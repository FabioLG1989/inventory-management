---
document_type: index
content_type: descriptive
summary: >-
  Summary catalog for the inventory-management LLM wiki — one line per page,
  frontmatter inline.
last_updated: '2026-11-12T18:06:44.520Z'
related:
  - ARCHITECTURE.md
  - SERVICES.md
---
# inventory-management LLM Wiki

Summary catalog of every page in this wiki. Each line carries the page summary, document type, tags, and related pages — frontmatter inline so a single read of `index.md` serves Tier 1 retrieval.

## Getting started

- [getting-started](getting-started.md) — *getting-started* — How to run, set up, build, and test this project locally — README setup reproduced verbatim plus wrapper / package-manager / CI command tables, each with its source. **Tags:** getting-started, setup, commands.

## Architecture

- [ARCHITECTURE](ARCHITECTURE.md) — *architecture* — The repository is a two-service co-located layout — classified as `polyrepo` by the structure analyzer, but practically a single-repo with two sibling servic... **Tags:** architecture, topology, javascript, vue, python.

## Conventions

- [conventions/project](conventions/project.md) — *conventions, prescriptive* — The single home for project-wide conventions — shared dependencies, tooling, quality gates, and service boundaries that recur across services, plus genuinely repo-wide rules; the per-service pages reference it. **Tags:** conventions, project.

## Services catalog

- [SERVICES](SERVICES.md) — *services* — Catalog of services detected in this project with links to service docs. **Tags:** services, catalog. **Related:** [[ARCHITECTURE]].

## Per-service docs

- [client](services/client.md) — *service* — The client is a Vue 3 single-page application running on port 3000 that renders the operator-facing dashboards: inventory, orders, demand forecasting, backlo... **Tags:** service, javascript, frontend, vue.
- [server](services/server.md) — *service* — The server is a Python FastAPI service running on port 8001 that exposes filtered REST endpoints over in-memory mock data. It serves as the sole backend for ... **Tags:** service, python, backend, fastapi.

## How agents should use this

- Start with this index. Read the 1–3 page bodies whose summaries match your question.
- Follow `**Related:**` `[[wikilinks]]` only when the matched pages reference them.
- Stop wikilink traversal at depth 2.
- If the wiki does not answer your question, run targeted Grep/Read on the source — never re-read the wiki cover-to-cover.
