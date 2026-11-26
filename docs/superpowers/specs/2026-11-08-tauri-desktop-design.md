# AI Media Renamer - Tauri v2 Desktop Shell Design

- Status: approved
- Date: 2026-11-08
- Approved: 2026-11-10
- Branch: `feat/tauri-desktop`
- Scope: Windows desktop packaging and shell for the existing React + FastAPI app
- Not in scope: AI pipeline changes, new rename features, macOS/Linux packaging

## 1. Summary

Wrap the existing React SPA and FastAPI backend in a Tauri v2 Windows shell. The shell owns the native window, tray, single-instance behavior, native dialogs, drag/drop, sidecar lifecycle, and GitHub Releases updater. The backend remains the same FastAPI service and still serves the SPA, but is packaged as a PyInstaller `onedir` resource and launched privately by the shell.

The design deliberately keeps the web app and CLI working. The desktop shell is additive: the browser launcher (`launch.py`), CLI (`cli.py`), and source-mode config remain usable.

## 2. Goals

1. Install with a normal Windows installer, no Python and no browser chrome.
2. Launch into the existing React app with the same REST and WebSocket behavior.
3. Native window, tray, single-instance, native drag/drop and file/folder pickers.
4. First-run setup that installs FFmpeg, ExifTool, llama.cpp, and models without terminal use.
5. In-app update: check, show release notes, download, verify signature, install, relaunch.
6. Keep user data (config, models, sessions, undo, logs) across updates.
7. Preserve the current feature set: analysis, staging, commit, rollback, sessions, models, settings, text/audio/document assets.
8. Keep browser and CLI modes working.

## 3. Non-goals

- No macOS or Linux installers in this phase.
- No MSI, AppX/MSIX, Microsoft Store, or winget packaging.
- No delta updates.
- No silent background installation. The user consents to each install.
- No file associations, Explorer context-menu entries, or deep links.
- No React rewrite of the initial setup wizard in v1 (see section 8).
- No change to the PRD's analysis, naming, metadata, or category behavior.
- No cloud service, telemetry, or crash upload.

## 4. Current-State Findings That Drive the Design

These are facts verified in the repository, not assumptions.

1. `build_v2.spec` builds a single `AIMediaRenamer.exe` from `launch.py`, with `console=True`, and excludes `tkinter`, `faster_whisper`, `ctranslate2`, `onnxruntime`, `av`, `pdfplumber`, `docx`, `openpyxl`, `pptx`, `imagehash`, `huggingface_hub`, `tokenizers`, and others. The shipped exe therefore does not contain the setup wizard or the full analysis stack.
2. `launch.py` starts uvicorn on dual-stack loopback and opens the default browser. It never runs the setup wizard.
3. `bootstrap.py` contains the Tk setup wizard, but the shipped exe does not include or invoke it. This is a PRD divergence.
4. `bootstrap.py:_launch_app()` still tries pywebview and falls back to a browser; pywebview is excluded from the build and is no longer a supported runtime.
5. `bootstrap.py` checks for updates and opens GitHub in a browser. There is no in-app installer.
6. `engine.py` reads and writes `config.json` next to `engine.py` (`CONFIG_PATH`, `load_config`). Under an installed app this can be a read-only or ephemeral install directory.
7. `LOG_DIR = Path(config["logging"]["directory"])` is resolved against the process working directory. Under a desktop shell that is undefined unless the shell controls it.
8. `USER_DATA_DIR`, `SESSION_DIR`, and `UNDO_DIR` already live under `%APPDATA%\ai-media-renamer`, but they ignore a test/portable override.
9. `_resolve_binary_path()` checks only the PyInstaller bundle and `PATH`. The setup wizard installs FFmpeg, ExifTool, and llama.cpp into `%APPDATA%\ai-media-renamer\bin`, which is usually not on `PATH`.
10. `_llamacpp_model_dir()` defaults to `~/.cache/ai-media-renamer/models`, while `LLAMACPP_MODELS_DIR` and `_llamacpp_gguf_paths()` use `%APPDATA%\ai-media-renamer\models`. The setup wizard and the Models page can disagree about where models live.
11. `server/main.py` serves the SPA with `StaticFiles(html=True)`, which does not provide SPA fallback for routes such as `/settings`. A webview reload on a client route can return 404.
12. `server/auth.py` is optional LAN JWT auth, disabled by default. `/api/auth/token` issues a JWT without authentication. It is not a desktop security boundary.
13. `server/routes/updates.py` is a stub returning `update_available: false`. The frontend has no update UI.
14. `frontend/src/pages/Analysis.tsx` uses `react-dropzone`; when the browser does not expose `File.path`, it falls back to `f.name`, which is not a usable server path. Tauri drag/drop must supply full paths.
15. The header version display reads `config.version` (not present) and falls back to `v2.0.0`; it does not use `engine.VERSION`.
16. There is no About page. Settings is a raw JSON config editor.
17. The release workflow runs only on `v*` tags and uploads a raw `AIMediaRenamer.exe`, with no installer, no updater JSON, and no signing.
18. `bootstrap.py:_install_llamacpp_runtime()` extracts the runtime zip but copies only `llama-server.exe` into `BIN_DIR`. The Windows build is a thin launcher plus `llama-server-impl.dll` and other DLLs, so a clean setup can leave a non-working runtime.
19. `projectmem` does not have this repository registered; follow the repository's `AGENTS.md` workflow instead.

## 5. Approaches Considered

| Approach | Result |
|---|---|
| Tauri v2 + Python `onedir` resource + loopback SPA | Chosen. Keeps the existing API/WS and same-origin behavior, supports full Python dependencies, and gives a native shell. |
| Tauri v2 + Python `onefile` as `externalBin` | Rejected. Tauri `externalBin` expects a single target-triple-suffixed executable; onefile extracts to a temp dir and makes model/tool paths and startup unpredictable. |
| Electron + Python sidecar | Rejected. Larger runtime and memory footprint, duplicates the existing web stack, and does not improve the Python lifecycle. |
| Browser + bootstrap updater | Rejected. Does not meet the native-window/tray/installer requirement and leaves the browser chrome and pywebview dead code. |
| Tauri loading local assets and calling the backend cross-origin | Rejected for v1. It forces CORS and WebSocket origin changes, and makes the SPA's relative API client and `BrowserRouter` behavior differ from browser mode. |

## 6. Chosen Architecture

### 6.1 Process Model

