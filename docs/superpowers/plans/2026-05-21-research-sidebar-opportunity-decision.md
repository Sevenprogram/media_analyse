# Research Sidebar Opportunity Decision Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore the full Research console sidebar, add `增长机会决策` as a first-class module, and improve opportunity charts plus data browsing with polished decision-oriented UI.

**Architecture:** Keep the existing `/research` React entry and existing dashboard summary/feedback APIs. Split the frontend into focused local modules under `api/webui/src/`, use local shadcn-style UI components backed by Radix primitives, and keep Recharts for charts. Backend scoring remains the source of truth; frontend renders standardized fields and diagnostic states.

**Tech Stack:** React 19, TypeScript, Vite, Recharts, lucide-react, Radix primitives, local shadcn-style CSS components, FastAPI dashboard summary and feedback endpoints.

---

## File Structure

- Modify `package.json` and `package-lock.json`
  - Add Radix dependencies for dialog, select, slot, tabs, and tooltip.
- Create `api/webui/src/types.ts`
  - Shared Research console, dashboard opportunity, job, sample, record, and execution types.
- Create `api/webui/src/utils/api.ts`
  - Shared API fetch helper and typed `ApiError`.
- Create `api/webui/src/utils/format.ts`
  - Chinese labels and formatting helpers for platform, risks, opportunity types, numbers, dates, signed deltas, and compact JSON.
- Create `api/webui/src/components/ui.tsx`
  - Local shadcn-style primitives: `Button`, `Badge`, `Card`, `Tabs`, `Drawer`, `ConfirmDialog`, `Tooltip`, `Select`, `Skeleton`.
- Create `api/webui/src/components/sidebar.tsx`
  - Full Research console grouped navigation.
- Create `api/webui/src/components/charts.tsx`
  - Shared opportunity and data-browser chart components and chart data helpers.
- Create `api/webui/src/pages/OpportunityDecisionPage.tsx`
  - `增长机会决策` module.
- Create `api/webui/src/pages/DataBrowserPage.tsx`
  - Optimized `数据浏览` module.
- Create `api/webui/src/pages/ResearchRestoredPages.tsx`
  - Restored shells for existing Research modules that are outside this slice.
- Replace `api/webui/src/main.tsx`
  - Thin app shell, full sidebar routing, state loading, feedback submit, and high-risk confirmation.
- Modify `api/webui/src/styles.css`
  - UI tokens, sidebar, opportunity decision page, charts, drawers, data browser cards, responsive rules.

Note: the original planned helper path `api/webui/src/lib` was changed to `api/webui/src/utils` because the repository `.gitignore` ignores any `lib/` directory.

---

## Task 1: Dependencies And Shared Types

- [x] Add Radix dependencies:
  - `@radix-ui/react-dialog`
  - `@radix-ui/react-select`
  - `@radix-ui/react-slot`
  - `@radix-ui/react-tabs`
  - `@radix-ui/react-tooltip`
- [x] Run `npm.cmd install`.
- [x] Create shared dashboard, opportunity, job, record, and tab types.
- [x] Create API helper.
- [x] Create formatting helpers.

Verification:

```powershell
npm.cmd run build
```

Expected: TypeScript and Vite build pass.

---

## Task 2: Local UI Components And Sidebar

- [x] Create local shadcn-style UI primitives.
- [x] Create full Research sidebar.
- [x] Restore navigation order:
  - `总览`
  - `任务工作台`
  - `增长机会决策`
  - `达人发现`
  - `关键词库`
  - `友商监控`
  - `内容跟踪`
  - `数据浏览`
  - `AI 分析`
  - `导出中心`
  - `配置`
- [x] Add shared CSS for buttons, badges, cards, tabs, drawer/dialog, tooltip, select, skeleton.

Verification:

```powershell
npm.cmd run build
```

Expected: TypeScript and Vite build pass.

---

## Task 3: Opportunity Decision Page

- [x] Create `OpportunityDecisionPage`.
- [x] Add opportunity type tabs:
  - `全部`
  - `关键词`
  - `内容`
  - `达人`
  - `友商动作`
- [x] Render conclusion-first structure:
  - page title and refresh
  - today conclusion card
  - Top 5 list
  - watchlist
  - selected opportunity explanation panel
  - four core charts
  - expandable analysis section
  - diagnostic panel
- [x] Add right-side detail drawer:
  - score breakdown
  - trend chart
  - platform contribution
  - risk tags
  - sample scope
  - evidence summary
  - typed evidence samples
  - feedback buttons
  - high-risk action entry
- [x] Add Recharts components:
  - score bars
  - trend chart
  - platform signal chart
  - risk distribution chart
  - opportunity matrix
  - competition gap ranking

Verification:

```powershell
npm.cmd run build
```

Expected: TypeScript and Vite build pass.

---

## Task 4: Data Browser Page

- [x] Create `DataBrowserPage`.
- [x] Replace table-first UX with summary and sample cards.
- [x] Add task selector.
- [x] Add charts:
  - platform distribution
  - publish-time distribution
  - keyword hits
  - data quality panel
- [x] Add tabs for:
  - posts
  - comments
  - raw records
  - AI results
- [x] Add expandable sample cards with raw JSON visible only after expansion.

Verification:

```powershell
npm.cmd run build
```

Expected: TypeScript and Vite build pass.

---

## Task 5: App Shell Restore And Routing

- [x] Replace simplified two-tab app shell.
- [x] Route sidebar tabs to:
  - `OpportunityDecisionPage`
  - `DataBrowserPage`
  - restored placeholder shells for other Research modules.
- [x] Keep existing dashboard summary and feedback APIs.
- [x] Keep high-risk actions behind confirmation modal.
- [x] Preserve diagnostic empty states when backend data is unavailable.

Verification:

```powershell
npm.cmd run build
```

Expected: full Research console shell renders.

---

## Task 6: Responsive Polish And Verification

- [x] Add responsive rules for wide desktop, tablet, and mobile.
- [x] Ensure text labels are UTF-8 Chinese, with no mojibake in source files.
- [x] Run focused backend tests.
- [x] Run frontend build.
- [x] Run browser smoke test with Vite preview.

Backend test command:

```powershell
pytest tests/test_dashboard_summary.py tests/test_dashboard_api.py tests/test_research_models.py tests/test_research_schema_migration.py -q
```

Expected: all selected tests pass. Existing SQLAlchemy deprecation warning is acceptable.

Frontend build command:

```powershell
npm.cmd run build
```

Expected: TypeScript and Vite build pass. Vite chunk-size warning is acceptable.

Browser smoke test:

```powershell
npm.cmd run preview -- --host 127.0.0.1 --port 4177
```

Expected:

- complete sidebar renders in the confirmed order
- `增长机会决策` is a sidebar module, not a replacement shell
- `数据浏览` is a separate sidebar module
- opportunity tabs render
- conclusion card, Top 5/watchlist area, explanation panel, charts, diagnostics render
- data browser summary, charts, sample tabs, and empty state render
- API 502 errors are acceptable only when FastAPI backend is not running during Vite preview

---

## Final Verification Results

- `npm.cmd install`: passed.
- `npm.cmd run build`: passed.
- `pytest tests/test_dashboard_summary.py tests/test_dashboard_api.py tests/test_research_models.py tests/test_research_schema_migration.py -q`: `16 passed, 1 warning`.
- Browser preview: passed on Vite fallback port `4178` because port `4177` was already in use.
- Console errors during preview: only expected `/api/reports/dashboard-summary` and `/api/research/jobs` 502 errors because FastAPI backend was not running behind Vite preview.
