# Tauri Desktop Shell Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship AI Media Renamer 2.2.0 as a signed-updater, installer-based Windows desktop app: a Tauri v2 shell that owns the window, tray, single-instance behavior, file drops, Python sidecar lifecycle, and in-app updates, while keeping the existing React SPA, FastAPI backend, browser mode, and CLI.

**Architecture:** Tauri (Rust) starts a PyInstaller `onedir` backend (`AIMediaRenamerBackend.exe`) on a random loopback port, passes a per-launch bearer token, and loads the SPA served by that backend. The shell lives in the tray, enforces one instance, and forwards dropped/second-launch paths to React. The backend remains the only owner of engine logic. Releases are NSIS installers with Tauri minisign updater artifacts published to GitHub Releases; `latest.json` drives in-app updates.

**Tech Stack:** Python 3.12, FastAPI, PyInstaller `onedir`, pytest; React 18 + TypeScript + Vite 5; Rust stable + Tauri v2 (`tauri-plugin-single-instance`, `-dialog`, `-updater`, `-process`, `-opener`); GitHub Actions on Windows; NSIS; PowerShell.

**Spec:** `docs/superpowers/specs/2026-11-08-tauri-desktop-design.md` (approved 2026-11-10).

---

## Global Constraints

- Work only on branch `feat/tauri-desktop`; never code on `main`. Commit after each task only after its verification gate. Never push without explicit user approval.
- Windows 11, PowerShell 5.1, Python 3.12, Node 20, Rust stable. Do not use `rg`; use the Grep tool.
- Baseline: `ruff check .` clean, `pytest` = **330 passed, 1 skipped** before this work. New tests add to that count; no existing test may be weakened or deleted.
- Do not change analysis prompts, AI outputs, naming rules, categories, commit/rollback semantics, staging schema, `engine.py` public behavior unrelated to paths/lifecycle, or the browser/CLI feature set.
- The installed app writes only under `<data_root>` (`AMR_DATA_DIR` or `%APPDATA%\ai-media-renamer`), never under the install directory. Source mode keeps repository `config.json` and `logs/`.
- The desktop token never appears in CLI arguments, logs, config, or disk. It travels only in `AMR_DESKTOP_TOKEN` and memory.
- Release backend is windowed (`console=False`); stdout/stderr must be redirected before importing `engine`/`server`.
- Never use `console=True` for `desktop_backend`; never use Tauri `externalBin` for the onedir backend; never bundle the SPA twice.
- Every changed Python file must pass `python -m py_compile <file>` and `ruff check <file>`.
- Tests must use `tmp_path`/`tmp_dir` and `monkeypatch`; never call `set_active_profile()`, `run_analysis()`, or `save_config()` against the real `config.json`. Monkeypatch `engine.save_config` when a route may persist.
- Use `str(fp).startswith(...)` for path checks and `shutil.move()` for cross-drive moves. Preserve Windows path/space/non-ASCII behavior.
- Use `apply_patch` for edits. Do not add comments except where required for a non-obvious Windows/Tauri contract.
- Frontend changes must pass `npm run build` (which runs `tsc`). Rust changes must pass `cargo fmt --check`, `cargo clippy -- -D warnings`, and `cargo test`.

---

## Review Focus (apply to every task)

| Class | What must not break | Owning tasks |
|---|---|---|
| **A. Fresh install, no data** | No `%APPDATA%` config, no tools, no models: shell shows setup, backend starts after setup, seed config is valid, no install-dir writes. | 1, 2, 6, 7 |
| **B. Source/portable** | `AMR_DATA_DIR` redirects config, logs, setup, sessions, undo, models, shell logs; source without override still uses repo config/logs and APPDATA user data; CLI unaffected. | 1, 2, 6 |
| **C. Startup/runtime races** | Port binding retry, backend crash dialog, no orphan backend/llama-server, version mismatch policy, SPA reload on client routes. | 3, 5, 7 |
| **D. Destructive actions** | Quit/setup/update blocked while analysis, commit, download, or migration runs; staging survives; update relaunches N→N+1; data survives. | 4, 8, 10, 11 |
| **E. Paths** | Spaces and non-ASCII in data root/model paths; cross-drive legacy model move; locked files; `.part` cleanup; no truncated destination. | 2, 9 |

---

## File Map

**Python**
- `engine.py` — path/config/log resolution, model dirs/migration, binary resolution, llama-server lifecycle.
- `bootstrap.py` — setup entry point, `CACHE_DIR`/`BIN_DIR`, runtime DLL install, `--no-launch`/`--no-update-check`.
- `desktop_backend.py` — **new** packaged backend entry point.
- `server/main.py` — desktop middleware registration, `/health`, SPA fallback.
- `server/desktop.py` — **new** desktop token/middleware/status helpers.
- `server/routes/desktop.py` — **new** `/api/desktop/status`, `/api/desktop/shutdown`.
- `server/routes/analysis.py`, `commit.py`, `models.py`, `deps.py` — busy flags.
- `server/routes/__init__.py` — register desktop router.
- `build_desktop.spec` — **new** onedir spec; delete `build_v2.spec` after CI switches.

**Frontend**
- `frontend/src/desktop/index.ts` — **new** Tauri bridge.
- `frontend/src/components/DesktopBridge.tsx` — **new** event/update wiring.
- `frontend/src/store.ts` — incoming paths.
- `frontend/src/api/client.ts` — desktop token.
- `frontend/src/pages/Analysis.tsx`, `Settings.tsx`; `frontend/src/App.tsx`; `frontend/src/main.tsx`.
- `frontend/vite.config.ts` — `127.0.0.1` host/proxy.
- `frontend/package.json` — Tauri JS plugins.
- root `package.json` — Tauri CLI + `dev:backend`.

**Tauri**
- `src-tauri/Cargo.toml`, `build.rs`, `tauri.conf.json`, `capabilities/default.json`, `capabilities/remote.json`.
- `src-tauri/src/main.rs`, `lib.rs`, `backend.rs`, `settings.rs`, `commands.rs`, `tray.rs`.
- `src-tauri/splash/index.html`; `src-tauri/icons/*`.
- `src-tauri/Info.plist` not needed (Windows only).

