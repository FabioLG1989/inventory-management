---
name: figma-design-fetcher
description: Fetches Figma designs, exports frame images at 2x, and extracts structured design constraints (layout, colors, typography, dimensions). Supports MCP, API token, and manual fallback.
user-invocable: true
argument-hint: '[--file-key KEY] [--node-ids ID1,ID2] [--output-dir DIR]'
allowed-tools: Read, Write, Bash, Glob, Grep
---

# Figma Design Fetcher

Fetches Figma designs and extracts structured design constraints for UI implementation and visual validation.

## Prerequisites

Access to Figma designs via one of:

- **Figma MCP server** (preferred) -- provides tool-based access
- **FIGMA_ACCESS_TOKEN** environment variable -- personal access token
- **Manual export** -- user-provided screenshot fallback

## Usage

```bash
# Fetch specific frames from a Figma file
/figma-design-fetcher --file-key abc123XYZ --node-ids 1:2,3:4

# Fetch with custom output directory
/figma-design-fetcher --file-key abc123XYZ --node-ids 1:2 --output-dir .claude-tmp/ui-validation/PROJ-100/figma

# Minimal invocation (will prompt for file key)
/figma-design-fetcher
```

## Output Structure

```
.claude-tmp/ui-validation/{ticketKey}/figma/
├── {label}.png                    # 2x exported frame image
├── {label}-constraints.json       # Structured design constraints
└── design-context.md              # Human-readable design summary
```

## Workflow

### Phase 1: Parse Arguments

Extract parameters from the invocation arguments:

| Argument   | Flag           | Default                                   |
| ---------- | -------------- | ----------------------------------------- |
| File key   | `--file-key`   | Prompt user if not provided               |
| Node IDs   | `--node-ids`   | Prompt user if not provided               |
| Output dir | `--output-dir` | `.claude-tmp/ui-validation/default/figma` |

**Parsing rules:**

- File key can be extracted from a full Figma URL: `https://www.figma.com/design/{fileKey}/...`
- Node IDs are comma-separated, in Figma's `X:Y` format
- Sanitize the label from the node name (replace spaces/special chars with hyphens, lowercase)

### Phase 2: Detect Figma Access

Attempt access methods in cascading order:

```
1. Check for Figma MCP server availability
   → If available: use MCP tools (figma_get_file, figma_get_images)
   → If not available: continue to step 2

2. Check for FIGMA_ACCESS_TOKEN environment variable
   → If set: use REST API with Bearer token
   → If not set: continue to step 3

3. Suggest MCP setup to user
   → Show: claude mcp add figma -- npx figma-developer-mcp --figma-api-key=<TOKEN>
   → Ask if user wants to set up now or provide token directly
   → If user provides token: export and use REST API
   → If user declines: continue to step 4

4. Ask user for manual exports
   → Request user to export frames as PNG at 2x from Figma
   → Ask user to place files in the output directory
   → Proceed with constraint extraction from filenames only

5. Screenshot-only fallback
   → If user has screenshots, read them directly
   → Skip constraint extraction (images only, no structured data)
```

### Phase 3: Fetch Frame Images

Using the detected access method, export frame images.

**REST API approach:**

```
GET https://api.figma.com/v1/images/{fileKey}
  ?ids={nodeId1},{nodeId2}
  &format=png
  &scale=2

Headers:
  X-Figma-Token: {token}
```

**Response handling:**

- Parse the `images` object from the response: `{ "images": { "1:2": "https://..." } }`
- Download each image URL to `{outputDir}/{label}.png`
- Retry up to 3 times on transient failures (429, 500, 503)
- Respect rate limits: wait and retry on 429 with `Retry-After` header

**MCP approach:**

- Use the `figma_get_images` tool with equivalent parameters
- Download returned URLs to the output directory

### Phase 4: Fetch Node Properties

Retrieve the full node tree for structural data.

**REST API approach:**

```
GET https://api.figma.com/v1/files/{fileKey}/nodes
  ?ids={nodeId1},{nodeId2}

Headers:
  X-Figma-Token: {token}
```

