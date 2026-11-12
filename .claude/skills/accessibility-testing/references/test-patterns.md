# Accessibility Test Patterns

Canonical code examples for axe-core integration, keyboard navigation, ARIA correctness, and focus management.

## Contents

- [Canonical Axe Scan Test](#canonical-axe-scan-test)
- [Keyboard Navigation](#keyboard-navigation)
- [ARIA Dynamic Content](#aria-dynamic-content)
- [Focus Management on Route Change](#focus-management-on-route-change)
- [ARIA Correctness Checks](#aria-correctness-checks)

---

## Canonical Axe Scan Test

```typescript
import { test, expect } from '../fixtures/a11y';
import { URLS } from '../constants/urls';

test.describe('Dashboard: Accessibility @a11y', () => {
  test('should have no axe violations @a11y', async ({ page, makeAxeBuilder }) => {
    await page.goto(URLS.dashboard);
    const results = await makeAxeBuilder()
      .withTags(['wcag2a', 'wcag2aa'])
      .analyze();
    expect(results.violations, formatViolations(results.violations)).toEqual([]);
  });
});

function formatViolations(violations: import('axe-core').Result[]): string {
  if (violations.length === 0) return '';
  return violations
    .map(
      (v) =>
        `[${v.impact}] ${v.id} — ${v.nodes.length} element(s)\n` +
        `  Fix: ${v.description}\n` +
        `  WCAG: ${v.tags.filter((t) => t.startsWith('wcag')).join(', ')}`,
    )
    .join('\n\n');
}
```

---

## Keyboard Navigation

**Tab order and skip link:**

```typescript
test('should move focus through interactive elements in DOM order @a11y', async ({ page }) => {
  await page.goto(URLS.dashboard);
  await page.keyboard.press('Tab');
  const firstFocused = page.locator(':focus');
  await expect(firstFocused, 'First focusable element should be the skip link').toHaveAttribute(
    'href',
    '#main-content',
  );
});
```

**Modal focus trap:**

```typescript
test('should trap focus inside modal when open @a11y', async ({ page }) => {
  await page.goto(URLS.dashboard);
  await page.getByRole('button', { name: 'Open settings' }).click();
  const modal = page.getByRole('dialog');
  await expect(modal, 'Modal should be visible').toBeVisible();

  const focusableInModal = modal.locator(
    'a[href], button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled]), [role="button"]:not([disabled]), [tabindex]:not([tabindex="-1"])',
  );
  const count = await focusableInModal.count();

  for (let i = 0; i < count; i++) {
    await page.keyboard.press('Tab');
    await expect(
      modal.locator(':focus'),
      `Focus should remain inside modal on Tab press ${i + 1}`,
    ).toHaveCount(1);
  }

  await page.keyboard.press('Escape');
  await expect(modal, 'Modal should close on Escape').toBeHidden();
});
```

**Arrow key navigation for composite widgets:**

```typescript
test('should navigate menu items with arrow keys @a11y', async ({ page }) => {
  await page.goto(URLS.nav);
  await page.getByRole('button', { name: 'Open menu' }).click();
  await page.keyboard.press('ArrowDown');
  const firstItem = page.getByRole('menuitem').first();
  await expect(firstItem, 'First menu item should receive focus').toBeFocused();
});
```

---

## ARIA Dynamic Content

**`aria-busy` during loading:**

```typescript
test('should announce loading state via aria-busy @a11y', async ({ page }) => {
  await page.goto(URLS.dashboard);
  await page.getByRole('button', { name: 'Refresh data' }).click();
  const region = page.getByRole('region', { name: 'Data table' });
  await expect(region, 'Region should be aria-busy while loading').toHaveAttribute(
    'aria-busy',
    'true',
  );
  await expect(region, 'Region should not be aria-busy after data loads').not.toHaveAttribute(
    'aria-busy',
    'true',
  );
});
```

**`aria-describedby` on form errors:**

```typescript
test('should link form error to field via aria-describedby @a11y', async ({ page }) => {
  await page.goto(URLS.signUp);
  await page.getByRole('button', { name: 'Submit' }).click();
  const emailField = page.getByRole('textbox', { name: 'Email' });
  const errorId = await emailField.getAttribute('aria-describedby');
  expect(errorId, 'Email field must have aria-describedby pointing to error').toBeTruthy();
  await expect(
    page.locator(`#${errorId}`),
    'Error message element must be visible',
  ).toBeVisible();
  await expect(emailField, 'Field must be marked invalid').toHaveAttribute('aria-invalid', 'true');
});
```

---

## Focus Management on Route Change

```typescript
test('should move focus to page heading on route change @a11y', async ({ page }) => {
  await page.goto(URLS.dashboard);
  await page.getByRole('link', { name: 'Settings' }).click();
  await expect(page, 'URL should update to settings route').toHaveURL(URLS.settings);
  const heading = page.getByRole('heading', { level: 1 });
  await expect(heading, 'H1 should receive focus after navigation').toBeFocused();
});
```

---

## ARIA Correctness Checks

**Modal dialog requirements:**

```typescript
const dialog = page.getByRole('dialog');
await expect(dialog).toHaveAttribute('aria-modal', 'true');
await expect(dialog).toHaveAttribute('aria-labelledby');
const labelId = await dialog.getAttribute('aria-labelledby');
await expect(page.locator(`#${labelId}`)).toBeVisible();
```

**Live region for async updates:**

```typescript
const liveRegion = page.locator('[aria-live]');
await expect(liveRegion).toHaveAttribute('aria-live', /(polite|assertive)/);
```

**Custom widget roles:**

```typescript
const listbox = page.getByRole('listbox');
const options = listbox.getByRole('option');
expect(await options.count()).toBeGreaterThanOrEqual(1);
```