**Build/CI/docs**
- `scripts/check_versions.py`, `scripts/build-desktop.ps1`.
- `.github/workflows/build.yml`.
- `VERSION`, `engine.py`, `pyproject.toml`, `frontend/package.json`, `src-tauri/Cargo.toml`, `src-tauri/tauri.conf.json` all set to `2.2.0`.
- `README.md`, `docs/`, `AGENTS.md`, `task.md`, `audit.md`.

---

### Task 1: Data root, config seeding, and log paths

**Files:**
- Modify: `engine.py` (top of file, path/config/load sections)
- Test: `tests/test_desktop_paths.py` (create)

**Interfaces:**
- `engine.BASE_DIR: Path` — repo root in source, `_MEIPASS` when frozen.
- `engine.BUNDLE_DIR: Path` — `_MEIPASS` when frozen, else `BASE_DIR`.
- `engine.is_frozen() -> bool`
- `engine.resolve_data_dir() -> Path`
- `engine.APP_DATA_DIR: Path` = `resolve_data_dir()`
- `engine.USER_DATA_DIR: Path` = `APP_DATA_DIR`
- `engine.resolve_config_path() -> Path`
- `engine.CONFIG_PATH: Path`
- `engine.load_config(config_path: str | Path | None = None, quiet: bool = False) -> dict[str, Any]`
- `engine._resolve_log_dir(cfg: dict[str, Any]) -> Path`
- `engine.LOG_DIR: Path`
- `engine._seed_config_if_missing() -> None`
- `engine.restore_default_config() -> bool` uses `CONFIG_PATH` + `BUNDLE_DIR/config.default.json`.

**Behavior:**
- `AMR_DATA_DIR` wins for `APP_DATA_DIR`; otherwise `%APPDATA%\\ai-media-renamer`; fallback `~/AppData/Roaming/ai-media-renamer`.
- `USER_DATA_DIR` stays `APP_DATA_DIR` in both source and frozen modes.
- `CONFIG_PATH`: frozen or `AMR_DATA_DIR` → `APP_DATA_DIR/config.json`; source without override → `BASE_DIR/config.json`.
- `load_config(None)` uses `CONFIG_PATH`; an absolute argument is used as-is; a relative argument resolves under `BASE_DIR` (preserves existing tests).
- On first run, if `CONFIG_PATH` is missing and mode is frozen/override, seed from `BUNDLE_DIR/config.default.json`. If a legacy `config.json` next to `sys.executable` or `BASE_DIR` exists and the destination is missing, copy it only when it parses as JSON.
- `_resolve_log_dir`: absolute `logging.directory` is honored; relative resolves under `BASE_DIR` for source without override, otherwise under `APP_DATA_DIR`. `LOG_DIR.mkdir(parents=True, exist_ok=True)`.
- `save_config()` creates `CONFIG_PATH.parent` and raises on failure.
- `reload_config()` refreshes `LOG_DIR` (add to its `global` list and assignment).
- Define path constants **before** the first `load_config()` call.

**Steps:**
- [ ] Write failing tests in `tests/test_desktop_paths.py`:
  - `test_amr_data_dir_overrides_appdata`
  - `test_app_data_dir_default`
  - `test_source_config_path_uses_repo`
  - `test_override_config_path_uses_data_root`
  - `test_frozen_config_path_uses_data_root` (monkeypatch `engine.is_frozen` and module constants)
  - `test_seed_config_from_bundled_default`
  - `test_legacy_portable_config_imported_once`
  - `test_seed_does_not_overwrite_existing_config`
  - `test_source_log_dir_is_repo`
  - `test_frozen_log_dir_is_data_root`
  - `test_reload_config_refreshes_log_dir`
  - `test_load_config_absolute_path`
  - `test_save_config_creates_parents` (monkeypatch `engine.CONFIG_PATH` to `tmp_path`; monkeypatch `engine.save_config` elsewhere as needed)
- [ ] Run `python -m pytest tests/test_desktop_paths.py -q`; confirm failures.
- [ ] Refactor `engine.py` path block. Keep module import side effects limited to resolving paths and loading config.
- [ ] Run the new test file, then `python -m pytest -q`, `ruff check engine.py tests/test_desktop_paths.py`, and `python -m py_compile engine.py`.
- [ ] Commit: `engine: resolve config and logs from writable data root`

---

### Task 2: Session/undo/model paths and legacy GGUF migration

**Files:**
- Modify: `engine.py` (`SESSION_DIR`, `UNDO_DIR`, `_llamacpp_gguf_paths`, `_llamacpp_model_dir`, `download_llamacpp_model`, `ensure_llamacpp_server`, new migration helpers)
- Modify: `server/main.py` startup hook (start migration thread)
- Test: `tests/test_desktop_model_paths.py` (create)

**Interfaces:**
- `engine.SESSION_DIR: Path = USER_DATA_DIR / "sessions"`
- `engine.UNDO_DIR: Path = USER_DATA_DIR`
- `engine.UNDO_LOG_FILE: Path = UNDO_DIR / "undo_log.jsonl"`
- `engine.LEGACY_MODELS_DIR: Path = Path.home() / ".cache" / "ai-media-renamer" / "models"`
- `engine.start_model_migration() -> None` — idempotent background starter.
- `engine.is_model_migration_running() -> bool`
- `engine.wait_for_model_migration(timeout: float = 300) -> bool`
- `engine.migrate_llamacpp_models() -> list[Path]` — returns destination paths moved.
- `engine.migrate_llamacpp_paths() -> bool`
- `engine._move_model_file(src: Path, dst: Path) -> Path` — atomic same-volume or cross-volume.

**Behavior:**
- `_llamacpp_model_dir()` returns configured `model.llamacpp.model_dir` if set; otherwise `LLAMACPP_MODELS_DIR`. `_llamacpp_gguf_paths()` and `download_llamacpp_model()` use it.
- Migration runs only when frozen or `AMR_DATA_DIR` is set; no-op in source mode.
- Move `*.gguf`, `*.mmproj`, and files whose names contain `mmproj` (case-insensitive). Skip when destination exists; log each moved/skipped path.
- Same volume: `os.replace`. Cross-volume/`OSError`: copy source → `<dst>.part`, `flush`, `fsync`, close, `os.replace(part, dst)`, then delete source. On failure leave source and delete the `.part` when possible; never overwrite and never leave a truncated destination.
- `migrate_llamacpp_paths()`: if `setup.json` has `onboarded: true`, config `gguf_path` is empty, and a catalog GGUF exists under `LLAMACPP_MODELS_DIR`, set `gguf_path` (and `mmproj_path` when present) and call `engine.save_config()`.
- `start_model_migration()` sets a flag, starts one daemon thread, and clears the flag in `finally`. `wait_for_model_migration` waits at most the timeout and returns False on timeout.
- `ensure_llamacpp_server()` and `download_llamacpp_model()` call `wait_for_model_migration()` first; on timeout raise/return with `"models are still being migrated"`.
- `server/main.py` startup calls `engine.start_model_migration()` inside the existing try/except.

