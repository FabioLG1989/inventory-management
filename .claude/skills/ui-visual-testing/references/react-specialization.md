# React & Next.js — Visual Testing Specialization

Framework-specific renderer timing, Playwright CT mounting syntax, and screenshot capture strategies for React and Next.js projects. Loaded by the `ui-visual-testing` skill when the project framework is detected as React or Next.js.

## Framework Detection

### React

- **DOM marker:** `<div id="root">` as the React mount point
- **Dependencies:** `react`, `react-dom` in `package.json`

### Next.js

- **DOM marker:** `window.__NEXT_DATA__` global, `<div id="__next">` container
- **Config files:** `next.config.ts`, `next.config.js`, `next.config.mjs`
- **Dependencies:** `next` in `package.json`

---

## Renderer Timing — React

### Hydration wait

React Server Components and client-side hydration mean the initial HTML may differ from the final interactive state. Screenshots must wait for hydration to complete.

```javascript
// Wait for React hydration to complete
await page.waitForFunction(() => {
  const html = document.documentElement;
  return !html.classList.contains('nprogress-busy') &&
         document.readyState === 'complete';
});

// Wait for any pending state updates to flush
await page.waitForTimeout(100);
```

### Suspense boundaries

React Suspense shows fallback content while async components load. Screenshots may capture the fallback instead of the resolved content.

```javascript
// Wait for all Suspense boundaries to resolve
await page.waitForFunction(() => {
  const skeletons = document.querySelectorAll(
    '[data-testid="skeleton"], .skeleton, [aria-busy="true"]'
  );
  return skeletons.length === 0;
});
```

### Lazy loading (`React.lazy`)

Dynamically imported components may not be loaded on initial render.

```javascript
// Wait for dynamic imports to resolve
await page.waitForLoadState('networkidle');

// Additionally wait for any lazy-loaded components
await page.waitForFunction(() => {
  const suspenseFallbacks = document.querySelectorAll('[data-suspense-fallback]');
  return suspenseFallbacks.length === 0;
});
```

### React 19 concurrent features

React 19 with concurrent rendering may batch updates and defer rendering:

```javascript
// Wait for concurrent renders to settle
await page.waitForTimeout(200);
await page.waitForFunction(() => {
  return document.readyState === 'complete' &&
         !document.querySelector('[aria-busy="true"]');
});
```

---

## Renderer Timing — Next.js

### SSR vs CSR considerations

Next.js pages can be SSR, SSG, or CSR. Each mode has different timing requirements.

**Detection:**

```javascript
const renderingMode = await page.evaluate(() => {
  if (window.__NEXT_DATA__?.props?.pageProps) return 'ssr';
  if (document.querySelector('#__next')?.children.length === 0) return 'csr';
  return 'ssg';
});
```

**SSR/SSG mitigation:**

```javascript
await page.waitForFunction(() => {
  return window.__NEXT_DATA__ !== undefined &&
         document.readyState === 'complete';
});
```

**CSR mitigation:**

```javascript
await page.waitForSelector('#__next > *');
await page.waitForLoadState('networkidle');
```

### App Router considerations

Next.js App Router (v13+) with React Server Components has additional timing concerns:

- **Streaming SSR:** Content may arrive in chunks:
  ```javascript
  await page.waitForFunction(() => {
    return !document.querySelector('template[data-next-stream]');
  });
  ```

- **Parallel routes:** Multiple route segments load independently:
  ```javascript
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(300);
  ```

- **Loading UI:** `loading.tsx` files show loading states during navigation:
  ```javascript
  await page.waitForFunction(() => {
    const loadingElements = document.querySelectorAll('[data-next-loading]');
    return loadingElements.length === 0;
  });
  ```

### Route prefetching

Next.js prefetches linked routes on hover/viewport intersection. This network activity can affect `networkidle` timing.

```javascript
// Use domcontentloaded + explicit selector instead of networkidle
await page.waitForLoadState('domcontentloaded');
await page.waitForSelector('[data-testid="page-content"]');
```

---

## Combined `frameworkWait()` Implementation

Use this as the React/Next.js implementation for step 5 in the universal capture sequence:

