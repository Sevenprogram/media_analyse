# Content Strategy Center Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `key_insights` tab into a polished enterprise-style content strategy dashboard that matches the approved spec and replaces the placeholder page.

**Architecture:** Add a dedicated `ContentStrategyCenterPage` React page that owns local filter state and static strategy mock data, render the full dashboard in modular sections, then wire it into `main.tsx`. Keep styles in `api/webui/src/styles.css` under a dedicated `ks-` namespace so the new page fits the existing shell without leaking into other screens.

**Tech Stack:** React 19, TypeScript, lucide-react, existing local UI primitives, Vite build pipeline, CSS/SVG/conic-gradient data visuals

---

### Task 1: Create The Page Skeleton And Mock Data

**Files:**
- Create: `api/webui/src/pages/ContentStrategyCenterPage.tsx`

- [ ] **Step 1: Create the page file with local types, filter options, and mock datasets**

Add a page component containing:
- filter state for platform / range / goal / audience / stage
- section data for metrics, donut charts, trend rows, framework rows, topic recommendations, competitor samples, risk alerts, weekly mix, and traffic share
- lightweight helper renderers for sparkline SVGs and donut visuals

- [ ] **Step 2: Build the dashboard JSX skeleton**

Render:
- title and action row
- filter bar
- top insight grid
- middle strategy grid
- bottom strategy grid

- [ ] **Step 3: Keep the page self-contained and typed**

Use explicit TypeScript object shapes in the page file so later API hookup can replace the mock constants without refactoring the JSX.

### Task 2: Wire The Page Into Navigation

**Files:**
- Modify: `api/webui/src/main.tsx`

- [ ] **Step 1: Import the new page component**

Add:

```tsx
import { ContentStrategyCenterPage } from "./pages/ContentStrategyCenterPage";
```

- [ ] **Step 2: Replace the `key_insights` placeholder render**

Change:

```tsx
{tab === "key_insights" && <PlaceholderPage ... />}
```

to:

```tsx
{tab === "key_insights" && <ContentStrategyCenterPage />}
```

- [ ] **Step 3: Verify no other tab behavior changes**

Keep the rest of the existing tab routing unchanged.

### Task 3: Add Dedicated `ks-` Styling

**Files:**
- Modify: `api/webui/src/styles.css`

- [ ] **Step 1: Add a namespaced style block for the new page**

Create a `Content Strategy Center` section with:
- page-level background treatment
- hero/title row
- filter pills and select wrappers
- metric card layouts
- table/list cards
- donut and sparkline visuals
- responsive breakpoints

- [ ] **Step 2: Match the approved enterprise dashboard aesthetic**

Implement:
- shallow warm-gray page background
- white rounded cards with fine borders
- teal-first semantic accents
- subtle hover transitions
- high-density table and legend spacing

- [ ] **Step 3: Add responsive rules**

Support:
- desktop multi-column dashboard
- medium-width two-column fallback
- mobile single-column stacking with scroll-safe tables

### Task 4: Build Visual Details And Empty-State Safety

**Files:**
- Modify: `api/webui/src/pages/ContentStrategyCenterPage.tsx`
- Modify: `api/webui/src/styles.css`

- [ ] **Step 1: Add lightweight data visuals**

Use:
- SVG path sparklines for keyword and metric trends
- conic-gradient or SVG donuts for pain-point and traffic distribution cards
- CSS bars for weekly mix and risk intensity

- [ ] **Step 2: Add card-level utility rendering**

Ensure long titles, list rows, and score labels wrap or truncate safely without breaking layout.

- [ ] **Step 3: Add graceful no-data fallback markup where appropriate**

Even though the initial page uses mock data, structure cards so later empty data can render simple fallback copy without redesign.

### Task 5: Validate And Finish

**Files:**
- Modify as needed after validation: `api/webui/src/pages/ContentStrategyCenterPage.tsx`, `api/webui/src/styles.css`, `api/webui/src/main.tsx`

- [ ] **Step 1: Run the production build**

Run:

```bash
npm.cmd run build
```

Expected:

```text
vite build completes successfully
```

- [ ] **Step 2: Fix any TypeScript or style regressions**

Apply only the minimal changes needed to restore a clean build.

- [ ] **Step 3: Review visual structure against the approved spec**

Confirm:
- `key_insights` is no longer a placeholder
- reference-style enterprise dashboard layout is present
- cards align cleanly inside the existing shell
- desktop and narrow layouts remain intact

- [ ] **Step 4: Commit**

```bash
git add api/webui/src/main.tsx api/webui/src/pages/ContentStrategyCenterPage.tsx api/webui/src/styles.css docs/superpowers/plans/2026-05-23-content-strategy-center.md
git commit -m "Build content strategy center dashboard"
```
