# Renderer Adapters Reference

This document covers framework-specific considerations for capturing deterministic screenshots with Playwright. Each framework has unique timing, hydration, and rendering characteristics that must be accounted for to produce consistent, comparable screenshots.

## Common Concerns

These issues apply across all frameworks and should always be addressed before framework-specific handling.

### Web fonts

Web fonts load asynchronously and can cause text layout shifts. If a screenshot is captured before fonts load, the fallback font will produce a different layout.

**Mitigation:**

```javascript
// Wait for all fonts to load before capturing
await page.evaluate(() => document.fonts.ready);
```

For fonts loaded via `@font-face` with `font-display: swap`, also wait for the swap to complete:

```javascript
await page.evaluate(async () => {
  await document.fonts.ready;
  // Additional wait for swap rendering
  await new Promise(resolve => requestAnimationFrame(resolve));
});
```

### Image lazy loading

Images with `loading="lazy"` or intersection-observer-based loading may not load until scrolled into view.

**Mitigation:**

```javascript
// Scroll to bottom and back to trigger all lazy images
await page.evaluate(async () => {
  await new Promise(resolve => {
    let totalHeight = 0;
    const distance = 300;
    const timer = setInterval(() => {
      window.scrollBy(0, distance);
      totalHeight += distance;
      if (totalHeight >= document.body.scrollHeight) {
        clearInterval(timer);
        window.scrollTo(0, 0);
        resolve(undefined);
      }
    }, 50);
  });
});

// Wait for all images to load
await page.evaluate(() =>
  Promise.all(
    Array.from(document.images)
      .filter(img => !img.complete)
      .map(img => new Promise(resolve => {
        img.onload = resolve;
        img.onerror = resolve;
      }))
  )
);
```

### CSS animations and transitions

Animations cause non-deterministic screenshots depending on capture timing.

**Mitigation (inject globally before capture):**

```javascript
await page.addStyleTag({
  content: `
    *, *::before, *::after {
      animation-duration: 0s !important;
      animation-delay: 0s !important;
      transition-duration: 0s !important;
      transition-delay: 0s !important;
      scroll-behavior: auto !important;
    }
  `
});
```

### Cursor and selection

The blinking cursor in input fields and text selections cause flicker in screenshots.

**Mitigation:**

```javascript
await page.addStyleTag({
  content: `
    * { caret-color: transparent !important; }
    ::selection { background: transparent !important; }
  `
});
```

### Dynamic content

Timestamps, relative dates ("3 minutes ago"), user avatars, and other dynamic content produce false-positive diffs.

**Mitigation options:**

1. **Mask regions** in the comparison step (preferred — preserves visual fidelity of capture):
   ```json
   { "maskRegions": [{ "selector": "[data-testid='timestamp']" }] }
   ```
2. **Mock the clock** for time-dependent content:
   ```javascript
   await page.clock.setFixedTime(new Date('2026-01-15T10:00:00Z'));
   ```
3. **Use data-testid markers** to identify dynamic regions automatically.

---

## Framework-Specific Renderer Timing

Each UI framework has unique hydration, transition, and async rendering characteristics that require additional wait logic beyond the common concerns above. This framework-specific timing is defined in specialization references:

| Framework | Specialization | Key concerns |
|-----------|---------------|--------------|
| React / Next.js | [`react-specialization.md`](react-specialization.md) | Hydration, Suspense boundaries, React.lazy, concurrent rendering, SSR/SSG/CSR modes, App Router streaming, route prefetching |
| Vue / Nuxt | `vue-specialization.md` (future) | Transitions, async components, reactivity batching via nextTick |
| Angular | `angular-specialization.md` (future) | Zone.js stability, change detection, OnPush strategy, Material CDK overlays |
| Svelte / SvelteKit | `svelte-specialization.md` (future) | tick() timing, load functions, form actions, Svelte transitions, Svelte 5 runes |

The loaded specialization provides the `frameworkWait()` implementation used in step 5 of the Universal Capture Sequence below.

### Adding a new specialization

To support a new framework or platform:

1. Create `references/<framework>-specialization.md` following the structure of existing specializations.
2. Document: framework detection markers, wait strategies (hydration, transitions, async rendering), and any CSS overrides beyond the common animation disabling.
3. The core renderer-adapters reference and the `ui-visual-testing` skill require no changes.

---

## Universal Capture Sequence

Combining all the above, the recommended capture sequence for any framework is:

```javascript
async function captureScreenshot(page, route, viewport, framework) {
  // 1. Set viewport
  await page.setViewportSize(viewport);

  // 2. Navigate
  await page.goto(route, { waitUntil: 'domcontentloaded' });

  // 3. Wait for network to settle
  await page.waitForLoadState('networkidle');

  // 4. Wait for fonts
  await page.evaluate(() => document.fonts.ready);

  // 5. Framework-specific wait
  await frameworkWait(page, framework);

  // 6. Scroll to trigger lazy content
  await triggerLazyContent(page);

  // 7. Wait for images
  await waitForImages(page);

  // 8. Disable animations
  await disableAnimations(page);

  // 9. Hide cursor and selections
  await hideCursorAndSelections(page);

  // 10. Final settle
  await page.waitForTimeout(200);

  // 11. Capture
  return await page.screenshot({ fullPage: true });
}
```

The `frameworkWait` function dispatches to the appropriate framework-specific logic based on detection of framework markers in the DOM.