**Extract from response:**

- `document.children` -- the node tree for each requested ID
- Node properties: `name`, `type`, `absoluteBoundingBox`, `fills`, `strokes`, `effects`
- Text nodes: `style` (fontFamily, fontSize, fontWeight, lineHeightPx, letterSpacing)
- Frame/component nodes: `layoutMode`, `primaryAxisAlignItems`, `counterAxisAlignItems`, `paddingLeft/Right/Top/Bottom`, `itemSpacing`
- Style references: `styles` object mapping style types to style IDs

### Phase 5: Extract Design Constraints

Transform raw Figma node data into structured constraint objects.

For each node, generate a `{label}-constraints.json`:

```json
{
  "nodeId": "1:2",
  "name": "KPI Card",
  "type": "FRAME",
  "dimensions": {
    "width": 320,
    "height": 180
  },
  "layout": {
    "mode": "VERTICAL",
    "cssEquivalent": "flex-column",
    "primaryAxisAlign": "MIN",
    "counterAxisAlign": "CENTER",
    "padding": {
      "top": 24,
      "right": 24,
      "bottom": 24,
      "left": 24
    },
    "itemSpacing": 12
  },
  "colors": [
    {
      "property": "fill",
      "hex": "#FFFFFF",
      "opacity": 1,
      "cssVar": "--color-surface"
    }
  ],
  "typography": [
    {
      "nodeName": "KPI Value",
      "fontFamily": "Inter",
      "fontSize": 32,
      "fontWeight": 700,
      "lineHeight": 40,
      "letterSpacing": -0.5,
      "cssVar": "--font-heading-lg"
    }
  ],
  "effects": [
    {
      "type": "DROP_SHADOW",
      "color": "rgba(0,0,0,0.08)",
      "offset": { "x": 0, "y": 2 },
      "radius": 8,
      "spread": 0
    }
  ],
  "children": [
    {
      "nodeId": "1:3",
      "name": "Label",
      "type": "TEXT"
    }
  ]
}
```

**Extraction rules:**

- Map Figma fill colors to the nearest design token (if a token map is available in the project)
- Convert `layoutMode` to CSS equivalent: `HORIZONTAL` -> `flex-row`, `VERTICAL` -> `flex-column`
- Resolve named styles via `GET /v1/files/{fileKey}/styles` when style references are present
- Round all numeric values to integers (pixels) or 2 decimal places (em/rem)

### Phase 6: Generate Design Context

Produce a human-readable `design-context.md` summarizing all fetched frames:

```markdown
# Design Context

## Source

- **Figma file:** {fileKey}
- **Fetched at:** {ISO timestamp}
- **Frames:** {count}

## Frame: {label}

- **Node ID:** {nodeId}
- **Dimensions:** {width} x {height}
- **Layout:** {cssEquivalent} with {itemSpacing}px gap
- **Background:** {hex} ({cssVar})
- **Key typography:**
  - Heading: {fontFamily} {fontWeight} {fontSize}px
  - Body: {fontFamily} {fontWeight} {fontSize}px

### Children

| Name | Type | Dimensions |
| ---- | ---- | ---------- |
| ...  | ...  | ...        |
```

## Error Handling

| Error                  | Action                                                     |
| ---------------------- | ---------------------------------------------------------- |
| 403 Forbidden          | Token lacks access. Ask user to verify token permissions.  |
| 404 Not Found          | File key or node IDs invalid. Ask user to verify.          |
| 429 Rate Limited       | Wait per `Retry-After` header, retry up to 3 times.        |
| Network timeout        | Retry with exponential backoff (1s, 2s, 4s).               |
| MCP tool not available | Fall through to next access method.                        |
| Empty node response    | Warn user; generate image-only output without constraints. |

## References

- [Figma API Guide](./references/figma-api-guide.md) -- endpoint details, auth, rate limits
- [Design Token Extraction](./references/design-token-extraction.md) -- mapping Figma properties to CSS
