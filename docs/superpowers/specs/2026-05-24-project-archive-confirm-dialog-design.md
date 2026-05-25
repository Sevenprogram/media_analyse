# Project Archive Confirm Dialog Design

## Context

The project workbench currently uses `window.confirm` when the user chooses "归档项目" from the project more menu. The browser-native dialog is visually disconnected from the app, exposes the local host label, and cannot use the workbench's spacing, typography, action hierarchy, or loading state.

## Selected Approach

Use a centered in-page confirmation dialog for project archive only.

The dialog appears over the existing workbench with a dim overlay. It clearly names the current project, explains the effect of archiving, and offers two actions:

- "取消": closes the dialog without calling the archive API.
- "确认归档": closes the menu, submits the archive action, and shows the existing workbench notice/loading behavior.

## User Experience

Trigger:

- User opens the project "更多" menu.
- User clicks "归档项目".
- The menu closes and the centered dialog opens.

Dialog content:

- Title: "归档项目"
- Description: "确认归档「{项目名}」？归档后会从默认列表隐藏，但不会删除采集记录、样本和历史任务。"
- Optional compact detail block: "保留采集记录 / 保留历史任务 / 可从归档数据继续追溯"

Action hierarchy:

- Secondary action: "取消"
- Destructive primary action: "确认归档"

Keyboard and accessibility behavior should come from the existing Radix `ConfirmDialog` wrapper:

- Escape closes the dialog.
- Focus is trapped inside the dialog while open.
- The title and description are exposed to assistive technology.

## Implementation Shape

Reuse the existing `ConfirmDialog` and `Button` components from `api/webui/src/components/ui.tsx`.

In `api/webui/src/pages/GrowthProjectWorkbenchPage.tsx`:

- Add local state for the archive confirmation dialog.
- Change `archiveProject()` so it opens the dialog instead of calling `window.confirm`.
- Add a `confirmArchiveProject()` handler that calls `onRun("archive")`.
- Keep the archive API flow in the existing parent callback; no backend changes are needed.

The existing `controlGrowthProject(..., "archive")` behavior remains unchanged.

## Error Handling

If the archive request fails, keep using the existing `notice` flow that displays the error message in the project workbench.

The confirm button should be disabled while the archive request is in flight to prevent duplicate submissions.

## Testing

Manual verification:

- Open project workbench.
- Open "更多".
- Click "归档项目".
- Confirm that the browser-native dialog no longer appears.
- Confirm that the centered in-page dialog appears with the current project name.
- Click "取消" and verify no request is submitted.
- Reopen the dialog, click "确认归档", and verify the existing archive flow still runs.

Automated verification can be limited to TypeScript build for this small UI change.
