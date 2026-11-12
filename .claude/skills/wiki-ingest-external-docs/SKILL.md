---
name: wiki-ingest-external-docs
version: 1.0.0
last-updated: 2026-05-14
description: Stages external descriptive documents (PDFs, DOCX, HTML, Notion/Confluence exports, Google Drive files, GitHub issues, images) into docs/llm-wiki/raw/external/ following Karpathy's LLM-Wiki pattern — immutable raw/ layer, manifest-indexed, content-addressed. Export-first, never API-fetch. The skill validates the wiki.cache_external flag, converts the source to markdown, hashes and stages the file at a content-addressed path, extracts LLM metadata (subject, service, authoritativeness), updates the manifest and ingestion-state, then runs a lint-and-deconflict pass against existing wiki pages. After staging, /wiki-refresh consumes the manifest entries on the next run. Use when a user provides an external document that contains descriptive context the codebase alone cannot supply.
argument-hint: '<source-path-or-url> [--subject <hint>] [--repo <name>] [--global] [--dry-run]'
user-invokable: true
disable-model-invocation: false
---

# Wiki Ingest External Docs

Input: $ARGUMENTS

Stage an external document into `docs/llm-wiki/raw/external/` so that `/wiki-refresh` absorbs its descriptive context into the relevant wiki pages on the next run.

## Flags

Parse `$ARGUMENTS`:

- `<source-path-or-url>` — required. Local file path or HTTP URL. MCP-sourced inputs (Notion, Confluence, Drive, Gmail, GitHub) are resolved in Phase 2.
- `--subject <hint>` — optional keyword hint (e.g. `auth`, `service:payments`, `rfc`). Aids the `extract-metadata` agent and routes the manifest entry.
- `--repo <name>` — in a multi-repo workspace, explicitly target the named child repo. Overrides auto-detection.
- `--global` — write to `docs/llm-wiki/global/raw/external/` (for vendor docs, RFCs, cross-cutting policy that spans all repos).
- `--dry-run` — run Phases 1–4 only (validate, resolve, convert, hash); no writes, no LLM metadata call.

## Contract

- **Export-first, never API-fetch.** This skill does not call Confluence/Notion/Drive APIs directly. MCP tools (`mcp__notion_*`, `mcp__atlassian_*`, `mcp__drive_*`) export content; this skill stages what they export.
- **Content-addressed paths.** The sha256 prefix in the filename makes every staging idempotent — re-ingesting the same content lands at the same path and is a no-op.
- **Manifest is the discovery index.** `wiki-refresh` reads `manifest.json`; files without a manifest entry are invisible to it.
- **Opt-in only.** `wiki.cache_external: true` must be set in `framework-config.json`. Without it the skill stops at Phase 1 with a clear message.
- **Descriptive content only.** Redirect prescriptive content (coding rules, testing conventions, multi-file checklists) to each service page's `## Conventions & How-To` (`docs/llm-wiki/wiki/services/<id>.md`).

## Sequential phases

Execute in order. Do NOT skip ahead.

### Phase 1: Validate flag

Read `<project-root>/.claude/framework-config.json`. Check for `wiki.cache_external: true`.

If the key is absent or `false`, emit:

```
External doc caching is disabled.
Set wiki.cache_external: true in .claude/framework-config.json to enable.
```

Then finish successfully with exit 0. Do NOT write anything.

### Phase 2: Resolve source

Determine the source type from `<source-path-or-url>`:

| Pattern | Source type | Resolution |
|---|---|---|
| Local path ending `.pdf`/`.docx`/`.pptx` | office | Read file directly |
| Local path ending `.md`/`.txt` | markdown | Read file directly |
| Local path ending `.png`/`.jpg`/`.jpeg`/`.gif`/`.webp` | image | Read file directly |
| Local path ending `.html`/`.htm` | html | Read file directly |
| `https://` URL | http | Fetch via `curl -sL` or browser tool |
| `notion://` or Notion page URL | notion | Export via `mcp__notion__get_page` → markdown |
| Confluence page URL | confluence | Export via `mcp__atlassian__get_page` → markdown |
| Google Drive URL | drive | Export via `mcp__drive__export` → docx → pandoc |
| GitHub issue/PR URL (`github.com/.../issues/` or `.../pull/`) | gh-issue | Export via `gh issue view` or `gh pr view --json` |
| Gmail URL or `mailto:` | gmail | Export via `mcp__gmail__get_message` → markdown |

If the source type cannot be determined, abort: `Cannot determine source type for: <input>. Provide a local file path or a recognized URL.`