```
AI Media Renamer.exe            Tauri shell (Rust)
  |
  |-- WebView2 (main window) --> http://127.0.0.1:<port>  (SPA served by FastAPI)
  |-- splash window ---------> bundled local HTML
  |-- tray + updater + single-instance + native dialogs
  |
  |-- child: AIMediaRenamerBackend.exe (PyInstaller onedir)
        |-- uvicorn / FastAPI on 127.0.0.1:<port>
        |-- engine.py
        |-- child: llama-server.exe on 127.0.0.1:8080
```

- The shell is the only process the user launches.
- The backend listens only on IPv4 loopback. The shell and the SPA use `127.0.0.1`, not `localhost`, to avoid Windows IPv6 ambiguity.
- The SPA is served by the backend. The shell does not bundle a second copy of the SPA; Tauri's `frontendDist` contains only a small splash page.
- The shell passes the port and a per-launch token to the backend. It does not rely on a fixed port.
- The shell runs one backend and one analysis job at a time, matching the current server design.
- Release builds load the backend-served SPA. Debug builds load Vite directly for HMR (section 9.6); the two paths are explicit, not inferred.

### 6.2 Startup Sequence

1. Tauri starts. The single-instance plugin is initialized first.
2. If another instance exists, focus its window, forward any file arguments, and exit this instance.
3. Create the tray icon and menu.
4. Create the splash window (local bundled HTML), hidden from the taskbar.
5. Resolve the data root exactly as the backend does: `AMR_DATA_DIR` if set, otherwise `%APPDATA%\ai-media-renamer`. Read `<data_root>\setup.json`.
   - If missing, or `onboarded` is false, run the setup wizard (section 8).
   - If setup is skipped or fails and the user chooses "Continue", mark onboarding as acknowledged and continue.
   - `AMR_DATA_DIR` is inherited by the backend and setup child, so shell and backend always read the same setup profile.
6. Pick a free loopback port by binding `127.0.0.1:0`, reading the port, and closing the listener. Retry at most 3 times.
7. Generate a per-launch token (two UUIDv4 values, hex-encoded).
8. Spawn `AIMediaRenamerBackend.exe` with `--host 127.0.0.1 --port <port>`, `AMR_DESKTOP_TOKEN=<token>`, and working directory `<data_root>`.
9. Create a Windows Job Object with `KILL_ON_JOB_CLOSE` and assign the backend process. This kills the backend and llama-server if the shell crashes.
10. Poll `GET http://127.0.0.1:<port>/health` every 250 ms for up to 30 seconds. Verify `status == "ok"`.
    - Release builds additionally require the returned engine version to equal the shell version. Debug builds log a mismatch and continue. `AMR_SKIP_VERSION_CHECK=1` is honored only when `cfg!(debug_assertions)` (section 9.5).
11. Create the main window hidden, with `WebviewUrl::External("http://127.0.0.1:<port>")` and an initialization script containing `window.__AMR_DESKTOP__`, `window.__AMR_DESKTOP_TOKEN__`, `window.__AMR_DESKTOP_PORT__`, and `window.__AMR_DESKTOP_VERSION__`.
12. The SPA mounts, its desktop bridge calls the `desktop_ready` command.
13. The shell shows the main window, closes the splash, and starts the auto-update check.
14. If the backend exits or health fails, close the splash, show a native error dialog with Retry, Open logs, and Quit, and clean up the job.

Debug builds replace steps 4-13 with a development flow: they create the main window with `WebviewUrl::External(devUrl)`, do not spawn the backend, do not generate a token, and do not create a splash. The developer runs the backend separately on the fixed Vite proxy target (`127.0.0.1:8000`). See section 9.6.

The splash should not disappear until the SPA is ready, to avoid a white flash. A 10-second fallback shows the main window even if `desktop_ready` is not received, so a frontend error is visible rather than leaving a permanent splash.

### 6.3 Shutdown Sequence

Normal quit (tray Quit, Settings Quit, update install, or close-to-tray disabled):

1. Set `quitting = true` so the close handler does not hide the window.
2. Call `GET /api/desktop/status`. If `analysis_running`, `commit_running`, a model download, a model migration, or setup is active, show the busy confirmation first.
3. Call `POST /api/desktop/shutdown` with the token.
4. The backend calls `engine.stop_llamacpp_server()` (only if it owns the process), then exits after the response is flushed.
5. The shell waits up to 5 seconds. If the child is still alive, terminate it, then close the Job Object.
6. Exit the Tauri process.

Unexpected backend exit:

1. The shell detects the child exit.
2. It shows a native dialog with Restart and Quit.
3. Restart uses the full app restart path, not a partial backend restart, so the SPA gets a fresh port and token.

The Job Object is the final safety net. Even if the shell is killed from Task Manager, the backend and llama-server are killed when the job handle closes.

### 6.4 Single Instance, Tray, and Close Behavior

- `tauri-plugin-single-instance` is initialized before other plugins.
- A second launch shows, restores, and focuses the main window.
- If the second launch has a file argument, the path is queued and emitted to the SPA as `desktop://open-paths`.
- File arguments are accepted only for existing files. Directories are ignored with a user-visible message in v1.
- Paths are canonicalized where possible. Relative paths use the second instance's `cwd`.
- Tray menu:
  - Show AI Media Renamer
  - Check for Updates
  - Setup & Dependencies
  - Open Logs
  - Open Data Folder
  - Quit
- Clicking the tray icon shows the window.
- Closing the window hides it to the tray by default. A first-run native notice explains that analysis continues in the tray.
- Settings has a "Close to tray" toggle. The preference is stored in the shell's own `desktop.json` under the Tauri app config directory; it does not belong in the engine config.
- Tray "Quit" always confirms if `/api/desktop/status` reports an active analysis, commit, model download, migration, or setup; otherwise it quits directly.
- Tray "Check for Updates" shows the window, navigates to Settings > Updates, and triggers an immediate check.
- Tray "Setup & Dependencies" confirms, stops the backend, runs the setup mode, and then restarts the entire app so the SPA gets a consistent port/token.

### 6.5 Drag/Drop and Pickers

- Tauri's native drag/drop is enabled. The SPA listens with `getCurrentWebview().onDragDropEvent()`.
- On `drop`, full Windows paths are added to the analysis file list.
- Directories are not silently expanded in v1; the UI tells the user to use the folder picker or add files.
- In desktop mode, the HTML file input is disabled (`noClick`) because a browser `File` has no filesystem path. A native "Choose files" button uses the Tauri dialog plugin instead.
- In browser mode, `react-dropzone` behavior is unchanged.
- The folder picker keeps its current server-side browser, plus a native "Choose folder" button in desktop mode using `open({ directory: true })`.
- The backend remains responsible for validating paths and extensions.

