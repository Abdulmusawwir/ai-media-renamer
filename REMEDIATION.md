# Remediation Plan — AI Media Renamer

> Source: codebase review (engine.py / app.py / cli.py / bootstrap.py / config / tests).
> Four workstreams. Wave 1 = all Critical + High items. Wave 2 = Medium backlog. Wave 3 = Low + docs/config hygiene.
> Each wave runs on its own feature branch and must pass the AGENTS.md Verification Gate (ruff, pytest, `py_compile`, audit.md sync) before commit.

## Wave 1 — Critical + High (in execution order)

### Workstream 1 — Security (completes Phase AI 20.x)

| # | Item | Location | Fix | Status |
|---|------|----------|-----|--------|
| S1 | Gemini API key leaks into error detail / `log_event` / `_format_ai_error` | `engine.py:1647, 1670, 603, 2136` | Register keys in a module secret cache; `_redact_sensitive()` masks key values + `?key=...` query strings in exception detail, log records, and formatted AI errors. | DONE |
| S2 | ExifTool argument injection from AI metadata | `engine.py:2263-2330` | `_sanitize_metadata_value()` strips `\r\n\x00`, collapses whitespace, strips leading `-`, caps length; applied to `title`/`summary`/`tags` in `_build_commit_args`. | DONE |
| S3 | `download_file` follows redirects to plaintext HTTP | `engine.py:3203` | Reject non-HTTPS from `resp.url` after redirects. | DONE |
| S4 | Keyring fail-closed + provider-switch consistency | `engine.py:3384, 545-576` | Wrap keyring calls; no plaintext fallback; `switch_ai_provider` mutates state only after a successful key store / consistent sequence. UI surfaces keychain unavailability via new `keyring_available()` probe (sidebar warning + guarded `load_api_key`/`save_api_key`/`switch_ai_provider` call sites). Completes 20.2. | DONE |
| S5 | Mask secrets in Config tab | `app.py:2053` | `mask_secrets()` deep-copies the JSON view, redacting `*api_key*/*token*/*password*/*secret*` keys; editor gets a warning caption. | DONE |

### Workstream 2 — Correctness & data-loss bugs

| # | Item | Location | Fix | Status |
|---|------|----------|-----|--------|
| C1 | Cross-drive commits fail via `Path.rename` | `engine.py:2383, 2448` | `_commit_move()` uses `shutil.move` (AGENTS.md Windows rule). | DONE |
| C2 | `skip_rename` silently overwrites same-name files | `engine.py:2379-2381, 2444-2446` | Dedup loop applies to the copy target too (`_commit_move`). | DONE |
| C3 | Rename race in parallel CLI commits | `engine.py:2437-2448` + `cli.py` | `_commit_move` retries with suffix on `FileExistsError` (bounded). | DONE |
| C4 | Rollback log dropped on partial failure | `engine.py:2666-2673` | Keep the batch entry when `failed > 0` so it can be retried. | DONE |
| C5 | `reload_config()` misses globals | `engine.py:216-239` | Move stray module-scope line into the function; refresh `DEFAULT_TEMPLATE_STRING`, `PROMPT_PROFILES`, `CURRENT_PROVIDER`, `TEXT_MODEL_NAME`, `IMAGE_PREVIEW_MAX_EDGE`, `VIDEO_GRID_SCALE`, `DOCUMENT_EXTENSIONS`. | DONE |
| C6 | AI response validation too lax | `engine.py:1355-1368, 1488` | Guard non-dict parses (`"null"`), require `tags` to be a list when present; keep permissive extra-field tolerance (existing tests rely on it). | DONE |
| C7 | ExifTool batch errors ignored + IPC deadlock risk | `engine.py:665-695, 2454-2458` | Reader-thread + queue with timeout; `execute_batch()` returns one output per arg-set; `execute_commit_batch` marks `ERROR:` when a file's write reports `Error:`. | DONE |
| C8 | `check_ollama_health` never detects vision models | `engine.py:2943` | Same 3-branch name extraction as `check_environment` (`hasattr(m, "model")`) + one retry on transient failures. | DONE |

### Workstream 3 — Streamlit health

| # | Item | Location | Fix | Status |
|---|------|----------|-----|--------|
| C9 | Phase 2 batches all AI calls | `app.py:1048-1140` | Restore per-asset rerun loop: ONE `analyze()` per execution, persist `staged_assets` + `analysis_index`, `st.rerun()`; terminate at end. | |
| C10 | "Stop Analysis" is dead state | `app.py:210, 256-257` | Render a real Stop button during analysis; loop reads `analysis_aborted` and finalizes. | |
| C11 | CSV import infinite rerun loop | `app.py:1592-1602` | Pop the uploader key before `st.rerun()`. | |
| C12 | Data-editor edits not synced | `app.py:1527-1531` | Sync `category`/`tags`/`proposed_filename` back to `staged_assets` alongside `rating`. | |
| C13 | All-audio uploads abort | `app.py:1309-1311` | Include `audio_results` in the abort guard. | |