```javascript
async function reactFrameworkWait(page) {
  // 1. Check for Next.js
  const isNextJs = await page.evaluate(() => !!window.__NEXT_DATA__);

  if (isNextJs) {
    // Wait for Next.js hydration
    await page.waitForFunction(() => {
      return window.__NEXT_DATA__ !== undefined &&
             document.readyState === 'complete';
    });

    // Wait for streaming to complete (App Router)
    await page.waitForFunction(() => {
      return !document.querySelector('template[data-next-stream]');
    }).catch(() => {}); // Ignore if not using streaming

    // Wait for loading states to clear
    await page.waitForFunction(() => {
      return document.querySelectorAll('[data-next-loading]').length === 0;
    }).catch(() => {});
  }

  // 2. Wait for Suspense boundaries (React universal)
  await page.waitForFunction(() => {
    const busy = document.querySelectorAll(
      '[data-testid="skeleton"], .skeleton, [aria-busy="true"]'
    );
    return busy.length === 0;
  });

  // 3. Wait for concurrent rendering to settle
  await page.waitForTimeout(200);
}
```

---

## Playwright Component Testing — Mounting

### React JSX mounting

```typescript
import { test, expect } from '@playwright/experimental-ct-react';
import { KpiCard } from '@/entities/kpi/ui/KpiCard';

test('renders KPI card with data', async ({ mount }) => {
  const component = await mount(
    <KpiCard
      label="Revenue"
      value={1250000}
      currency="USD"
      trend={{ direction: 'up', percentage: 12.5 }}
    />
  );

  await expect(component).toContainText('Revenue');
  await expect(component).toContainText('$1,250,000');
  await expect(component).toContainText('+12.5%');
});
```

### Context providers

Many React components require context (theme, auth, router). Create a `TestWrapper`:

```typescript
// src/__tests__/component/test-utils.tsx
import { ThemeProvider } from '@/shared/ui/ThemeProvider';

export function TestWrapper({ children }: { children: React.ReactNode }) {
  return (
    <ThemeProvider defaultTheme="light">
      {children}
    </ThemeProvider>
  );
}
```

```typescript
import { test, expect } from '@playwright/experimental-ct-react';
import { KpiCard } from '@/entities/kpi/ui/KpiCard';
import { TestWrapper } from './test-utils';

test('renders with theme context', async ({ mount }) => {
  const component = await mount(
    <TestWrapper>
      <KpiCard label="Revenue" value={1250000} currency="USD" />
    </TestWrapper>
  );

  await expect(component).toBeVisible();
});
```

### Event handlers

```typescript
test('calls onClick when card is clicked', async ({ mount }) => {
  let clicked = false;

  const component = await mount(
    <KpiCard
      label="Revenue"
      value={1250000}
      currency="USD"
      onClick={() => { clicked = true; }}
    />
  );

  await component.click();
  expect(clicked).toBe(true);
});
```

### Multiple visual states

```typescript
test.describe('Badge component', () => {
  const variants = ['success', 'warning', 'error', 'info'] as const;

  for (const variant of variants) {
    test(`renders ${variant} variant`, async ({ mount }) => {
      const component = await mount(
        <Badge variant={variant} label={`${variant} badge`} />
      );

      await expect(component).toBeVisible();
      await expect(component).toHaveScreenshot(`badge-${variant}.png`);
    });
  }

  test('renders disabled state', async ({ mount }) => {
    const component = await mount(
      <Badge variant="success" label="Disabled" disabled />
    );

    await expect(component).toHaveCSS('opacity', '0.5');
  });

  test('renders loading state', async ({ mount }) => {
    const component = await mount(
      <Badge variant="success" label="Loading" loading />
    );

    await expect(component.locator('[data-testid="spinner"]')).toBeVisible();
  });
});
```

### Accessibility testing

```typescript
import { test, expect } from '@playwright/experimental-ct-react';
import AxeBuilder from '@axe-core/playwright';
import { KpiCard } from '@/entities/kpi/ui/KpiCard';

test('has no accessibility violations', async ({ mount, page }) => {
  await mount(
    <KpiCard label="Revenue" value={1250000} currency="USD" />
  );

  const accessibilityScanResults = await new AxeBuilder({ page })
    .include('[data-testid="kpi-card"]')
    .analyze();

  expect(accessibilityScanResults.violations).toEqual([]);
});
```