**Steps:**
- [ ] Write failing tests:
  - `test_session_undo_paths_use_user_data_dir`
  - `test_model_dir_defaults_to_user_models`
  - `test_model_dir_honors_config_override`
  - `test_gguf_paths_and_download_agree`
  - `test_migration_source_mode_is_noop`
  - `test_migration_moves_gguf_and_mmproj`
  - `test_migration_skips_existing_destination`
  - `test_cross_volume_copy_uses_part_and_keeps_source_on_failure` (monkeypatch `os.replace`/`shutil.copyfileobj` to raise on the first attempt)
  - `test_migration_never_truncates_existing_destination`
  - `test_migrate_paths_repairs_empty_config` (monkeypatch `save_config`)
  - `test_wait_for_migration_timeout`
  - `test_ensure_server_waits_for_migration` (monkeypatch `_llamacpp_server_running`/`wait_for_model_migration`)
- [ ] Run `python -m pytest tests/test_desktop_model_paths.py -q`; confirm failures.
- [ ] Implement helpers and update both model path consumers.
- [ ] Run new tests, full `pytest`, `ruff check engine.py server/main.py tests/test_desktop_model_paths.py`, `py_compile` both.
- [ ] Commit: `engine: unify model paths and migrate legacy GGUF cache safely`

---

### Task 3: Binary resolution, llama-server lifecycle, and runtime install

**Files:**
- Modify: `engine.py` (`_resolve_binary_path`, `ensure_llamacpp_server`, new `stop_llamacpp_server`, module lock)
- Modify: `bootstrap.py` (`CACHE_DIR`, `BIN_DIR`, `_install_llamacpp_runtime`, remove `_add_to_user_path` calls)
- Test: `tests/test_desktop_binaries.py` (create)

**Interfaces:**
- `engine._resolve_binary_path(name: str) -> str | None`
- `engine.stop_llamacpp_server() -> bool`
- `engine._LLAMACPP_LOCK: threading.Lock`
- `engine._llamacpp_proc: subprocess.Popen | None`
- `bootstrap.CACHE_DIR = engine.USER_DATA_DIR / "cache"`
- `bootstrap.BIN_DIR = engine.USER_DATA_DIR / "bin"`

**Behavior:**
- Resolution order: `USER_DATA_DIR/bin/<name>`, then `.exe`, then `_MEIPASS/bin/<name>`/`.exe`, then `shutil.which`.
- `ensure_llamacpp_server()` acquires `_LLAMACPP_LOCK`; rechecks running; waits for migration; stores the spawned `Popen` in `_llamacpp_proc`; closes the log handle only after spawn.
- `stop_llamacpp_server()` terminates/kills only the owned `_llamacpp_proc`; clears it; returns True when it stopped a process.
- Remove `_add_to_user_path()` calls from setup paths (runtime, exiftool, ffmpeg). The function may remain for compatibility, but setup must not mutate PATH.
- `_install_llamacpp_runtime()` copies **every file** from the directory containing the extracted `llama-server.exe` into `BIN_DIR` recursively; preserve relative subdirectories; `copy2`.
- After copy, verify every required pattern exists: `llama-server.exe`, `llama-server-impl.dll`, `llama.dll`, `ggml*.dll`, `mtmd.dll`, `libomp*.dll`. Raise a clear error listing missing files; do not report success. Keep the existing download/checksum flow and retry loop.

**Steps:**
- [ ] Write failing tests:
  - `test_binary_prefers_user_bin`
  - `test_binary_accepts_exe_suffix`
  - `test_binary_falls_back_to_meipass`
  - `test_binary_falls_back_to_path`
  - `test_stop_server_terminates_owned_process`
  - `test_stop_server_noop_when_not_owned`
  - `test_ensure_server_is_locked` (two threads, one spawn)
  - `test_runtime_install_copies_all_adjacent_dlls` (fake zip/extract dir)
  - `test_runtime_install_fails_when_impl_dll_missing`
  - `test_bootstrap_bin_follows_amr_data_dir`
- [ ] Run `python -m pytest tests/test_desktop_binaries.py -q`; confirm failures.
- [ ] Implement, including a small helper `_copy_llamacpp_runtime_tree(src_dir, bin_dir) -> list[Path]` so it is unit-testable without Tk.
- [ ] Run new tests, full `pytest`, `ruff check engine.py bootstrap.py tests/test_desktop_binaries.py`, `py_compile` both.
- [ ] Commit: `bootstrap: install full llama.cpp runtime and resolve user binaries`

---

### Task 4: Desktop token boundary, health, status, and shutdown

**Files:**
- Create: `server/desktop.py`
- Create: `server/routes/desktop.py`
- Modify: `server/main.py`
- Modify: `server/routes/__init__.py`
- Modify: `server/routes/analysis.py`
- Modify: `server/routes/commit.py`
- Modify: `server/routes/models.py`
- Modify: `server/deps.py`
- Test: `tests/test_desktop_security.py` (create)
- Test: `tests/test_desktop_status.py` (create)

**Interfaces:**
- `server.desktop.DESKTOP_TOKEN: str` = `os.environ.get("AMR_DESKTOP_TOKEN", "").strip()`
- `server.desktop.desktop_mode() -> bool`
- `server.desktop.bearer_token(request) -> str | None`
- `server.desktop.ws_token_ok(token: str | None) -> bool`
- `server.desktop.host_allowed(request) -> bool`
- `server.desktop.origin_allowed(request) -> bool`
- `server.desktop.is_desktop_request(path: str, method: str, request) -> bool` (middleware helper)
- `server.deps.set_analysis_running(value: bool)`, `analysis_running() -> bool`
- `server.deps.set_commit_running(value: bool)`, `commit_running() -> bool`
- `server.models_active_downloads() -> bool` (in `server/routes/models.py`)
- `server.routes.desktop.router`:
  - `GET /api/desktop/status` → `{analysis_running, commit_running, model_downloads_running, model_migration_running, setup_running: false, staging_count}`
  - `POST /api/desktop/shutdown` → `{ok: true}` then stop llama-server and exit.

