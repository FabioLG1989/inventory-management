---
name: extract-metadata
description: Extracts structured metadata from a staged markdown document to populate the manifest entry. Determines subject keywords, which service the document describes, which source files it references, how authoritative the source is, and whether it should be treated as the canonical source of truth for any claim.
---

## Objective

Read the provided staged markdown document and the project context, then return a JSON object with five metadata fields. These fields drive how `wiki-refresh` routes and weights the document when absorbing it into wiki pages.

## Input

You receive:

1. `document_content` — the full text of the staged markdown file (after frontmatter).
2. `subject_hint` — an optional user-provided keyword (may be empty string).
3. `service_ids` — a JSON array of service IDs from `framework-config.json::stack_profile.by_service` (may be empty array).

## Output format

Return strict JSON. No prose, no markdown fences. First character `{`, last character `}`.

```json
{
  "subject_keywords": ["<keyword1>", "<keyword2>"],
  "describes_service": "<service-id-or-null>",
  "describes_files": ["<relative-path1>"],
  "authoritativeness": "<rfc|runbook|code-derivative|vendor-doc|meeting-note>",
  "source_of_truth": false
}
```

Field rules:

- `subject_keywords` — 1–5 lowercase short nouns or hyphenated phrases that best describe the document's topic. Include the `subject_hint` value if provided and relevant. Examples: `["auth", "oauth2", "sessions"]`, `["payments", "stripe", "webhooks"]`, `["deployment", "kubernetes"]`.
- `describes_service` — the single service ID from `service_ids` that this document is primarily about, or `null` if the document is cross-cutting or not service-specific. Match against `service_ids` by substring if necessary (e.g., "payments service" → `"payments"`). If no confident match exists, use `null`.
- `describes_files` — a best-effort list of relative file paths that the document explicitly references (e.g., `src/auth/oauth.ts`). Empty array `[]` when none are clearly mentioned.
- `authoritativeness` — one of:
  - `"rfc"` — an IETF/W3C/ISO standard or formal specification.
  - `"runbook"` — an operational guide or incident runbook.
  - `"code-derivative"` — generated from code (API spec, auto-generated schema, OpenAPI).
  - `"vendor-doc"` — third-party vendor documentation or SDK guide.
  - `"meeting-note"` — meeting minutes, decision notes, or informal writeup.
  - Default to `"vendor-doc"` when uncertain.
- `source_of_truth` — `true` only when this document is the canonical, authoritative definition of a protocol or contract that the codebase implements (e.g., the actual RFC for a protocol, the official API spec from a third party). Default `false`.

## Tools

Use only the content provided in your input. Do not call any file-read or search tools. Do not hallucinate file paths.

## Boundaries

- Return exactly the JSON object — no surrounding text.
- Do not invent service IDs that are not in `service_ids`.
- Keep `subject_keywords` to 1–5 entries; prefer precision over breadth.
- When in doubt about `source_of_truth`, use `false` — this flag must be earned by clear evidence of canonical authority.
- If `subject_hint` is provided, it takes priority over your own inference for the first keyword in `subject_keywords`.
