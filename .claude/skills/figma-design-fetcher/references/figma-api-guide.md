# Figma REST API Guide

Reference for the Figma REST API v1 endpoints used by the figma-design-fetcher skill.

## Authentication

### Personal Access Token

Generate at: https://www.figma.com/developers/api#access-tokens

```
Header: X-Figma-Token: {personal_access_token}
```

Scopes required:
- `file_read` -- read file and node data
- `file_dev_resources:read` -- read dev mode resources (optional)

### OAuth 2.0

For production integrations, use OAuth 2.0 flow:
- Authorization URL: `https://www.figma.com/oauth`
- Token URL: `https://www.figma.com/api/oauth/token`
- Pass token as: `Authorization: Bearer {access_token}`

### MCP Alternative

When using the Figma MCP server, authentication is handled by the server configuration:

```bash
claude mcp add figma -- npx figma-developer-mcp --figma-api-key=<YOUR_TOKEN>
```

MCP tools handle authentication internally. No headers needed in tool calls.

## Endpoints

### GET /v1/images/{fileKey}

Export images from a Figma file.

**Parameters:**

| Parameter       | Type   | Required | Description                                     |
| --------------- | ------ | -------- | ----------------------------------------------- |
| `ids`           | string | Yes      | Comma-separated node IDs (e.g., `1:2,3:4`)     |
| `format`        | string | No       | `png` (default), `jpg`, `svg`, `pdf`            |
| `scale`         | number | No       | Export scale: 0.01 to 4.0 (default: 1)          |
| `svg_include_id`| bool   | No       | Include node IDs in SVG output (default: false) |
| `svg_simplify_stroke` | bool | No  | Simplify strokes in SVG (default: true)         |
| `use_absolute_bounds` | bool | No  | Use absolute bounds for rendering               |

**Request:**

```
GET https://api.figma.com/v1/images/abc123XYZ?ids=1:2,3:4&format=png&scale=2
X-Figma-Token: fig_pat_xxxxx
```

**Response:**

```json
{
  "err": null,
  "images": {
    "1:2": "https://figma-alpha-api.s3.us-west-2.amazonaws.com/images/...",
    "3:4": "https://figma-alpha-api.s3.us-west-2.amazonaws.com/images/..."
  }
}
```

**Notes:**
- Image URLs are temporary (valid for ~14 days).
- Download images immediately after fetching URLs.
- For `scale=2`, a 320px wide frame produces a 640px wide image.

### GET /v1/files/{fileKey}/nodes

Fetch specific nodes from a Figma file with full property data.

**Parameters:**

| Parameter   | Type   | Required | Description                                      |
| ----------- | ------ | -------- | ------------------------------------------------ |
| `ids`       | string | Yes      | Comma-separated node IDs                         |
| `depth`     | number | No       | Depth of child nodes to include (default: all)   |
| `geometry`  | string | No       | Set to `paths` to include vector path data       |
| `plugin_data` | string | No    | Comma-separated plugin IDs for plugin data       |

**Request:**

```
GET https://api.figma.com/v1/files/abc123XYZ/nodes?ids=1:2,3:4
X-Figma-Token: fig_pat_xxxxx
```

**Response (abbreviated):**

```json
{
  "name": "My Design File",
  "nodes": {
    "1:2": {
      "document": {
        "id": "1:2",
        "name": "KPI Card",
        "type": "FRAME",
        "absoluteBoundingBox": { "x": 0, "y": 0, "width": 320, "height": 180 },
        "fills": [
          {
            "type": "SOLID",
            "color": { "r": 1, "g": 1, "b": 1, "a": 1 },
            "blendMode": "NORMAL"
          }
        ],
        "layoutMode": "VERTICAL",
        "primaryAxisAlignItems": "MIN",
        "counterAxisAlignItems": "CENTER",
        "paddingLeft": 24,
        "paddingRight": 24,
        "paddingTop": 24,
        "paddingBottom": 24,
        "itemSpacing": 12,
        "children": [...]
      }
    }
  }
}
```

### GET /v1/files/{fileKey}/styles

Fetch all published styles in a file.

**Request:**

```
GET https://api.figma.com/v1/files/abc123XYZ/styles
X-Figma-Token: fig_pat_xxxxx
```

**Response:**

```json
{
  "meta": {
    "styles": [
      {
        "key": "abc123",
        "name": "Brand/Primary",
        "style_type": "FILL",
        "description": "Primary brand color",
        "node_id": "10:5"
      },
      {
        "key": "def456",
        "name": "Heading/Large",
        "style_type": "TEXT",
        "description": "Large heading style",
        "node_id": "10:8"
      }
    ]
  }
}
```

**Style types:** `FILL`, `TEXT`, `EFFECT`, `GRID`

To resolve a style's actual properties, fetch the style's node via `/v1/files/{fileKey}/nodes?ids={nodeId}`.

### GET /v1/files/{fileKey}

Fetch the entire file tree (use sparingly -- can be very large).

**Parameters:**

| Parameter   | Type   | Required | Description                                      |
| ----------- | ------ | -------- | ------------------------------------------------ |
| `depth`     | number | No       | Limit traversal depth (recommended: 1 or 2)     |
| `branch_data` | bool | No      | Include branch metadata                          |

**Usage guidance:** Prefer `/v1/files/{fileKey}/nodes` with specific IDs over fetching the full file. Full file responses can be tens of megabytes for complex designs.

## Rate Limits

Figma API enforces rate limits per personal access token:

| Limit Type        | Value                |
| ----------------- | -------------------- |
| Requests/minute   | ~30 for image export |
| Requests/minute   | ~60 for file reads   |
| Concurrent exports| ~10                  |

**Handling 429 responses:**

```
HTTP/1.1 429 Too Many Requests
Retry-After: 30
```

- Read the `Retry-After` header (seconds).
- Wait the specified duration before retrying.
- Implement exponential backoff as a fallback: 1s, 2s, 4s.
- Maximum 3 retries before failing with a user-facing error.

## Error Responses

All errors follow this structure:

```json
{
  "err": "Error message",
  "status": 403
}
```

| Status | Meaning                    | Resolution                                         |
| ------ | -------------------------- | -------------------------------------------------- |
| 400    | Bad request                | Check node ID format (must be `X:Y`)               |
| 403    | Forbidden                  | Token invalid or lacks permissions                  |
| 404    | Not found                  | File key or node ID does not exist                  |
| 429    | Rate limited               | Wait per Retry-After, then retry                    |
| 500    | Internal server error      | Transient; retry with backoff                       |
| 503    | Service unavailable        | Transient; retry with backoff                       |

## MCP Tool Signatures

When using Figma via MCP, the following tools are typically available:

### `figma_get_file`

Fetches file metadata and node tree.

```json
{
  "tool": "figma_get_file",
  "arguments": {
    "fileKey": "abc123XYZ",
    "depth": 2
  }
}
```

### `figma_get_images`

Exports images for specified nodes.

```json
{
  "tool": "figma_get_images",
  "arguments": {
    "fileKey": "abc123XYZ",
    "nodeIds": ["1:2", "3:4"],
    "format": "png",
    "scale": 2
  }
}
```

### `figma_get_file_nodes`

Fetches specific node data.

```json
{
  "tool": "figma_get_file_nodes",
  "arguments": {
    "fileKey": "abc123XYZ",
    "nodeIds": ["1:2", "3:4"]
  }
}
```

### `figma_get_file_styles`

Fetches published styles.

```json
{
  "tool": "figma_get_file_styles",
  "arguments": {
    "fileKey": "abc123XYZ"
  }
}
```
