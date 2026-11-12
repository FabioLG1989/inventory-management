# WCAG 2.1 Quick Reference — Level A and AA

Covers the success criteria most commonly failed in web applications. Use this table to map a
failing axe rule or a manual observation to the authoritative WCAG reference and the Playwright
pattern that tests it.

Source: https://www.w3.org/TR/WCAG21/

---

## Level A

| Criterion | Name | Requirement | axe catches | Playwright pattern |
|-----------|------|-------------|-------------|-------------------|
| 1.1.1 | Non-text Content | Every image, icon, and canvas has a text alternative | ✓ `image-alt`, `input-image-alt` | Inject axe scan; assert `alt` attribute on `<img>` elements |
| 1.3.1 | Info and Relationships | Structure conveyed visually (headings, lists, tables) is expressed in semantics | ✓ `heading-order`, `list`, `td-headers-attr` | Inject axe scan; assert `getByRole('heading')` hierarchy |
| 1.3.2 | Meaningful Sequence | Reading order in the DOM matches the visual order | ✗ | Assert focus order via sequential Tab presses matches visual left-to-right, top-to-bottom order |
| 1.3.3 | Sensory Characteristics | Instructions do not rely solely on shape, color, size, or position | ✗ | Manual review — no automated Playwright pattern available |
| 2.1.1 | Keyboard | All functionality is operable with keyboard alone | ✗ | Tab through all interactive elements; assert each receives focus and activates on Enter/Space |
| 2.1.2 | No Keyboard Trap | Focus can always move away from a component using only keyboard | ✗ | Tab past each focusable region; assert focus is never permanently stuck |
| 2.4.1 | Bypass Blocks | Mechanism to skip repeated navigation exists | ✗ | First Tab from page top should focus a skip link; Enter should move focus to `#main-content` |
| 2.4.2 | Page Titled | Each page has a descriptive title | ✓ `document-title` | `await expect(page).toHaveTitle(/<expected pattern>/)` |
| 2.4.3 | Focus Order | Focusable components receive focus in order that preserves meaning | ✗ | Collect focused elements via sequential Tab presses; assert order matches DOM sequence |
| 2.4.4 | Link Purpose in Context | Each link's purpose is determinable from its text or context | ✓ `link-name` | Inject axe scan; assert `getByRole('link')` locators have accessible names |
| 3.1.1 | Language of Page | Human language of each page is programmatically determinable | ✓ `html-has-lang`, `html-lang-valid` | Inject axe scan |
| 3.3.1 | Error Identification | Input errors are identified and described in text | ✗ | Assert `aria-invalid="true"` on invalid fields; assert `aria-describedby` links field to error |
| 3.3.2 | Labels or Instructions | Labels or instructions provided for user input | ✓ `label` | Inject axe scan; assert `getByRole('textbox')` has accessible name |
| 4.1.1 | Parsing | No duplicate IDs; no invalid HTML that breaks AT | ✓ `duplicate-id`, `duplicate-id-active` | Inject axe scan |
| 4.1.2 | Name, Role, Value | UI components have correct name, role, and state/value | ✓ `aria-*` rules | Inject axe scan; assert custom widgets carry correct `role` and `aria-*` attributes |

---

## Level AA

