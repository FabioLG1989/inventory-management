# Design Token Extraction

Mapping Figma node properties to CSS custom properties and framework-compatible design tokens.

## Overview

Figma stores design data as structured node properties. This reference describes how to transform those properties into CSS custom properties (`--token-name`) that align with a Tailwind CSS v4 / design-system workflow.

## Color Extraction

### Figma Color Model

Figma represents colors as RGBA objects with values between 0 and 1:

```json
{
  "fills": [
    {
      "type": "SOLID",
      "color": { "r": 0.102, "g": 0.110, "b": 0.180, "a": 1 },
      "blendMode": "NORMAL",
      "visible": true
    }
  ]
}
```

### Conversion to CSS

```
Figma { r, g, b, a } → CSS hex/rgba

r: 0.102 → Math.round(0.102 * 255) = 26 → hex "1a"
g: 0.110 → Math.round(0.110 * 255) = 28 → hex "1c"
b: 0.180 → Math.round(0.180 * 255) = 46 → hex "2e"
a: 1     → fully opaque

Result: #1a1c2e
```

### Mapping to Design Tokens

Map extracted colors to CSS custom properties based on usage context:

| Figma Context              | CSS Custom Property          | Example Value |
| -------------------------- | ---------------------------- | ------------- |
| Frame background fill      | `--color-surface`            | `#ffffff`     |
| Primary button fill        | `--color-brand-primary`      | `#2563eb`     |
| Text fill (heading)        | `--color-text-primary`       | `#1a1c2e`     |
| Text fill (body)           | `--color-text-secondary`     | `#6b7280`     |
| Border/stroke color        | `--color-border`             | `#e5e7eb`     |
| Error/destructive fill     | `--color-error`              | `#dc2626`     |
| Success fill               | `--color-success`            | `#16a34a`     |

### Named Style Resolution

When a node references a named style (via the `styles` property), resolve it:

```json
{
  "styles": {
    "fill": "S:abc123,"
  }
}
```

1. Fetch the style node via `GET /v1/files/{fileKey}/nodes?ids={styleNodeId}`
2. Use the style `name` as the token name basis: `"Brand/Primary"` -> `--color-brand-primary`
3. Extract the actual color value from the style node's fills

### Gradient Handling

For gradient fills, extract the color stops:

```json
{
  "type": "GRADIENT_LINEAR",
  "gradientHandlePositions": [
    { "x": 0, "y": 0.5 },
    { "x": 1, "y": 0.5 }
  ],
  "gradientStops": [
    { "color": { "r": 0.149, "g": 0.388, "b": 0.922, "a": 1 }, "position": 0 },
    { "color": { "r": 0.478, "g": 0.227, "b": 0.922, "a": 1 }, "position": 1 }
  ]
}
```

Convert to CSS:
```css
--gradient-primary: linear-gradient(90deg, #2663eb 0%, #7a3aeb 100%);
```

## Typography Extraction

### Figma Text Style Properties

```json
{
  "type": "TEXT",
  "style": {
    "fontFamily": "Inter",
    "fontPostScriptName": "Inter-Bold",
    "fontSize": 32,
    "fontWeight": 700,
    "lineHeightPx": 40,
    "lineHeightPercent": 125,
    "lineHeightUnit": "PIXELS",
    "letterSpacing": -0.5,
    "textAlignHorizontal": "LEFT",
    "textAlignVertical": "TOP",
    "textDecoration": "NONE",
    "textCase": "ORIGINAL"
  },
  "characters": "Revenue"
}
```

### Mapping to CSS Custom Properties

| Figma Property      | CSS Custom Property        | CSS Property        | Conversion                          |
| ------------------- | -------------------------- | ------------------- | ----------------------------------- |
| `fontFamily`        | `--font-family-{name}`     | `font-family`       | Direct mapping                      |
| `fontSize`          | `--font-size-{scale}`      | `font-size`         | px value; convert to rem (px / 16)  |
| `fontWeight`        | `--font-weight-{name}`     | `font-weight`       | Numeric (100-900)                   |
| `lineHeightPx`      | `--line-height-{scale}`    | `line-height`       | ratio = lineHeightPx / fontSize     |
| `letterSpacing`     | `--letter-spacing-{name}`  | `letter-spacing`    | px value; convert to em if needed   |

### Typography Scale Mapping

Map Figma font sizes to a semantic scale:

| fontSize (px) | Token Name              | CSS Variable             |
| ------------- | ----------------------- | ------------------------ |
| 12            | `xs`                    | `--font-size-xs`         |
| 14            | `sm`                    | `--font-size-sm`         |
| 16            | `base`                  | `--font-size-base`       |
| 18            | `lg`                    | `--font-size-lg`         |
| 20            | `xl`                    | `--font-size-xl`         |
| 24            | `2xl`                   | `--font-size-2xl`        |
| 30            | `3xl`                   | `--font-size-3xl`        |
| 36            | `4xl`                   | `--font-size-4xl`        |
| 48            | `5xl`                   | `--font-size-5xl`        |