**Behavior:**
- Desktop mode only when `AMR_DESKTOP_TOKEN` is non-empty.
- In desktop mode, every `/api/*` request requires `Authorization: Bearer <token>` (constant-time compare via `secrets.compare_digest`). `/health` is exempt. `/api/auth/token` returns 404 in desktop mode.
- Mutating methods (`POST`, `PUT`, `PATCH`, `DELETE`) require `Host` to be `127.0.0.1:<port>` or `localhost:<port>` and, when an `Origin` header is present, an origin of `http://127.0.0.1:<port>` or `http://localhost:<port>`. Reject with 403.
- WebSocket `/api/analyze/stream` verifies `?token=` when `desktop_mode()`, else the existing LAN `auth.AUTH_ENABLED` check. Keep both paths.
- `/health` returns `{status, version, desktop}`; `desktop` is `desktop_mode()`.
- Desktop mode forces LAN auth off for requests: `server.auth.AUTH_ENABLED` must not enable a second auth path. In `create_app`, when desktop mode, do not install the token issuer; add the desktop middleware. `deps.require_auth` remains a no-op.
- Busy flags:
  - `server/routes/analysis.py`: `run_analysis()` sets `set_analysis_running(True)` at entry and `False` in `finally`; also wrap the `/analyze` background thread and WS thread so a crash clears it. `reset_cancel_event()` stays.
  - `server/routes/commit.py`: set `True` before the commit loop and `False` in its existing `finally`.
  - `server/routes/models.py`: `models_active_downloads()` returns True when any state has `state == "downloading"`; update under `_STATE_LOCK`. Remove the racy `_current_download_name` global by passing name into `_on_progress` via a closure.
  - `setup_running` is always `False` server-side; the shell adds its own child state.
  - `staging_count` = `len(deps.get_active_staging())`.
- `POST /api/desktop/shutdown` calls `engine.stop_llamacpp_server()` in a short background task, flushes, then `os._exit(0)`. Isolate the exit in `server/desktop.py::_exit_process()` so tests can monkeypatch it.
- Middleware must not block `/health`, static assets, or `/api/desktop/status` when the token is correct.

**Steps:**
- [ ] Write failing tests:
  - `test_desktop_mode_requires_token`
  - `test_health_is_unauthenticated`
  - `test_health_reports_desktop`
  - `test_auth_token_endpoint_is_404_in_desktop`
  - `test_wrong_token_rejected`
  - `test_correct_token_accepted`
  - `test_mutating_request_rejects_foreign_origin`
  - `test_mutating_request_rejects_foreign_host`
  - `test_ws_rejects_missing_desktop_token` (or test `ws_token_ok` directly)
  - `test_ws_accepts_desktop_token`
  - `test_status_shape_and_busy_flags`
  - `test_status_requires_token`
  - `test_analysis_flag_cleared_on_exception`
  - `test_commit_flag_cleared_on_exception`
  - `test_model_downloads_running`
  - `test_shutdown_stops_llama_and_exits` (monkeypatch `_exit_process`)
- [ ] Run both new test files; confirm failures.
- [ ] Implement `server/desktop.py`, `server/routes/desktop.py`, middleware registration, and busy flags.
- [ ] Run new tests, full `pytest`, `ruff check` all changed files, `py_compile` all changed `.py`.
- [ ] Commit: `server: add desktop token boundary and status endpoint`

---

### Task 5: SPA fallback for client routes

**Files:**
- Modify: `server/main.py`
- Test: `tests/test_spa_fallback.py` (create)

**Interfaces:**
- `server.main.SPAStaticFiles(StaticFiles)` with `async def get_response(self, path: str, scope) -> Response`.

**Behavior:**
- Serve `index.html` for unknown non-API paths without a file extension (`/settings`, `/analysis`, nested client routes).
- Return 404 for missing assets with a suffix (`/assets/missing.js`) and for `/api/*`.
- Do not shadow real files.
- Preserve `html=True` behavior for `/`.

**Steps:**
- [ ] Write failing tests with `TestClient` and a temporary dist directory containing `index.html` and `assets/app.js`:
  - `test_root_serves_index`
  - `test_client_route_serves_index`
  - `test_missing_asset_returns_404`
  - `test_api_route_wins_over_spa`
- [ ] Run `python -m pytest tests/test_spa_fallback.py -q`; confirm failures.
- [ ] Implement `SPAStaticFiles`; mount it only when `_DIST.is_dir()`.
- [ ] Run new tests, full `pytest`, `ruff check server/main.py tests/test_spa_fallback.py`, `py_compile server/main.py`.
- [ ] Commit: `server: add SPA fallback for client-side routes`

---

### Task 6: `desktop_backend.py` entry point and setup flags

**Files:**
- Create: `desktop_backend.py`
- Modify: `bootstrap.py` (`main`, `_launch_app`, `_finish_setup`)
- Test: `tests/test_desktop_entrypoint.py` (create)

**Interfaces:**
- `desktop_backend.main(argv: list[str] | None = None) -> int`
- `desktop_backend._configure_windowed_stdio() -> None`
- `desktop_backend._run_smoke_test(host: str, port: int) -> int`
- `bootstrap.main(argv: list[str] | None = None) -> int`
- `bootstrap._finish_setup(win, no_launch: bool) -> int`
- `bootstrap._launch_app(win) -> None` (source users only; starts `launch.py`, no pywebview)

**Flags:**
- `--host` (default `127.0.0.1`), `--port` (required for normal desktop run; default 8000 for dev)
- `--setup` — run Tk wizard with `--no-launch --no-update-check`; return its code.
- `--mark-onboarded` — if `setup.json` is missing or `onboarded` false, `save_setup_profile(onboarded=True)` preserving existing profile; return 0.
- `--no-launch` — setup must not start the app.
- `--no-update-check` — skip the setup update check.
- `--smoke-test` — start uvicorn in-process on the given port, poll `/health` up to 30s, set `should_exit`, join, return 0/1.
- No unknown flags accepted (argparse exit 2).

