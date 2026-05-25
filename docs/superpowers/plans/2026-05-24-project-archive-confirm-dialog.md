# Project Archive Confirm Dialog Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the project workbench's browser-native archive confirmation with a centered in-page confirmation dialog.

**Architecture:** Keep the archive API flow unchanged and update only the project workbench presentation layer. Reuse the existing Radix-backed `ConfirmDialog` and `Button` components, with local state in `ProjectWorkspace` for opening, submitting, and disabling the archive confirmation.

**Tech Stack:** React, TypeScript, Radix Dialog wrapper, existing CSS in `api/webui/src/styles.css`, Vite build.

---

### File Structure

- Modify `api/webui/src/pages/GrowthProjectWorkbenchPage.tsx`: import `ConfirmDialog`, replace `window.confirm` for archive with local dialog state, and render the archive confirmation dialog near the top of `ProjectWorkspace`.
- Modify `api/webui/src/styles.css`: add focused styles for the archive confirmation body, warning icon, effect list, and action row.
- Verify with `npm.cmd run build`.

### Task 1: Wire The Archive Dialog

**Files:**
- Modify: `api/webui/src/pages/GrowthProjectWorkbenchPage.tsx`

- [ ] **Step 1: Import the existing dialog component**

Change:

```tsx
import { Button } from "../components/ui";
```

to:

```tsx
import { Button, ConfirmDialog } from "../components/ui";
```

- [ ] **Step 2: Add local state inside `ProjectWorkspace`**

Add after the existing `moreMenuOpen` state:

```tsx
const [archiveConfirmOpen, setArchiveConfirmOpen] = React.useState(false);
const [archiving, setArchiving] = React.useState(false);
```

- [ ] **Step 3: Replace the archive browser confirm**

Replace the current `archiveProject()` body with:

```tsx
function archiveProject() {
  setMoreMenuOpen(false);
  setArchiveConfirmOpen(true);
}
```

- [ ] **Step 4: Add the actual submit handler**

Add below `archiveProject()`:

```tsx
async function confirmArchiveProject() {
  setArchiving(true);
  try {
    await onRun("archive");
    setArchiveConfirmOpen(false);
  } finally {
    setArchiving(false);
  }
}
```

- [ ] **Step 5: Render the centered confirmation dialog**

Add this near the top of `<main className="growth-project-detail">`, before the loading overlay:

```tsx
<ConfirmDialog
  open={archiveConfirmOpen}
  onOpenChange={(open) => {
    if (!open && !archiving) setArchiveConfirmOpen(false);
  }}
  title="归档项目"
  description={`确认归档“${projectName}”？归档后会从默认列表隐藏，但不会删除采集记录、样本和历史任务。`}
>
  <div className="project-archive-confirm">
    <div className="project-archive-confirm__summary">
      <AlertTriangle size={18} />
      <div>
        <strong>{projectName}</strong>
        <span>归档只会隐藏项目入口，已采集数据会继续保留。</span>
      </div>
    </div>
    <div className="project-archive-confirm__effects">
      <span>保留采集记录</span>
      <span>保留样本与证据</span>
      <span>保留历史任务</span>
    </div>
    <div className="project-archive-confirm__actions">
      <Button variant="ghost" onClick={() => setArchiveConfirmOpen(false)} disabled={archiving}>
        取消
      </Button>
      <Button variant="danger" onClick={() => void confirmArchiveProject()} disabled={archiving}>
        {archiving ? <RefreshCw size={16} className="spin" /> : <AlertTriangle size={16} />}
        确认归档
      </Button>
    </div>
  </div>
</ConfirmDialog>
```

### Task 2: Style The Dialog Content

**Files:**
- Modify: `api/webui/src/styles.css`

- [ ] **Step 1: Add local archive confirmation styles**

Add these styles next to the project workbench header/menu styles:

```css
.project-archive-confirm {
  display: grid;
  gap: 14px;
  margin-top: 16px;
}

.project-archive-confirm__summary {
  display: flex;
  gap: 12px;
  align-items: flex-start;
  padding: 12px;
  border: 1px solid #fecaca;
  border-radius: 10px;
  background: #fff7f7;
  color: #991b1b;
}

.project-archive-confirm__summary > svg {
  flex: 0 0 auto;
  margin-top: 1px;
}

.project-archive-confirm__summary div {
  display: grid;
  gap: 4px;
  min-width: 0;
}

.project-archive-confirm__summary strong {
  color: #7f1d1d;
}

.project-archive-confirm__summary span {
  color: #7a4f4f;
  font-size: 13px;
  line-height: 1.6;
}

.project-archive-confirm__effects {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}

.project-archive-confirm__effects span {
  min-height: 34px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  background: #f7faf9;
  color: var(--muted);
  font-size: 12px;
  font-weight: 700;
}

.project-archive-confirm__actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}

@media (max-width: 640px) {
  .project-archive-confirm__effects {
    grid-template-columns: 1fr;
  }
}
```

### Task 3: Verify

**Files:**
- No code changes.

- [ ] **Step 1: Run the production build**

Run:

```powershell
npm.cmd run build
```

Expected: TypeScript and Vite build complete without errors.

- [ ] **Step 2: Manual browser check**

Start the dev server if it is not already running:

```powershell
npm.cmd run dev
```

Open the workbench, click `更多`, then click `归档项目`.

Expected:

- The browser-native `127.0.0.1:8080 says` confirm dialog does not appear.
- A centered in-page dialog appears.
- `取消` closes the dialog without archiving.
- `确认归档` disables duplicate submission while the archive request is in flight.