### 6.6 Update Flow

1. The SPA checks for updates silently after launch if the last check was more than 24 hours ago, and every 24 hours while running.
2. A manual check is available in Settings > Updates and from the tray.
3. The Tauri updater reads `latest.json` from the GitHub Releases latest URL and verifies the minisign signature before installing.
4. If an update is available, the UI shows current version, latest version, release notes, and an "Install update" action. Download is not automatic.
5. Before install, read `/api/desktop/status`:
   - If `analysis_running` or `commit_running`, block and explain.
   - If staged rows exist (`staging_count > 0`), offer "Save session" and "Install anyway".
   - If a setup, model download, or model migration is running, block.
6. Install:
   - Show download progress from the Tauri updater chunk events.
   - On completion, show "Installing. The app will close and reopen."
   - Call the updater with `install({ restartAfterInstall: true })` and configure `plugins.updater.windows.installMode = "passive"`. Tauri v2 exits the app and launches NSIS with `/R`, so the installer relaunches the new version. Do not depend on the NSIS finish page.
   - The Rust updater's before-exit hook stops the backend and llama-server.
   - Phase C verifies the relaunch on a real N to N+1 install before the release workflow is finalized. If `/R` does not relaunch on the pinned Tauri version, add an NSIS post-install launch hook instead of changing this contract.
7. On failure:
   - Signature mismatch: refuse; show a clear error and the GitHub release link.
   - Network failure: show retry and the release link.
   - Installer failure: the app may be closed; the release link remains available.
8. Browser mode shows "Desktop updates are installed by the desktop app" and links to the release page.
9. No auto-download and no silent install.

## 7. Runtime Contract

### 7.1 Port, Token, and Health

- Port: chosen by the shell on `127.0.0.1`, passed as `--port`.
- Token: random per launch, passed via `AMR_DESKTOP_TOKEN`.
- The token is never passed on the command line and never written to disk.
- The token is injected into the webview before page scripts run.
- Frontend reads the injected token into its in-memory `_cachedToken`; it does not call `/api/auth/token` in desktop mode.
- REST requests use `Authorization: Bearer <token>`.
- WebSocket requests use `?token=<token>` because browsers cannot set WebSocket headers.
- `/health` is unauthenticated but exposes only `status`, `version`, and `desktop`.
- `/api/*` requires the desktop token when `AMR_DESKTOP_TOKEN` is set.
- Static SPA assets do not require the token; they contain no user data.
- `/api/auth/token` is disabled in desktop mode.
- Uvicorn access logging is disabled in desktop mode so query-string WebSocket tokens are not written to logs.
- The backend checks the `Host` header against `127.0.0.1:<port>` and `localhost:<port>` to block DNS-rebinding style attacks.
- Mutating requests with an `Origin` header must match the loopback origin. WebSocket handshakes are checked the same way.
- Token comparisons use `hmac.compare_digest`.
- Desktop mode forces LAN JWT auth off regardless of `config.json`, so there is exactly one auth mechanism. `/api/auth/token` returns 404 in desktop mode.
- The frontend's existing LAN JWT flow remains for browser mode; desktop mode does not enable it.
- Debug mode is the only exception: the backend runs without `AMR_DESKTOP_TOKEN` and the shell loads Vite. Release builds never take that path.

Health response:

```json
{
  "status": "ok",
  "version": "2.2.0",
  "desktop": true
}
```

### 7.2 Data Paths

The installed app must never write into its install directory.

| Data | Path |
|---|---|
| Engine config (installed) | `%APPDATA%\ai-media-renamer\config.json` |
| Engine config (source/CLI) | repository `config.json` (unchanged) |
| Config template | bundled `config.default.json` |
| Logs (installed) | `%APPDATA%\ai-media-renamer\logs` |
| Logs (source) | repository `logs` (unchanged) |
| Setup profile | `<data_root>\setup.json` |
| FFmpeg, ExifTool, llama.cpp | `<data_root>\bin` |
| GGUF models | `<data_root>\models` |
| Sessions | `<data_root>\sessions` |
| Undo log | `<data_root>\undo_log.jsonl` |
| Shell preferences | Tauri app config directory (`desktop.json`), not `<data_root>` |
| Shell logs | `<data_root>\logs\desktop-shell.log` |
| Backend stdout/stderr | `<data_root>\logs\backend-process.log` |

- `<data_root>` is `AMR_DATA_DIR` when set, otherwise `%APPDATA%\ai-media-renamer`.
- `AMR_DATA_DIR` overrides the user data root for tests and portable runs. When set, config, logs, models, setup, sessions, undo, shell logs, and the setup wizard's `CACHE_DIR`/`BIN_DIR` all live under it.
- The shell reads `setup.json` and writes `desktop.json` using the same `AMR_DATA_DIR` resolution. The shell inherits and forwards the variable to the backend and setup child.
- `bootstrap.py` must stop computing `CACHE_DIR` and `BIN_DIR` directly from `%APPDATA%`; it imports `engine.USER_DATA_DIR` so source, frozen, and override modes agree.
- Source/CLI mode keeps the current repository `config.json` and `logs/` behavior unless `AMR_DATA_DIR` is set. This avoids breaking developers and the CLI.
- Frozen mode uses `%APPDATA%\ai-media-renamer`.
- First frozen launch seeds `config.json` from bundled `config.default.json`.
- If a legacy portable `config.json` exists next to the backend executable or next to `engine.py`, it is imported only when the destination config does not exist and it parses as JSON.
- The app never mutates a legacy `config.json` in place.
- Uninstall preserves `%APPDATA%\ai-media-renamer` so models and sessions survive reinstalls. Settings and README explain how to remove it.

### 7.3 Engine Path Changes

- Add `APP_DATA_DIR` resolution:
  - `AMR_DATA_DIR` if set.
  - Otherwise `%APPDATA%\ai-media-renamer`.
  - Fallback `~/AppData/Roaming/ai-media-renamer`.
- `USER_DATA_DIR = APP_DATA_DIR`.
- `CONFIG_PATH`:
  - Frozen or `AMR_DATA_DIR`: `APP_DATA_DIR / "config.json"`.
  - Source: `Path(__file__).parent / "config.json"`.
- `load_config()`:
  - Accept an absolute path for tests.
  - In frozen/override mode, seed missing config from bundled `config.default.json`.
  - In source mode, keep current auto-recovery behavior.
  - Never write into a read-only install directory.