**Behavior:**
- At the very top of `desktop_backend.py`, before importing `engine` or `server`, call `_configure_windowed_stdio()`: if `sys.stdout`/`sys.stderr` is `None`, open `<data_root>/logs/backend-process.log` in append, line-buffered, and assign both. Determine `<data_root>` without importing engine: `AMR_DATA_DIR` or `%APPDATA%/ai-media-renamer`.
- Normal mode: `uvicorn.run("server.main:app", host=args.host, port=args.port, log_level="warning", access_log=False)` and return 0.
- `--setup` calls `bootstrap.main(["--setup", "--no-launch", "--no-update-check"])`; do not call `_launch_app`.
- `bootstrap.main` takes `argv` (default `sys.argv[1:]`), returns int, and has no top-level `sys.exit` except `if __name__ == "__main__": sys.exit(main())`.
- All setup exits (`skipped`, plan declined, server start failure, success) go through `_finish_setup`: close window; if `no_launch`, return 0; otherwise `_launch_app` and return 0. Failure returns 1.
- `_launch_app` removes `webview`/`pywebview`; it spawns `[sys.executable, BASE_DIR/"launch.py"]` with `CREATE_NO_WINDOW`, logs, closes the wizard, and returns. It must not terminate the child.
- Keep `--no-gui` headless behavior; route it through the same return-code contract.
- `--mark-onboarded` uses `engine.load_setup_profile`/`save_setup_profile` and must not overwrite an existing profile.

**Steps:**
- [ ] Write failing tests:
  - `test_argparse_rejects_unknown_flag`
  - `test_mark_onboarded_creates_profile`
  - `test_mark_onboarded_preserves_existing_profile` (monkeypatch `engine.save_setup_profile`)
  - `test_setup_calls_bootstrap_with_no_launch` (monkeypatch `bootstrap.main`)
  - `test_setup_failure_returns_nonzero`
  - `test_smoke_test_returns_nonzero_when_health_never_ok` (monkeypatch health probe)
  - `test_windowed_stdio_redirects_none` (monkeypatch `sys.stdout`/`sys.stderr` and `AMR_DATA_DIR`)
  - `test_bootstrap_main_no_launch_returns_zero` (monkeypatch `SetupWindow`/`_finish_setup`)
  - `test_launch_app_does_not_import_pywebview`
- [ ] Run `python -m pytest tests/test_desktop_entrypoint.py -q`; confirm failures.
- [ ] Implement entry point and refactor `bootstrap.main` exits conservatively.
- [ ] Run new tests, full `pytest`, `ruff check desktop_backend.py bootstrap.py tests/test_desktop_entrypoint.py`, `py_compile` both.
- [ ] Commit: `desktop: add windowed backend entry point and setup-only mode`

---

### Task 7: Tauri scaffold, backend lifecycle, and release startup

**Files:**
- Create: root `package.json`
- Create: `src-tauri/Cargo.toml`, `src-tauri/build.rs`, `src-tauri/tauri.conf.json`
- Create: `src-tauri/src/main.rs`, `src-tauri/src/lib.rs`, `src-tauri/src/backend.rs`, `src-tauri/src/settings.rs`, `src-tauri/src/commands.rs`
- Create: `src-tauri/capabilities/default.json`, `src-tauri/capabilities/remote.json`
- Create: `src-tauri/splash/index.html`
- Create: `src-tauri/icons/*` (generate from `icon.ico`)
- Modify: `frontend/vite.config.ts`
- Modify: `frontend/package.json`

**Interfaces (Rust):**
- `backend::pick_port() -> std::io::Result<u16>`
- `backend::generate_token() -> String`
- `backend::resolve_data_dir() -> PathBuf`
- `backend::filter_path_args(args: &[String]) -> Vec<PathBuf>`
- `backend::version_compatible(shell: &str, backend: &str, debug: bool) -> bool`
- `backend::spawn_backend(port: u16, token: &str) -> Result<BackendProcess, String>`
- `backend::wait_for_health(port: u16, timeout: Duration) -> Result<Health, String>`
- `BackendProcess { child: Child, job: JobHandle }` with `stop() -> Result<(), String>`
- `commands::desktop_ready(app: AppHandle) -> Result<(), String>`
- `commands::pending_paths(state: State<'_, ShellState>) -> Vec<String>`
- `commands::release_page_url() -> String`

**Config requirements:**
- `productName: "AI Media Renamer"`; `version: "2.2.0"`; identifier `com.abdulmusawwir.ai-media-renamer`.
- `build.frontendDist: "../src-tauri/splash"`; `build.devUrl: "http://127.0.0.1:5173"`.
- `app.windows` main window label `main`, title, 1280×800, min 960×640, `visible: false`.
- `bundle.active: true`, `targets: ["nsis"]`, `createUpdaterArtifacts: true`, `resources: {"../dist/AIMediaRenamerBackend/": "AIMediaRenamerBackend/"}`.
- `plugins.updater.windows.installMode: "passive"`; updater endpoints include the GitHub `latest.json`; public key placeholder replaced by the generated key in Task 10.
- `plugins.single-instance` is registered before other plugins.
- `security.csp` remains null for v1 because the SPA is same-origin; remote capability is restricted to `http://127.0.0.1:*`.
- NSIS: per-user install, no admin, `installMode` from updater config.

**Startup behavior:**
1. Register single-instance plugin first; on second launch, focus/show main window and queue any existing file paths.
2. Resolve `<data_root>` from `AMR_DATA_DIR` or `%APPDATA%/ai-media-renamer`; inherit/forward `AMR_DATA_DIR` to backend/setup.
3. In debug (`cfg!(debug_assertions)`): do **not** spawn backend, generate token, create splash, or assign a secondary window. Load `devUrl` directly; frontend runs in browser-mode semantics. Backend is started separately with `npm run dev:backend`.
4. In release: create splash from local `splash/index.html`, hidden from taskbar; pick port (bind `127.0.0.1:0`, retry ×3); generate 64-char token; spawn `AIMediaRenamerBackend.exe` with `--host 127.0.0.1 --port <port>`, env `AMR_DESKTOP_TOKEN`, cwd `<data_root>`; create Job Object with `KILL_ON_JOB_CLOSE` and assign child; capture stdout/stderr to `<data_root>/logs/backend-process.log`.
5. Poll `/health` 250ms up to 30s; require `status == "ok"`; release requires version equality; debug logs mismatch and continues; `AMR_SKIP_VERSION_CHECK=1` only honored in debug.
6. Create main window hidden/`visible:false`; inject `window.__AMR_DESKTOP__=true`, `__AMR_DESKTOP_TOKEN__`, `__AMR_DESKTOP_PORT__`, `__AMR_DESKTOP_VERSION__` via `initialization_script`; `desktop_ready` navigates main to `http://127.0.0.1:<port>`, shows it, closes splash; 10s fallback shows window and logs.
7. On startup failure, show native dialog Retry / Open Logs / Quit; stop process and job; no orphan llama-server.
8. Free port retry: if spawn or health fails with a bind/early-exit error, retry up to 3 times with a new port/token.
9. On exit, stop backend via `POST /api/desktop/shutdown` (5s), then kill; close Job Object.
10. Logs: shell log `<data_root>/logs/desktop-shell.log`; backend process log as above.

