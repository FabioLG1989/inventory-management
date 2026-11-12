# Playwright Component Testing Reference

This document covers the **stack-agnostic** setup, configuration, and usage patterns for Playwright Component Testing (CT). Framework-specific mounting syntax, install commands, and config variants live in `*-specialization.md` files.

## Overview

Playwright Component Testing allows mounting individual components in a real browser, testing them in isolation without a full application server. This is Level 2 in the testing pyramid — between unit tests (JSDOM) and full E2E tests.

### When to use CT vs full-page capture

| Use CT when... | Use full-page capture when... |
|----------------|-------------------------------|
| Testing a component in isolation | Testing a complete page with routing |
| Component has multiple visual states to verify | Page requires API responses and auth |
| You need to test responsive behaviour of a single component | You need to verify component integration in context |
| The component is reusable across multiple pages | The test covers a user flow spanning multiple pages |
| You want fast iteration (no server needed) | You need to test SSR/hydration behaviour |
| Testing design system atoms and molecules | Testing full-page layouts and compositions |

## Installation

Install the framework-appropriate Playwright CT package. See the loaded `*-specialization.md` for the exact package name:

```bash
pnpm add -D @playwright/experimental-ct-{framework}
pnpm exec playwright install chromium
```

Replace `{framework}` with the appropriate variant (e.g. `react`, `vue`, `svelte`). Note: not all frameworks have Playwright CT support (e.g. Angular does not — use full-page capture with isolated routes or Storybook integration instead).

## Config Template

### `playwright-ct.config.ts`

```typescript
// Import from the framework-appropriate CT package
// e.g. '@playwright/experimental-ct-react', '@playwright/experimental-ct-vue', etc.
import { defineConfig, devices } from '@playwright/experimental-ct-{framework}';
import path from 'path';

export default defineConfig({
  testDir: './src/__tests__/component',
  snapshotDir: './__screenshots__/components',

  // Timeout per test
  timeout: 30_000,

  // Fail the build on CI if test.only is left in source
  forbidOnly: !!process.env.CI,

  // Retry on CI only
  retries: process.env.CI ? 2 : 0,

  // Reporter
  reporter: process.env.CI ? 'github' : 'html',

  use: {
    // Collect trace on first retry
    trace: 'on-first-retry',

    // Screenshot on failure
    screenshot: 'only-on-failure',

    // CT-specific: configure the bundler
    ctPort: 3100,
    ctViteConfig: {
      resolve: {
        alias: {
          '@': path.resolve(__dirname, './src'),
        },
      },
    },
  },

  projects: [
    {
      name: 'chromium-desktop',
      use: { ...devices['Desktop Chrome'] },
    },
    {
      name: 'chromium-tablet',
      use: { ...devices['iPad (gen 7)'] },
    },
    {
      name: 'chromium-mobile',
      use: { ...devices['iPhone 13'] },
    },
  ],
});
```

### Key config notes

- **`ctViteConfig`**: Playwright CT uses Vite under the hood for bundling. Pass your path aliases and any Vite plugins needed here.
- **`ctPort`**: The port for the CT dev server. Choose a port that does not conflict with your application dev server.
- **`snapshotDir`**: Where visual comparison snapshots are stored. Keep separate from E2E screenshots.

## Mounting Components with Props

The mounting API varies by framework. See the loaded `*-specialization.md` for exact syntax. The patterns below illustrate **generic concepts** using pseudocode-style examples.

### Basic mounting

```typescript
// Import from framework-appropriate CT package
import { test, expect } from '@playwright/experimental-ct-{framework}';

test('renders component with data', async ({ mount }) => {
  // Mounting syntax is framework-specific:
  // - React: mount(<Component prop="value" />)
  // - Vue/Svelte: mount(Component, { props: { prop: 'value' } })
  const component = await mount(/* framework-specific mounting */);

  await expect(component).toContainText('Expected text');
});
```

### Mounting with context providers

Many frameworks require context or providers (theme, auth, routing). Create a `TestWrapper` that wraps the component under test. The wrapper implementation is framework-specific — see the specialization reference.

### Testing event handlers

```typescript
test('calls handler on interaction', async ({ mount }) => {
  let clicked = false;

  const component = await mount(/* component with onClick={() => { clicked = true; }} */);

  await component.click();
  expect(clicked).toBe(true);
});
```

### Testing multiple states

```typescript
test.describe('Badge component', () => {
  const variants = ['success', 'warning', 'error', 'info'] as const;

  for (const variant of variants) {
    test(`renders ${variant} variant`, async ({ mount }) => {
      const component = await mount(/* Badge with variant */);

      await expect(component).toBeVisible();
      await expect(component).toHaveScreenshot(`badge-${variant}.png`);
    });
  }
});
```

