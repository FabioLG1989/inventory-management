---
name: ui-testing
description: >
  Stack-agnostic UI testing orchestration across 4 levels: unit, component,
  E2E, and visual. Detects project testing tools, loads framework-specific
  specializations, suggests setup when missing, and coordinates test
  generation for UI tasks. Use when implementing UI components, pages,
  or features that need testing.
user-invocable: true
argument-hint: '[--ticket KEY] [--levels unit,component,e2e,visual]'
allowed-tools: Read, Write, Bash, Glob, Grep, Edit, Skill
---

# UI Testing Orchestration

Coordinates test generation across four testing levels for UI tasks. Detects the project's existing testing infrastructure, loads framework-specific specializations, suggests setup when tools are missing, and delegates test generation to specialised mastery skills.

This skill is **stack-agnostic**. Core orchestration logic (test level selection, tool detection algorithm, report format) is framework-independent. Framework-specific knowledge (tool variants, install commands, starter configs) lives in `references/*-specialization.md` files that are loaded dynamically based on project detection. Project-specific test layout (where atoms / molecules / pages live in THIS codebase) is delegated to the service page's `## Conventions & How-To` → Testing sub-heading at `docs/llm-wiki/wiki/services/<id>.md` (synthesised by `/initialize-project`).

## Boundary — relationship to `/ui-visual-testing`

This skill is the **orchestrator** across all four testing levels (unit / component / E2E / visual). When the resolved level set includes Level 4 (visual), this skill delegates to `/ui-visual-testing` (see Step 6). The visual-testing skill is also independently invokable when only visual regression / Figma-fidelity work is needed; this skill is the right entry point when multiple levels apply.

## Workflow

### Step 1 — Parse Arguments

Extract from the invocation:

- `--ticket KEY` — ticket identifier (e.g. `DOP-194`). When provided, the skill reads ticket content to classify the UI task and derive test requirements from the Definition of Done.
- `--levels unit,component,e2e,visual` — explicit comma-separated list of levels to run. When omitted, levels are derived from the ticket DoD or the decision matrix.

If neither `--ticket` nor `--levels` is provided, prompt the user:

> Which test levels should I generate? Options: `unit`, `component`, `e2e`, `visual` (comma-separated), or provide a `--ticket` key so I can determine them automatically.

### Step 2 — Load Framework Specialization

Detect the project's UI framework and load the corresponding specialization reference:

1. **Detect framework** by checking (in order):
   - Config files in the project root: `next.config.*` (Next.js/React), `nuxt.config.*` (Nuxt/Vue), `angular.json` (Angular), `svelte.config.*` (Svelte/SvelteKit)
   - Framework-specific dependencies in `package.json`: `next`, `react`, `vue`, `@angular/core`, `svelte`
   - Existing test file imports (fallback heuristic)

2. **Load the specialization** from `references/<framework>-specialization.md`:
   - React / Next.js → [`references/react-specialization.md`](references/react-specialization.md)
   - Future specializations follow the same `<framework>-specialization.md` convention.

