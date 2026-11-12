---
name: accessibility-testing
version: 1.0.0
last-updated: 2026-06-10
description: >
  Automated and manual accessibility testing for web UIs. Use when implementing or reviewing UI
  components, pages, or features that need WCAG 2.1 compliance verification. Covers axe-core
  integration with Playwright, keyboard navigation testing, ARIA correctness, focus management,
  color contrast, and screen reader compatibility. Invoked by /ui-testing for accessibility tasks;
  also directly invokable. Triggers on: accessibility, a11y, WCAG, axe, aria, keyboard navigation,
  screen reader, focus management, color contrast.
argument-hint: '--files <paths> [--wcag A|AA|AAA] [--include keyboard|contrast|aria|all]'
allowed-tools: Read, Write, Bash, Glob, Grep, Edit, Task
user-invocable: true
is_linkable_to_agents: true
---

# Accessibility Testing

Generates and runs axe-core-based accessibility tests embedded in Playwright component and E2E
tests. Supplements automated scanning with patterns for keyboard navigation, ARIA correctness, and
focus management that axe-core cannot catch automatically.

## Contents

| Reference | Purpose |
|-----------|---------|
| [wcag-quick-ref.md](references/wcag-quick-ref.md) | WCAG 2.1 Level A and AA criteria, axe coverage, Playwright patterns |
| [test-patterns.md](references/test-patterns.md) | Canonical axe scan test, keyboard navigation, ARIA correctness, and focus management code examples |

---

## WCAG 2.1 Coverage

| Level | Criterion | Automated (axe) | Patterns in this skill |
|-------|-----------|-----------------|------------------------|
| A | 1.1.1 Non-text Content | ✓ missing alt | ✓ |
| A | 1.3.1 Info & Relationships | ✓ semantic HTML | ✓ |
| A | 1.3.2 Meaningful Sequence | ✗ | ✓ DOM order tests |
| A | 2.1.1 Keyboard | ✗ | ✓ keyboard nav patterns |
| A | 2.4.1 Bypass Blocks | ✗ | ✓ skip link patterns |
| A | 2.4.3 Focus Order | ✗ | ✓ focus trap patterns |
| A | 4.1.1 Parsing | ✓ duplicate IDs | ✓ |
| A | 4.1.2 Name, Role, Value | ✓ ARIA | ✓ |
| AA | 1.4.3 Contrast (Minimum) | ✓ via axe | ✓ |
| AA | 1.4.4 Resize Text | ✗ | ✓ viewport resize pattern |
| AA | 2.4.6 Headings and Labels | ✓ heading order | ✓ |
| AA | 4.1.3 Status Messages | ✗ | ✓ aria-live patterns |

---

## Prerequisites

- A Playwright (or equivalent E2E runner) setup in the project — `@playwright/test` in `package.json`
  or `playwright` in PATH
- `@axe-core/playwright` and `axe-core` in devDependencies (see Setup)

If the runner is not detected the skill still generates the tests and emits install instructions;
it does not abort.

---

## Setup

Install `@axe-core/playwright` and `axe-core` in the target project. `axe-core` must be a direct
dependency, not transitive — the generated tests import its `Result` type by name, which pnpm's
isolated `node_modules` will not resolve otherwise:

```bash
pnpm add -D @axe-core/playwright axe-core
# or
npm install --save-dev @axe-core/playwright axe-core
```

Create the fixture at `<E2E_DIR>/fixtures/a11y.ts`, extending the project's fixture barrel
(`<E2E_DIR>/fixtures/index.ts`) rather than Playwright's `base` directly. This extends the
canonical barrel — it does not replace it. `export * from './a11y'` would silently lose to the
barrel's own local `test` binding (a local export always wins over a same-named `export *`
re-export in ES modules), so a11y specs import `test`/`expect` from this file directly instead of
from the barrel:

```typescript
// <E2E_DIR>/fixtures/a11y.ts
import { test as baseTest } from './index';
import AxeBuilder from '@axe-core/playwright';

export const test = baseTest.extend<{ makeAxeBuilder: () => AxeBuilder }>({
  makeAxeBuilder: async ({ page }, use) => {
    const makeAxeBuilder = () => new AxeBuilder({ page });
    await use(makeAxeBuilder);
  },
});

export { expect } from '@playwright/test';
```

---

## Arguments

| Argument | Values | Default | Description |
|----------|--------|---------|-------------|
| `--files` | glob or path list | (required) | Target component or page files to test |
| `--wcag` | `A`, `AA`, `AAA` | `AA` | Minimum WCAG conformance level |
| `--include` | `keyboard`, `contrast`, `aria`, `all` | `all` | Test categories to generate beyond axe scan |