- `save_config()`:
  - Create the parent directory.
  - Write temp file in the same directory and `os.replace`.
  - Raise on failure; do not silently fall back.
- `LOG_DIR`:
  - Absolute `logging.directory` wins.
  - Relative path resolves under the mode's data root (frozen: APPDATA; source: repository).
  - `reload_config()` refreshes `LOG_DIR`, not only the other globals.
- `SESSION_DIR = USER_DATA_DIR / "sessions"`.
- `UNDO_DIR = USER_DATA_DIR`.
- `LLAMACPP_MODELS_DIR = USER_DATA_DIR / "models"`.
- `_llamacpp_model_dir()` returns the configured directory if set, otherwise `LLAMACPP_MODELS_DIR`.
- `download_llamacpp_model()` and `_llamacpp_gguf_paths()` must use the same directory.
- `_resolve_binary_path()` checks, in order:
  1. `USER_DATA_DIR / "bin" / name` and `name.exe`.
  2. PyInstaller `_MEIPASS/bin`.
  3. `PATH`.
- Stop calling `_add_to_user_path()` during setup. The resolver no longer needs PATH mutation, and avoiding it removes a registry side effect.
- Add `stop_llamacpp_server()` that terminates only a process this app started.
- Add a lock around `ensure_llamacpp_server()` so startup and first analysis cannot start two servers.
- Add `migrate_llamacpp_paths()`: if `setup.json` says onboarded, config's GGUF path is empty, and a catalog GGUF exists under `LLAMACPP_MODELS_DIR`, configure it. This repairs users whose old portable config was not imported.
- Add `migrate_llamacpp_models()` for the old `~/.cache/ai-media-renamer/models` location:
  - Runs only in frozen or `AMR_DATA_DIR` mode.
  - Moves `.gguf` and `mmproj` files into `LLAMACPP_MODELS_DIR` when the destination file does not exist.
  - Uses `os.replace` when on the same volume. For a cross-drive move, copies to `<name>.part`, flushes, then `os.replace`s the `.part` into place, and only then deletes the source. An interrupted move leaves the source and a `.part`, never a truncated destination.
  - Never overwrites an existing destination and never deletes a source that failed to move.
  - Runs in a background thread at backend startup. `ensure_llamacpp_server()` and model downloads wait for the migration event (up to 5 minutes) before touching model files; a timeout returns a clear "models are still being migrated" error.
  - Logs each moved/skipped file path at info level.
- `bootstrap.py` `CACHE_DIR` and `BIN_DIR` derive from `engine.USER_DATA_DIR`; no direct `%APPDATA%` computation remains.
- `_install_llamacpp_runtime()` copies every file from the directory containing the extracted `llama-server.exe` into `BIN_DIR` (preserving subdirectories), not just the launcher. Verify `llama-server-impl.dll`, `llama.dll`, `ggml*.dll`, `mtmd.dll`, and `libomp*.dll` are present before reporting success.

### 7.4 llama-server Lifecycle

- The desktop backend starts a daemon thread on startup that calls `ensure_llamacpp_server()`.
- If the model path is missing, the thread exits quietly; the environment page reports the missing pieces.
- Before analysis begins, the analysis route verifies the server is running; if not, it calls `ensure_llamacpp_server()` with a timeout and emits a clear error on failure.
- `ensure_llamacpp_server()` records the `Popen` handle it creates.
- `stop_llamacpp_server()` kills only that owned handle. A server that was already running is left alone.
- The setup wizard stops any server it started before the setup-only process exits, so the backend can own the lifecycle.
- The backend's FastAPI shutdown hook calls `stop_llamacpp_server()`.
- If llama-server crashes, analysis fails with the current clear error. Automatic restart of a crashed llama-server is not in v1.

### 7.5 SPA Serving and Reloads

- Replace the plain `StaticFiles` mount with an SPA-aware static handler.
- It serves real assets normally.
- On a 404 for a non-API path, it serves `index.html`, so `/settings`, `/staging`, and other client routes survive webview reloads.
- API routes and `/health` remain registered before the static mount.
- The SPA uses `BrowserRouter` unchanged.

### 7.6 Desktop Status Endpoint

The shell must not infer backend activity from the SPA, because the SPA can reload or crash while work continues. Add an authenticated `GET /api/desktop/status` that returns:

```json
{
  "analysis_running": false,
  "commit_running": false,
  "model_downloads_running": false,
  "model_migration_running": false,
  "setup_running": false,
  "staging_count": 0
}
```

- `analysis_running` is set by the WebSocket analysis runner before the thread starts and cleared in its `finally` block. Cancellation still counts as running until the thread exits.
- `commit_running` is set around the commit route's batch operation and cleared in `finally`.
- `model_downloads_running` is true when any model download state is `downloading`.
- `model_migration_running` is true while the legacy model migration thread is active.
- `setup_running` is always false in the backend process; the shell adds its own setup-child state before showing the combined status.
- `staging_count` is the number of staged rows in `ACTIVE_STAGING`.
- If the endpoint fails because the backend is down, the shell treats the backend as not busy and proceeds with quit or restart.
- This endpoint is the single source of truth for quit, setup, and update guards. The SPA uses the same endpoint to disable conflicting actions.

## 8. First-Run Setup

### 8.1 Recommended v1: Reuse the Tk Setup Wizard

The Tk wizard already handles hardware detection, use-case questions, FFmpeg, ExifTool, llama.cpp, GGUF models, Whisper, and setup profile persistence. Rewriting it in React is a separate feature, not a packaging step.

Implementation:

- The same `AIMediaRenamerBackend.exe` serves both roles:
  - Normal operation: FastAPI sidecar.
  - `--setup`: run `bootstrap.main()` and exit.
- Add `--no-launch` so the setup process does not start a server or a browser.
- Add `--no-update-check` because Tauri owns updates.
- Add `--mark-onboarded` to record "continue without setup" without clearing an existing profile.
- `bootstrap.main()` returns an exit code:
  - `0`: setup completed, or user intentionally skipped.
  - `1`: user closed the window or setup failed.
- A non-zero exit is not fatal. The shell asks: "Setup did not finish. Continue anyway?", then Retry or Quit.
- If the user continues, the shell runs `--mark-onboarded` only when `setup.json` is missing; it does not overwrite an existing profile.
- Tauri runs the setup executable from the bundled resources, with working directory `<data_root>` and the inherited `AMR_DATA_DIR` environment.
- The splash window says "Setting up AI Media Renamer..." while the Tk wizard is open.
- Setup is also available from the tray later. The shell stops the backend first, runs setup, then restarts the whole app.
- Remove the pywebview branch from `_launch_app()`. For source users, launch `launch.py` and open the browser, or simply instruct them to run `launch.py`. The desktop shell never calls `_launch_app()`.

