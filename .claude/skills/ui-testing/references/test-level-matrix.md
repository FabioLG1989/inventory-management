# Test Level Decision Matrix

This matrix maps UI task types to the four testing levels. Use it to determine which tests to generate when the ticket DoD does not explicitly specify test requirements.

## Legend

| Label | Meaning |
|-------|---------|
| **Required** | Must be included; the task is incomplete without this level |
| **Recommended** | Strongly advised; skip only with explicit justification |
| **If Figma exists** | Required when Figma designs are linked in the ticket or a `ui-visual-testing.json` mapping is present |
| **If behaviour changes** | Required only when the fix alters observable component behaviour |
| **If flow affected** | Required only when the fix impacts a user flow covered by E2E tests |
| **Screenshot mode** | Run visual regression (screenshot diff) only, not Figma comparison |
| **Required (both modes)** | Run both Figma fidelity and screenshot regression |
| **Required (regression)** | Run screenshot regression across all themed pages |
| `-` | Not applicable for this task type |

## Matrix

| UI Task Type | Unit | Component | E2E | Visual |
|---|---|---|---|---|
| New atom/molecule component | Required | Recommended | - | If Figma exists |
| New organism/widget | Required | Required | Recommended | If Figma exists |
| New page/feature | Required | - | Required | If Figma exists |
| Redesign existing screen | Required | - | Required | Required (both modes) |
| Bug fix on existing UI | If behaviour changes | - | If flow affected | Screenshot mode |
| Design token/theme change | - | - | - | Required (regression) |
| Accessibility improvement | Required | Recommended | - | - |

## Detailed Explanations

### New atom/molecule component

Small, reusable UI primitives such as buttons, badges, input fields, tooltips, and card shells.

- **Unit (Required):** Every atom and molecule must have unit tests covering its props API, conditional rendering, event callbacks, and edge cases (empty strings, `null` values, overflow text). These components are the foundation of the design system, so regressions here cascade across the entire application.
- **Component (Recommended):** Playwright Component Testing is valuable for verifying visual states (hover, focus, disabled, active) in isolation across viewports. Recommended because it catches rendering issues that unit tests with JSDOM cannot detect (e.g. CSS clipping, z-index conflicts).
- **E2E (-):** Atoms and molecules are too granular for end-to-end flows. They will be covered implicitly when testing pages and features that consume them.
- **Visual (If Figma exists):** When a Figma design node is available, compare the rendered component against the design to validate spacing, colours, typography, and border-radius. Skip if no design reference exists.

**Example — `Badge` component:**
```
Unit tests:
  - renders label text
  - applies variant class (success, warning, error, info)
  - does not render when label is empty
  - forwards onClick when interactive=true
  - is keyboard-accessible (Enter/Space triggers onClick)

Component tests:
  - screenshot: default state, each variant, hover state, focus ring
  - viewport: 320px (mobile), 768px (tablet), 1440px (desktop)

Visual tests:
  - compare against Figma node 12:345 at 1x and 2x scale
```

### New organism/widget

Composite UI blocks such as `KpiDashboard`, `InsightPanel`, `DataTable`, or `NavigationSidebar`. These compose multiple atoms/molecules and often include data-fetching or state logic.

- **Unit (Required):** Test the widget's internal logic: data transformations, conditional rendering branches, loading/error/empty states, and prop-driven configurations. Mock data-fetching hooks or API calls.
- **Component (Required):** Organisms are complex enough that DOM-only testing misses layout issues. Playwright CT verifies that child components compose correctly, that responsive breakpoints work, and that interactive flows (expand/collapse, pagination, sorting) render as expected.
- **E2E (Recommended):** If the widget appears on a critical page, an E2E test validates the full integration: API responses, routing, and user interactions in a real browser. Recommended rather than required because not all widgets sit on user-facing routes immediately.
- **Visual (If Figma exists):** Design fidelity is important for organisms since they define the visual identity of a page section. Compare against Figma when designs are available.

**Example — `KpiDashboard` widget:**
```
Unit tests:
  - renders correct number of KPI cards from data array
  - shows loading skeleton when isLoading=true
  - shows empty state when data is empty
  - formats currency values correctly
  - calculates trend percentages

Component tests:
  - screenshot: populated state, loading state, empty state, error state
  - viewport: mobile (stacked layout), tablet (2-column), desktop (4-column)
  - interaction: hover on KPI card shows tooltip

E2E tests:
  - navigate to /dashboard, verify KPI cards render with API data
  - filter by date range, verify KPI values update

Visual tests:
  - compare populated dashboard against Figma node 45:678
```

### New page/feature

Full-page implementations or feature slices that introduce new routes or user-facing functionality, such as a new dashboard page, a settings screen, or an approval workflow.

- **Unit (Required):** Test page-level logic: route parameter parsing, data aggregation from multiple sources, permission checks, form validation, and state management. Also unit-test any new hooks or utilities introduced with the feature.
- **Component (-):** Pages are too large for isolated component testing. Their child widgets and components should already have their own component tests.
- **E2E (Required):** New pages introduce new user flows that must be validated end-to-end. Test the happy path, key error scenarios, and edge cases (empty data, unauthorised access, deep linking).
- **Visual (If Figma exists):** Full-page visual comparison catches layout issues, spacing inconsistencies, and responsive problems that unit and E2E tests miss.

