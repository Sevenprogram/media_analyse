# Project-Scoped Today Intelligence Design

## Goal

Today Intelligence must produce different AI analysis for different growth projects, and must restore the last saved analysis when the user switches back to a project.

## Behavior

- When a project is selected, the frontend calls Today Intelligence with `project_id`.
- The backend resolves `project_id` to a growth project record and builds an analysis bundle from that project's jobs, samples, keywords, platforms, opportunities, and risks.
- The result is stored in `research_global_settings` under a project-specific key: `reports:today-intelligence:project:{project_id}`.
- Switching projects reads the saved project result first. A fresh saved result is returned directly. A stale saved result is also returned so the page can show the previous analysis with stale status instead of blanking the page.
- If no saved result exists for the project, the backend generates one with the AI Gateway.
- Clicking regenerate forces AI analysis for the current project and overwrites only that project's saved result.
- With no selected project, the current global behavior remains available.

## Data Rules

- Project identity is resolved through the existing growth project resolver.
- Project jobs are found with the existing project-key matching logic used by reporting.
- Project sample stats are computed from those job ids using existing `get_job_stats_many`.
- AI may explain and prioritize, but counts and evidence remain rule-derived.

## UI Rules

- The page should show the selected project's analysis without mixing in global cached data.
- While switching, stale project history is better than an empty panel.
- Regenerate targets the selected project only.
- Existing page layout and visual language remain unchanged.