Trade-off: the first-run window is Tk, not React. It is functional and already integrated with the engine, but it is visually different from the SPA. If a fully uniform native onboarding is required, Phase E replaces it with React setup endpoints.

### 8.2 Alternative: React Onboarding

If the Tk window is not acceptable:

- Start the backend immediately with the default config.
- Add setup endpoints:
  - `GET /api/setup/profile`
  - `PUT /api/setup/profile`
  - `POST /api/setup/install`
  - `GET /api/setup/status` or a WebSocket/SSE progress stream
- Reuse the engine install functions, with a lock so one install runs at a time.
- Add a `/onboarding` route or modal in the SPA.
- The shell opens the SPA instead of the Tk wizard.
- This is a larger change because install progress, cancellation, and error recovery must be exposed over HTTP.

Recommendation: ship v1 with the Tk wizard, then replace it in Phase E if the visual mismatch matters.

## 9. Packaging and Build

### 9.1 Repository Layout

```
src-tauri/
  Cargo.toml
  build.rs
  tauri.conf.json
  capabilities/
    default.json
    remote.json
  icons/
  splash/
    index.html
  src/
    main.rs
    lib.rs
desktop_backend.py          # new backend entrypoint: server or --setup
build_desktop.spec          # PyInstaller onedir build
scripts/
  check_versions.py
  build-desktop.ps1
package.json                # root, Tauri CLI only
```

The old `build_v2.spec` and `launch.py` remain for the browser/portable path for now. The release workflow moves to the desktop build.

### 9.2 Tauri Configuration

- `productName`: `AI Media Renamer`
- `identifier`: `com.abdulmusawwir.ai-media-renamer`
- `version`: must equal `engine.VERSION`, `pyproject.toml`, `frontend/package.json`, and `src-tauri/Cargo.toml`
- `build.frontendDist`: `src-tauri/splash` (tiny local splash only)
- `build.devUrl`: `http://127.0.0.1:5173` for Vite HMR; set `frontend/vite.config.ts` `server.host = "127.0.0.1"` so the origin matches the capability wildcard
- `build.beforeDevCommand`: `npm --prefix frontend run dev`
- `build.beforeBuildCommand`: empty; the build script builds the SPA and PyInstaller bundle first
- `bundle.targets`: `["nsis"]`
- `bundle.resources`: map explicitly: `{"../dist/AIMediaRenamerBackend/": "AIMediaRenamerBackend/"}` so the folder name is stable across Tauri versions
- `bundle.createUpdaterArtifacts`: `true`
- `bundle.windows.nsis.installMode`: `currentUser`
- `bundle.windows.nsis.displayLanguageSelector`: `false`
- `bundle.windows.webviewInstallMode`: `embedBootstrapper` initially; switch to `offlineInstaller` if offline setup is required
- `plugins.updater.endpoints`: `["https://github.com/<owner>/<repo>/releases/latest/download/latest.json"]`
- `plugins.updater.pubkey`: the minisign public key
- `plugins.updater.windows.installMode`: `passive`; the JS install call passes `restartAfterInstall: true` explicitly
- `app.windows`: empty; windows are created programmatically
- `app.trayIcon`: optional; the tray is created in Rust
- `app.security.csp`: start with the safest CSP that still allows Tauri IPC and the loopback API, and validate it before release. Do not ship `null` without review.

The backend is resolved at runtime with `BaseDirectory::Resource` + `AIMediaRenamerBackend/AIMediaRenamerBackend.exe`. Tauri resource directories preserve the folder name, so this path is stable across install and update.

### 9.3 Python Bundle

`build_desktop.spec`:

- Entry: `desktop_backend.py`
- `onedir`, `console=False`
- Name: `AIMediaRenamerBackend`
- Data:
  - `frontend/dist` -> `frontend/dist`
  - `config.default.json`
  - `icon.ico`
- Hidden imports: `bootstrap`, `engine`, every `server.*` module, `tkinter`, `fastapi`, `starlette`, `uvicorn`, `websockets`, `jwt`, `pydantic`, `openai`, `httpx`, `requests`, `numpy`, `scipy`, `PIL`, `imagehash`, `pdfplumber`, `pdfminer`, `docx`, `openpyxl`, `pptx`, `faster_whisper`, `ctranslate2`, `av`, `onnxruntime`, `huggingface_hub`, `tokenizers`, `multipart`.
- Do not exclude `tkinter`; setup mode needs it.
- Do not exclude `scipy`; `imagehash.phash` uses it.
- Keep `pandas`, `plotly`, `torch`, `streamlit`, `pywebview`, `rich`, `pyarrow`, and unused test libraries out.
- `upx=False` to reduce antivirus false positives.
- `console=False` means `sys.stdout`/`sys.stderr` may be `None`. At the very top of `desktop_backend.py`, before importing `engine` or `server`, redirect both to `<data_root>\logs\backend-process.log` (create parents; line-buffered) when they are `None`. Rust also captures the child's redirected handles, so uvicorn logging has a valid target.
- Verify the onedir layout:
  - `AIMediaRenamerBackend.exe`
  - `_internal/server/...`
  - `_internal/frontend/dist/...`
  - `_internal/config.default.json`
  - `_internal/icon.ico`

`frontend/dist` must exist before PyInstaller runs. The CI build fails if it does not, instead of shipping an API-only app.

### 9.4 Build Pipeline

1. `npm ci` and `npm run build` in `frontend/`.
2. `npm ci` at the repository root for the Tauri CLI.
3. `pyinstaller build_desktop.spec --noconfirm`.
4. Smoke test the backend exe with a temporary `AMR_DATA_DIR`:
   - Start with `--host 127.0.0.1 --port 8123 --smoke-test`.
   - Probe `/health`.
   - Stop it.
5. `npm run tauri build` from the root.
6. Tauri produces the NSIS installer, `.sig`, and `latest.json`.
7. `tauri-action` uploads them to the GitHub Release.

The root `package.json` contains only the Tauri CLI and scripts. The frontend keeps its own dependencies.

### 9.5 Versioning

- `engine.VERSION` is the version source.
- `scripts/check_versions.py` verifies:
  - `engine.VERSION`
  - `pyproject.toml` `project.version`
  - `frontend/package.json` `version`
  - `src-tauri/tauri.conf.json` `version`
  - `src-tauri/Cargo.toml` `package.version`
  - GitHub tag `v<version>` when running in CI
  - `latest.json` when present
