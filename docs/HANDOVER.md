# Handover — current repository state

Facts on disk, not conversation history. Read this before making changes.

## Current work

- Active branch: `pipeline/2026-11-28` (local only; **not pushed**).
- Base: `main` at `45b1258` (v2.2.6 release).
- Task: 1-9 UI improvements — visual depth, header/sidebar hierarchy, actionable empty states, Analysis progress experience, structured Settings, honest Models page, tooltip polish, table/chart polish and folder picker improvements.

## Completed on this branch

- Gradient app-shell canvas and `.ui-surface` elevated cards applied across pages.
- Shared `PageHeader` with icon chip, title, description and action slot on all six pages.
- Top bar now shows `Workspace / current page` and a tooltipped status pill; duplicate app name removed.
- Sidebar gained a Workspace label, softer gradient active state and tighter rhythm.
- Actionable empty states with icon and next-step button on Staging, Commit and Sessions; Models shows icon and setup guidance.
- Analysis step strip (Add media, Extract, Analyze, Review & commit) driven by `progress.status`; log kept.
- Stronger dropzone with icon chip, active styling and selected-file badge; click/drop/native-picker behaviour unchanged.
- Settings structured overview cards; raw JSON moved into an Advanced disclosure.
- Models shows Vision and "On server"/"Catalog" badges from `/api/environment`; Download disabled when on server. No sizes or install claims invented.
- Tooltip max width and left/right placement; status pill, model downloads and Settings cards have tooltips.
- Staggered card entrance with reduced-motion respected.
- Sticky table headers, denser rows and a gradient chart card.
- DirectoryPicker filter, clickable breadcrumb segments and file-kind icons.
- New tests: PageHeader, DirectoryPicker filter/breadcrumbs, tooltip placement.

## Verification performed

| Check | Command | Result |
|---|---|---|
| Python lint | `ruff check .` | passed, 0 errors |
| Python tests | `python -m pytest -q` | 447 passed, 1 skipped |
| Version validator | `python scripts/check_versions.py --tag v2.2.6 --latest-json dist/latest.json` | all versions match |
| TypeScript | `npx tsc --noEmit -p tsconfig.json` | exit 0 |
| Frontend tests | `npm test` | 5 files, 16 tests passed |
| Frontend build | `npm run build` | passed |
| Rust format | `cargo fmt --check` | exit 0 |
| Rust lint | `cargo clippy -- -D warnings` | exit 0 |
| Rust tests | `scripts/cargo-test-gnu.ps1` | 18 passed, 0 failed |
| Browser pass | Playwright over six pages at 1440x900 and 1024x768 | 0 console errors, no horizontal overflow, nav tooltip works |

No E2E suite exists; browser checks were manual Playwright runs.

## Pending / uncommitted

- None. Working tree clean on `pipeline/2026-11-28` at the end of the build stage.

## Waiting on the user

- Tray menu clicks: Show, Quit, Setup & Dependencies.
- Clean-machine first-run wizard with an empty `%APPDATA%\ai-media-renamer`.
- Explicit approval before push, merge or a new release. Gate B approval is still pending.

## Warnings and hard stops

- Published **v2.2.6** does **not** include this branch's second UI pass. A new build/release is needed to ship it.
- No database, SQL migrations, cron schedules or live database exist.
- CI needs `TAURI_SIGNING_PRIVATE_KEY` and `TAURI_SIGNING_PRIVATE_KEY_PASSWORD` secrets.
- `main` is protected by the **Protect main** ruleset: pull request required, `tests` check required.
- Never push, deploy, apply migrations or change secrets/hosting/cron without explicit approval in a later turn.

## Git state to inspect first

`git status -sb` and `git log --oneline -15`. Expect `pipeline/2026-11-28` with the UI commits on top of `45b1258`.
