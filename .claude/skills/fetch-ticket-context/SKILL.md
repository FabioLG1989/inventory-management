---
name: fetch-ticket-context
description: Gather all context for a Jira ticket or Linear issue — body, comments, linked URLs, attachments, and related issues — and write it to the canonical context artifact path. Context-gathering ONLY; does not plan, analyze requirements, or recommend implementation.
argument-hint: "TICKET-ID [--provider jira|linear] [--all-comments] [--include-bots] [--include-status-changes] [--refresh-external]"
---

# Fetch Ticket Context

## Scope (load-bearing)

This skill **only gathers context**. It does NOT plan, perform
requirements analysis, generate BDD scenarios, propose implementation
steps, or recommend code changes. Planning is the planner agent's job
(the planning phase of `/create-implementation-plan`); implementation
is the `implementer-generic` agent's job (`/implement-ticket` Phase 4).

Concretely the skill produces ONE artifact at the canonical path:

```
$ARTIFACTS_DIR/context/ticket-context.md
```

(where `$ARTIFACTS_DIR = <projectPath>/<TEMP_DIR>/tickets/<TICKET_ID>/artifacts/`).

The artifact contains the following seven sections, in this exact order:

1. `## Ticket` — id, title, type, status, priority, assignee, sprint, epic, labels, plus a `comments:` counter line and an `artifact-size:` line
2. `## Description` — body verbatim
3. `## Acceptance Criteria` — extracted as a list (best effort; mark
   `(not specified)` when the field is empty)
4. `## Comments` — chronological, each with `[#commentId]`, author + timestamp, optional metadata sub-bullets (mentions, ticket-refs, external-links count), then the body. Header carries an objective counter ("47 fetched · 32 shown · 12 bots hidden · 3 status-changes hidden") AND a synthesis hint for downstream readers ("most recent wins on conflict")
5. `## Linked Resources` — every URL found in description / comments,
   paired with fetched content for Confluence / Notion / Figma frames
   when the integration is reachable. Each entry carries an `Origin:`
   line (`description` or `comment #NNNN (author, date)`). Mark unreachable
   links explicitly (`⚠️ unreachable: 403 / 404 / network`).
6. `## Attachments` — any attached files copied to
   `$ARTIFACTS_DIR/context/attachments/<filename>` with an inline
   reference (no inline base64 dumps).
7. `## Related Tickets` — Blocking / Depends on / Blocked by, ids only

Out of scope and explicitly forbidden:

- ❌ Generating an implementation plan or step list
- ❌ Producing risk assessments, BDD scenarios, INVEST checks
- ❌ Recommending an implementer agent or files to create
- ❌ Classifying comment intent, pairing Q&A, deriving decisions
- ❌ Writing anywhere outside `$ARTIFACTS_DIR/context/`

The context-gathering caller in `/create-implementation-plan` and the
Phase 1 caller in `/create-sdd-ticket` (for Jira or Linear input) both consume
the artifact at the path above; downstream phases never re-fetch.

## Prerequisites

- **Atlassian MCP**: Official remote server with OAuth (for Jira and Confluence)
- **Linear MCP**: Project-scoped server with OAuth (for `--provider linear`)
- **Notion MCP**: Official remote server with OAuth (for Notion)

Setup these servers with:

```bash
claude mcp add atlassian https://mcp.atlassian.com/v1/sse --transport sse
claude mcp add --transport http --scope project linear https://mcp.linear.app/mcp
claude mcp add notion https://mcp.notion.com/mcp --transport http
```

Each server's live tool schema is authoritative for tool and argument names —
inspect it before calling. Never fall back to an SDK, REST, or GraphQL transport
when a tool call fails.

## Usage

Provider selection is explicit. It is never inferred from an identifier such as
`ABC-123`; omitting `--provider` preserves Jira behavior.

```bash
# Jira (default)
/fetch-ticket-context PROJ-123

# Linear
/fetch-ticket-context ENG-123 --provider linear
```

**URL Parsing:** If a full URL is provided, the skill will automatically extract the ticket key using this pattern:

- Pattern: `https://*.atlassian.net/browse/{TICKET-KEY}`
- Example: `https://acme.atlassian.net/browse/PROJ-123` → extracts `PROJ-123`

### Flags