## Capturing Component Screenshots in Isolation

### Basic screenshot comparison

```typescript
test('matches visual snapshot', async ({ mount }) => {
  const component = await mount(/* component under test */);

  // Disable animations before capture
  await component.evaluate(el => {
    const style = document.createElement('style');
    style.textContent = '*, *::before, *::after { animation-duration: 0s !important; transition-duration: 0s !important; }';
    document.head.appendChild(style);
  });

  await expect(component).toHaveScreenshot('component-default.png', {
    maxDiffPixelRatio: 0.02,
  });
});
```

### Screenshot with interaction states

```typescript
test('hover state matches snapshot', async ({ mount }) => {
  const component = await mount(/* interactive component */);

  // Capture default state
  await expect(component).toHaveScreenshot('component-idle.png');

  // Hover and capture
  await component.hover();
  await expect(component).toHaveScreenshot('component-hover.png');

  // Focus and capture
  await component.focus();
  await expect(component).toHaveScreenshot('component-focus.png');
});
```

### Screenshots with custom pixelmatch options

```typescript
test('matches design with custom threshold', async ({ mount }) => {
  const component = await mount(/* component under test */);

  await expect(component).toHaveScreenshot('component.png', {
    maxDiffPixelRatio: 0.01,  // Stricter than default
    threshold: 0.1,            // pixelmatch sensitivity
    animations: 'disabled',    // Built-in animation disabling
  });
});
```

## Multi-Viewport Component Testing

### Using Playwright projects

The config template above defines three projects (desktop, tablet, mobile). Each test automatically runs at all three viewport sizes.

### Explicit viewport testing within a single test

For cases where you need to test specific viewport transitions:

```typescript
test('responsive layout changes', async ({ mount, page }) => {
  const component = await mount(/* dashboard component with mock data */);

  // Desktop: 4-column grid
  await page.setViewportSize({ width: 1440, height: 900 });
  await expect(component).toHaveScreenshot('dashboard-desktop.png');

  // Tablet: 2-column grid
  await page.setViewportSize({ width: 768, height: 1024 });
  await expect(component).toHaveScreenshot('dashboard-tablet.png');

  // Mobile: single column
  await page.setViewportSize({ width: 375, height: 667 });
  await expect(component).toHaveScreenshot('dashboard-mobile.png');
});
```

### Testing responsive behaviour logic

```typescript
test('collapses sidebar on mobile viewport', async ({ mount, page }) => {
  await page.setViewportSize({ width: 375, height: 667 });

  const component = await mount(/* sidebar component with mock nav items */);

  // Sidebar should be collapsed on mobile
  await expect(component.locator('[data-testid="sidebar-expanded"]')).not.toBeVisible();
  await expect(component.locator('[data-testid="sidebar-toggle"]')).toBeVisible();

  // Click toggle to expand
  await component.locator('[data-testid="sidebar-toggle"]').click();
  await expect(component.locator('[data-testid="sidebar-expanded"]')).toBeVisible();
});
```

## Framework-Specific Mounting

Each framework has its own mounting syntax, import paths, and context provider patterns. Consult the loaded specialization reference:

| Framework | Specialization | Mounting style |
|-----------|---------------|----------------|
| React | [`react-specialization.md`](react-specialization.md) | JSX: `mount(<Component prop="value" />)` |
| Vue | `vue-specialization.md` (future) | Object props: `mount(Component, { props: { ... } })` |
| Svelte | `svelte-specialization.md` (future) | Object props: `mount(Component, { props: { ... } })` |
| Angular | N/A | No Playwright CT adapter — use full-page capture |

## Accessibility Testing with CT

Integrate axe-core for accessibility validation in component tests:

```bash
pnpm add -D @axe-core/playwright
```

```typescript
import { test, expect } from '@playwright/experimental-ct-{framework}';
import AxeBuilder from '@axe-core/playwright';

test('has no accessibility violations', async ({ mount, page }) => {
  await mount(/* component under test */);

  const accessibilityScanResults = await new AxeBuilder({ page })
    .include('[data-testid="component-root"]')
    .analyze();

  expect(accessibilityScanResults.violations).toEqual([]);
});
```

## Directory Structure

Recommended test file organisation:

```
src/__tests__/component/
├── entities/
│   ├── kpi/
│   │   └── KpiCard.spec.tsx
│   └── insight/
│       └── InsightCard.spec.tsx
├── shared/
│   └── ui/
│       ├── Badge.spec.tsx
│       ├── Button.spec.tsx
│       └── Tooltip.spec.tsx
├── widgets/
│   ├── KpiDashboard.spec.tsx
│   └── InsightPanel.spec.tsx
└── test-utils.tsx
```

Test files use `.spec.tsx` extension to distinguish from unit tests (`.test.tsx`).