---

## Workflow

**Agent invocation.** The phases below delegate to the files under `agents/`. Spawn each one with
`Task` when it is available. When it is not (Codex CLI has no `Task` tool), read the agent file and
follow it inline in the current turn — the inputs, outputs and ordering are identical either way.
Never skip an agent because `Task` is unavailable.

### Phase 0 — Parse Arguments

Extract `--files`, `--wcag`, and `--include` from the invocation. When `--wcag` is `A`, set
axe tags to `['wcag2a']`. When `AA` (default), use `['wcag2a', 'wcag2aa']`. When `AAA`, add
`'wcag2aaa'`.

Map `--include all` to the full set: keyboard, contrast, aria, focus.

### Phase 1 — Inject axe-core into Existing Playwright Tests

For each target file:

1. Locate its existing Playwright test file (pattern: `*.spec.ts`, `*.e2e.spec.ts`, `*.ct.spec.ts`
   alongside or under the E2E directory).
2. If a test file exists, extend the existing `test.describe` block with an axe scan test. Do not
   create a parallel file — inject into the existing `describe` block.
3. If no test file exists, create `<E2E_DIR>/tests/<component-name>.a11y.spec.ts`.

Canonical axe scan test: see [`references/test-patterns.md`](./references/test-patterns.md#canonical-axe-scan-test).

### Phase 2 — Generate Keyboard and ARIA Tests

Generate additional test cases for elements axe cannot validate at runtime. For each interactive
element found in the target file (buttons, links, inputs, `<textarea>`, `<select>`, modals, menus,
composite widgets, and elements with an interactive ARIA role such as `role="button"`):

Canonical examples for keyboard navigation (tab order, modal focus trap, arrow key composite widgets), ARIA dynamic content (`aria-busy`, `aria-describedby`), and focus management on route change: see [`references/test-patterns.md`](./references/test-patterns.md).

### Phase 3 — Run and Report

Run the generated tests with the `@a11y` tag filter:

```bash
npx playwright test --grep @a11y
```

Present a violations summary in this format when failures occur:

```
Accessibility violations found: 3

[critical] aria-required-children — 1 element
  Element: <ul role="listbox">
  Fix:     Add role="option" to each child <li>
  WCAG:    1.3.1 (A), 4.1.2 (AA)

[serious] color-contrast — 2 elements
  Element: <span class="label-muted">
  Fix:     Increase text color contrast ratio to at least 4.5:1
  WCAG:    1.4.3 (AA)

[moderate] label — 1 element
  Element: <input type="search">
  Fix:     Add an associated <label> or aria-label attribute
  WCAG:    1.3.1 (A), 4.1.2 (AA)
```

---

## Keyboard Navigation Patterns

Axe-core cannot verify runtime keyboard behavior. Apply these patterns for every interactive
element found in the target files.

| Element Type | Pattern | Key Sequence |
|--------------|---------|-------------|
| Modal dialog | Focus enters first focusable child on open; Tab stays in modal; Escape closes | Tab, Shift+Tab, Escape |
| Dropdown menu | Arrow keys move between items; Escape closes; Enter activates | ArrowDown, ArrowUp, Escape, Enter |
| Tabs widget | Arrow keys switch tabs; Tab moves into tab panel | ArrowLeft, ArrowRight, Tab |
| Listbox | Arrow keys move between options; Space/Enter selects | ArrowDown, ArrowUp, Space, Enter |
| Skip link | First Tab press from top exposes skip link; Enter moves focus to landmark | Tab, Enter |
| Date picker | Arrow keys navigate calendar; Escape closes | ArrowKeys, Escape, Enter |

---

## ARIA Correctness Patterns

These checks supplement axe and target runtime behavior. See [`references/test-patterns.md`](./references/test-patterns.md#aria-correctness-checks) for modal dialog, live region, and custom widget role checks.

---

## Focus Management Patterns

| Trigger | Expected focus destination |
|---------|---------------------------|
| Modal opens | First focusable element inside modal |
| Modal closes | Element that triggered the modal to open |
| Route change (SPA) | `<h1>` of the new page, or the main landmark |
| Toast/alert dismissal | Element that triggered the action, or logical predecessor |
| Inline error appears | Field with `aria-invalid="true"` or the error message |

---

## Agent Invocation

Delegate to `./agents/implementer.md` with the resolved context:

```
/accessibility-testing --files src/components/Dashboard.tsx --wcag AA --include all
```

The implementer agent reads target files, detects existing Playwright tests, injects the axe
fixture, and generates the full test suite for all four pattern categories.