Snap to the nearest scale value. If a Figma font size is 32px, map to `4xl` (closest to 36) or create a custom token.

## Spacing Extraction

### Figma Spacing Properties

Figma auto-layout frames expose padding and spacing:

```json
{
  "layoutMode": "VERTICAL",
  "paddingLeft": 24,
  "paddingRight": 24,
  "paddingTop": 24,
  "paddingBottom": 24,
  "itemSpacing": 12
}
```

### Mapping to CSS Custom Properties

| Figma Property   | CSS Custom Property       | CSS Property   |
| ---------------- | ------------------------- | -------------- |
| `paddingTop`     | `--spacing-{scale}`       | `padding-top`  |
| `paddingRight`   | `--spacing-{scale}`       | `padding-right`|
| `paddingBottom`  | `--spacing-{scale}`       | `padding-bottom`|
| `paddingLeft`    | `--spacing-{scale}`       | `padding-left` |
| `itemSpacing`    | `--spacing-{scale}`       | `gap`          |

### Spacing Scale

Map pixel values to a spacing scale (base-4 or base-8 system):

| px Value | Token Name | CSS Variable       |
| -------- | ---------- | ------------------- |
| 0        | `0`        | `--spacing-0`       |
| 4        | `1`        | `--spacing-1`       |
| 8        | `2`        | `--spacing-2`       |
| 12       | `3`        | `--spacing-3`       |
| 16       | `4`        | `--spacing-4`       |
| 20       | `5`        | `--spacing-5`       |
| 24       | `6`        | `--spacing-6`       |
| 32       | `8`        | `--spacing-8`       |
| 40       | `10`       | `--spacing-10`      |
| 48       | `12`       | `--spacing-12`      |
| 64       | `16`       | `--spacing-16`      |

Snap to the nearest scale value. Flag non-standard values for manual review.

## Layout Mode Mapping

### Auto-Layout to CSS Flexbox

| Figma `layoutMode`      | CSS Equivalent        | Tailwind Class    |
| ------------------------ | --------------------- | ----------------- |
| `HORIZONTAL`             | `flex-direction: row` | `flex-row`        |
| `VERTICAL`               | `flex-direction: column` | `flex-col`     |
| (not set / `NONE`)       | No auto-layout        | (manual position) |

### Primary Axis Alignment

| Figma `primaryAxisAlignItems` | CSS `justify-content`  | Tailwind Class      |
| ----------------------------- | ---------------------- | ------------------- |
| `MIN`                         | `flex-start`           | `justify-start`     |
| `CENTER`                      | `center`               | `justify-center`    |
| `MAX`                         | `flex-end`             | `justify-end`       |
| `SPACE_BETWEEN`               | `space-between`        | `justify-between`   |

### Counter Axis Alignment

| Figma `counterAxisAlignItems` | CSS `align-items`      | Tailwind Class      |
| ----------------------------- | ---------------------- | ------------------- |
| `MIN`                         | `flex-start`           | `items-start`       |
| `CENTER`                      | `center`               | `items-center`      |
| `MAX`                         | `flex-end`             | `items-end`         |
| `BASELINE`                    | `baseline`             | `items-baseline`    |

### Sizing Behavior

| Figma Property                 | CSS Equivalent                  |
| ------------------------------ | ------------------------------- |
| `primaryAxisSizingMode: FIXED` | `width/height: {value}px`       |
| `primaryAxisSizingMode: AUTO`  | `width/height: auto` (fit-content) |
| `counterAxisSizingMode: FIXED` | explicit cross-axis dimension   |
| `counterAxisSizingMode: AUTO`  | `auto` on cross-axis            |
| `layoutGrow: 1`               | `flex-grow: 1` (`flex-1`)       |
| `layoutGrow: 0`               | `flex-grow: 0`                  |

### Wrap Behavior

| Figma `layoutWrap`  | CSS Equivalent       | Tailwind Class  |
| ------------------- | -------------------- | --------------- |
| `WRAP`              | `flex-wrap: wrap`    | `flex-wrap`     |
| `NO_WRAP`           | `flex-wrap: nowrap`  | `flex-nowrap`   |

## Auto-Layout to CSS Grid

For grid-like layouts (detected when children have uniform sizing in a wrapping horizontal auto-layout):

```json
{
  "layoutMode": "HORIZONTAL",
  "layoutWrap": "WRAP",
  "itemSpacing": 16,
  "counterAxisSpacing": 16
}
```