- CI runs the check before building.
- Proposed release for this work: `2.2.0`.
- Release builds compare `/health` engine version with the shell version at startup and refuse to load a mismatched installation, telling the user to reinstall.
- Debug builds log the mismatch and continue; `AMR_SKIP_VERSION_CHECK=1` is honored only in debug builds. This keeps `tauri dev` usable while source and shell versions move independently.
- The source/browser and CLI paths do not perform the shell version gate.

### 9.6 Development Mode

`tauri dev` is a separate flow from a release install:

- `npm run tauri dev` runs Vite on `127.0.0.1:5173`; Tauri creates the main window at the `devUrl` and does not spawn the backend or create a splash.
- The developer runs the backend separately:
  ```
  python desktop_backend.py --host 127.0.0.1 --port 8000 --no-launch --no-update-check
  ```
  Add a root script `npm run dev:backend` for this command.
- The backend has no `AMR_DESKTOP_TOKEN`, so desktop auth, Host, and Origin enforcement are inert. That is acceptable for debug only; a release build always sets the token.
- `frontend/vite.config.ts` keeps its `/api` and WebSocket proxy but changes the target from `localhost:8000` to `127.0.0.1:8000`, matching the backend dev bind.
- The Tauri remote capability wildcard `http://127.0.0.1:*` covers both 5173 and the release port. No additional dev capability is needed.
- Debug builds skip the updater UI's live actions and show the release-page fallback, so an accidental dev update cannot replace the developer's build.
- Release behavior is verified through the installed NSIS build, not through `tauri dev`.

## 10. Updater Details

### 10.1 Keys and Files

- Generate a minisign keypair with the Tauri signer.
- Public key goes in `tauri.conf.json`.
- Private key and password go in GitHub Actions secrets:
  - `TAURI_SIGNING_PRIVATE_KEY`
  - `TAURI_SIGNING_PRIVATE_KEY_PASSWORD`
- Back up the private key offline. Losing it means existing installs cannot verify future updates and users must reinstall manually.
- `tauri-action` generates and uploads `latest.json` with:
  - version
  - notes
  - publication date
  - Windows x64 installer URL
  - signature
- The updater endpoint uses GitHub's `releases/latest/download/latest.json`, so it does not hit the API and does not need a token.
- The repository must be public for unauthenticated update checks.
- Windows install calls `update.install({ restartAfterInstall: true })`. The updater plugin exits the app and runs NSIS with `/R`; the finish-page relaunch is not part of the contract.
- `installMode` is `passive`, not `quiet`. Passive shows progress and works with per-user installs; quiet can fail silently when elevation is involved.

### 10.2 Signing vs SmartScreen

- Tauri's updater signature is minisign. It proves the update came from the project; it does not make Windows SmartScreen trust the installer.
- Authenticode is a separate code-signing certificate. Without it, users may see "Unknown publisher" and SmartScreen warnings.
- No Authenticode certificate is available for this release. Document the SmartScreen warning and keep the minisign updater.
- If an Authenticode certificate is available, configure Tauri's Windows signing (`certificateThumbprint` or `signCommand`) and timestamping. Do not put certificate secrets in the repository.

### 10.3 Updater UI State Machine

`idle -> checking -> up-to-date | available -> downloading -> installing -> (app exits)`

- `error` is reachable from checking, downloading, and installing.
- Download has no cancel action in v1; closing the app is the escape hatch.
- The release notes are rendered as text, not HTML.
- The install action is disabled while analysis is running or staged rows are unsaved until the user confirms.
- The browser build shows a link to the release page instead of the updater UI.

### 10.4 Release Workflow

- Trigger: `v*` tags.
- Jobs: Windows runner.
- Steps:
  - checkout
  - Python 3.12
  - install requirements
  - Node 20 for frontend and root
  - build frontend
  - version check
  - PyInstaller build
  - backend smoke test
  - Rust cache
  - `tauri-action` with NSIS, updater JSON upload, and NSIS preference
- Permissions: `contents: write`.
- The old raw-exe upload is removed from the desktop release path.
- Optionally keep a manual workflow for a portable exe for one release; it is not the primary artifact.

## 11. Security

### 11.1 Threat Model

- The backend binds loopback, but any local process and any webpage can attempt to reach it.
- The main risks are:
  - A malicious local webpage sending requests to the loopback API.
  - DNS rebinding.
  - Token leakage in logs.
  - A compromised SPA page using Tauri IPC.
  - An unsigned or tampered update.
  - A malicious local process racing the backend port.

### 11.2 Controls

- Random per-launch token required on every `/api/*` call and WebSocket.
- Host allowlist.
- Origin check for mutations and WebSocket handshakes.
- No access logs in desktop mode.
- Token never written to config, disk, or command line.
- Token not included in error messages.
- Backend only on `127.0.0.1`, never `0.0.0.0`.
- No LAN exposure in desktop mode.
- Tauri remote capability scoped to `http://127.0.0.1:*`.
- Remote IPC permissions limited to core app/event/webview, dialog, updater, and process. No shell, filesystem, or arbitrary URL opener.
- Custom commands are limited to opening logs/data, reading pending paths, shell preferences, setup, quit, and a constrained GitHub release link.
- Updater uses pinned minisign public key and HTTPS GitHub release URL.
- Authenticode if available.
- CSP on the SPA served by FastAPI, validated against Tauri IPC and Vite production output.
- No remote fonts, scripts, or images.
- Logs redact paths per the engine config.
- No telemetry.

### 11.3 Remote Capability Caveat

Tauri capabilities are static. A wildcard loopback port means any loopback origin could receive the granted permissions if it were loaded into the main window. The shell only loads the port it verified via `/health`, and the port/token are random. The remaining exposure is limited to non-destructive commands, updater (signature-verified), and quit. Do not add shell execution, arbitrary file reads, or arbitrary URL opening to the remote capability.

## 12. Frontend Changes

### 12.1 Desktop Bridge

Add `frontend/src/desktop/`:

- `isDesktop()`: checks the injected flag or `window.__TAURI_INTERNALS__`.
- `getDesktopToken()`: returns the injected token.
- `onOpenPaths(cb)`: listens for `desktop://open-paths`.
- `getPendingPaths()`: invokes the Rust command.
- `onShowUpdates(cb)`: listens for `desktop://show-updates`.
- `desktopReady()`: invokes the Rust `desktop_ready` command.
- `openLogs()`, `openDataFolder()`, `openReleasePage()`: invoke Rust commands.
- `getShellSettings()`, `setCloseToTray()`: invoke Rust commands.