| Criterion | Name | Requirement | axe catches | Playwright pattern |
|-----------|------|-------------|-------------|-------------------|
| 1.2.4 | Captions (Live) | Live audio has captions | ✗ | Manual review |
| 1.3.4 | Orientation | Content is not locked to one display orientation | ✗ | Set viewport to portrait and landscape; assert no content is cut off |
| 1.3.5 | Identify Input Purpose | Autocomplete purpose of form inputs is programmatically determinable | ✓ `autocomplete-valid` | Inject axe scan |
| 1.4.3 | Contrast (Minimum) | Text has at least 4.5:1 contrast ratio (3:1 for large text) | ✓ `color-contrast` | Inject axe scan |
| 1.4.4 | Resize Text | Text can be resized to 200% without loss of content | ✗ | Set `page.setViewportSize` to narrow width; assert no horizontal scrollbar and no text truncation |
| 1.4.10 | Reflow | Content reflows at 320 CSS pixels width without two-dimensional scrolling | ✗ | Set viewport width to 320px; assert no horizontal overflow |
| 1.4.11 | Non-text Contrast | UI components and graphical objects have at least 3:1 contrast ratio | ✓ `color-contrast` (partial) | Inject axe scan; manually verify custom icons and focus indicators |
| 1.4.12 | Text Spacing | No loss of content when line-height, letter-spacing, and word-spacing are overridden | ✗ | Inject CSS overrides via `page.addStyleTag`; assert no content overflow |
| 1.4.13 | Content on Hover or Focus | Content triggered by hover/focus is dismissible, hoverable, and persistent | ✗ | Hover over tooltip triggers; assert tooltip remains while cursor is over it; assert Escape dismisses it |
| 2.4.5 | Multiple Ways | More than one way to locate a page (search, sitemap, or navigation) | ✗ | Manual review |
| 2.4.6 | Headings and Labels | Headings and labels describe topic or purpose | ✓ `heading-order` (partial) | Assert `getByRole('heading')` text matches the page/section content |
| 2.4.7 | Focus Visible | Keyboard focus indicator is visible | ✗ | Tab to each interactive element; assert `:focus-visible` pseudo-class applies a non-default outline |
| 3.1.2 | Language of Parts | Language of each part is determinable when different from page language | ✓ `valid-lang` | Inject axe scan |
| 3.2.3 | Consistent Navigation | Navigation repeated across pages appears in same order | ✗ | Manual review across page objects |
| 3.2.4 | Consistent Identification | Components with the same function are identified consistently | ✗ | Assert identical accessible names for the same action across multiple page objects |
| 3.3.3 | Error Suggestion | Error messages include a suggestion for correction when feasible | ✗ | Assert visible error text contains actionable guidance; check `aria-describedby` target content |
| 3.3.4 | Error Prevention (Legal, Financial, Data) | Submissions are reversible, checked, or confirmed | ✗ | Assert destructive actions require a confirmation step |
| 4.1.3 | Status Messages | Status messages can be determined by role or property without receiving focus | ✗ | Assert success/error toasts carry `role="status"` or `role="alert"`; assert `aria-live` region announces them |

---

## axe Rule to WCAG Mapping — Frequently Triggered Rules

| axe Rule ID | WCAG Criterion | Impact |
|-------------|----------------|--------|
| `color-contrast` | 1.4.3 (AA) | serious |
| `image-alt` | 1.1.1 (A) | critical |
| `label` | 1.3.1, 4.1.2 (A) | critical |
| `link-name` | 2.4.4, 4.1.2 (A) | serious |
| `aria-required-children` | 1.3.1, 4.1.2 (A) | critical |
| `aria-required-parent` | 1.3.1, 4.1.2 (A) | critical |
| `aria-roles` | 4.1.2 (A) | critical |
| `button-name` | 4.1.2 (A) | critical |
| `duplicate-id-active` | 4.1.1 (A) | serious |
| `heading-order` | 1.3.1, 2.4.6 (A/AA) | moderate |
| `html-has-lang` | 3.1.1 (A) | serious |
| `input-image-alt` | 1.1.1 (A) | critical |
| `region` | 1.3.1 (A) | moderate |
| `select-name` | 1.3.1, 4.1.2 (A) | critical |
| `td-headers-attr` | 1.3.1 (A) | critical |

---

## Scope — This Skill vs Manual Testing

| Category | Covered by this skill | Requires manual review |
|----------|-----------------------|------------------------|
| Automated axe scan | ✓ All rules in the mapping table above | Rules marked ✗ in the tables |
| Keyboard navigation | ✓ Tab order, focus traps, skip links, arrow keys for composite widgets | Complex gesture interactions (drag-and-drop, multi-touch) |
| ARIA correctness | ✓ Dialog, live region, form validation, loading state patterns | Novel custom widgets not covered by WAI-ARIA Authoring Practices |
| Focus management | ✓ Modal open/close, route change, inline errors | Focus management inside third-party embedded widgets |
| Color contrast | ✓ via axe `color-contrast` rule | Custom canvas or SVG text rendering |
| Screen reader compatibility | ✗ | Full screen reader testing (NVDA + Firefox, VoiceOver + Safari, JAWS + Chrome) |
| Cognitive accessibility (WCAG 2.2) | ✗ | Manual evaluation of AAA criteria and WCAG 2.2 additions |