| Flag | Default | Description |
|------|---------|-------------|
| `--provider jira\|linear` | `jira` | Select the tracker explicitly. |
| `--all-comments` | off (cap at 50 most recent) | Jira only. Lift the `max_comments` cap. Use only when downstream truly needs every comment. |
| `--include-bots` | off | Jira only. Keep bot/integration comments (Slack, Jenkins, GitHub, Bitbucket, Bamboo). |
| `--include-status-changes` | off | Jira only. Keep status-change auto-comments (already in changelog by default). |
| `--refresh-external` | off | Bypass the external-doc cache for this run; always re-fetch external docs. |

## Workflow

### Phase 0: Select provider

Validate `--provider` as exactly `jira` or `linear`; default to `jira`.
Set `PROVIDER`, `TICKET_ID`, and `$ARTIFACTS_DIR` once. For Jira URLs,
extract the issue key. For Linear, require the exact issue identifier and do not
infer the provider from its shape.

### Phase 1: Fetch and normalize the ticket

For `jira`, follow the existing Jira adapter below.

For `linear`, call the Linear MCP issue-get and comment-list operations for the
exact identifier supplied. Preserve description and comment bodies as native
Markdown, set `ticket_updated` from Linear's issue update timestamp, and
normalize the response to the same working fields used by Phase 5. Missing
Jira-only fields such as sprint or epic become `(not specified)`. Keep an empty
comment collection when there are no comments. Then continue at Phase 2;
Jira-specific pagination and ADF conversion do not apply, and the comment-control
flags have no effect.

#### Jira adapter

Call the Atlassian MCP issue-get operation. Request the ticket with these
parameters:

- `fields`: `summary,description,priority,assignee,labels,comment,issuelinks,status,parent,customfield_*`
- `expand`: `renderedFields,names` — `renderedFields` returns description/comments as HTML so we can convert to markdown cleanly. Do NOT expand `changelog`: Jira's changelog preserves the full body of every deleted comment in `histories[].items[].fromString` (where `field == "Comment"` and `toString == ""`). Including it in the response leaks deleted-comment bodies into the LLM context and they end up treated as live answers during synthesis.
- `comment_limit`: high enough to bring the first page (Phase 1a handles pagination beyond that)

```bash
# Pseudo-code — the real call is the Atlassian MCP issue-get operation:
ticket_data=$(fetch_jira_issue "$JIRA_KEY" \
    --fields "summary,description,priority,assignee,labels,comment,issuelinks,status,parent,customfield_*" \
    --expand "renderedFields,names")

# Extract top-level fields
summary=$(echo "$ticket_data" | jq -r '.fields.summary')
description=$(echo "$ticket_data" | jq -r '.renderedFields.description // .fields.description')
acceptance_criteria=$(echo "$ticket_data" | jq -r '.fields.customfield_10XXX // "Not specified"')
priority=$(echo "$ticket_data" | jq -r '.fields.priority.name')
assignee=$(echo "$ticket_data" | jq -r '.fields.assignee.displayName // "Unassigned"')
labels=$(echo "$ticket_data" | jq -r '.fields.labels | join(", ")')
sprint=$(echo "$ticket_data" | jq -r '.fields.customfield_sprint[0].name // "No sprint"')
epic_link=$(echo "$ticket_data" | jq -r '.fields.parent.key // "No epic"')
ticket_updated=$(echo "$ticket_data" | jq -r '.fields.updated')
```

#### 1a. Comment pagination

The issue response carries the first page of comments inline. If
`comment.total > comment.maxResults`, fetch the remaining pages with the MCP
comment-list operation, accumulating results:

```bash
total_comments=$(echo "$ticket_data" | jq -r '.fields.comment.total')
max_per_page=$(echo "$ticket_data" | jq -r '.fields.comment.maxResults')
collected_comments=$(echo "$ticket_data" | jq -c '.fields.comment.comments')

if [[ "$total_comments" -gt "$max_per_page" ]]; then
    start_at=$max_per_page
    while [[ "$start_at" -lt "$total_comments" ]]; do
        # Next page via the MCP comment-list operation, `expand=renderedBody`
        page_comments=$(fetch_jira_comments_page "$JIRA_KEY" \
            --start-at "$start_at" \
            --max-results 100 \
            --expand "renderedBody")
        collected_comments=$(echo "$collected_comments" "$page_comments" | jq -s 'add')
        start_at=$((start_at + 100))
    done
fi
```

#### 1b. Normalize each comment