**Dev setup:**
- `frontend/vite.config.ts`: `server.host = "127.0.0.1"`; proxy target default `http://127.0.0.1:8000` for both server and preview.
- Root scripts: `"tauri": "tauri"`, `"dev:backend": "python desktop_backend.py --host 127.0.0.1 --port 8000 --no-launch --no-update-check"`.
- Frontend deps: `@tauri-apps/api`, `@tauri-apps/plugin-dialog`, `@tauri-apps/plugin-process`, `@tauri-apps/plugin-updater`.
- Root devDeps: `@tauri-apps/cli`.

**Steps:**
- [ ] Scaffold files. Use `npm run tauri icon icon.ico` to generate icons.
- [ ] Add Rust unit tests in `backend.rs`:
  - `test_filter_path_args_keeps_existing_media`
  - `test_filter_path_args_ignores_dirs`
  - `test_version_compatible_exact`
  - `test_version_compatible_mismatch_debug`
  - `test_resolve_data_dir_override` (env)
  - `test_generate_token_length`
- [ ] Add test-only health parser test.
- [ ] Run `cargo fmt`, `cargo clippy -- -D warnings`, `cargo test` in `src-tauri/`. Then `npm run build` in `frontend/`.
- [ ] Manual release smoke: `npm run tauri build -- --debug` is not a release build; verify dev mode loads Vite with no splash. Use a local resource layout to verify backend spawn/health if available.
- [ ] Commit: `desktop: scaffold Tauri shell and backend lifecycle`

---

### Task 8: Tray, single-instance UX, safe quit, and shell preferences

**Files:**
- Modify: `src-tauri/src/lib.rs`
- Modify: `src-tauri/src/settings.rs`
- Modify: `src-tauri/src/commands.rs`
- Modify: `src-tauri/src/tray.rs` (create if split)
- Modify: `src-tauri/capabilities/default.json`
- Test: `src-tauri/src/settings.rs` unit tests

**Interfaces:**
- `settings::ShellSettings { close_to_tray: bool }` (default `true`)
- `settings::load(app: &AppHandle) -> ShellSettings`
- `settings::save(app: &AppHandle, settings: &ShellSettings) -> Result<(), String>`
- `commands::get_shell_settings(app) -> ShellSettings`
- `commands::set_close_to_tray(app, value: bool) -> Result<(), String>`
- `commands::open_logs(app) -> Result<(), String>`
- `commands::open_data_folder(app) -> Result<(), String>`
- `commands::restart_app(app)`
- `commands::quit_app(app) -> Result<(), String>`
- `commands::get_backend_status() -> Result<DesktopStatus, String>`

**Behavior:**
- Tray menu, in order: Show, Check for Updates, Setup & Dependencies, Open Logs, Open Data Folder, Quit. Double-click shows main.
- Close button: if `close_to_tray`, hide window and show a one-time notification (tray balloon or native notification) explaining how to quit. If false, quit safely.
- First launch with no `desktop.json`: default true; create file lazily.
- `desktop.json` lives in Tauri app config dir, not `<data_root>`. Malformed file falls back to defaults and logs.
- Quit/setup/update guards call `GET /api/desktop/status` with the token. If `analysis_running || commit_running || model_downloads_running || model_migration_running || setup_running`, show “An operation is still running” with Continue/Stay. If backend is unreachable, treat as not busy.
- `quit_app`: set `quitting` atomic; call shutdown; wait 5s; kill; close job; exit.
- `restart_app`: stop backend; relaunch current exe with same args; exit.
- `run_setup` (tray): stop backend; spawn `AIMediaRenamerBackend.exe --setup --no-launch --no-update-check` from resources with cwd `<data_root>` and inherited `AMR_DATA_DIR`; if exit 0 or user continues, restart app. If non-zero, native Retry/Continue/Quit.
- `Open Logs` opens `<data_root>/logs`; `Open Data Folder` opens `<data_root>`.
- Version shown in the UI comes from `/health`, not a hardcoded string.

**Steps:**
- [ ] Write failing tests in `settings.rs`: default true, missing file, malformed file, round-trip.
- [ ] Write a Rust test for the status guard decision using a pure helper `fn should_block(status: &DesktopStatus) -> bool`.
- [ ] Implement tray, close handling, preferences, commands, and guards.
- [ ] Run `cargo fmt`, `cargo clippy -- -D warnings`, `cargo test`.
- [ ] Manual: close-to-tray, tray Show/Quit, second instance focus; no orphan process in Task Manager.
- [ ] Commit: `desktop: add tray, close-to-tray, and safe lifecycle commands`

---

### Task 9: React desktop bridge, native pickers, and drag/drop