**Multi-repo target resolution (without `--global`)**:

1. If `--repo <name>` is set, locate the child repo by name under the workspace root. If not found, abort.
2. Otherwise run `git rev-parse --show-toplevel` relative to the source file's directory. If this succeeds and the result is inside the workspace, use that repo.
3. If the source file is outside any repo boundary, list all child repos and ask: `Which repo should this document be staged under? (options: <repo-list>) Or pass --global to write to the shared tree.` In non-interactive mode (no TTY), abort with: `Cannot auto-detect target repo. Pass --repo <name> or --global.`

With `--global`, the staging path is `docs/llm-wiki/global/raw/external/`. Without it, the path is `docs/llm-wiki/raw/external/` inside the resolved repo.

### Phase 3: Clean and convert

Run `scripts/clean_and_convert.sh "<source-file-or-url>" "<source-type>" "<output-dir>"`.

The script detects installed tools and falls back gracefully. Conversion rules:

| Source type | Primary | Fallback | Offline |
|---|---|---|---|
| `office` (PDF/DOCX/PPTX) | docling | unstructured | marker |
| `html` | readability + markdownify | pandoc | lynx -dump |
| `markdown` | copy verbatim | — | — |
| `notion` | MCP export (already markdown) | — | — |
| `confluence` | MCP export → markdown | confluence-markdown-exporter | — |
| `drive` | MCP export → docx → pandoc | — | — |
| `image` | VLM caption (you, using vision) | — | — |
| `gh-issue` | gh CLI JSON → inline markdown | — | — |

For `image` source type: describe the image in detail as markdown prose. If the image is an architecture diagram, produce a Mermaid block that represents the topology (use best effort; note uncertainty inline).

The script writes a single `.md` file to a temp directory and prints its path on stdout. If the conversion exits non-zero, surface the error verbatim and abort.

### Phase 4: Hash and stage

Run:

```bash
python3 scripts/hash_and_stage.py \
  --input "<converted-temp-file>" \
  --staging-dir "<docs/llm-wiki/raw/external or global path>" \
  --slug "<basename-without-extension>" \
  --source-uri "<original source-path-or-url>" \
  --source-type "<source-type>"
```

The script:
1. Computes SHA-256 of the converted file content.
2. Derives `<sha256-8chars>-<slugified-name>.md` as the output filename.
3. Checks if the file already exists at that path.
   - If yes and content matches: print `Already staged: <path>` and exit 0 (idempotent no-op).
   - If yes and content differs: overwrite (content changed since last ingest).
4. Writes the file with the mandatory frontmatter block prepended (see Frontmatter Contract below).
5. Prints the final staged path on stdout.

If `--dry-run` is active, print `[dry-run] Would stage: <path>` and finish successfully here.

### Phase 5: Extract metadata

Invoke the `agents/extract-metadata.md` sub-agent with:

- The full content of the staged markdown file.
- The `--subject` hint from `$ARGUMENTS` (may be empty).
- The list of service IDs from `framework-config.json::stack_profile.by_service` keys (for `describes_service` resolution).

The agent returns JSON:

```json
{
  "subject_keywords": ["auth", "sessions", "oauth"],
  "describes_service": "payments",
  "describes_files": [],
  "authoritativeness": "vendor-doc",
  "source_of_truth": false
}
```

If the agent call fails or returns malformed JSON, retry once with a stricter prompt. If still failing, use defaults: `subject_keywords: [<subject hint or "general">]`, `describes_service: null`, `describes_files: []`, `authoritativeness: "vendor-doc"`, `source_of_truth: false`.

Patch the staged file's frontmatter in-place with the extracted values (use surgical file edit, not full rewrite).

### Phase 6: Update manifest

Run:

```bash
python3 scripts/update_manifest.py \
  --manifest-path "<staging-dir>/manifest.json" \
  --staged-path "<staged-file-path>" \
  --source-uri "<original-source>" \
  --source-type "<source-type>" \
  --content-sha256 "<full-sha256>" \
  --subject-keywords "<comma-separated>" \
  --describes-service "<service-or-empty>" \
  --describes-files "<comma-separated-or-empty>" \
  --authoritativeness "<value>" \
  --source-of-truth "<true|false>"
```

The script reads the existing `manifest.json` (or creates it), appends/updates the entry keyed by the staged filename, and writes atomically (write to `.manifest.json.tmp`, then rename).

Manifest entry shape:

```json
{
  "<sha-prefix>-<slug>.md": {
    "source_uri": "...",
    "source_type": "pdf",
    "ingested_at": "2026-05-14T13:22:00Z",
    "last_verified": "2026-05-14T13:22:00Z",
    "content_sha256": "...",
    "subject_keywords": ["auth"],
    "describes_service": "payments",
    "describes_files": [],
    "authoritativeness": "vendor-doc",
    "source_of_truth": false
  }
}
```

### Phase 7: Update ingestion state

Run:

```bash
python3 scripts/update_state.py \
  --state-path "<repo-wiki-dir>/.ingestion-state.json" \
  --source-uri "<original-source>" \
  --content-hash "<sha256>" \
  --staged-path "<staged-file-path>" \
  [--global]
```

The `.ingestion-state.json` shape:

```json
{
  "entries": {
    "<source_uri>": {
      "staged_path": "docs/llm-wiki/raw/external/<file>.md",
      "content_hash": "<sha256>",
      "last_ingested": "2026-05-14T13:22:00Z",
      "last_verified": "2026-05-14T13:22:00Z",
      "etag": null
    }
  }
}
```

When `--global` is active, the state file is `docs/llm-wiki/global/.ingestion-state.json`.

### Phase 8: Lint and deconflict

Invoke the `agents/lint-and-deconflict.md` sub-agent with:

- The staged markdown file content.
- A list of existing wiki page summaries from `docs/llm-wiki/wiki/index.md`.
- The manifest entry created in Phase 6.

The agent returns JSON:

```json
{
  "severity": "none | warn | block",
  "contradictions": [
    { "wiki_page": "wiki/services/payments.md", "claim": "...", "conflict": "...", "recommendation": "..." }
  ],
  "stale_claims": ["..."],
  "missing_cross_refs": ["..."],
  "notes": "..."
}
```

- `severity: "none"` — proceed normally.
- `severity: "warn"` — print the contradictions/stale-claims list and proceed.
- `severity: "block"` — print the full lint output and abort. Do NOT leave a staged file that actively contradicts existing trusted wiki content. The user must resolve the conflict first (edit the doc or the wiki page, then re-ingest).

### Phase 9: Report

Print a human-readable summary:

```
Staged: docs/llm-wiki/raw/external/<file>.md
Source: <original-source>
Type:   <source-type>
Subject: <subject_keywords joined by ", ">
Service: <describes_service or "—">
Authoritativeness: <authoritativeness>
SHA-256: <full hash>
Lint: <none | N warnings | BLOCKED>

Next step: run /wiki-refresh to absorb this document into the wiki.
```

If `--dry-run`, add `(dry-run — nothing was written)` at the top.

## Frontmatter contract

Every staged markdown file carries this YAML frontmatter (written by `hash_and_stage.py`, patched by Phase 5):

```yaml
---
source_uri: <original URL or absolute path>
source_type: pdf | notion | confluence | gh-issue | docx | html | image | markdown | ...
ingested_at: <ISO 8601 timestamp>
last_verified: <ISO 8601 timestamp>
content_sha256: <full sha256 hex>
authoritativeness: rfc | runbook | code-derivative | vendor-doc | meeting-note
source_of_truth: false
subject: [auth, sessions, oauth]
describes_service: payments
describes_files: []
---
```

`source_of_truth: true` is reserved for documents that are the canonical authority for a fact (e.g., the official RFC defining a protocol the system implements). Set by the `extract-metadata` agent only when confidence is high.

## Failure modes

- `wiki.cache_external` absent or false → no-op + clear message. Exit 0.
- Source file not found → `Source not found: <path>. Aborting.` Exit non-zero.
- Conversion tool missing and no fallback available → surface installer hint from `clean_and_convert.sh`, abort.
- `extract-metadata` fails twice → use defaults, continue (warn in report).
- Lint severity `block` → print full lint output, abort. Exit non-zero.
- Staged file already exists with identical content → idempotent no-op, skip to Phase 9.
- Non-interactive multi-repo ambiguity → `Cannot auto-detect target repo. Pass --repo <name> or --global.` Exit non-zero.

## What gets touched

- `docs/llm-wiki/raw/external/<hash>-<slug>.md` (new or updated staged file)
- `docs/llm-wiki/raw/external/manifest.json` (append/update entry)
- `docs/llm-wiki/.ingestion-state.json` (append/update state)
- `docs/llm-wiki/global/raw/external/` and `docs/llm-wiki/global/.ingestion-state.json` (only with `--global`)

## What never gets touched

- `docs/llm-wiki/wiki/**` — the LLM-owned layer is only written by `/wiki-refresh`.
- Any file outside `docs/llm-wiki/`.
- Any source file the user provided.
