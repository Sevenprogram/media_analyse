# Growth Intelligence P0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the P0 business-usable growth intelligence experience: seven primary pages, unified evidence/quality/action UI patterns, and clearer task/project workflows while reusing current crawler and research APIs.

**Architecture:** Phase 1 reorganizes the frontend information architecture without changing crawler internals. Phase 2 adds shared decision-support UI components and page-level aggregations. Phase 3 adds backend diagnostics and richer API shapes only where the existing pages cannot support P0 decisions.

**Tech Stack:** React 19, TypeScript, Vite, lucide-react, Recharts, FastAPI, SQLite-backed research repository.

---

## File Structure

- Modify `api/webui/src/types.ts`: replace old `ResearchTab` with the new primary navigation ids while retaining hidden legacy routes only if needed internally.
- Modify `api/webui/src/components/sidebar.tsx`: reduce primary navigation to 今日情报、项目工作台、达人发现、内容追踪、友商监控、关键词热度、设置.
- Create `api/webui/src/pages/GrowthIntelligencePages.tsx`: shared P0 page wrappers and upgraded pages that compose existing endpoint data into the new product design.
- Modify `api/webui/src/main.tsx`: route new tabs to the new pages and keep legacy data pages accessible through page actions rather than primary nav.
- Modify `api/webui/src/styles.css`: add layout styles for P0 product pages, evidence drawers, quality strips, action lists, and radar/ledger patterns.
- Later backend phase: modify `api/routers/research.py`, `api/routers/reports.py`, and `research/execution.py` only after the UI restructure proves the exact missing data.

## Task 1: Navigation And App Shell

**Files:**
- Modify: `api/webui/src/types.ts`
- Modify: `api/webui/src/components/sidebar.tsx`
- Modify: `api/webui/src/main.tsx`

- [ ] **Step 1: Update `ResearchTab` ids**

Use these ids:

```ts
export type ResearchTab =
  | "today"
  | "projects"
  | "creators"
  | "content_tracking"
  | "competitors"
  | "keyword_heat"
  | "settings";
```

- [ ] **Step 2: Replace sidebar groups**

Use one primary navigation group with these labels and icons:

```ts
[
  { id: "today", label: "今日情报", icon: Home },
  { id: "projects", label: "项目工作台", icon: Gauge },
  { id: "creators", label: "达人发现", icon: Users },
  { id: "content_tracking", label: "内容追踪", icon: Layers },
  { id: "competitors", label: "友商监控", icon: Activity },
  { id: "keyword_heat", label: "关键词热度", icon: KeyRound },
  { id: "settings", label: "设置", icon: Settings },
]
```

- [ ] **Step 3: Update default selected tab**

Set:

```ts
const [tab, setTab] = React.useState<ResearchTab>("today");
```

- [ ] **Step 4: Build**

Run: `npm.cmd run build`

Expected: TypeScript errors for missing new route components before Task 2, or PASS after Task 2.

## Task 2: Create P0 Page Composition Layer

**Files:**
- Create: `api/webui/src/pages/GrowthIntelligencePages.tsx`
- Modify: `api/webui/src/main.tsx`

- [ ] **Step 1: Create shared UI helpers**

Create functions/components:

```tsx
export function TodayIntelligencePage(props: TodayIntelligencePageProps) { ... }
export function ProjectsHubPage(props: ProjectsHubPageProps) { ... }
export function KeywordHeatPage(props: KeywordHeatPageProps) { ... }
export function SettingsHubPage() { ... }
```

Reuse existing `CreatorDiscoveryPage`, `ContentTrackingPage`, and `CompetitorMonitorPage` initially, but wrap them under the new navigation labels.

- [ ] **Step 2: Route new tabs in `main.tsx`**

Map:

```tsx
{tab === "today" && <TodayIntelligencePage ... />}
{tab === "projects" && <ProjectsHubPage ... />}
{tab === "creators" && <CreatorDiscoveryPage />}
{tab === "content_tracking" && <ContentTrackingPage />}
{tab === "competitors" && <CompetitorMonitorPage />}
{tab === "keyword_heat" && <KeywordHeatPage ... />}
{tab === "settings" && <SettingsHubPage />}
```

- [ ] **Step 3: Preserve hidden actions**

Replace old `onOpenData={() => setTab("data")}` and `onOpenAi={() => setTab("ai")}` with local drawers or omit those buttons until a secondary route is added.

- [ ] **Step 4: Build**

Run: `npm.cmd run build`

Expected: PASS.

## Task 3: Today Intelligence P0

**Files:**
- Modify: `api/webui/src/pages/GrowthIntelligencePages.tsx`
- Modify: `api/webui/src/styles.css`

- [ ] **Step 1: Implement action list**

Use `dashboard.actions.do_now`, `watch_today`, and diagnostics to render a prioritized action list.

- [ ] **Step 2: Implement opportunity queue**

Use `dashboard.opportunities` or `dashboard.top_opportunities`.

- [ ] **Step 3: Implement risk and sample quality panel**

Use `dashboard.decision`, `dashboard.monitoring`, `databaseStats`, and diagnostics.

- [ ] **Step 4: Add evidence drawer**

Clicking an opportunity opens a drawer with summary, samples, risks, and actions.

- [ ] **Step 5: Build**

Run: `npm.cmd run build`

Expected: PASS.

## Task 4: Projects Hub P0

**Files:**
- Modify: `api/webui/src/pages/GrowthIntelligencePages.tsx`
- Modify: `api/webui/src/styles.css`

- [ ] **Step 1: Wrap existing `GrowthProjectWorkbenchPage` concepts into project hub**

Show project list, selected project health, research config summary, collection progress, sample evidence counts, and next actions.

- [ ] **Step 2: Keep existing create/edit controls available**

Render the existing `GrowthProjectWorkbenchPage` as the detailed workspace or reuse its create/update callbacks.

- [ ] **Step 3: Add P0 tabs**

Tabs: 项目概览、研究配置、采集计划、样本与证据、洞察与建议、历史任务、导出.

- [ ] **Step 4: Build**

Run: `npm.cmd run build`

Expected: PASS.

## Task 5: Keyword Heat P0

**Files:**
- Modify: `api/webui/src/pages/GrowthIntelligencePages.tsx`
- Modify: `api/webui/src/styles.css`

- [ ] **Step 1: Derive keyword rows from selected project, jobs, and posts**

Create keyword radar rows from project keywords and post matches.

- [ ] **Step 2: Show sample quality**

Show content count, creator proxy count, platform count, and confidence.

- [ ] **Step 3: Show replenishment advice**

For low sample rows, suggest expanded collection instead of strong conclusions.

- [ ] **Step 4: Build**

Run: `npm.cmd run build`

Expected: PASS.

## Task 6: P0 Polish And Verification

**Files:**
- Modify: `api/webui/src/styles.css`

- [ ] **Step 1: Add responsive layout styles**

Ensure all new grids collapse on narrow screens.

- [ ] **Step 2: Run build**

Run: `npm.cmd run build`

Expected: PASS.

- [ ] **Step 3: Start dev server**

Run: `npm.cmd run dev`

Expected: local Vite server URL.

- [ ] **Step 4: Verify in browser**

Open the local URL and inspect all seven primary pages for nonblank rendering and no console errors.

## Scope Gaps After P0 UI Restructure

These remain for follow-up implementation plans:

- Backend unified `Evidence` model.
- Backend `MetricSnapshot` model.
- True all-platform capability matrix.
- Full crawler unit diagnostics API.
- Video OCR/transcript processing.
- Vector similarity search.
- Role-based permissions.

