# Handover — current repository state

Facts on disk, not conversation history. Read this before making changes.

## Current work

- Active branch: `pipeline/2026-11-28` (local; pushed after Gate B approval).
- Base: `main` at `331d3eb` (second UI pass, PR #16).
- Task: Phase A items 1-6 and Phase B items 1-5 — one obvious starting point, clear source modes, live results, per-file status and recents that resume. Item 7 (API docs link in Settings) is deferred.
- Version stays **2.2.6** by explicit user instruction: the existing v2.2.6 release assets are replaced with this build rather than bumping the version. Check the GitHub release for the current asset.

## Completed on this branch

- Analysis opens with a large dropzone and one Run button; source segmented control Files / Folder / Recent.
- Recent folders carry `{path, at}` in localStorage, validate stored paths, show relative labels and reload their list when the Recent tab opens.
- Live result cards populate one per `asset_analyzed` event, keyed by original path; name, category, tags and summary only — no invented thumbnails.
- Per-file status (Queued / Done / Failed) beside each queued file, driven by the analysis WebSocket.
- Profile selection, language and advanced settings moved behind a **More options** disclosure with a visible default and an auto-routing chip.
- "Last run" line shows the real staged count, or the last saved session with one-click restore when staging is empty.
- Progress steps now lead to Review and Commit; completion no longer auto-navigates, so the result cards stay visible.
- Every changed action gives a toast plus inline state, and errors name the next step.
- Sessions table shows relative modified time and "Restore" opens Staging.
- Duplicate `pyinstaller` install removed from CI and the desktop build script (it is already in `requirements.txt`).

## Verification performed

| Check | Command | Result |
|---|---|---|
| Python lint | `python -m ruff check .` | passed, 0 errors |
| Python tests | `python -m pytest -q` | 447 passed, 1 skipped |
| Version validator | `python scripts/check_versions.py --tag v2.2.6` | all versions match |
| TypeScript | `npx tsc --noEmit -p tsconfig.json` | exit 0 |
| Frontend tests | `npm test` | 8 files, 39 tests passed |
| Frontend build | `npm run build` | passed |
| Rust format | `cargo fmt --check` | exit 0 |
| Rust lint | `cargo clippy --all-targets -- -D warnings` | exit 0 |
| Rust tests | `cargo test` with GNU harness tweaks | 18 passed, 0 failed |
| Browser pass | Playwright over six pages at 1440x900 and 1024x768 | 0 console errors, no horizontal overflow |

No E2E suite exists; browser checks were manual Playwright runs.

## Pending / uncommitted

- None at the end of the build stage. Working tree clean on `pipeline/2026-11-28`.

## Waiting on the user

- Tray menu clicks: Show, Quit, Setup & Dependencies.
- Clean-machine first-run wizard with an empty `%APPDATA%\ai-media-renamer`.
- Push, merge and the v2.2.6 asset replacement were explicitly approved on 2026-11-28; further releases still need a new yes.

## Warnings and hard stops

- No database, SQL migrations, cron schedules or live database exist.
- CI needs `TAURI_SIGNING_PRIVATE_KEY` and `TAURI_SIGNING_PRIVATE_KEY_PASSWORD` secrets; local updater key is `C:\Users\AMQB\.tauri\ai-media-renamer.key`.
- `main` is protected by the **Protect main** ruleset: pull request required, `tests` check required.
- Session restore returns staged assets and an asset count only — not the AI profile or settings.
- Per-file status is keyed by basename because `asset_error` carries only `path.name`; duplicate filenames in different folders share a badge.

## Git state to inspect first

`git status -sb` and `git log --oneline -15`. Expect the Phase A/B UI commits plus the build cleanup on top of `331d3eb`.
