# AGENTS.md — Master Configuration & Session Orchestrator

This is the root instruction file. Every session MUST read this first, then delegate to the specialized context files listed below.

---

## Mandatory Context File Check Order

Before any code generation, read ALL of the following files in this exact order:

1. **@AGENTS.md** — Master rules: module boundaries, naming conventions, Windows constraints, and session workflow. Every line of generated code MUST comply.
2. **@prd.md** — Absolute scope boundary. Never implement anything outside this document. Never strip features the PRD guarantees.
3. **@implementation_plan.md** — The full milestone backlog. Mark tasks with `[x]` as they are completed. Never skip phases or reorder them.
4. **@task.md** — Active session scratchpad. Read this for immediate micro-tasks. Update it before finishing every session.
5. **@audit.md** — Known bugs, orphaned code, and PRD divergences. Must be consulted before marking ANY task as complete.

---

## Session Workflow

### 1. Start
```
Read @task.md → Read @AGENTS.md → Read @implementation_plan.md → Read @audit.md
```

### 2. Execute
- Pick one checkbox from `@implementation_plan.md` or one line from `@task.md`.
- Generate code that strictly follows `@system_prompt.md` rules.
- Never exceed the scope defined in `@prd.md`.

### 3. Verify (before marking done)
- Cross-check new code against every item in **@audit.md** Section 1 (bugs) and Section 3 (divergences).
- If the new code introduces a bug, creates orphaned code, or diverges from `@prd.md`, fix it before proceeding.
- If the new code resolves an existing audit item, update `@audit.md` with a resolution note.

### 4. Commit
- Update `@task.md`: clear completed items, verify `@implementation_plan.md` checkbox, sync `@audit.md` if applicable.
- Leave the session with `@task.md` pointing at the next unstarted micro-task.

---

## Critical Technical Quick Reference

### Commands
```bash
pip install -r requirements.txt
streamlit run app.py              # web app (primary)
python cli.py "path/to/dir"       # CLI
python cli.py "path/to/dir" --verbose --profile cinematography --case-style kebab-case --max-chars 60
python cli.py "path/to/dir" --dry-run                              # preview only
python cli.py "path/to/dir" --force                                 # re-analyze all
python cli.py "path/to/dir" --export-csv staging.csv                # export after analysis
python cli.py "path/to/dir" --import-csv staging.csv                # skip analysis, load from CSV
ruff check .                      # lint
pytest                            # unit tests
```

### Module roles
| File | Role | Must never |
|---|---|---|
| `engine.py` | Pure importable core | Call UI, run as entrypoint |
| `app.py` | Streamlit web UI | Reimplement engine logic |
| `cli.py` | CLI entrypoint | Reimplement engine logic |
| `config.json` | Single source of truth | Duplicate config in Python code |

### Per-asset rerun loop (app.py — most commonly broken pattern)
- Phase 1 (parallel FFmpeg extraction) runs ONCE per session.
- Phase 2 does ONE `analyze_asset_with_ai()` call per script execution, increments `analysis_index`, calls `st.rerun()`.
- Never batch AI calls in a single execution.
- Re-analysis: filters `base64_cache` to selected file names, resets `analysis_index=0`, sets `analysis_in_progress=True`. Uses same Phase 2 loop.

### Single-frame extraction (engine.py)
- `process_video_to_base64()` extracts ONE frame at the video midpoint (replaced the old 5×2 storyboard grid).
- AI receives a single representative frame per video — no more grid descriptions in summaries.
- `-ss` before `-i` (input seeking) for speed; `-vframes 1`; scale via `VIDEO_GRID_SCALE`.
- Images: downscaled via FFmpeg to `IMAGE_PREVIEW_MAX_EDGE` (1024px) in memory.

### ExifTool metadata (engine.py — most commonly misconfigured)
- `XMP-dc:Subject=` — one arg PER TAG. Never comma-separated.
- `EXIF:XPKeywords=` — images only (Windows "Tags" column).
- Metadata IS correct (verified by DaVinci Resolve, Premiere Pro). Windows Explorer just doesn't surface XMP for MP4 — not a bug.

### Session state reset pattern
On file change → reset: `analysis_done`, `analysis_in_progress`, `analysis_aborted`, `staged_assets`, `base64_cache`.
On Clear All → also pop: `uploaded_files`, `temp_dir`, increment `clear_counter`.
On commit success → clear: `uploaded_files`, `base64_cache`, `staged_assets`, `temp_dir`, `analysis_done`, `output_dir`, `logger`; increment `clear_counter`.

### AI Profile selector location
- In `app.py` main interface (NOT sidebar), placed right before the "Run AI Analysis" button.
- Changeable per analysis run. Has `on_change` that calls `set_active_profile()`.
- Custom profile shows text area for user prompt + export button.

### Staging table dynamic category options
- `st.column_config.SelectboxColumn` options built from `set(CATEGORY_LIST) | set(all categories in staged_assets)`.
- Ensures custom categories applied via bulk apply remain selectable in the data editor.

### Windows constraints
- `str(fp).startswith()` for path checks (not `Path.startswith()` — positional on Windows).
- `Path.rename()` fails cross-drive — use `shutil.move()`.

---

## Verification Gate (MANDATORY)

Before marking ANY task `[x]` in `@implementation_plan.md`:

1. **Search** the new/changed files for any violation of `@AGENTS.md` rules:
   - Wrong naming convention?
   - Forbidden import?
   - Module boundary crossed (e.g., `st.` call in `engine.py`)?
2. **Check** `@audit.md` Section 1 — did this introduce a new bug? Update the section if yes.
3. **Check** `@audit.md` Section 3 — did this diverge from `@prd.md`? If yes, revert the scope expansion.
4. **Update** `@task.md` — move completed items to done, add any discovered follow-ups.
5. **Final syntax check** — `python -m py_compile <file>` for every changed `.py` file.

Only after all five steps pass may a task be marked complete.

---

## Git Workflow

### 1. Feature branch first
- Before making any code modifications, create a new micro-focused feature branch from `main`.
- Branch naming: `feat/<short-description>` (e.g. `feat/upload-progress`, `feat/category-management`).
- Never commit or work directly on `main`.

### 2. Incremental commits
- After a task in `@task.md` is successfully implemented **and** passes the Verification Gate, make a local Git commit.
- Commit message format: `scope: concise description of what changed`
  - Examples: `upload: add progress bar during file copy`, `tests: add unit tests for config loading`
- Keep commits small and focused — one commit per completed task, not one giant commit for multiple tasks.

### 3. Push requires permission
- Do **not** run `git push` to the remote GitHub repository without explicit user approval.
- After committing, present the commit summary and ask before proceeding.
