# Decisions

Current architectural and UI rules. These are facts for the next session, not suggestions.

## UI system

- `frontend/src/styles.css` `:root` holds the design tokens. New controls must use them rather than new hard-coded colours or spacing.
- Every page uses `frontend/src/components/PageHeader.tsx` for its title, description and optional action.
- Empty states must offer the next action, not just a sentence.
- Model availability is labelled "On server" or "Catalog" from `/api/environment`; never claim "installed" or invent sizes.
- Tooltips use max width and the side variant closest to free screen space; icon-only controls need one.
- Shared `.ui-*` classes are the preferred styling layer. Existing Tailwind markup is kept where it works; do not replace working page logic with new React primitives.
- `frontend/src/components/Tooltip.tsx` is the only app-level tooltip. Use it for icon-only controls and hints that need explanation. Do not rely on native `title` for new controls.
- Recharts' own `Tooltip` in `Staging.tsx` stays; it is a chart component, not an app tooltip.
- Reduced-motion preferences must be respected. `.ui-spinner` keeps a 2.4s rotation so progress is still visible.
- Empty and error states use `.ui-empty` and `.ui-inline-error` rather than page-specific text alone.
- Table containers use `.ui-scroll` for contained, styled scrolling.
- The Analysis page owns one primary action (Run). Source modes and advanced controls live behind small disclosures; results appear as cards, not only a log.
- Session "Restore" loads staged assets only. The server returns `{loaded, asset_count}`; settings restoration is deliberately deferred and must not be claimed.
- Per-file status is keyed by the full original path; `asset_error` now carries `path` as well as the basename `name`.
- `frontend/src/utils/relativeTime.ts` and `analysisResults.ts` hold the shared time and result/status helpers.
- The Tailwind theme uses `ok` for success; `success` is not a defined colour token.

## Repository and release

- `main` is protected by the GitHub ruleset **Protect main**: changes arrive by pull request and the `tests` check must pass.
- Local checkpoint commits on `pipeline/<date>` are permitted only after Gate A approval; pushing and deploying are never implied.
- Release v2.2.6 exists on GitHub; its installer and `.sig` were replaced on 2026-11-28 with the build from this branch, at the user's explicit instruction not to bump the version. Check the release assets for the current file.
- No database, migrations or cron schedules exist in this project.

## Why these choices

- Refining the existing dark palette preserves continuity with the shipped splash and sidebar.
- CSS classes and one tooltip component give a consistent look without the churn and risk of replacing six pages' working controls.
- Medium density keeps tables scannable in a working tool.
