# Figma Mapping Reference

This document covers the conventions, structure, and usage patterns for `ui-visual-testing.json` configuration files that map UI routes and components to Figma design references.

## Configuration File: `ui-visual-testing.json`

### Purpose

The `ui-visual-testing.json` file defines the mapping between implementation routes/components and their Figma design counterparts. It is the primary input for the visual testing pipeline.

### Location conventions

The skill searches for configuration files in this order:

1. **Explicit path** — provided via `--mapping PATH` argument.
2. **Component-level** — co-located with the component being tested:
   ```
   src/widgets/kpi-dashboard/ui-visual-testing.json
   src/features/approve-insight/ui-visual-testing.json
   ```
3. **Page-level** — co-located with the page:
   ```
   src/app/dashboard/ui-visual-testing.json
   src/app/insights/ui-visual-testing.json
   ```
4. **Project root** — single file covering all screens:
   ```
   ui-visual-testing.json
   ```

Co-located configs are preferred because they travel with the component, making it clear which tests belong to which code. The project-root config is useful for cross-cutting concerns like theme regression testing.

### Merging behaviour

When multiple config files are found (e.g. component-level + root), they are merged:

- `screens` arrays are concatenated.
- `thresholds` from the more specific file take precedence.
- `figma.fileKey` from the more specific file takes precedence.
- `maxIterations` from the more specific file takes precedence.

## Schema

```json
{
  "$schema": "https://qubika-agentic-framework/schemas/ui-visual-testing.schema.json",
  "figma": {
    "fileKey": "abc123DEF456",
    "accessToken": "$FIGMA_ACCESS_TOKEN"
  },
  "thresholds": {
    "figma": 2,
    "regression": 5
  },
  "maxIterations": 3,
  "screens": [
    {
      "label": "Dashboard – Desktop",
      "figmaNodeId": "12:345",
      "route": "/dashboard",
      "viewport": { "width": 1440, "height": 900 },
      "modes": ["figma", "screenshot"],
      "waitForSelector": "[data-testid='kpi-grid']",
      "delay": 500,
      "maskRegions": [
        {
          "selector": "[data-testid='current-date']",
          "reason": "Dynamic date content"
        }
      ]
    }
  ]
}
```

### Field reference

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `figma.fileKey` | string | For Figma mode | The Figma file key from the URL: `figma.com/file/<fileKey>/...` |
| `figma.accessToken` | string | No | Figma API token. Use `$ENV_VAR` syntax for environment variable reference. Defaults to `$FIGMA_ACCESS_TOKEN`. |
| `thresholds.figma` | number | No | Maximum allowed mismatch percentage for Figma comparisons. Default: `2`. |
| `thresholds.regression` | number | No | Maximum allowed mismatch percentage for screenshot regression. Default: `5`. |
| `maxIterations` | number | No | Maximum fix-recapture cycles before marking as FAIL. Default: `3`. |
| `screens[].label` | string | Yes | Human-readable name for the screen. Used in reports and file names. |
| `screens[].figmaNodeId` | string | For Figma mode | Figma node ID in `<page>:<node>` format (e.g. `12:345`). |
| `screens[].route` | string | Yes | URL path to navigate to (appended to `--base-url`). |
| `screens[].viewport` | object | Yes | `{ width: number, height: number }` defining the browser viewport. |
| `screens[].modes` | string[] | No | Which modes to run: `["figma"]`, `["screenshot"]`, or `["figma", "screenshot"]`. Default: auto-detect. |
| `screens[].waitForSelector` | string | No | CSS selector to wait for before capturing. Useful for async-loaded content. |
| `screens[].delay` | number | No | Additional milliseconds to wait after selector is found. Useful for animations settling. |
| `screens[].maskRegions` | array | No | Regions to mask during comparison (not capture). |
| `screens[].maskRegions[].selector` | string | Yes | CSS selector identifying the region to mask. |
| `screens[].maskRegions[].reason` | string | No | Documentation of why this region is masked. |

## Finding Figma Node IDs

### From the Figma URL

When you select a frame or component in Figma, the URL updates to include the node ID:

```
https://www.figma.com/file/abc123/MyProject?node-id=12%3A345
                                                    ^^^^^^^^
                                                    node-id = 12:345
```

The `%3A` is the URL-encoded colon. In the config file, use the decoded form: `"12:345"`.

### From the Figma API

Query the file structure to find node IDs programmatically:

```bash
curl -H "X-Figma-Token: $FIGMA_ACCESS_TOKEN" \
  "https://api.figma.com/v1/files/<fileKey>" \
  | jq '.document.children[].children[] | {name, id}'
```

### From ticket context

When a ticket includes Figma URLs, extract the node ID:

1. Parse the ticket description for URLs matching `figma.com/file/` or `figma.com/design/`.
2. Extract the `node-id` query parameter.
3. URL-decode the value (`%3A` becomes `:`).
4. Map to the appropriate screen entry.