Convert to CSS Grid when:
- `layoutWrap` is `WRAP`
- Children have uniform or repeating widths
- Both `itemSpacing` and `counterAxisSpacing` are defined

```css
display: grid;
grid-template-columns: repeat(auto-fill, minmax({childWidth}px, 1fr));
gap: {itemSpacing}px {counterAxisSpacing}px;
```

Otherwise, stick with flexbox:
```css
display: flex;
flex-wrap: wrap;
gap: {itemSpacing}px;
```

## Named Style Resolution

### Process

1. When a node has a `styles` property, it references named styles by ID:

```json
{
  "styles": {
    "fill": "S:style_id_1,",
    "text": "S:style_id_2,",
    "effect": "S:style_id_3,"
  }
}
```

2. Fetch styles from the file: `GET /v1/files/{fileKey}/styles`

3. Match the style key to get the human-readable name:

```json
{
  "key": "style_id_1",
  "name": "Brand/Primary",
  "style_type": "FILL"
}
```

4. Convert the style name to a CSS custom property:

| Style Name          | Convention             | CSS Variable              |
| ------------------- | ---------------------- | ------------------------- |
| `Brand/Primary`     | Slash-separated group  | `--color-brand-primary`   |
| `Neutral/Gray 500`  | With numeric suffix    | `--color-neutral-gray-500`|
| `Heading/Large`     | Typography group       | `--font-heading-lg`       |
| `Shadow/Card`       | Effect group           | `--shadow-card`           |

### Naming Convention

- Replace `/` with `-`
- Replace spaces with `-`
- Lowercase everything
- Prefix with category: `--color-`, `--font-`, `--shadow-`, `--border-`

## Complete Extraction Example

Given a Figma KPI Card frame:

```json
{
  "id": "1:2",
  "name": "KPI Card",
  "type": "FRAME",
  "absoluteBoundingBox": { "x": 0, "y": 0, "width": 320, "height": 180 },
  "fills": [{ "type": "SOLID", "color": { "r": 1, "g": 1, "b": 1, "a": 1 } }],
  "effects": [
    {
      "type": "DROP_SHADOW",
      "color": { "r": 0, "g": 0, "b": 0, "a": 0.08 },
      "offset": { "x": 0, "y": 2 },
      "radius": 8,
      "spread": 0
    }
  ],
  "layoutMode": "VERTICAL",
  "primaryAxisAlignItems": "MIN",
  "counterAxisAlignItems": "MIN",
  "paddingTop": 24,
  "paddingRight": 24,
  "paddingBottom": 24,
  "paddingLeft": 24,
  "itemSpacing": 8,
  "children": [
    {
      "id": "1:3",
      "name": "Label",
      "type": "TEXT",
      "style": {
        "fontFamily": "Inter",
        "fontSize": 14,
        "fontWeight": 500,
        "lineHeightPx": 20
      },
      "fills": [{ "type": "SOLID", "color": { "r": 0.42, "g": 0.45, "b": 0.50, "a": 1 } }],
      "characters": "Revenue"
    },
    {
      "id": "1:4",
      "name": "Value",
      "type": "TEXT",
      "style": {
        "fontFamily": "Inter",
        "fontSize": 32,
        "fontWeight": 700,
        "lineHeightPx": 40,
        "letterSpacing": -0.5
      },
      "fills": [{ "type": "SOLID", "color": { "r": 0.10, "g": 0.11, "b": 0.18, "a": 1 } }],
      "characters": "$1.2M"
    }
  ]
}
```

Extracted CSS tokens:

```css
@theme {
  /* Colors */
  --color-surface: #ffffff;
  --color-text-primary: #1a1c2e;
  --color-text-secondary: #6b7380;

  /* Typography */
  --font-family-primary: 'Inter', sans-serif;
  --font-size-sm: 0.875rem;    /* 14px */
  --font-size-4xl: 2rem;       /* 32px */
  --font-weight-medium: 500;
  --font-weight-bold: 700;
  --line-height-sm: 1.43;      /* 20/14 */
  --line-height-4xl: 1.25;     /* 40/32 */

  /* Spacing */
  --spacing-2: 0.5rem;         /* 8px */
  --spacing-6: 1.5rem;         /* 24px */

  /* Effects */
  --shadow-card: 0 2px 8px rgba(0, 0, 0, 0.08);

  /* Layout (reference, not typically tokenized) */
  --radius-card: 0;
}
```

Extracted component class:

```css
@layer components {
  .kpi-card {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    justify-content: flex-start;
    padding: var(--spacing-6);
    gap: var(--spacing-2);
    width: 320px;
    height: 180px;
    background: var(--color-surface);
    box-shadow: var(--shadow-card);
  }
}
```
