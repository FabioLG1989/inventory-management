# Karpathy LLM-Wiki Pattern — Design Reference

This document distills Andrej Karpathy's LLM-Wiki concept and its derivatives into the design contract for `wiki-ingest-external-docs` and `wiki-refresh`. It is intended as a stable reference that the LLM ingestion agents can cite when making routing and deconfliction decisions.

**Primary source:** Karpathy's original gist and blog discussion at https://gist.github.com/karpathy/  
**Related art:** OpenAI AGENTS.md spec (https://cdn.openai.com/spec/agents-md/v0.1.0/agents-md.pdf), Continue.dev context providers (https://docs.continue.dev/customization/context-providers), DeepWiki (https://deepwiki.com), Datadog's monorepo agents post (https://www.datadoghq.com/blog/engineering/monorepo-agents/).

---

## 1. The four-layer model

Every LLM-Wiki deployment has exactly four layers. Collapsing or skipping any layer creates failure modes at scale.

### 1.1 `raw/` — immutable external sources

`raw/` holds files that the LLM never writes and never edits. These are:

- External documents ingested by `wiki-ingest-external-docs` (PDFs, Notion exports, Confluence pages, GitHub issues, API specs).
- Files produced by deterministic analyzers during `initialize-project` (structured JSON outputs from the four Phase 1 analyzers).

Immutability is enforced by convention, not file permissions. The `wiki-refresh` skill reads `raw/` but never modifies it. Only the ingestion skill writes to `raw/`, and only by appending or overwriting content-addressed files (idempotent).

Content addressing (SHA-256 prefix in filename) is essential: it prevents duplication, enables deduplication across runs, and gives each file a stable identity that survives rename or re-upload of the source.

### 1.2 `wiki/` — LLM-owned markdown

`wiki/` is the only layer the LLM writes. It contains:

- `index.md` — the routing table. One line per page; the LLM uses it to decide which pages to update when new evidence arrives.
- `ARCHITECTURE.md` — cross-cutting system architecture.
- `SERVICES.md` — service catalog.
- `wiki/services/<service-id>.md` — one page per service, written by `initialize-project` Phase 4 and updated by `wiki-refresh`.

The LLM edits `wiki/` pages surgically — preserving accurate prose, updating only drifted facts. It never regenerates from scratch. This is the "tireless knowledge engineer" model: the LLM is a careful editor, not a bulk generator.

### 1.3 `index.md` — the router

`index.md` is a flat routing table, not a hierarchical outline. Its job is to let the LLM answer: "Given this evidence (git diff, external doc), which page should I update?" The routing decision is made by the LLM using `index.md` as its only lookup structure — no rigid frontmatter mapping, no hard-coded rules.

Each line in `index.md` carries: page path, one-line summary, document type, tags, related pages. This is enough for the LLM to route reliably across dozens of pages. Beyond ~200 pages, the index should be split into sub-indexes per domain.

### 1.4 `log.md` — history

`log.md` records every refresh: which pages were updated, which evidence triggered the update, what was changed. It is append-only. The LLM never reads `log.md` during a refresh run (doing so would pollute the evidence pack with historical noise). `log.md` is for human auditors and post-hoc debugging only.

---

## 2. The three operations

### 2.1 Ingest

Ingestion follows the **export-first** principle. The wiki never calls external APIs to fetch content. Instead:

1. The user (or an automated trigger) exports the document to a local file.
2. `wiki-ingest-external-docs` converts, hashes, stages to `raw/external/`, and updates `manifest.json`.
3. `wiki-refresh` reads `manifest.json` on the next run and absorbs the content.

Export-first has three practical advantages: it avoids auth/compliance complexity, it makes every staged file diffable and auditable in version control, and it decouples the ingestion cadence from API availability.

### 2.2 Query

Query operations (what does the wiki say about X?) operate on `wiki/` only. Tools like Continue.dev context providers, DeepWiki search, or an agent's Grep all target `wiki/`, never `raw/`. This separation means the LLM-owned layer is always a clean, curated view — no raw noise, no duplicate content from multiple ingestion runs.

### 2.3 Lint

The lint operation validates the wiki's internal consistency:

- **Contradiction detection.** Claims across pages should not contradict each other. `wiki-ingest-external-docs` runs a local lint pass (the `lint-and-deconflict` agent) before committing a staged file to the manifest.
- **Staleness detection.** Pages are marked with `last_updated`. Pages not refreshed in a configurable window are candidates for a re-review pass.
- **Stale retrieval reference rate.** Elastic SLO: warn when >10% of `raw/` entries have `last_verified` older than 6 months; page when >25%. This metric surfaces sources that have likely changed upstream.
- **Orphan detection.** Files in `raw/external/` without a `manifest.json` entry are invisible to `wiki-refresh`. The lint step flags them.

---

## 3. Export-first, not API-fetch

The distinction matters on 6000+ developer machines:

- API connectors require per-developer OAuth tokens. Rotating them at scale is an operational burden.
- API responses vary by user permissions. Two developers may fetch different versions of the same Confluence page.
- API connectors create a runtime dependency on the external system's uptime. A Confluence outage blocks the wiki refresh.
- Exported files are committed to the repo, making every wiki refresh a reproducible, auditable operation.

The only exception: MCP tools (Notion MCP, Atlassian MCP, Drive MCP) that are already wired into the developer's local tool environment are acceptable as export mechanisms — they run as the developer, on the developer's machine, and produce a local file. This is still export-first; the MCP tool does the export, the skill stages the result.

---

## 4. LLMs as tireless knowledge engineers

The "tireless knowledge engineer" framing is Karpathy's. It has a precise operational meaning:

- The LLM does not summarize or paraphrase freely. It edits existing pages conservatively, preserving accurate prose.
- The LLM does not invent structure. It follows the four-layer model mechanically.
- The LLM does not decide what is important. The routing table (`index.md`) and the evidence pack (git diff + external docs) define the decision space.
- The LLM does execute repetitive review at a scale no human can sustain: reading every diff, checking every page, updating only what drifted, doing this after every ticket merge.

The conservatism rule in `wiki-refresh` ("no change is a successful outcome") is the operational guard against the LLM overstepping this role.

---

## 5. Citations carry stable IDs

Every `raw/external/` file has a `content_sha256` in its frontmatter. When `wiki-refresh` absorbs a staged document into a wiki page, the LLM should cite it using the filename (which carries the 8-char sha prefix) rather than the original source URL. This citation is stable: the URL may rot, the Confluence page may move, but the staged file (and its hash) never changes.

Example citation in a wiki page:

```markdown
The OAuth 2.0 token exchange flow is documented in the vendor spec
([a3f7b209-stripe-oauth-api-spec.md](../raw/external/a3f7b209-stripe-oauth-api-spec.md)).
```

---

## 6. Multi-repo: nearest-wins precedence

The nearest-wins rule (from AGENTS.md and Datadog's monorepo agents post) applies to wiki state:

- Each child repo has its own `docs/llm-wiki/.state.json` and `docs/llm-wiki/raw/external/manifest.json`.
- A document ingested without `--global` goes into the closest ancestor repo's wiki tree.
- `wiki-refresh` iterates per-repo, using each repo's `.state.json` as its baseline.
- The global tree (`docs/llm-wiki/global/`) holds documents that span all repos — vendor SDKs, company-wide RFCs, cross-cutting architecture decisions.

On each refresh run, `wiki-refresh` checks both the per-repo manifest and the global manifest. Global manifest entries appear in every repo's evidence pack.

This mirrors how AGENTS.md works: the nearest ancestor's instructions take precedence over the global parent. For wiki routing, the nearest-repo manifest entry takes precedence over the global entry when both describe the same service.

---

## 7. Failure modes

These are the documented failure modes in production LLM-Wiki deployments. Each has a corresponding mitigation in this framework.

### 7.1 Wiki bloat

**Symptom:** Pages grow on every refresh; the index becomes too large for the LLM to navigate reliably.  
**Cause:** The conservatism rule is not enforced; the LLM adds detail on every pass.  
**Mitigation:** The downgrade guard in `wiki-refresh` Phase 6 (`downgraded_to_skip`) and the high-level-only rule in Phase 5 together enforce maximum altitude. Pages should only document public contracts, not implementation details.

### 7.2 Stale content

**Symptom:** Pages record facts that are months or years out of date.  
**Cause:** `wiki-refresh` was not run after significant changes, or the git diff was too large for the LLM to notice all affected pages.  
**Mitigation:** `/implement-ticket` Phase 9 triggers `wiki-refresh` after every ticket merge. The stale retrieval reference rate SLO catches pages not refreshed in 6 months.

### 7.3 Conflicting sources

**Symptom:** Two wiki pages record contradicting facts about the same service; `raw/external/` contains a document that contradicts the wiki.  
**Cause:** Ingestion without lint, or concurrent wiki edits.  
**Mitigation:** The `lint-and-deconflict` agent blocks staging of contradicting documents. The `wiki-refresh` Phase 5 conservatism rule prevents the refresh from propagating a contradiction into a new page.

### 7.4 Agent over-trust

**Symptom:** The LLM updates wiki pages based on a staged document with low authoritativeness (e.g., a meeting note with an unverified claim), overwriting more authoritative existing content.  
**Cause:** The evidence pack does not communicate authoritativeness levels; the LLM treats all evidence equally.  
**Mitigation:** Each manifest entry carries `authoritativeness` and `source_of_truth`. The `wiki-refresh` Phase 3.5 prompt instructs the LLM to weight evidence by authoritativeness: `source_of_truth: true` overrides; `meeting-note` is advisory only and should not overwrite `rfc` or `runbook` claims.

### 7.5 Index drift

**Symptom:** `index.md` no longer reflects the actual pages on disk; routing becomes unreliable.  
**Cause:** Pages were deleted or renamed outside of `wiki-refresh`; or `index.md` was manually edited inconsistently.  
**Mitigation:** `wiki-refresh` surgically patches `index.md` in Phase 6 whenever a page's `summary`/`tags`/`related` changes. A lint pass can detect orphaned index entries.

---

## 8. Quick-reference decision table

| Question | Answer |
|---|---|
| Should I call the Confluence API to fetch a page? | No. Export to a local file, then ingest. |
| Can I write directly to `wiki/`? | Only `wiki-refresh` writes `wiki/`. Ingest writes only `raw/`. |
| Where do cross-cutting vendor docs go? | `docs/llm-wiki/global/raw/external/` via `--global`. |
| A staged doc contradicts the wiki. What happens? | `lint-and-deconflict` blocks staging; user must resolve. |
| A meeting note conflicts with an RFC. Which wins? | RFC wins; `authoritativeness` field drives precedence. |
| Re-running ingest on the same file — is it safe? | Yes. SHA-256 content addressing makes it idempotent. |
| Where is the routing table? | `docs/llm-wiki/wiki/index.md`. |
| What advances `last_refresh_at`? | `wiki-refresh` Phase 7 (write `.state.json`), after all page updates succeed. |