**Files:**
- Create: `frontend/src/desktop/index.ts`
- Create: `frontend/src/components/DesktopBridge.tsx`
- Modify: `frontend/src/store.ts`
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/main.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/pages/Analysis.tsx`
- Modify: `frontend/src/pages/Settings.tsx`
- Test: `npm run build` + manual dev smoke

**Interfaces:**
- `desktop.isDesktop: boolean`
- `desktop.token: string | null`
- `desktop.port: number | null`
- `desktop.version: string | null`
- `desktop.invoke<T>(cmd: string, args?: Record<string, unknown>): Promise<T>`
- `desktop.listen<T>(event: string, cb: (payload: T) => void): Promise<() => void>`
- `desktop.pickFiles(): Promise<string[]>`
- `desktop.pickFolder(): Promise<string | null>`
- `installDesktopDropHandler(onPaths: (paths: string[]) => void): Promise<() => void>`
- `store`: `incomingPaths: string[]`, `pushIncomingPaths(paths)`, `clearIncomingPaths()`.

**Behavior:**
- `desktop/index.ts` dynamically imports Tauri APIs only when `window.__AMR_DESKTOP__` is true; browser builds must not require Tauri modules at runtime.
- In `main.tsx`, if desktop, assign `_cachedToken = window.__AMR_DESKTOP_TOKEN__` before the first `getAnalysisToken()` call (export a setter `setDesktopToken` or initialize from `window` in `client.ts`). Do not call `/api/auth/token` in desktop mode.
- `DesktopBridge`:
  - on mount, `getCurrentWebview().onDragDropEvent`; on `drop`, filter existing files and push to store; on `over`, prevent default.
  - load pending paths on mount; listen `desktop://open-paths`; call `desktop_ready` once after the app renders.
  - load shell settings; expose close-to-tray toggle in Settings.
- `Analysis.tsx`:
  - `useDropzone({ noClick: isDesktop, onDrop })`; desktop drop comes only from Tauri, so avoid double-adding.
  - Native “Choose files” opens `pickFiles()` and feeds files; also add per-asset “Choose file” when file input cannot supply paths.
  - Native “Choose folder” sets the analysis folder.
  - Browser mode keeps existing HTML5 drop/browse behavior.
- `Settings.tsx`:
  - “Close to tray” toggle (desktop only) via `set_close_to_tray`.
  - “Open logs” / “Open data folder” (desktop only).
- `App.tsx` header version uses `/health` response (add `getHealth()` to client and a query/hook `useHealth`), fallback to `config.version`, never `v2.0.0`.
- `client.ts` adds `getHealth()` and does not overwrite `_cachedToken` when desktop token is set.
- No Tauri calls when `isDesktop` is false; no console errors in browser mode.

**Steps:**
- [ ] Implement bridge and state.
- [ ] In dev: start `npm run dev:backend` in one terminal, `npm run tauri dev` in another; verify SPA loads at `127.0.0.1:5173`, no token/splash, REST/WS work.
- [ ] Verify browser mode (`npm run dev` only) still loads and all pages work.
- [ ] Verify native picker + drag/drop add files/folders without duplicates; verify `/settings` reload in browser mode hits SPA fallback.
- [ ] Run `npm run build`; fix TS errors.
- [ ] Commit: `frontend: add desktop bridge, native pickers, and file drops`

---

### Task 10: In-app updater UI and install flow

**Files:**
- Modify: `frontend/src/desktop/index.ts`
- Modify: `frontend/src/components/DesktopBridge.tsx`
- Modify: `frontend/src/pages/Settings.tsx`
- Modify: `src-tauri/capabilities/default.json`
- Modify: `src-tauri/capabilities/remote.json`
- Modify: `src-tauri/tauri.conf.json` (pubkey, endpoints)
- Test: manual update N→N+1, plus `npm run build`

**Interfaces:**
- `desktop.checkForUpdate(): Promise<DesktopUpdate | null>`
- `desktop.downloadAndInstall(update, onProgress): Promise<void>`
- `desktop.relaunch(): Promise<void>`
- `DesktopUpdate { version, notes, date }`
- UI states: `idle | checking | up-to-date | available | downloading | installing | error`.

**Behavior:**
- Desktop: use `@tauri-apps/plugin-updater` `check()`, render version + notes in Settings/About, “Install update” calls `update.downloadAndInstall((event) => ...)`, then `install({ restartAfterInstall: true })` via the updater API; do not rely on a finish page. `tauri.conf.json` sets `installMode: "passive"`.
- Browser mode: no updater calls; show “Updates are managed by the desktop app” and a release-page link.
- Errors (offline, signature invalid, download failure) leave app usable and show a retry action.
- Guard: before install, call `/api/desktop/status`; if analysis/commit/download/migration/setup active, show the safe-dialog; only proceed on explicit “Continue”.
- After install/relaunch, verify N→N+1 and config/models/sessions survive.
- Remote capability allows updater/process only from `http://127.0.0.1:*`; no wildcard remote origin.
- `Check for Updates` tray item triggers the same UI/command without requiring Settings to be open (emit `desktop://check-updates`).

**Steps:**
- [ ] Generate updater key with `npm run tauri signer generate -- -w ~/.tauri/ai-media-renamer.key`; store public key in `tauri.conf.json`; document private key as a CI secret (`TAURI_SIGNING_PRIVATE_KEY`).
- [ ] Implement update UI and progress.
- [ ] Build a 2.2.0 local N, bump to 2.2.1, build N+1, host `latest.json` + `.nsis.zip`/`.sig` locally, and verify update install + relaunch. If `/R` is not honored on the pinned Tauri version, add the documented NSIS post-install hook fallback.
- [ ] Verify signature failure and offline failure leave the app running.
- [ ] Run `npm run build`; `cargo clippy -- -D warnings`; `cargo test`.
- [ ] Commit: `desktop: add signed in-app update flow`

---

### Task 11: Backend build, version sync, and CI release pipeline

**Files:**
- Create: `scripts/check_versions.py`
- Create: `scripts/build-desktop.ps1`
- Create: `build_desktop.spec`
- Delete: `build_v2.spec` (after workflow switch)
- Modify: `.github/workflows/build.yml`
- Modify: `VERSION`, `engine.py`, `pyproject.toml`, `frontend/package.json`, root `package.json`, `src-tauri/Cargo.toml`, `src-tauri/tauri.conf.json`

**Interfaces:**
- `scripts/check_versions.py --tag v2.2.0` exits 0 when all versions match; prints every mismatch; validates `latest.json` version/URL/signature fields when present.
- `scripts/build-desktop.ps1`:
  1. `npm ci` in `frontend/`; `npm run build`.
  2. `pyinstaller build_desktop.spec --noconfirm`.
  3. `npm ci` at repo root.
  4. `npm run tauri build`.
  5. Assert outputs: `src-tauri/target/release/bundle/nsis/*.exe`, `*.sig`, `latest.json`.