Build a normalized in-memory representation per comment. This shape is
internal — it never appears as JSON in the artifact; it drives the
markdown render in Phase 5.

```jsonc
{
  "id": "10042",
  "author": { "accountId": "...", "displayName": "Jane Doe", "accountType": "atlassian" },
  "created": "2026-05-10T14:32:00Z",
  "updated": "2026-05-10T14:35:00Z",
  "body_markdown": "<rendered body in markdown>",
  "body_plain": "<plain text for regex>",
  "mentions": [{ "accountId": "...", "displayName": "John Smith" }],
  "ticket_refs": ["PROJ-99", "PROJ-120"],
  "external_links": { "notion": [...], "confluence": [...], "figma": [...], "other": [...] },
  "is_bot": false,
  "is_status_change": false,
  "filtered": false,
  "filter_reason": null
}
```

Per-field rules:

- **`body_markdown`**: prefer `renderedBody` (HTML) → markdown via a
  simple HTML-to-markdown transform. If only ADF JSON is present,
  convert directly covering at least `paragraph`, `heading`,
  `bulletList`, `orderedList`, `codeBlock`, `inlineCode`, `link`,
  `mention`, `emoji`, `mediaSingle`. For any unsupported node type,
  include the plain text of the subtree and append `_(partial conversion)_`
  to `body_markdown`. Never abort processing on a single comment.
- **`mentions`**: ADF marks mentions as `{ "type": "mention", "attrs":
  { "id": "<accountId>", "text": "@..." } }`. Preserve `attrs.id` as
  `accountId` when present, and derive `displayName` from the embedded
  mention text in `attrs.text` (for example, strip a leading `@` from
  `@John Smith` to produce `John Smith`). If `attrs.text` is missing or
  empty, fall back to `@unknown-user` and continue.
- **`ticket_refs`**: regex `\b[A-Z][A-Z0-9]+-[0-9]+\b` over `body_plain`.
  Enrichment (summary/status of referenced tickets) happens in Phase 4.
- **`is_bot`**: true when `author.accountType == "app"` OR `author.displayName`
  matches the bot blacklist (case-insensitive contains): `Slack`, `Jenkins`,
  `GitHub`, `Bitbucket`, `Bamboo`.