## Phase AI 20.3–20.5 — Local server exposure, input validation, log privacy

| # | Item | Location | Fix | Status |
|---|------|----------|-----|--------|
| 20.3 | Streamlit binds loopback by default + LAN opt-in | `bootstrap.py:1312`, `.streamlit/config.toml`, `config.json` `server.lan_expose`, `app.py` Config tab | Explicit `--server.address=127.0.0.1` unless `lan_expose`; in-UI toggle + warnings; Docker host ports bound to `127.0.0.1:`. | DONE |
| 20.4 | Input validation & injection | `engine.py:3691-3727, 2702-2752, 2470` | `unsafe_allow_html` sites audited (all static); `_neutralize_csv_formula()` on import/export; CSV `proposed_filename` path-separator rejection; `load_session` schema validation + symlink rejection; `_safe_stem()` traversal lock-in. | DONE |
| 20.5 | Log path privacy | `engine.py:657-715`, `config.json` `logging.redact_paths` | `redact_paths` flag (default on) masks Windows/UNC/POSIX absolute paths in `log_event`; retention documented. | DONE |

## Wave 2 — Medium backlog (Workstreams 2 + 3)

- `app.py:435,461-466,495-501` — move provider reset / engine switch / config writes into callbacks.
- `app.py:1154-1199` — AI profile selector placement relative to Run button.
- `app.py:1751-1775` — align commit-success reset to AGENTS.md contract (or document divergence).
- `app.py:940-941` — Clear All silently deletes saved sessions → confirm dialog / exclude.
- `app.py:1677-1776` — `exif.close()` via `finally`; `app.py:882` temp-dir leak (`rmtree` old dir).
- `app.py:1604-1617, 1794-2004` — guard expander / analytics heavy work with tab/`details.open` gating.
- `engine.py:941,962-973` — locking on `_whisper_model_cache`.
- `engine.py:2109,2130` — respect `config["model"]["last_provider"]` instead of hardcoded `"ollama"`.
- `engine.py:1213` — `sanitize_name` stops stripping the words `grid`/`sequence`.
- `engine.py:1199` — `validate_category` uses `get_active_categories()`.
- `engine.py:1138` — `.doc` handled truthfully (log `unsupported_doc`, report `False`).
- `engine.py:3348, 3313` — Ollama/llama.cpp ports from config/env, not hardcoded.
- `engine.py:212` — atomic `save_config` (temp + `os.replace`).
- `engine.py:902` — replace `tempfile.mktemp`.
- `engine.py:647-648` — `ExifToolSession.__init__` raises instead of `print` + `sys.exit`; callers catch.
- `engine.py:83-93, 117` — defer config validation so imports don't `print`/`sys.exit`.
- `app.py:925-932` etc. — single `_reset_analysis_state()` helper; clear `analysis_index`, `duplicate_pairs`.
- `cli.py:908-985` — argparse mutually-exclusive groups; sync `--case-style` default to `DEFAULT_CASE_STYLE`.

## Wave 3 — CLI, docs, config & lint hygiene

- **CLI**: `--import-csv` should not require a positional `dir`; `--categories-override` validated as dict.
- **Telemetry divergence**: `implementation_plan.md` Layer 15 + CHANGELOG + `README_TECH.md:82-83` claim telemetry that does not exist (PRIVACY.md says none). Document reality; re-scope 20.5. **RESOLVED (v1.6.3):** 20.5 re-scoped in `implementation_plan.md` — no `track_event()` exists, PRIVACY.md already documents "no telemetry", purge item marked N/A. A separate pass should still clean the stale telemetry claims in `CHANGELOG.md` + `README_TECH.md`.
- **Config**: fix `model.providers.gemini.selected_model` (`llama-3.2-90b-vision-preview` → real Gemini model); drop dead `preview.video_grid_tile` / `video_frame_count`.
- **Ruff**: fix 70 lint errors (43 auto-fixable; mostly `tests/` F401/E501/I001).
- **Single source of truth**: `NAMED_TEMPLATES`, llama.cpp URLs/digests duplicated in code vs config.
- **`save_session` timestamp collisions** (`engine.py:2483`); `load_session` KeyError on malformed files.
- **Docs sync**: `task.md`, `audit.md` §1/§3, `implementation_plan.md` checkboxes per AGENTS.md.