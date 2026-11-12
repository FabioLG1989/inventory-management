# inventory-management — LLM Wiki router

## Wiki at a glance

This directory is the LLM-owned knowledge base for **inventory-management**. 2 services: `client`, `server`.

Top-level docs under `wiki/`: `index.md`, `ARCHITECTURE.md`, `SERVICES.md`, `getting-started.md`, `conventions/project.md`. Per-service docs under `wiki/services/<id>.md`; each carries a `## Conventions & How-To` section — the prescriptive "how to write code in this service" rules. Genuinely repo-wide rules live on the `wiki/conventions/project.md` page. The generated pages carry `document_type` / `content_type` / `summary` / `last_updated` / `tags` / `related` frontmatter; most pages are `descriptive` (they describe what the project IS), and the per-service `## Conventions & How-To` sections plus the `wiki/conventions/project.md` page hold the prescriptive content. `index.md` aggregates that frontmatter inline so a single read serves Tier 1 retrieval.

## How to query (decision table)

| Question is about… | Read first | Drill into… |
|---|---|---|
| how to run, set up, build, or test the project locally | `wiki/getting-started.md` | the sourced wrapper / package-manager / CI command tables |
| architecture, topology, monorepo shape | `wiki/index.md` (summaries) → `wiki/ARCHITECTURE.md` | `wiki/services/<id>.md` for service-specific detail |
| a specific service | `wiki/SERVICES.md` (catalog) | `wiki/services/<id>.md` |
| request lifecycle, auth, middleware, integrations | `wiki/SERVICES.md` (find the relevant service) | `wiki/services/<id>.md` |
| how to write code in a service — coding conventions, testing rules, multi-file change checklists (prescriptive) | `wiki/services/<id>.md` → `## Conventions & How-To` | project-wide rules on the `wiki/conventions/project.md` page |
| how to write code across the whole project — project-wide conventions (prescriptive) | `wiki/conventions/project.md` | the per-service `## Conventions & How-To` sections for service-specific deltas |
| "I don't know which page" | `grep -i "<term>" wiki/index.md`, then read matched pages | follow `[[wikilinks]]` in matched pages, depth ≤ 2 |

## Tier discipline

1. **Tier 1 (always):** read `wiki/index.md`. One file, summaries inline. Pick the 1–3 pages whose summaries match your question.
2. **Tier 2 (on relevance):** read those page bodies. Stop.
3. **Tier 3 (on demand):** follow `**Related:**` `[[wikilinks]]` on the matched pages. Cap traversal at depth 2.
4. **Fallback:** if the wiki does not answer your question, run targeted Grep/Read on the source. Do **not** re-read the wiki cover-to-cover.

## Keeping the wiki fresh

Use `/wiki-refresh` after changes have landed to update pages whose facts drifted. The skill diffs against the per-repo commits in `.state.json`, asks an LLM to identify affected pages using `index.md` as the routing table, and surgically edits each. Use `/wiki-add-service <name>` to create a new service-doc page for a service that exists in the project but has no wiki page yet.

## Off-limits

- Do not edit `CLAUDE.md` by hand. It is regenerated whenever the active provider's wiki is rebuilt.
- Do not edit `.state.json` by hand. `/wiki-refresh` owns it.
