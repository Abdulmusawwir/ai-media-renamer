# Handover — current repository state

This file records state on disk, not conversation history. Read it before making changes.

## Current work

- Active branch for this doc update: `docs/handover-v226`. `main` is at `34778dd` (v2.2.6).
- The `pipeline/2026-11-26` branch was pushed, merged into `main` via PR #14, and deleted.
- Task in this pipeline: thorough UI analysis and modernisation — modern, elegant, user friendly, actionable, with tooltips.

## Completed on this branch

- Design tokens and shared `.ui-*` classes in `frontend/src/styles.css`.
- Reduced-motion support: global transitions shortened, `.ui-spinner` slowed to 2.4s.
- Accessible `frontend/src/components/Tooltip.tsx` with hover, focus, keyboard support, `aria-describedby`, and timer cleanup; 4 unit tests.
- Shared button classes applied across Analysis, Staging, Commit, Sessions, Settings, Models and icon-only dismiss/remove controls.
- Standardised empty and inline-error states in Commit, Models, Sessions, Staging, Settings and DirectoryPicker.
- Tooltips on sidebar nav items, dismiss/remove buttons, folder recents, drive buttons and the add badge.
- Responsive polish: 1400px content ceiling, stable scrollbar gutters, styled scrollbars, `ui-scroll` on table containers.
- Removed three unused CSS classes found in the diff audit.
- `.gitignore` now ignores `.opencode/pipeline/`.

## Verification performed

| Check | Command | Result |
|---|---|---|
| Python lint | `ruff check .` | passed, 0 errors |
| Python tests | `python -m pytest -q` | 447 passed, 1 skipped |
| Version validator | `python scripts/check_versions.py --tag v2.2.6 --latest-json dist/latest.json` | all versions match |
| TypeScript | `npx tsc --noEmit -p tsconfig.json` | exit 0 |
| Frontend tests | `npm test` | 3 files, 11 tests passed |
| Frontend build | `npm run build` | passed |
| Rust format | `cargo fmt --check` | exit 0 |
| Rust lint | `cargo clippy -- -D warnings` | exit 0 |
| Rust tests | `scripts/cargo-test-gnu.ps1` | 18 passed, 0 failed |
| Browser checks | Playwright over all six pages at 1440x900 and 1024x768 | no console errors, no horizontal overflow, nav tooltip works, reduced motion 2.4s, add-file toast works |

No E2E test suite exists in this repository; the browser checks above were manual Playwright runs.

## Pending / uncommitted

- None. Working tree is clean on `pipeline/2026-11-26`.

## Waiting on the user

- Tray menu clicks: Show, Quit, Setup & Dependencies.
- Clean-machine first-run wizard with an empty `%APPDATA%\ai-media-renamer`.
- Explicit approval before deployment. Push, merge into `main` and the v2.2.6 release were approved and completed.

## Warnings and hard stops

- The published **v2.2.6** GitHub release and installer include the UI changes: https://github.com/Abdulmusawwir/ai-media-renamer/releases/tag/v2.2.6. The remote installer hash was verified against the local build.
- No database, SQL migrations, cron schedules or live database exist in this project.
- CI needs `TAURI_SIGNING_PRIVATE_KEY` and `TAURI_SIGNING_PRIVATE_KEY_PASSWORD` secrets for signed updater artifacts.
- `main` is protected by the GitHub ruleset **Protect main**: pull request required, `tests` check required. Direct pushes are rejected.
- Never push, deploy, apply migrations, write to a live database, or change secrets/hosting/cron without explicit approval in a later turn.

## Git state to inspect first

Run `git status -sb` and `git log --oneline -15`. Expect to be on `pipeline/2026-11-26` with the UI commits on top of `00d53c5`.
