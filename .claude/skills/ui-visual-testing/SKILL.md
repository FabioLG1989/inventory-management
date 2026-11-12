---
name: ui-visual-testing
description: >
  Stack-agnostic dual-mode visual testing: Figma design fidelity and screenshot
  regression. Compares implementation against Figma designs or baseline
  screenshots with iterative fix loop. Loads framework-specific renderer
  timing via specializations. Supports configurable thresholds and region masking.
user-invocable: true
argument-hint: '[--ticket KEY] [--base-url URL] [--max-iterations N] [--mapping PATH] [--mode figma|screenshot|both]'
allowed-tools: Read, Write, Bash, Glob, Grep, Edit, Skill
---

# UI Visual Testing

Dual-mode visual testing pipeline that compares UI implementation against Figma design references and/or baseline screenshots. Supports iterative fix loops with configurable thresholds and region masking.

This skill is **stack-agnostic**. The visual testing pipeline (configuration, capture, comparison, iteration) is framework-independent. Framework-specific renderer timing (hydration, transitions, async rendering) lives in `references/*-specialization.md` files loaded dynamically based on project detection. See [`references/renderer-adapters.md`](references/renderer-adapters.md) for the universal capture sequence and common concerns.

## Boundary — relationship to `/ui-testing`

This skill handles **only Level 4 (visual)** of the broader UI testing taxonomy: Figma design fidelity + screenshot regression. For unit / component / E2E orchestration use `/ui-testing`, which delegates Level 4 to this skill when the resolved level set includes visual. Both invocation paths are supported — invoke this skill directly when only visual work is needed; invoke `/ui-testing` when multiple levels apply.

## Modes

| Mode           | Purpose                                                | Reference source                                      | Default threshold   |
| -------------- | ------------------------------------------------------ | ----------------------------------------------------- | ------------------- |
| **Figma**      | Verify implementation matches design specifications    | Figma design exports via `figma-design-fetcher` skill | 2% mismatch         |
| **Screenshot** | Detect unintended visual regressions                   | Previously captured baseline screenshots              | 5% mismatch         |
| **Both**       | Run Figma fidelity + screenshot regression in sequence | Both sources                                          | Per-mode thresholds |

## CLI Interface

```
/ui-visual-testing [options]

Options:
  --ticket KEY           Ticket identifier for context (e.g. DOP-194)
  --base-url URL         Base URL for captures (default: http://localhost:3000)
  --max-iterations N     Max fix-recapture cycles (default: 3)
  --mapping PATH         Path to ui-visual-testing.json (default: auto-detect)
  --mode MODE            figma | screenshot | both (default: auto-detect)
```

## Pipeline Workflow

### Step 1 — Resolve Configuration

Locate the `ui-visual-testing.json` configuration file using this search order:

1. Explicit `--mapping PATH` argument.
2. Co-located config in the component/page directory being tested.
3. `ui-visual-testing.json` in the project root.
4. Generate a minimal config from ticket context if none found.

Read and validate the configuration:

```json
{
  "figma": { "fileKey": "abc123" },
  "thresholds": { "figma": 2, "regression": 5 },
  "maxIterations": 3,
  "screens": [
    {
      "label": "Dashboard – Desktop",
      "figmaNodeId": "12:345",
      "route": "/dashboard",
      "viewport": { "width": 1440, "height": 900 },
      "modes": ["figma", "screenshot"]
    }
  ]
}
```

Validate required fields:

- `screens` array must have at least one entry.
- Each screen must have `label`, `route`, and `viewport`.
- Figma mode requires `figmaNodeId` and `figma.fileKey`.
- Override `maxIterations` with `--max-iterations` argument if provided.

### Step 1b — Load Framework Specialization

Detect the project's UI framework and load the corresponding specialization for renderer timing:

1. **Detect framework** using config files and `package.json` dependencies (same heuristics as the `ui-testing` skill).
2. **Load the specialization** from `references/<framework>-specialization.md`:
   - React / Next.js → [`references/react-specialization.md`](references/react-specialization.md)
   - Future specializations follow the same `<framework>-specialization.md` convention.
3. The specialization provides the `frameworkWait()` logic used in Step 5 for deterministic screenshot capture. If no specialization exists, the universal capture sequence from [`references/renderer-adapters.md`](references/renderer-adapters.md) is used as-is.

### Step 2 — Determine Active Modes

Resolve which modes to run for each screen:

1. **Explicit `--mode` argument** takes precedence and applies to all screens.
2. **Per-screen `modes` array** in the config file.
3. **Auto-detection** based on context:
   - **Figma mode activates** when:
     - The screen entry has a `figmaNodeId`.
     - The ticket description contains Figma URLs.
     - A `figma.fileKey` is configured.
   - **Screenshot mode activates** when:
     - The task modifies an existing screen (detected from git diff).
     - Baseline screenshots exist for the route.
     - The task type is "redesign", "bug fix", or "design token change".

Log the resolved modes:

```
Resolved modes:
  Dashboard – Desktop:  figma + screenshot
  Dashboard – Mobile:   figma only (no baseline exists)
  Settings – Desktop:   screenshot only (no Figma node mapped)
```

### Step 3 — Figma Mode: Fetch Design Context

For screens running in Figma mode:

1. Invoke the `figma-design-fetcher` skill to export design frames:
   ```
   /figma-design-fetcher --file-key <fileKey> --node-ids <nodeId1>,<nodeId2> --scale 2 --format png
   ```
2. Store exported images in `.visual-testing/figma-references/`.
3. Validate that the export dimensions match the configured viewport (allowing for scale factor).
4. If the `figma-design-fetcher` skill is unavailable:
   - Check for manually placed reference images in `.visual-testing/figma-references/`.
   - If none found, skip Figma mode for affected screens and log a warning.

### Step 4 — Screenshot Mode: Capture Before State

For screens running in screenshot mode:

1. Check for existing baseline screenshots in:
   - `.visual-testing/baselines/<screen-label>/`
   - `__screenshots__/<screen-label>/`
2. If baselines exist, use them as the "before" reference.
3. If no baselines exist and the task is modifying an existing screen:
   - Stash current changes: `git stash`.
   - Launch the dev server and capture the current (pre-change) state.
   - Restore changes: `git stash pop`.
   - Store captured images as temporary baselines.
4. If no baselines exist and this is a new screen, screenshot mode is not applicable — skip and log.

Capture parameters:

- Use the viewport dimensions from the screen config.
- Wait for network idle and framework-specific readiness (see [`references/renderer-adapters.md`](references/renderer-adapters.md)).
- Disable CSS animations and transitions for deterministic captures.

### Step 5 — Capture After/Actual Screenshots

Capture screenshots of the current implementation state:

1. Ensure the dev server is running at `--base-url` (default `http://localhost:3000`).
   - If not running, attempt to start it: `pnpm dev`.
   - Wait for server readiness with a health check loop (max 30 seconds).
2. For each screen in the config:
   - Navigate to `<base-url><route>`.
   - Set viewport to configured dimensions.
   - Wait for page readiness:
     - `page.waitForLoadState('networkidle')`
     - Framework-specific waits (see [`references/renderer-adapters.md`](references/renderer-adapters.md)).
     - Custom wait selectors if specified in the screen config.
   - Disable animations:
     ```javascript
     await page.addStyleTag({
       content:
         '*, *::before, *::after { animation-duration: 0s !important; transition-duration: 0s !important; }',
     });
     ```
   - Capture full-page or element-specific screenshot.
   - Store in `.visual-testing/actual/<screen-label>/`.

3. If a screen has `maskRegions` configured, apply masks before comparison (not before capture):
   ```json
   "maskRegions": [
     { "selector": "[data-testid='timestamp']", "reason": "dynamic content" },
     { "selector": ".avatar", "reason": "user-specific content" }
   ]
   ```

### Step 6 — Compare

Run pixel-level comparison for each screen and active mode:

#### Figma mode comparison

- **Reference:** Figma export from Step 3.
- **Actual:** Screenshot from Step 5.
- **Threshold:** `thresholds.figma` (default 2%).
- **Pre-processing:** Resize reference to match actual dimensions if scale factor differs.

#### Screenshot mode comparison

- **Reference:** Baseline from Step 4.
- **Actual:** Screenshot from Step 5.
- **Threshold:** `thresholds.regression` (default 5%).

#### Comparison algorithm

```javascript
import pixelmatch from 'pixelmatch';
import { PNG } from 'pngjs';

const reference = PNG.sync.read(referenceBuffer);
const actual = PNG.sync.read(actualBuffer);
const diff = new PNG({ width: reference.width, height: reference.height });

const mismatchedPixels = pixelmatch(
  reference.data,
  actual.data,
  diff.data,
  reference.width,
  reference.height,
  { threshold: 0.1, alpha: 0.5 },
);

const totalPixels = reference.width * reference.height;
const mismatchPercentage = (mismatchedPixels / totalPixels) * 100;
```

Store results for each screen:

```json
{
  "screen": "Dashboard – Desktop",
  "mode": "figma",
  "mismatchPercentage": 1.3,
  "threshold": 2,
  "passed": true,
  "diffImagePath": ".visual-testing/diffs/dashboard-desktop-figma.png"
}
```