**Example — `/insights` page:**
```
Unit tests:
  - page component renders InsightPanel widget
  - useInsights hook returns formatted data
  - approval mutation sends correct payload
  - permission guard redirects unauthenticated users

E2E tests:
  - navigate to /insights, verify insight list loads
  - click "Approve" on an insight, verify status changes
  - submit with empty comment, verify validation error
  - test as read-only user, verify approve button is hidden

Visual tests:
  - compare /insights at 1440x900 against Figma node 89:012
  - compare /insights at 375x812 (mobile) against Figma node 89:013
```

### Redesign existing screen

Modifying the visual appearance, layout, or interaction patterns of an existing page or widget. This includes design refreshes, layout restructuring, and component migrations.

- **Unit (Required):** Ensure all existing behaviour is preserved. Update existing tests if the component API changes. Add new tests for any added functionality.
- **Component (-):** Unless the redesign introduces new isolated components, full-page comparisons are more valuable.
- **E2E (Required):** Redesigns can inadvertently break user flows. Re-run all existing E2E tests for affected routes and add new ones for changed interactions.
- **Visual (Required — both modes):** This is the most critical use case for visual testing. Run both:
  - **Figma mode:** Verify the new implementation matches the new designs.
  - **Screenshot mode:** Capture before/after diffs to confirm only intended areas changed and no collateral damage occurred.

**Example — Dashboard redesign:**
```
Unit tests:
  - all existing dashboard unit tests still pass
  - new grid layout hook returns correct column count per breakpoint
  - new animation utilities produce correct CSS values

E2E tests:
  - all existing dashboard E2E tests pass
  - new drag-to-reorder interaction works
  - new collapse/expand sections persist state

Visual tests:
  - Figma mode: compare redesigned dashboard against Figma node 99:100
  - Screenshot mode: diff before vs after, threshold 5%
  - Both modes at 3 viewports: mobile, tablet, desktop
```

### Bug fix on existing UI

Targeted fixes for visual glitches, interaction bugs, or rendering issues in existing components.

- **Unit (If behaviour changes):** If the fix changes how a component processes props, handles events, or renders conditionally, add or update unit tests to cover the fixed behaviour. If the fix is purely CSS, unit tests may not be necessary.
- **Component (-):** Bug fixes are typically too narrow for new component-level tests.
- **E2E (If flow affected):** If the bug was reported in the context of a user flow (e.g. "checkout button does not respond after adding 10 items"), add or update the relevant E2E test to prevent regression.
- **Visual (Screenshot mode):** Capture a screenshot of the fixed area and store it as a new baseline. This ensures the bug does not reappear in future changes.

**Example — Tooltip overflow fix:**
```
Unit tests:
  - tooltip truncates text longer than 200 characters
  - tooltip positions correctly when near viewport edge (if logic changed)

Visual tests:
  - screenshot of tooltip with long text, stored as baseline
  - screenshot of tooltip near right edge of viewport
```

### Design token/theme change

Modifications to CSS custom properties, theme definitions, colour palettes, typography scales, or spacing tokens.

- **Unit (-):** Token changes are declarative CSS; there is no component logic to unit-test.
- **Component (-):** Individual component rendering is unlikely to break from global token changes, but visual regression will catch any issues.
- **E2E (-):** Token changes do not affect user flows or application behaviour.
- **Visual (Required — regression):** Token changes can have sweeping visual impact across every page. Run screenshot regression against all critical screens in both light and dark themes to detect unintended changes.

**Example — Brand colour update:**
```
Visual tests:
  - screenshot regression across 8 critical pages
  - both light mode and dark mode
  - threshold: 0% for pages that should not change
  - threshold: acceptable range for pages with the updated token
```

### Accessibility improvement

Changes to ARIA attributes, keyboard navigation, focus management, screen reader support, colour contrast, or semantic HTML structure.

- **Unit (Required):** Test the programmatic accessibility of components: correct ARIA roles and attributes, keyboard event handlers, focus trap behaviour, and screen reader text. Use `@testing-library/jest-dom` matchers like `toHaveAccessibleName()`, `toHaveRole()`, and `toBeVisible()`.
- **Component (Recommended):** Playwright CT with axe-core integration can validate accessibility in a real browser rendering context, catching issues that JSDOM misses (e.g. colour contrast, focus indicator visibility, scroll behaviour).
- **E2E (-):** Accessibility improvements rarely change user flows. Axe-core audits can be added to existing E2E tests instead.
- **Visual (-):** Accessibility changes are typically non-visual or minimally visual (focus rings, skip links). Visual testing adds little value here.

**Example — Focus management improvement:**
```
Unit tests:
  - modal traps focus within its boundaries
  - Escape key closes modal and returns focus to trigger
  - all interactive elements have accessible names
  - tab order follows logical reading order

Component tests:
  - axe-core audit: 0 violations on modal in open state
  - screenshot: focus ring visible on all interactive elements
  - keyboard navigation: Tab through all elements in sequence
```

## Applying the Matrix

When the skill resolves test levels in Step 3 of the workflow:

1. Classify the UI task (Step 2).
2. Look up the row in the matrix.
3. For each column:
   - **Required** entries are always included.
   - **Recommended** entries are included by default but can be skipped if the user requests a faster run.
   - **Conditional** entries (e.g. "If Figma exists") are evaluated against the project context.
   - **`-`** entries are excluded.
4. Present the resolved levels to the user for confirmation before generating tests.