**Example ticket description:**
```
Design: https://www.figma.com/file/abc123/DOP?node-id=12%3A345&mode=design
Mobile: https://www.figma.com/file/abc123/DOP?node-id=12%3A400&mode=design
```

Extracted mapping:
```json
{
  "screens": [
    { "figmaNodeId": "12:345", "label": "Design reference" },
    { "figmaNodeId": "12:400", "label": "Mobile reference" }
  ]
}
```

## Viewport Mapping

### Standard breakpoints

Map Figma frame dimensions to standard viewport configurations:

| Figma frame width | Viewport name | Config |
|-------------------|---------------|--------|
| 375px | Mobile (iPhone SE) | `{ "width": 375, "height": 667 }` |
| 390px | Mobile (iPhone 14) | `{ "width": 390, "height": 844 }` |
| 428px | Mobile (iPhone 14 Plus) | `{ "width": 428, "height": 926 }` |
| 768px | Tablet (iPad Mini) | `{ "width": 768, "height": 1024 }` |
| 1024px | Tablet (iPad Pro) | `{ "width": 1024, "height": 1366 }` |
| 1280px | Desktop (small) | `{ "width": 1280, "height": 800 }` |
| 1440px | Desktop (standard) | `{ "width": 1440, "height": 900 }` |
| 1920px | Desktop (large) | `{ "width": 1920, "height": 1080 }` |

### Inferring viewports from Figma

When the Figma frame dimensions do not match a standard breakpoint exactly, use the closest standard viewport. The comparison algorithm handles minor dimension differences by resizing the reference image.

### Multi-viewport entries

A single screen design often has multiple viewport variants in Figma. Create separate entries for each:

```json
{
  "screens": [
    {
      "label": "Dashboard – Desktop",
      "figmaNodeId": "12:345",
      "route": "/dashboard",
      "viewport": { "width": 1440, "height": 900 }
    },
    {
      "label": "Dashboard – Tablet",
      "figmaNodeId": "12:346",
      "route": "/dashboard",
      "viewport": { "width": 768, "height": 1024 }
    },
    {
      "label": "Dashboard – Mobile",
      "figmaNodeId": "12:347",
      "route": "/dashboard",
      "viewport": { "width": 375, "height": 667 }
    }
  ]
}
```

## Co-location Patterns

### Widget-level mapping

For a widget like `KpiDashboard`, place the config alongside the widget code:

```
src/widgets/kpi-dashboard/
├── ui/
│   └── KpiDashboard.tsx
├── model/
│   └── types.ts
├── index.ts
└── ui-visual-testing.json     ← co-located config
```

The config only includes screens relevant to this widget:

```json
{
  "figma": { "fileKey": "abc123" },
  "screens": [
    {
      "label": "KpiDashboard – Full (Desktop)",
      "figmaNodeId": "45:678",
      "route": "/dashboard",
      "viewport": { "width": 1440, "height": 900 },
      "waitForSelector": "[data-testid='kpi-dashboard']"
    }
  ]
}
```

### Page-level mapping

For full-page visual testing, co-locate with the page:

```
src/app/dashboard/
├── page.tsx
├── layout.tsx
└── ui-visual-testing.json     ← page-level config
```

### Theme/token-level mapping

For design token changes that affect all pages, use the project root config:

```
project-root/
├── ui-visual-testing.json     ← root config for global regression
├── src/
└── ...
```

The root config includes all critical screens:

```json
{
  "thresholds": { "regression": 0 },
  "screens": [
    { "label": "Dashboard", "route": "/dashboard", "viewport": { "width": 1440, "height": 900 }, "modes": ["screenshot"] },
    { "label": "Insights", "route": "/insights", "viewport": { "width": 1440, "height": 900 }, "modes": ["screenshot"] },
    { "label": "Settings", "route": "/settings", "viewport": { "width": 1440, "height": 900 }, "modes": ["screenshot"] }
  ]
}
```

## Auto-generation from Ticket Context

When no `ui-visual-testing.json` exists and a `--ticket` is provided, the skill can generate a starter config:

1. Parse the ticket for Figma URLs and extract node IDs.
2. Identify affected routes from the ticket description or git diff.
3. Determine viewports from the Figma frame dimensions or default to desktop (1440x900).
4. Generate the config file and present it to the user for confirmation before writing.

**Example auto-generated config:**

```json
{
  "$schema": "https://qubika-agentic-framework/schemas/ui-visual-testing.schema.json",
  "figma": {
    "fileKey": "abc123"
  },
  "thresholds": {
    "figma": 2,
    "regression": 5
  },
  "maxIterations": 3,
  "screens": [
    {
      "label": "Dashboard – Desktop (from ticket DOP-194)",
      "figmaNodeId": "12:345",
      "route": "/dashboard",
      "viewport": { "width": 1440, "height": 900 },
      "modes": ["figma"]
    }
  ]
}
```

The skill always asks the user to review and confirm auto-generated configs before using them in the pipeline.