### Step 7 — Iteration Loop

For screens that **fail** comparison (mismatch > threshold):

1. **Analyse the diff image** to identify specific regions of mismatch.
2. **Invoke the visual-verifier agent** (if available) with:
   - The diff image.
   - The reference image (Figma export or baseline).
   - The actual screenshot.
   - The component source code.
3. **Apply suggested fixes** to the source code.
4. **Re-capture** the screen (repeat Step 5 for the failing screen only).
5. **Re-compare** (repeat Step 6 for the failing screen only).
6. **Check result:**
   - If now passing, move to the next failing screen.
   - If still failing and iterations < `maxIterations`, repeat from sub-step 1.
   - If `maxIterations` reached, mark as FAIL and proceed.

Log each iteration:

```
Screen: Dashboard – Desktop (figma mode)
  Iteration 1: 4.7% mismatch (threshold: 2%) — FAIL
    Fix: adjusted padding-top from 24px to 16px in KpiCard
  Iteration 2: 1.1% mismatch (threshold: 2%) — PASS
```

### Step 8 — Final Verdict

Produce the final report and artifacts:

#### Summary output

```
=== Visual Testing Report ===
Mode: both (figma + screenshot)
Screens tested: 4

Results:
  Dashboard – Desktop (figma):     PASS (1.1% < 2%)
  Dashboard – Desktop (screenshot): PASS (0.3% < 5%)
  Dashboard – Mobile (figma):      PASS (1.8% < 2%)
  Settings – Desktop (screenshot): FAIL (7.2% > 5%) — max iterations reached

Overall: FAIL
```

#### Artifacts

All artifacts are stored in `.visual-testing/` relative to the project root:

```
.visual-testing/
├── figma-references/         # Figma exports (Step 3)
│   ├── dashboard-desktop.png
│   └── dashboard-mobile.png
├── baselines/                # Screenshot baselines (Step 4)
│   └── dashboard-desktop.png
├── actual/                   # Current captures (Step 5)
│   ├── dashboard-desktop.png
│   ├── dashboard-mobile.png
│   └── settings-desktop.png
├── diffs/                    # Diff images (Step 6)
│   ├── dashboard-desktop-figma.png
│   ├── dashboard-desktop-screenshot.png
│   └── settings-desktop-screenshot.png
└── visual-diff-report.json   # Machine-readable report
```

#### Report JSON schema

```json
{
  "timestamp": "2026-03-25T14:30:00Z",
  "ticket": "DOP-194",
  "overallResult": "FAIL",
  "screens": [
    {
      "label": "Dashboard – Desktop",
      "route": "/dashboard",
      "viewport": { "width": 1440, "height": 900 },
      "results": [
        {
          "mode": "figma",
          "result": "PASS",
          "mismatchPercentage": 1.1,
          "threshold": 2,
          "iterations": 2,
          "diffImage": ".visual-testing/diffs/dashboard-desktop-figma.png"
        },
        {
          "mode": "screenshot",
          "result": "PASS",
          "mismatchPercentage": 0.3,
          "threshold": 5,
          "iterations": 1,
          "diffImage": ".visual-testing/diffs/dashboard-desktop-screenshot.png"
        }
      ]
    }
  ]
}
```

#### Baseline updates

When screenshot mode passes and no previous baseline existed, or when the user confirms a baseline update:

- Copy the actual screenshot to the baselines directory.
- Log: `Baseline updated: .visual-testing/baselines/dashboard-desktop.png`

Baseline updates should never happen automatically for failing comparisons. Always require explicit user confirmation.

## Error Handling

| Error                                   | Recovery                                                  |
| --------------------------------------- | --------------------------------------------------------- |
| Dev server not running                  | Attempt `pnpm dev`, wait 30s, retry                       |
| Figma export fails                      | Skip Figma mode, warn user, continue with screenshot mode |
| Viewport mismatch (reference vs actual) | Resize reference to match, log warning                    |
| Page load timeout                       | Retry once with extended timeout (60s), then SKIP         |
| pixelmatch dimension mismatch           | Crop to smallest common dimensions, log warning           |
| Git stash conflict (Step 4)             | Skip before-capture, use existing baselines only          |

## Exit Codes

| Code | Meaning                                                           |
| ---- | ----------------------------------------------------------------- |
| 0    | All screens passed in all active modes                            |
| 1    | One or more screens failed visual comparison                      |
| 2    | Configuration error (missing config, invalid schema)              |
| 3    | Infrastructure error (server not starting, browser not installed) |
| 4    | Skipped — no screens to test (all modes deactivated)              |