All Tauri imports are dynamic or guarded so the browser build still works.

Add a `DesktopBridge` component inside the router:

- On mount, call `desktopReady()`, load pending paths, register listeners.
- Add incoming paths to a Zustand `incomingPaths` slice.
- On `desktop://show-updates`, navigate to `/settings?focus=updates`.
- Start the update check after 5 seconds if desktop and not dev.

### 12.2 Analysis Page

- `useDropzone({ noClick: isDesktop, onDrop })`.
- Native "Choose files" button in desktop mode.
- Subscribe to Tauri drag/drop events; set a drag-active state for `enter`/`over`/`leave`; add paths on `drop`.
- Merge `incomingPaths` from the store, then clear them.
- Keep the existing folder picker; add a native "Choose folder" button in desktop mode.
- Filter empty paths and de-duplicate as today.
- Do not fall back to `f.name` in desktop mode.

### 12.3 Settings / About

Add a "Desktop App" section:

- Current shell version, backend version, data folder, log folder.
- Update status and actions; disable install while `/api/desktop/status` reports analysis, commit, download, or migration activity.
- "Close to tray" toggle.
- "Run setup" button (confirmation required).
- "Open logs", "Open data folder", "Quit".
- Release page link.
- No raw token or port display.

### 12.4 Header

Replace the stale `config.version`/`v2.0.0` display with the backend version from `/health` or the desktop info command. In browser mode, `/health` works.

### 12.5 API Client

- At module load, if `window.__AMR_DESKTOP_TOKEN__` exists, set `_cachedToken` and skip `/api/auth/token`.
- Keep the existing LAN token flow for browser mode.
- No changes to API paths; same-origin loopback works because `API_BASE` is empty.

## 13. Testing

### 13.1 Python

- `AMR_DATA_DIR` override:
  - config, logs, models, sessions, undo, setup, `CACHE_DIR`, and `BIN_DIR` all under the override.
  - shell resolution reads the same `setup.json` path.
- Source mode remains repository config/logs.
- Frozen mode uses APPDATA; simulate with `sys.frozen` or a helper.
- Missing config seeds from `config.default.json`.
- Legacy config import only when destination is missing.
- `save_config` creates parents and raises on failure.
- `reload_config` refreshes `LOG_DIR`.
- `_resolve_binary_path` prefers `USER_DATA_DIR/bin` and `.exe`.
- `_llamacpp_model_dir` and `_llamacpp_gguf_paths` agree.
- `download_llamacpp_model` uses the same model dir.
- `migrate_llamacpp_paths` repairs an onboarded profile with an installed GGUF.
- `migrate_llamacpp_models` moves legacy cache files only when the destination is missing, does not overwrite, leaves failed moves intact, and never leaves a truncated destination.
- `ensure_llamacpp_server` waits for migration and does not start during an active move.
- Windowed-mode logging has a valid stdout/stderr target before uvicorn starts.
- `_install_llamacpp_runtime` installs the launcher and every adjacent DLL, and fails if `llama-server-impl.dll` is missing.
- `stop_llamacpp_server` only kills owned processes.
- `ensure_llamacpp_server` is idempotent under concurrent calls.
- Desktop auth middleware:
  - `/health` allowed without token.
  - `/api/*` 401 without token.
  - valid bearer allowed.
  - WebSocket token check.
  - bad Host rejected.
  - bad Origin rejected.
  - `/api/auth/token` disabled in desktop mode.
  - desktop mode forces LAN JWT auth off even if config enables it.
- SPA fallback serves `index.html` for `/settings`, not for `/assets/*.js` or `/api/*`.
- `/health` includes version and desktop flag.
- `/api/desktop/status` reports analysis, commit, download, migration, setup, and staging counts; it requires the token.
- `bootstrap.main()` exit codes for setup-only, skip, and failure.
- `bootstrap.CACHE_DIR` and `BIN_DIR` follow `AMR_DATA_DIR`.
- Version gate: release refuses a mismatch; debug logs and continues; debug-only bypass works.

### 13.2 Rust

- `cargo test` for pure helpers:
   - port picking
   - token generation
   - argv path filtering
   - setup detection
   - data-root resolution (`AMR_DATA_DIR` vs APPDATA)
   - version comparison and debug-only bypass
- `cargo clippy -- -D warnings`.
- Job Object assignment and cleanup are tested manually on Windows.

### 13.3 Frontend

- `tsc` and `vite build`.
- Desktop detection and token injection.
- Browser build still loads with no Tauri globals.
- Drag/drop path handling in desktop mode.
- Update UI state transitions with a mocked updater.

### 13.4 Manual Windows QA

1. Fresh Windows 11 install, standard user, no Python.
2. Installer runs without UAC; app launches.
3. First-run setup downloads tools and a model; app opens after setup; a clean llama-server install includes its DLLs and starts.
4. Skip setup; app opens with environment warnings; tray setup completes it.
5. Drag files from Explorer; analyze; stage; commit; rollback.
6. Documents, spreadsheets, audio, images, and videos still work.
7. Close to tray during analysis; analysis finishes; reopen.
8. Second launch focuses the first; second launch with a file path adds it.
9. Reload on `/settings` works (SPA fallback).
10. Update from N to N+1: check, notes, download, install, relaunch; config/models/sessions survive. Confirm the app comes back without relying on a finish page.
11. Signature failure and offline update failure leave the app usable.
12. Upgrade from 2.1.0 with a model in `~/.cache`: the model is moved, not re-downloaded, and analysis still finds it.
13. `tauri dev` loads Vite at `127.0.0.1:5173`, the backend runs separately on 8000, and no token/splash/sidecar is required.
14. Uninstall preserves user data; reinstall sees it.
15. Paths with spaces and non-ASCII characters.
16. Antivirus scan and SmartScreen behavior.
17. Backend crash shows Restart/Quit; restart works.
18. llama-server missing or crashed gives a clear analysis error.
19. Windows shutdown kills backend and llama-server.
20. No token in logs.

## 14. Rollout

### Phase A - Backend foundations

- Add config/log path separation for frozen vs source.
- Add `AMR_DATA_DIR` and make `bootstrap.CACHE_DIR`/`BIN_DIR` follow it.
- Seed config, import legacy config, repair GGUF paths.
- Unify model directories and add legacy `~/.cache` model migration.
- Add binary resolution from user bin.
- Add `stop_llamacpp_server` and start lock.
- Add SPA fallback.
- Add desktop token auth, `/health` desktop flag, and `/api/desktop/status`.
- Add `desktop_backend.py`, `--setup`, `--no-launch`, `--no-update-check`, `--mark-onboarded`, `--smoke-test`.
- Add tests.