3. If no specialization file exists for the detected framework, proceed with **generic defaults only** (the core skill remains fully functional without a specialization — it just won't suggest framework-specific tool variants or starter configs).

Log the result:

```
Framework detected: React (Next.js)
Specialization loaded: references/react-specialization.md
```

### Step 3 — UI Task Detection

Classify the current task by running `classifyUITask()` logic against the available context:

1. If a ticket key was provided, read the ticket content (title, description, acceptance criteria, DoD).
2. Scan the current working branch diff (`git diff main...HEAD --name-only`) to identify changed/new UI files.
3. **Read the project's testing layout** from the frontend service page's `## Conventions & How-To` → Testing sub-heading (`docs/llm-wiki/wiki/services/<id>.md`, synthesised by `/initialize-project`). It documents WHICH directories hold atoms / molecules / organisms / pages in this codebase — atomic-design layout, FSD layout, flat `components/`, Next.js `app/`, or any other shape. Do NOT hardcode a methodology here; the project's actual convention is the source of truth.
4. Classify into one of these task types by matching the changed files against the directory patterns from the testing conventions page:
   - **New atom/molecule component** — new file in the project's atom/molecule directory
   - **New organism/widget** — new file in the project's organism/widget directory
   - **New page/feature** — new file in the project's pages/features directory
   - **Redesign existing screen** — modifications to existing page/widget with visual changes
   - **Bug fix on existing UI** — fix-type commit touching UI files
   - **Design token/theme change** — changes to theme tokens, design system primitives, or global stylesheets
   - **Accessibility improvement** — a11y-related changes (aria attributes, keyboard navigation, focus management)

If the service page's `## Conventions & How-To` → Testing sub-heading is missing (project not yet initialised), fall back to detecting common patterns from `package.json` + the actual directory tree under `src/` or `apps/`. Surface a warning that the classification is heuristic; recommend the user run `/initialize-project` for accurate convention pickup.

Output the classification and proceed.

### Step 4 — Determine Test Levels

Resolve which of the four levels apply using this priority order:

1. **Explicit `--levels` argument** — use as-is, no further logic needed.
2. **Ticket DoD** — if the ticket specifies test requirements (e.g. "unit tests required", "E2E coverage for happy path"), map those to levels.
3. **Decision matrix** — look up the task type from Step 3 in [`references/test-level-matrix.md`](references/test-level-matrix.md) to determine Required / Recommended / Optional levels.

If the matrix yields only "Recommended" levels (none Required), confirm with the user before proceeding.

Present the resolved levels to the user:

```
UI Task Type: New organism/widget
Test levels:
  - Unit:      Required
  - Component: Required
  - E2E:       Recommended
  - Visual:    If Figma exists → checking...
```

### Step 5 — Detect Tools

For each active level, detect whether the necessary tooling is installed. Follow the detection order specified in [`references/tool-detection.md`](references/tool-detection.md). Use the loaded specialization (Step 2) for framework-specific tool variants and install commands.

#### Level 1 — Unit Testing

1. Check for `vitest.config.ts` or `vitest.config.js` in the project root.
2. If not found, check for `jest.config.*` (js, ts, json, cjs, mjs).
3. Check for the framework-appropriate Testing Library package in `package.json` (e.g. `@testing-library/react`, `@testing-library/vue`, `@testing-library/svelte`).
4. If nothing found, suggest installation using the specialization's recommended install command. Generic fallback:
   ```
   pnpm add -D vitest @testing-library/{framework} @testing-library/jest-dom
   ```

#### Level 2 — Component Testing

1. Check for the framework-appropriate Playwright CT package in `package.json` (e.g. `@playwright/experimental-ct-react`, `@playwright/experimental-ct-vue`).
2. Check for `playwright-ct.config.ts` in the project root.
3. If not found, suggest installation using the specialization's recommended install command and provide a starter config.

#### Level 3 — E2E Testing

1. Check for `@playwright/test` in `package.json`.
2. Check for `playwright.config.ts` in the project root.
3. If not found, suggest installation:
   ```
   pnpm add -D @playwright/test && pnpm exec playwright install
   ```

#### Level 4 — Visual Testing

1. Visual testing always uses Playwright + `pixelmatch`.
2. Check for `pixelmatch` and `pngjs` in `package.json`.
3. If not found, suggest installation:
   ```
   pnpm add -D pixelmatch pngjs
   ```

If any required tool is missing, ask the user whether to install it or skip that level.

### Step 6 — Generate Tests

For each active level, delegate to the appropriate mastery skill:

| Level           | Skill                                            | Notes                                           |
| --------------- | ------------------------------------------------ | ----------------------------------------------- |
| Unit            | `jest-coverage-automation` (Jest) or inline generation | Based on detected tool from Step 5              |
| Component       | (inline generation)                              | Generate Playwright CT test files directly      |
| E2E             | `playwright-e2e-automation`                      | Pass route paths and user flows                 |
| Visual          | `ui-visual-testing`                              | Pass Figma mapping and screenshot config        |
| Accessibility   | `accessibility-testing`                          | Always run when task type is a11y; run alongside component/E2E for new pages |

#### Unit test generation

When the detected runner is Jest, invoke the skill with the target files:

```
/jest-coverage-automation --files <changed-ui-files>
```

For any other runner, generate the unit test files directly, following the project's existing test files and the service page's Testing rules.

#### Component test generation

Generate Playwright Component Test files that:

- Mount the component in isolation with representative props
- Test interactive states (hover, focus, disabled, loading, error)
- Capture screenshots at each viewport breakpoint
- Delegate accessibility verification to `/accessibility-testing --files <component-file> --wcag AA`

#### E2E test generation

Invoke Playwright E2E automation:

```
/playwright-e2e-automation --routes <affected-routes> --flows <user-flows>
```

#### Visual test generation

Invoke the visual testing skill:

```
/ui-visual-testing --ticket <KEY> --mode figma|screenshot|both
```

### Step 7 — Run Tests and Report

Execute all generated tests and produce a summary report:

1. **Run unit tests:**

   ```bash
   pnpm vitest run --reporter=verbose <test-files>
   ```

2. **Run component tests:**

   ```bash
   pnpm playwright test --config=playwright-ct.config.ts <test-files>
   ```

3. **Run E2E tests:**

   ```bash
   pnpm playwright test <test-files>
   ```

4. **Run visual tests:**
   Handled by the `ui-visual-testing` skill's own execution pipeline.

5. **Aggregate results:**

```
=== UI Testing Report ===
Task:       New organism/widget — KpiDashboard
Ticket:     DOP-194

Level 1 — Unit:       8/8 passed  (coverage: 87%)
Level 2 — Component:  4/4 passed  (3 viewports)
Level 3 — E2E:        3/3 passed  (happy path, error state, empty state)
Level 4 — Visual:     2/2 passed  (diff < 2% threshold)

Overall: PASS
```

If any level fails, provide actionable diagnostics:

- For unit failures: show the failing assertion and the component code in question.
- For component failures: include the screenshot diff if available.
- For E2E failures: include the trace file path and the step that failed.
- For visual failures: include the diff image path and the mismatch percentage.

## Error Handling

- If a mastery skill is not available, fall back to inline test generation using best practices for the detected tool.
- If the dev server is not running (needed for E2E/visual), attempt to start it and wait for readiness before proceeding.
- If test generation fails for a specific level, log the error and continue with remaining levels.
- Always produce a partial report even if some levels fail.

## Exit Codes

| Code | Meaning                                                 |
| ---- | ------------------------------------------------------- |
| 0    | All requested levels passed                             |
| 1    | One or more test failures                               |
| 2    | Tool detection failed and user declined setup           |
| 3    | Configuration error (invalid arguments, missing ticket) |
