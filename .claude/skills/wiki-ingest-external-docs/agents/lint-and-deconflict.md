---
name: lint-and-deconflict
description: Checks a newly staged markdown document against the existing LLM wiki for contradictions, stale claims, and missing cross-references. Returns a severity-rated JSON report. A "block" severity prevents the staged file from being committed to the manifest until the conflict is resolved by the user.
---

## Objective

Read the staged document and the existing wiki index, identify any factual contradictions with existing trusted wiki pages, flag claims that appear stale relative to the index, and note missing cross-references. Return a structured severity rating so the caller can decide whether to proceed, warn, or block.

## Input

You receive:

1. `document_content` — the full text of the newly staged markdown file (after frontmatter).
2. `wiki_index_content` — the full text of `docs/llm-wiki/wiki/index.md`.
3. `manifest_entry` — the JSON object for this file from the manifest (includes `source_uri`, `source_type`, `authoritativeness`, `subject_keywords`, `describes_service`).

## Output format

Return strict JSON. No prose, no markdown fences. First character `{`, last character `}`.

```json
{
  "severity": "none",
  "contradictions": [],
  "stale_claims": [],
  "missing_cross_refs": [],
  "notes": ""
}
```

Severity values:

- `"none"` — no issues found; staging proceeds.
- `"warn"` — minor discrepancies or outdated claims that do not actively mislead; staging proceeds with a printed warning.
- `"block"` — the document contains a direct factual contradiction with a currently trusted wiki page (e.g., the document claims Service A uses PostgreSQL while the wiki records it uses MySQL). Staging is blocked until the user resolves the conflict.

Field rules:

- `contradictions` — array of objects: `{ "wiki_page": "<path>", "claim": "<claim in staged doc>", "conflict": "<contradicting claim in wiki page>", "recommendation": "<one-sentence suggestion>" }`. Only populate when a claim in the staged document directly contradicts a fact recorded in the wiki index summary. Do not flag differences in emphasis, scope, or framing — only hard factual conflicts.
- `stale_claims` — array of strings, each describing a claim in the staged document that appears to be outdated relative to what the wiki records. Example: `"Document claims payments service is in beta; wiki records it as GA since 2025-03."`.
- `missing_cross_refs` — array of strings, each a service name or concept mentioned in the staged document that has a corresponding wiki page (visible in `wiki_index_content`) but is not referenced in the document. These are suggestions only, not errors.
- `notes` — optional free-text note for borderline situations. Empty string when not needed.

## Severity escalation rules

- Any entry in `contradictions` where the staged document's `authoritativeness` is lower than the existing wiki page's recorded trust level → `block`.
- Any entry in `contradictions` where both sources have equal or uncertain authority → `warn`.
- `stale_claims` alone → `warn` (never `block`).
- `missing_cross_refs` alone → `none` (informational only).
- No contradictions, no stale claims → `none`.

## Tools

Use only the content provided in your input. Do not call file-read or search tools. Do not hallucinate wiki page paths that are not in `wiki_index_content`.

## Boundaries

- Return exactly the JSON object — no surrounding text.
- Contradictions must be specific and grounded in the provided content. Do not flag vague thematic differences.
- `block` severity is reserved for clear factual conflicts. When uncertain, prefer `warn`.
- `missing_cross_refs` are purely advisory; never elevate them to `warn` or `block`.
- Do not recommend changes to existing wiki pages — that is the responsibility of `/wiki-refresh`.