- **`is_status_change`**: true when `body_plain` matches `^Status changed:`
  (Jira's auto-comment prefix on transitions). Localized prefixes — e.g.
  `^Estado cambiado:` for Spanish sites — should be added here if a target
  site uses them. Do NOT cross-reference the changelog: expanding it leaks
  deleted-comment bodies into context, which downstream synthesis then
  treats as live answers.

#### 1c. Noise filters

Apply in order. Filtered comments are NOT discarded — they stay in
memory with `filtered: true` and `filter_reason` so the counter in
`## Comments` and `## Ticket` reports accurate numbers.

| Filter | Default | Override flag | Reason |
|---|---|---|---|
| `drop_bots` | on | `--include-bots` | Bot comments are noise in 99% of tickets |
| `drop_status_changes` | on | `--include-status-changes` | Same info is already in the changelog |
| `min_length_chars` | 20 | (none) | "+1", "thanks", "ok" add nothing |
| `dedupe_quoted` | on | (none) | Strip `> ...` blocks that quote earlier comments |
| `max_comments` | 50 most recent | `--all-comments` | Token budget |

Track the counts so the header line in `## Comments` reads, for example:
`47 fetched · 32 shown · 12 bots hidden · 3 status-changes hidden`.

**Output:**

```
✓ Fetched Jira ticket: PROJ-123
  Summary: Implement OAuth2 authentication
  Comments: 47 total, 32 shown (12 bots hidden, 3 status-change hidden)
  Priority: High
  Sprint: Sprint 15
  Epic: PROJ-100 (Authentication Epic)
```

### Phase 2: Extract External Links

Run the URL regex over BOTH the description AND every shown comment's
`body_plain`. Track which document each link came from so the artifact
can mark `Origin:` per link.

```bash
declare -a notion_link_entries=()
declare -a confluence_link_entries=()
declare -a figma_link_entries=()
declare -a other_link_entries=()

all_sources=()
all_sources+=("description::$description_plain")
for comment in "${shown_comments[@]}"; do
    cid=$(echo "$comment" | jq -r '.id')
    cauthor=$(echo "$comment" | jq -r '.author.displayName')
    ccreated=$(echo "$comment" | jq -r '.created' | cut -c1-10)
    cbody=$(echo "$comment" | jq -r '.body_plain')
    all_sources+=("comment #${cid} (${cauthor}, ${ccreated})::${cbody}")
done

for src in "${all_sources[@]}"; do
    origin="${src%%::*}"
    text="${src#*::}"

    while IFS= read -r url; do
        [[ -z "$url" ]] && continue
        notion_link_entries+=("${url}|${origin}")
    done < <(echo "$text" | grep -oE 'https://[^/]*\.notion\.so/[^[:space:]]+' || true)

    while IFS= read -r url; do
        [[ -z "$url" ]] && continue
        confluence_link_entries+=("${url}|${origin}")
    done < <(echo "$text" | grep -oE 'https://[^/]*\.atlassian\.net/wiki/[^[:space:]]+' || true)

    while IFS= read -r url; do
        [[ -z "$url" ]] && continue
        figma_link_entries+=("${url}|${origin}")
    done < <(echo "$text" | grep -oE 'https://www\.figma\.com/[^[:space:]]+' || true)

    while IFS= read -r url; do
        [[ -z "$url" ]] && continue
        other_link_entries+=("${url}|${origin}")
    done < <(echo "$text" | grep -oE 'https://[^[:space:]]+' \
        | grep -v 'notion\|atlassian\.net/wiki\|figma' || true)
done
```

The origin string is preserved through Phase 3 fetching and lands in
`## Linked Resources` as `Origin: description` or
`Origin: comment #10042 (Jane Doe, 2026-05-10)`.

### Phase 3: Fetch External Documentation

For each discovered link, fetch the content using the appropriate skill,
preserving the `origin` tag.

#### 3a. Fetch Notion Documents

```bash
if [[ ${#notion_link_entries[@]} -gt 0 ]]; then
    echo "📄 Found Notion documentation:"
    for entry in "${notion_link_entries[@]}"; do
        url="${entry%%|*}"
        origin="${entry#*|}"
        echo "  - $url (from: $origin)"

        # Use notion-document-manager skill
        notion_content=$(fetch_notion_page "$url")

        cat >> "$ARTIFACTS_DIR/context/_external-fragments.md" <<FRAGMENT
### Notion: $url
Origin: $origin

$notion_content

---
FRAGMENT
    done
fi
```

#### 3b. Fetch Confluence Pages

```bash
if [[ ${#confluence_link_entries[@]} -gt 0 ]]; then
    echo "📚 Found Confluence documentation:"
    for entry in "${confluence_link_entries[@]}"; do
        url="${entry%%|*}"
        origin="${entry#*|}"
        echo "  - $url (from: $origin)"

        page_id=$(echo "$url" | grep -oP 'pages/\K[0-9]+')
        confluence_content=$(mcp__atlassian__getConfluencePage --page_id "$page_id")

        cat >> "$ARTIFACTS_DIR/context/_external-fragments.md" <<FRAGMENT
### Confluence: $url
Origin: $origin

$confluence_content

---
FRAGMENT
    done
fi
```

#### 3c. Handle Figma Links

```bash
if [[ ${#figma_link_entries[@]} -gt 0 ]]; then
    echo "🎨 Found Figma designs:"
    for entry in "${figma_link_entries[@]}"; do
        url="${entry%%|*}"
        origin="${entry#*|}"
        echo "  - $url (from: $origin)"

        cat >> "$ARTIFACTS_DIR/context/_external-fragments.md" <<FRAGMENT
### Figma: $url
Origin: $origin

⚠️  Manual review required. Open in browser.

---
FRAGMENT
    done
fi
```

#### 3d. Fetch Other URLs

```bash
if [[ ${#other_link_entries[@]} -gt 0 ]]; then
    for entry in "${other_link_entries[@]}"; do
        url="${entry%%|*}"
        origin="${entry#*|}"
        content=$(fetch_url_content "$url")

        cat >> "$ARTIFACTS_DIR/context/_external-fragments.md" <<FRAGMENT
### External Doc: $url
Origin: $origin

$content

---
FRAGMENT
    done
fi
```

### Phase 4: Fetch Related Tickets

For Linear, normalize any issue relationships exposed by the active MCP schema
into the same Blocking / Depends on / Blocked by lists. Use `(none)` when a
relationship type is unavailable.

```bash
blockers=$(echo "$ticket_data" | jq -r '.fields.issuelinks[] | select(.type.outward=="blocks" and .outwardIssue) | .outwardIssue.key')
dependencies=$(echo "$ticket_data" | jq -r '.fields.issuelinks[] | select(.type.inward=="is blocked by" and .inwardIssue) | .inwardIssue.key')
blocked_by=$(echo "$ticket_data" | jq -r '.fields.issuelinks[] | select(.type.inward=="is blocked by" and .inwardIssue) | .inwardIssue.key')

# Optionally enrich each id with its summary; ids alone are still acceptable per the artifact contract.
```

### Phase 5: Compose Full Context

```bash
context_file="$ARTIFACTS_DIR/context/ticket-context.md"
mkdir -p "$(dirname "$context_file")"

# Pre-compute counters for the header line
total=$total_comments
shown=$shown_count
bots_hidden=$bots_filtered_count
status_hidden=$status_changes_filtered_count

# Estimate artifact size for the size line; finalize after writing
artifact_mode="full"  # full | truncated | brief — see Token Budget below

cat > "$context_file" <<EOF
# Context for $TICKET_ID: $summary

## Ticket

- **id:** $TICKET_ID
- **title:** $summary
- **type:** $issuetype
- **status:** $status
- **priority:** $priority
- **assignee:** $assignee
- **sprint:** $sprint
- **epic:** $epic_link
- **labels:** $labels
- **comments:** $total total — $shown shown, $bots_hidden bots hidden, $status_hidden status-change hidden
- **artifact-size:** ~${tokens_est} tokens — ${artifact_mode} mode

## Description

$description_markdown

## Acceptance Criteria

$acceptance_criteria

## Comments

> $total comments fetched · $shown shown · $bots_hidden bots hidden · $status_hidden status-changes hidden$( visible_before_cap=$(( total - bots_hidden - status_hidden - ${short_hidden:-0} )); [[ "$artifact_mode" == "full" && "$shown" -lt "$visible_before_cap" ]] && echo " · max-comments cap: 50" )
> Listed chronologically. When two comments conflict on the same point, the most recent one wins (downstream synthesis rule). Comments that read as questions with no later answer remain open.

$(format_enriched_comments "$shown_comments")

## Linked Resources

$(cat "$ARTIFACTS_DIR/context/_external-fragments.md" 2>/dev/null || echo "No external links found.")

## Attachments

$(format_attachments "$ticket_data" "$ARTIFACTS_DIR/context/attachments")

## Related Tickets

**Blocking:** $(echo "$blockers" | paste -sd ', ' -)
**Depends on:** $(echo "$dependencies" | paste -sd ', ' -)
**Blocked by:** $(echo "$blocked_by" | paste -sd ', ' -)
EOF

echo "✓ Context written to: $context_file"
```

#### Enriched comment render

`format_enriched_comments` produces one block per shown comment:

```markdown
### [#10042] 2026-05-10 14:32 — Jane Doe
- mentions: @John Smith
- ticket-refs: PROJ-99, PROJ-120
- external-links: 1 Notion (see Linked Resources)

> Necesitamos soportar Google, GitHub y Microsoft.
> @John ver doc adjunta en Notion.
```

Rules:

- `[#10042]` is the literal `comment.id` from Jira — downstream readers
  (planner, SDD synthesizer) cite it as `comment #10042` to point back to
  the source.
- Sub-bullets (`mentions:`, `ticket-refs:`, `external-links:`) appear
  ONLY when they have content. Empty fields are omitted entirely — no
  `mentions: (none)` lines.
- If `body_markdown` carries the `_(partial conversion)_` marker, prefix
  the body block with `> ⚠️ ADF partial conversion — original body may render differently in Jira.`

## Output Format

Single artifact at `$ARTIFACTS_DIR/context/ticket-context.md`. Example:

```markdown
# Context for PROJ-123: Implement OAuth2 authentication

## Ticket

- **id:** PROJ-123
- **title:** Implement OAuth2 authentication
- **type:** Story
- **status:** In Progress
- **priority:** High
- **assignee:** Jane Doe
- **sprint:** Sprint 15
- **epic:** PROJ-100 (Authentication Epic)
- **labels:** backend, security, authentication
- **comments:** 47 total — 32 shown, 12 bots hidden, 3 status-change hidden
- **artifact-size:** ~18,200 tokens — full mode

## Description

Implement OAuth2 authentication flow following the industry standard...

## Acceptance Criteria

- Users can log in with Google, GitHub, Microsoft
- Refresh tokens work correctly
- Session management is secure
- All security tests pass

## Comments

> 47 comments fetched · 32 shown · 12 bots hidden · 3 status-changes hidden · max-comments cap: 50
> Listed chronologically. When two comments conflict on the same point, the most recent one wins (downstream synthesis rule). Comments that read as questions with no later answer remain open.

### [#10042] 2026-04-15 14:32 — Jane Doe
- mentions: @John Smith
- ticket-refs: PROJ-99

> Confirmed with security team: PKCE flow is mandatory for SPAs.

### [#10045] 2026-04-16 09:01 — Bob Smith
- external-links: 1 Confluence (see Linked Resources)

> Linked the OAuth provider matrix in Confluence (see Linked Resources).

### [#10052] 2026-04-18 11:20 — Carla Lead

> Agregar tests para password validation y rate limiting.

## Linked Resources

### Confluence: OAuth Provider Matrix
URL: https://acme.atlassian.net/wiki/spaces/ENG/pages/12345
Origin: description

[Full Confluence content fetched and included here...]

### Notion: Design Specification
URL: https://notion.so/acme/oauth-redesign-abc123
Origin: comment #10042 (Jane Doe, 2026-04-15)

[Full Notion content fetched and included here...]

### Figma: Login Flow Mockups
URL: https://figma.com/file/login-flow
Origin: description

⚠️ Manual review required (Figma frames cached at $ARTIFACTS_DIR/context/figma/login-flow/).

## Attachments

- [oauth-sequence-diagram.png]($ARTIFACTS_DIR/context/attachments/oauth-sequence-diagram.png)

## Related Tickets

**Blocking:** PROJ-120, PROJ-121
**Depends on:** PROJ-99
**Blocked by:** (none)
```

Downstream phases consume this artifact path; nobody re-fetches the
ticket from its provider. The section names and ordering are a frozen
contract — `planner` and `create-sdd-ticket` parse the artifact by
section heading, so changes here MUST be coordinated.

## Error Handling

### Missing Ticket

```bash
if [[ -z "$ticket_data" ]]; then
    echo "❌ Ticket not found: $TICKET_ID ($PROVIDER)"
    echo "Verify ticket key and permissions"
    exit 1
fi
```

### Permission Denied on External Docs

```bash
# For Notion
if [[ "$notion_content" == *"403"* ]]; then
    echo "⚠️  Cannot access Notion page (permission denied)"
    echo "Grant bot access: Settings → Connections → Notion MCP"
    # Continue with other docs; mark the entry as unreachable in the artifact
fi

# For Confluence
if [[ "$confluence_content" == *"403"* ]]; then
    echo "⚠️  Cannot access Confluence page (permission denied)"
    echo "Check Confluence permissions for bot user"
fi
```

### Comment ADF Conversion Failures

If a comment's ADF body contains unsupported node types, fall back to
the plain-text subtree and append `_(partial conversion)_` to
`body_markdown`. Never abort the run on a single bad comment — the
remaining comments still ship.

### Rate Limits

```bash
# Notion: 30 searches/min, 180 req/min total
fetch_with_rate_limit() {
    local url="$1"
    sleep 0.5  # 2 req/sec — well under limit
    fetch_notion_page "$url"
}
```

### Malformed URLs

```bash
validate_url() {
    local url="$1"
    if [[ ! "$url" =~ ^https?:// ]]; then
        echo "⚠️  Invalid URL: $url (skipping)"
        return 1
    fi
    return 0
}
```

### Zero Comments

The `## Comments` section is still emitted, with a single line
`> 0 comments`. Skipping the section breaks downstream parsing that
counts on positional ordering of headings.

## Best Practices

### 1. Cache the artifact (with provider update timestamp invalidation)

```bash
cache_dir="$HOME/.cache/ticket_context/$PROVIDER"
cache_file="$cache_dir/${TICKET_ID}.md"
cache_meta="$cache_dir/${TICKET_ID}.meta.json"

# Cache hit ONLY when both age and ticket.updated agree
if [[ -f "$cache_file" && -f "$cache_meta" ]]; then
    cached_updated=$(jq -r '.ticket_updated' "$cache_meta")

    if stat -c %Y "$cache_file" >/dev/null 2>&1; then
        cache_mtime=$(stat -c %Y "$cache_file")
    else
        cache_mtime=$(stat -f %m "$cache_file")
    fi
    cache_age_min=$(( ( $(date +%s) - cache_mtime ) / 60 ))

    # Provider adapter fetches only the update timestamp:
    # Jira -> fields.updated; Linear -> issue updatedAt/update timestamp.
    current_updated=$(fetch_ticket_updated "$PROVIDER" "$TICKET_ID")

    if [[ "$cached_updated" == "$current_updated" && "$cache_age_min" -lt 60 ]]; then
        echo "Using cached context (ticket.updated unchanged, < 1 hour old)"
        cp "$cache_file" "$ARTIFACTS_DIR/context/ticket-context.md"
        exit 0
    fi
fi

# Fetch fresh context
# ... (full workflow above) ...

# Persist cache with metadata
mkdir -p "$cache_dir"
cp "$ARTIFACTS_DIR/context/ticket-context.md" "$cache_file"
jq -n --arg updated "$ticket_updated" '{ticket_updated: $updated}' > "$cache_meta"
```

Use Jira's `ticket.updated` or Linear's issue update timestamp. Namespacing by
provider prevents identical-looking identifiers from sharing cache entries.

### 2. Handle Large Context

Estimate the artifact size and degrade gracefully:

```bash
context_size=$(wc -c < "$context_file")
tokens_est=$((context_size / 4))

if [[ $tokens_est -gt 50000 ]]; then
    # Brief mode: keep Ticket / Description / AC + links without inline content
    artifact_mode="brief"
elif [[ $tokens_est -gt 20000 ]]; then
    # Truncated mode: keep only the 30 most recent comments fully;
    # older ones collapse to a single line `[#10001] 2025-12-01 — Jane Doe: <one-line preview>`.
    # Truncate Notion / Confluence bodies >5k chars with a `⚠️ truncated to 5k chars` notice.
    artifact_mode="truncated"
fi
```

The `## Ticket` section's `artifact-size:` line reports the final mode.

### 3. Parallel Fetching (if multiple docs)

```bash
# For multiple Notion pages, fetch in parallel
for entry in "${notion_link_entries[@]}"; do
    notion_url="${entry%%|*}"
    (
        content=$(fetch_notion_page "$notion_url")
        echo "$content" > "/tmp/notion_$(basename "$notion_url").md"
    ) &
done
wait
```

### 4. Provide Summary

```bash
echo "
## Context Summary

- Jira ticket: $summary
- Comments: $shown / $total (filtered: $bots_hidden bots, $status_hidden status-changes)
- External docs: ${doc_count} documents fetched
- Related tickets: ${related_count} dependencies
- Total context size: ~${tokens_est} tokens (${artifact_mode} mode)
- Ready for implementation: ✓
"
```

## Integration with Workflow

This skill is the **context-gathering step** of `/create-implementation-plan`
when the source is Jira or Linear. It is ALSO the first step of
`/create-sdd-ticket` Phase 1 for either tracker. Callers pass
`--provider jira|linear` explicitly. It produces the canonical `context/ticket-context.md`
artifact that every later phase reads — the planner agent absorbs it;
the SDD synthesizer in `create-sdd-ticket` treats `## Description` plus
`## Comments` as the source of truth (with the most recent comment
winning on conflicts).

This skill **only gathers context**: ticket body, comments, linked URLs
(Confluence / Notion / Figma frames when reachable), and attachments. It
does NOT plan, classify intent, derive decisions, pair Q&A, or
recommend code changes.

## Troubleshooting

**Issue: "Comments missing from artifact"**

- Verify the initial fetch used `--fields ... ,comment, ...` AND `--expand renderedFields,names`.
- If `comment.total > comment.maxResults`, confirm pagination ran (Phase 1a).
- Filters drop bots, status-changes, and comments under 20 chars by default — try `--include-bots --include-status-changes` to see whether material was filtered.

**Issue: "Comments show with garbled bodies"**

- ADF conversion fell back to plain text. Look for `_(partial conversion)_` markers; those flag node types we did not render. The plain text is correct, only formatting may be off.

**Issue: "Context too large"**

- Brief / truncated mode activates above 20k / 50k tokens. Check the `artifact-size:` line in `## Ticket`.
- Drop `--all-comments` if it was passed.

**Issue: "Cannot fetch Notion page"**

- Verify Notion MCP is configured: `mcp__notion__fetch_page --help`.
- Check bot has access to page in Notion settings.

## Examples

### Example 1: Simple Ticket (No External Docs)

```bash
$ /fetch-ticket-context PROJ-100

✓ Fetched Jira ticket: PROJ-100
  Summary: Fix null pointer in auth handler
  Comments: 2 total, 2 shown
  Priority: Medium
  No external documentation links found

Context ready (~500 tokens — full mode)
```

### Example 2: Complex Ticket (Multiple External Docs)

```bash
$ /fetch-ticket-context PROJ-123

✓ Fetched Jira ticket: PROJ-123
  Summary: Implement OAuth2 authentication
  Comments: 47 total, 32 shown (12 bots hidden, 3 status-change hidden)

📄 Found Notion documentation:
  - https://notion.so/OAuth-Design-Spec-abc123 (from: comment #10042)
✓ Fetched 1 Notion document (25KB, chunked)

📚 Found Confluence documentation:
  - https://company.atlassian.net/wiki/pages/456789 (from: description)
✓ Fetched 1 Confluence page

🎨 Found Figma designs:
  - https://figma.com/file/oauth-flow (from: description)
⚠️  1 Figma link requires manual review

🔗 Related Issues:
  - PROJ-120 (Blocking): Set up OAuth providers
  - PROJ-99 (Dependency): User database schema

Context ready (~15,000 tokens — full mode)
```

### Example 3: Ticket with 200+ comments

```bash
$ /fetch-ticket-context PROJ-456 --all-comments

✓ Fetched Jira ticket: PROJ-456
  Summary: Long-running incident triage thread
  Comments: 234 total, 234 shown (--all-comments)
  Paginated 3 pages

Context ready (~62,000 tokens — brief mode)
⚠ Brief mode active — body excerpts of external docs were omitted; links preserved.
```

## Caching to docs/llm-wiki/raw/external/

When `framework-config.json` has `wiki.cache_external: true` (default `false`) AND the project
has been initialized (`docs/llm-wiki/` exists), the skill MUST persist every fetched external doc to:

```
docs/llm-wiki/raw/external/<source-type>/<source-id>.md
```

with frontmatter carrying `source_url`, `source_type`, `source_id`, `ticket_id`, `fetched_at`, and
`sha256`. Use the `external-cache` helper exposed at:

```
orchestration/src/services/wiki/external-cache.ts
```

Specifically:

```ts
import { writeExternalCache } from '<orchestration>/services/wiki/external-cache.js';

writeExternalCache({
  projectPath,
  sourceType: provider,        // 'jira' | 'linear'
  sourceId: 'PROJ-123',
  sourceUrl: 'https://...',
  ticketId: 'PROJ-123',
  title: 'Add user search',
  body: fetchedMarkdown,
});
```

Before fetching, ALWAYS check the cache first (unless `--refresh-external` was passed):

```ts
import { readExternalCache } from '<orchestration>/services/wiki/external-cache.js';

const hit = readExternalCache({ projectPath, sourceType: provider, sourceId: ticketId });
if (hit) {
  // Use hit.body; skip the network call.
}
```

### Cache rules

- When `wiki.cache_external` is `false` (the default), the skill MUST NOT write to the cache and
  falls back to the legacy "fetch-and-discard" path. This keeps the default behavior identical to
  pre-cache behavior — no surprise file writes.
- The cache is invalidated automatically after 7 days (`maxAgeMs` default in `readExternalCache`).
- Pass `--refresh-external` to bypass the cache for a single run.
- Supported `source_type` values: `jira`, `linear`, `notion`, `confluence`, `github`, `other`.
- `sourceId` is sanitized for filesystem safety: characters outside `[a-zA-Z0-9._-]` are replaced
  with `_`. For example, `PROJ-123` stays `PROJ-123.md` and `notion uuid/abc` becomes
  `notion_uuid_abc.md`.
- Links extracted from ticket **comments** use the same cache as links from the description. The
  cache key is `sourceType` + `sourceId` (the resource's own id), not the ticket id — so the same
  Notion page linked from multiple tickets benefits.

## References

- Notion Manager (when installed): `.claude/skills/notion-document-manager/SKILL.md`
- Confluence Skill (when installed): `.claude/skills/mastering-confluence/SKILL.md`
- External cache helper: `orchestration/src/services/wiki/external-cache.ts`