**`build_desktop.spec`:**
- onedir (`COLLECT`), name `AIMediaRenamerBackend`, `console=False`, `upx=False`.
- entry `desktop_backend.py`.
- datas: `frontend/dist`, `config.default.json`, `icon.ico`, `bootstrap.py` if needed by hidden imports.
- hidden imports: `engine`, all `server`/`server.routes`, `uvicorn`, `fastapi`, `starlette`, `jwt`, `pydantic`, `openai`, `requests`, `numpy`, `PIL`, `multipart`, `bootstrap`, `tkinter`, `imagehash`, `scipy`, and analysis document/audio stack (`faster_whisper`, `ctranslate2`, `av`, `pdfplumber`, `docx`, `openpyxl`, `pptx`, `huggingface_hub`, `tokenizers`).
- excludes: `pandas`, `plotly`, `torch`, `streamlit`, `pywebview`, `rich`, `pyarrow`, tests.
- Verify onedir layout: `AIMediaRenamerBackend.exe`, `_internal/server/...`, `_internal/frontend/dist/index.html`.

**Version bump:**
- Set all version files to `2.2.0`; `VERSION` has no `v` prefix; tag is `v2.2.0`.

**CI (`.github/workflows/build.yml`):**
- Trigger only `push.tags: ["v*"]`; `permissions.contents: write`.
- Windows runner; Python 3.12; Node 20 with frontend and root npm caches; Rust stable + `Swatinem/rust-cache`.
- Steps: checkout → version check (`python scripts/check_versions.py --tag $env:GITHUB_REF_NAME`) → frontend `npm ci && npm run build` → `pip install -r requirements.txt pyinstaller` → `pyinstaller build_desktop.spec --noconfirm` → backend smoke with temp `AMR_DATA_DIR` and `--smoke-test` → root `npm ci` → `tauri-action` with `TAURI_SIGNING_PRIVATE_KEY`/password → upload NSIS `.exe`, `.sig`, and `latest.json`.
- Smoke test: `Start-Process dist/AIMediaRenamerBackend/AIMediaRenamerBackend.exe -ArgumentList '--host','127.0.0.1','--port','8123','--smoke-test'`; wait; require it to exit 0; on failure print backend-process.log.
- `tauri-action` must publish `latest.json`, not the plain exe only.

**Steps:**
- [ ] Use Test-Driven Development for `check_versions.py`: write `tests/test_check_versions.py` with temp version files and one mismatch case; run failing; implement; pass.
- [ ] Implement spec/scripts; build locally on Windows; verify onedir layout and smoke test.
- [ ] Run `python -m pytest`, `ruff check`, `npm run build`.
- [ ] Commit: `build: package onedir backend and NSIS installer`

---

### Task 12: Documentation, audit sync, and release prep

**Files:**
- Modify: `README.md`
- Modify: `AGENTS.md` (desktop commands/runtime note)
- Modify: `task.md` (current focus, next micro-task)
- Modify: `audit.md` (resolve findings #18; note new desktop surfaces)
- Modify: `docs/superpowers/specs/2026-11-08-tauri-desktop-design.md` only if implementation deviates (record deviation)
- Test: no new tests; run full verification gate

**Behavior/Docs:**
- README install section: NSIS per-user install, SmartScreen “Unknown publisher” because unsigned, uninstall preserves `%APPDATA%\ai-media-renamer`, data-root override, tray/close-to-tray, setup from tray, update flow, browser/CLI still supported.
- Document generated updater key handling and CI secrets; never commit the private key.
- Document `npm run dev:backend` + `npm run tauri dev` workflow.
- `audit.md` mark runtime DLL bug resolved by Task 3; add any new orphaned code/divergence found.
- `task.md` points at the next unstarted task/release step.

**Steps:**
- [ ] Run `python -m pytest` and confirm baseline + new tests pass.
- [ ] Run `ruff check .`; `python -m py_compile` every changed Python file.
- [ ] Run `cargo fmt --check`, `cargo clippy -- -D warnings`, `cargo test` in `src-tauri/`.
- [ ] Run `npm run build` in `frontend/` and `npm run tauri build` if resources are staged.
- [ ] Manually verify acceptance criteria: fresh install, setup, SPA/REST/WS, tray, second instance, drag/drop, `/settings` reload, version gate, quit/setup/update guards, legacy model migration, 2.1.0→2.2.0 data survival.
- [ ] Commit: `docs: document desktop install, updates, and data locations`

---

## Verification Gate (before any task commit)

Run the relevant subset, then all of it before release:

```powershell
python -m pytest -q
ruff check .
python -m py_compile <changed-python-files>
cd frontend; npm run build
cd src-tauri; cargo fmt --check; cargo clippy -- -D warnings; cargo test
```

Then check `audit.md` for new bugs/divergences and update `task.md`. No task is complete until these pass (or the failure is recorded as a blocker, not skipped).

## Manual Acceptance Matrix

| # | Scenario | Expected |
|---|---|---|
| 1 | Fresh Windows user, no `%APPDATA%` data, no tools | Installer runs; setup opens; after setup the app opens; config seeded; no install-dir writes |
| 2 | Launch with `AMR_DATA_DIR=D:\tmp\amr` | Config/logs/setup/sessions/undo/models/shell logs all under `D:\tmp\amr`; CLI/source config unaffected |
| 3 | Kill backend while app runs | Shell shows retry/logs/quit; no orphan `llama-server` |
| 4 | Quit during analysis/commit/download/migration | Guard warns; Stay keeps operation; Continue exits cleanly |
| 5 | Drag file onto window | Adds path once; native picker works; no double-add |
| 6 | Second launch, no args | First window focuses; no second instance |
| 7 | Second launch with file | First window focuses and adds file; folders ignored |
| 8 | Reload on `/settings` | SPA loads (no 404) |
| 9 | 2.1.0→2.2.0 with model in `~/.cache` | Model moved, not re-downloaded; analysis finds it |
| 10 | Update N→N+1 | Check, notes, download, install, relaunch; config/models/sessions survive; no finish-page dependency |
| 11 | Offline/signature-invalid update | App stays usable; clear retry |
| 12 | `tauri dev` | Vite HMR at `127.0.0.1:5173`; backend separate on 8000; no token/splash/sidecar |
| 13 | Browser mode + CLI | Existing flows still work |
| 14 | Uninstall | `%APPDATA%\ai-media-renamer` preserved; README explains removal |