### Phase B - Tauri shell

- Add `src-tauri` project, icons, capabilities.
- Implement release startup, health, splash, token injection, Job Object, single instance, tray, close-to-tray, error dialogs, logs.
- Implement the debug dev flow (Vite `devUrl`, external backend, no token/splash/sidecar).
- Use `/api/desktop/status` for quit/setup guards.
- Add native drag/drop, file picker, folder picker.
- Add DesktopBridge and header version.
- Add shell settings and open logs/data commands.

### Phase C - Updater and installer

- Add updater plugin, signing keys, latest.json, NSIS config (`installMode: "passive"`), WebView2 mode.
- Add Settings update UI, auto-check, tray check, save-session guard, before-exit shutdown.
- Verify `install({ restartAfterInstall: true })` relaunches through NSIS `/R` on a real N to N+1 update before finalizing the workflow.
- Add GitHub Actions workflow and version check.
- Add Authenticode if a certificate is available.

### Phase D - Hardening and release

- Smoke test installer, update, uninstall, and data preservation.
- Verify CSP and remote capability.
- Update README, PRD notes, audit, and task files.
- Release 2.2.0.

### Phase E - Optional native onboarding

- Add setup endpoints and a React onboarding flow.
- Retire the Tk setup path from the desktop shell if desired.
- Keep the Tk wizard available for source users or remove it in a later major release.

## 15. Decisions and Open Questions

### Approved decisions

1. Use Tauri v2 with a PyInstaller `onedir` backend resource and loopback SPA.
2. Use per-user NSIS, no elevation.
3. Use GitHub Releases with minisign updater signatures.
4. Reuse the Tk setup wizard for v1 through `--setup --no-launch`.
5. Keep source/CLI config in the repository; installed config in APPDATA.
6. Keep user data in `%APPDATA%\ai-media-renamer`.
7. Keep the browser/CLI paths; do not delete them.
8. Ship unsigned if no Authenticode certificate is available, with a documented SmartScreen warning.
9. Release as 2.2.0.
10. `tauri dev` loads Vite at `127.0.0.1:5173` with a separately started backend on 8000; release builds load the backend-served SPA. Debug mode has no token, splash, or sidecar.
11. `AMR_DATA_DIR` scopes shell setup detection and bootstrap paths, not only engine data.
12. `/api/desktop/status` is the authoritative busy state for quit, setup, and update guards.
13. `install({ restartAfterInstall: true })` plus `installMode: "passive"` is the relaunch contract.
14. Legacy `~/.cache` GGUF files are migrated on first frozen launch, not left orphaned or re-downloaded.
15. The version-equality gate is release-only; debug logs mismatches.

### Resolved user decisions

1. Ship v1 with the Tk setup wizard; React onboarding remains Phase E.
2. No Authenticode certificate is available. Ship unsigned and document the SmartScreen "Unknown publisher" warning.
3. Use `embedBootstrapper` for WebView2.
4. The NSIS installer is the only published artifact; do not publish the old portable exe.
5. Release as 2.2.0.
6. Closing the window minimizes to the tray by default, with a first-run notice and a Settings toggle.

## 16. Acceptance Criteria

- A standard user can install and launch the app without Python, a terminal, or a browser.
- The window shows the existing SPA at loopback with REST and WebSocket working.
- First-run setup installs tools/models and persists `setup.json`.
- Config, logs, models, sessions, and undo live in `%APPDATA%\ai-media-renamer` (or `AMR_DATA_DIR`) and survive updates.
- Legacy `~/.cache` GGUF models are moved, not orphaned, on first frozen launch.
- Quit, setup, and update guards use `/api/desktop/status`, not SPA state.
- `tauri dev` uses Vite HMR with a separate backend and no release token, splash, or sidecar.
- The version gate rejects mismatches only in release builds.
- Native drag/drop supplies full paths; browser drop behavior is unchanged.
- Single instance focuses the existing window; file arguments are delivered.
- Close-to-tray works and can be disabled.
- Update check, download, signature verification, install, and relaunch work from N to N+1.
- Update failure does not corrupt the installation or user data.
- `/settings` survives a webview reload.
- No backend token appears in logs.
- `ruff check .` is clean, the Python suite passes, and the frontend builds.
- The installed app's version matches `/health` and the release tag.
- Uninstall preserves user data.

## 17. Steelman: Why This Could Be Wrong

- **Tauri remote IPC may be harder than expected.** If a loopback origin cannot reliably use the updater plugin, the fallback is to drive updates from Rust commands and a small IPC surface. Phase B should include a spike before the update UI is built.
- **The sidecar lifecycle is the highest-risk area.** Port races, orphaned llama-server processes, and antivirus delays are the likely failure modes. The Job Object, health polling, and startup logs are not optional.
- **The onedir bundle may be large.** `ctranslate2`, `onnxruntime`, `scipy`, and `av` add hundreds of MB. If size becomes unacceptable, the alternative is an optional feature-pack download, but that changes the offline promise and setup complexity. This design assumes size is acceptable.
- **The Tk setup window undercuts the native feel.** It is accepted for v1, but if it proves unacceptable after release, React onboarding becomes the next investment.
- **Unsigned installers still trigger SmartScreen.** The updater signature does not solve first-install trust. Authenticode is the only real fix.
- **APPDATA config for the installed app is a behavior change for portable users.** The legacy import and setup repair reduce the impact, but some users will still need to reselect a model. Document it.
- **Per-user NSIS installs can be blocked by corporate policy.** A per-machine MSI would be the alternative, but it requires elevation and more installer work.
- **Auto-update consent is manual.** Users who ignore updates stay on old versions; that is intentional for safety but may be seen as friction.

## 18. Implementation Boundaries

Allowed in this work:

- Tauri shell, build scripts, installer, updater, tray, native dialogs, drag/drop, pickers.
- Python path/lifecycle/auth changes required by the desktop shell.
- SPA fallback, desktop bridge, update UI, version display.
- Setup-only flags and exit-code fixes.
- Tests, CI, README, PRD notes, audit/task updates.

Not allowed in this work:

- New AI models or naming behavior.
- New categories or prompt profiles.
- Changes to commit/rollback semantics beyond what the desktop shell requires.
- Replacing React Router, state management, or the analysis pipeline.
- Storing user data in the install directory.
- Adding telemetry or remote services.
