# React & Next.js — UI Testing Specialization

Framework-specific tool variants, install commands, starter configs, and detection heuristics for React and Next.js projects. Loaded by the `ui-testing` skill when the project framework is detected as React or Next.js.

## Framework Detection

### React

- **Config file:** `vite.config.ts` with `@vitejs/plugin-react` import
- **Dependencies:** `react`, `react-dom` in `package.json`

### Next.js

- **Config files:** `next.config.ts`, `next.config.js`, `next.config.mjs`
- **Dependencies:** `next` in `package.json`
- **Detection hint:** If `next` is detected, treat as React + Next.js (Next.js implies React)

---

## Level 1 — Unit Testing

### Recommended stack

- **Test runner:** Vitest (preferred) — fast, native ESM support, first-class Vite integration
- **Fallback:** Jest — works but requires `ts-jest` or `@swc/jest` for TypeScript
- **Testing Library:** `@testing-library/react` (requires `react-dom`, typically already installed)

### Install command

```bash
pnpm add -D vitest @vitest/ui @testing-library/react @testing-library/jest-dom @testing-library/user-event jsdom
```

With Jest fallback:

```bash
pnpm add -D jest @types/jest ts-jest @testing-library/react @testing-library/jest-dom @testing-library/user-event jest-environment-jsdom
```

### Starter Vitest config

```typescript
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: true,
    // Replace with the project's actual setup-file path (auto-detect from
    // any existing vitest/jest config, else fall back to the path documented
    // in the service page's ## Conventions & How-To → Testing sub-heading).
    setupFiles: ['./src/test-setup.ts'],
    // Replace with the project's actual source root(s).
    include: ['src/**/*.test.{ts,tsx}'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'json', 'html'],
      include: ['src/**/*.{ts,tsx}'],
      exclude: ['src/**/*.test.{ts,tsx}', 'src/**/*.d.ts'],
    },
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
})
```

### Next.js-specific unit testing

- For React Server Components (RSC), use Vitest with `server` environment for server components and `jsdom` for client components
- Use `vi.mock('next/navigation', ...)` to mock Next.js navigation hooks (`useRouter`, `usePathname`, `useSearchParams`)
- Use `vi.mock('next/image', ...)` to mock `next/image` in unit tests

---

## Level 2 — Component Testing (Playwright CT)

### Package

```bash
pnpm add -D @playwright/experimental-ct-react
pnpm exec playwright install chromium
```

### Starter config (`playwright-ct.config.ts`)

```typescript
import { defineConfig, devices } from '@playwright/experimental-ct-react'
import path from 'path'

export default defineConfig({
  testDir: './src/__tests__/component',
  snapshotDir: './__screenshots__/components',
  timeout: 30_000,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  reporter: process.env.CI ? 'github' : 'html',
  use: {
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
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
})
```

### Next.js considerations for CT

- Ensure `next.config.js` settings are compatible with CT bundling (CT uses Vite, not Webpack/Turbopack)
- Mock Next.js-specific imports (`next/link`, `next/image`, `next/router`) in the CT Vite config
- Context providers (theme, auth) should be wrapped via a `TestWrapper` component

---

## Level 3 — E2E Testing

### Standard config

Standard Playwright config applies. The key Next.js-specific addition is the `webServer` option to auto-start the dev server:

```typescript
import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './src/__tests__/e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: 'html',
  use: {
    baseURL: 'http://localhost:3000',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
    {
      name: 'mobile',
      use: { ...devices['Pixel 5'] },
    },
  ],
  webServer: {
    command: 'pnpm dev',
    url: 'http://localhost:3000',
    reuseExistingServer: !process.env.CI,
  },
})
```

### Next.js webServer notes

- `pnpm dev` starts the Next.js dev server on port 3000 by default
- For CI, consider `pnpm build && pnpm start` for production-like testing
- The `reuseExistingServer` option prevents conflicts when the dev server is already running locally

---

## Level 4 — Visual Testing

No special tool configuration beyond standard Playwright + pixelmatch. Framework-specific considerations for React/Next.js are in the `ui-visual-testing` skill's [`react-specialization.md`](../../ui-visual-testing/references/react-specialization.md) (renderer timing, hydration waiting, etc.).
