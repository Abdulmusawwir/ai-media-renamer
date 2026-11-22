//! Tauri desktop shell for AI Media Renamer.

mod backend;
mod commands;
mod settings;
mod tray;

use std::error::Error;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Mutex;
use std::time::Duration;

use backend::BackendProcess;
use tauri::{
    AppHandle, Emitter, Manager, RunEvent, WebviewUrl, WebviewWindow, WebviewWindowBuilder,
};

/// Shared shell state consumed by the command bridge and later lifecycle tasks.
#[derive(Default)]
pub struct ShellState {
    pub backend: Mutex<Option<BackendProcess>>,
    pub port: Mutex<Option<u16>>,
    pub token: Mutex<Option<String>>,
    pub pending_paths: Mutex<Vec<PathBuf>>,
    pub ready: AtomicBool,
    pub failed: AtomicBool,
    pub quitting: AtomicBool,
    pub data_dir: Mutex<Option<PathBuf>>,
}

/// Build and run the desktop shell.
pub fn run() {
    let app = tauri::Builder::default()
        // Single-instance must be registered before every other plugin.
        .plugin(tauri_plugin_single_instance::init(|app, argv, cwd| {
            handle_second_instance(app, argv, cwd);
        }))
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_process::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .manage(ShellState::default())
        .invoke_handler(tauri::generate_handler![
            commands::desktop_ready,
            commands::pending_paths,
            commands::release_page_url,
            commands::get_shell_settings,
            commands::set_close_to_tray,
            commands::open_logs,
            commands::open_data_folder,
            commands::get_backend_status,
            commands::restart_app,
            commands::quit_app
        ])
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                let app = window.app_handle();
                let state = app.state::<ShellState>();
                if state.quitting.load(Ordering::SeqCst) {
                    return;
                }
                if crate::settings::load_shell_settings(app).close_to_tray {
                    // Hide silently: a modal dialog here is confusing when the
                    // wizard or a restart closes the window as part of its own
                    // flow. The tray icon and its "Show" item are the cue.
                    api.prevent_close();
                    let _ = window.hide();
                    settings::log("window closed; app remains in the system tray");
                }
            }
        })
        .setup(|app| {
            setup(app)?;
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("failed to build the AI Media Renamer desktop shell");

    app.run(|app_handle, event| {
        if let RunEvent::Exit = event {
            stop_backend(app_handle);
        }
    });
}

fn setup(app: &mut tauri::App) -> Result<(), Box<dyn Error>> {
    let handle = app.handle().clone();
    let data_dir = backend::resolve_data_dir();
    std::fs::create_dir_all(settings::logs_dir(&data_dir))?;

    // The backend and the setup child must resolve the same data root.
    std::env::set_var("AMR_DATA_DIR", &data_dir);
    if let Err(err) = settings::init_logging(&data_dir) {
        settings::log(&format!("could not initialise the shell log: {err}"));
    }

    settings::log(&format!(
        "shell starting: version {}, data root {}",
        env!("CARGO_PKG_VERSION"),
        data_dir.display()
    ));

    {
        let state = handle.state::<ShellState>();
        let mut stored = state
            .data_dir
            .lock()
            .map_err(|_| std::io::Error::other("shell state lock poisoned"))?;
        *stored = Some(data_dir.clone());
    }

    tray::build_tray(&handle)?;

    if cfg!(debug_assertions) {
        settings::log("debug build: backend is not spawned; loading the Vite dev server");
        let window = create_main_window(&handle, None, None)?;
        window.show()?;
        window.set_focus()?;
        return Ok(());
    }

    // Startup runs off the main thread so the event loop keeps dispatching
    // while the backend boots and while startup dialogs are shown.
    create_splash(&handle)?;
    start_release(&handle);
    Ok(())
}

fn start_release(app: &AppHandle) {
    let app = app.clone();
    std::thread::spawn(move || {
        stop_backend(&app);
        match start_backend(&app) {
            Ok(()) => finish_startup(app),
            Err(err) => {
                settings::log(&format!("backend startup failed: {err}"));
                prompt_failure(app, err);
            }
        }
    });
}

fn finish_startup(app: AppHandle) {
    let (port, token) = match read_connection(&app) {
        Ok(connection) => connection,
        Err(err) => {
            prompt_failure(app, err);
            return;
        }
    };

    // Window creation is marshalled to the main thread by Tauri; doing it from
    // this worker avoids the WebView2 deadlock that hits synchronous event
    // handlers on Windows.
    match create_main_window(&app, Some(port), Some(&token)) {
        Ok(_) => spawn_ready_fallback(app),
        Err(err) => {
            let message = format!("could not create the main window: {err}");
            settings::log(&message);
            prompt_failure(app, message);
        }
    }
}

fn handle_second_instance(app: &AppHandle, argv: Vec<String>, cwd: String) {
    let cwd = PathBuf::from(cwd);
    let mut candidates = Vec::new();
    for argument in argv.into_iter().skip(1) {
        let path = PathBuf::from(&argument);
        let absolute = if path.is_absolute() {
            path
        } else {
            cwd.join(path)
        };
        if let Some(value) = absolute.to_str() {
            candidates.push(value.to_string());
        }
    }

    let paths = backend::filter_path_args(&candidates);
    if !paths.is_empty() {
        let state = app.state::<ShellState>();
        if let Ok(mut pending) = state.pending_paths.lock() {
            pending.extend(paths.clone());
        };
    }

    focus_main(app);

    if !paths.is_empty() && app.get_webview_window("main").is_some() {
        let payload: Vec<String> = paths
            .iter()
            .map(|path| path.to_string_lossy().into_owned())
            .collect();
        let _ = app.emit("desktop://open-paths", payload);
    }
}

fn focus_main(app: &AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.show();
        let _ = window.unminimize();
        let _ = window.set_focus();
    }
}

fn start_backend(app: &AppHandle) -> Result<(), String> {
    let mut last_error = String::from("backend did not start");

    for _ in 0..3 {
        let port = backend::pick_port().map_err(|err| format!("could not pick a port: {err}"))?;
        let token = backend::generate_token();
        settings::log(&format!("spawning backend on 127.0.0.1:{port}"));

        let mut process = match backend::spawn_backend(port, &token) {
            Ok(process) => process,
            Err(err) => {
                last_error = err;
                continue;
            }
        };

        match backend::wait_for_health(port, Duration::from_secs(30)) {
            Ok(health) => {
                let shell_version = env!("CARGO_PKG_VERSION");
                if !backend::version_compatible(
                    shell_version,
                    &health.version,
                    cfg!(debug_assertions),
                ) {
                    let _ = process.stop();
                    return Err(format!(
                        "backend version {} does not match shell version {}; reinstall the app",
                        health.version, shell_version
                    ));
                }
                if health.version != shell_version {
                    settings::log(&format!(
                        "version mismatch: shell {}, backend {}; continuing in debug",
                        shell_version, health.version
                    ));
                }

                {
                    let state = app.state::<ShellState>();
                    *state
                        .port
                        .lock()
                        .map_err(|_| "shell state lock poisoned".to_string())? = Some(port);
                    *state
                        .token
                        .lock()
                        .map_err(|_| "shell state lock poisoned".to_string())? = Some(token);
                    *state
                        .backend
                        .lock()
                        .map_err(|_| "shell state lock poisoned".to_string())? = Some(process);
                }

                settings::log(&format!("backend ready: version {}", health.version));
                return Ok(());
            }
            Err(err) => {
                last_error = err;
                let _ = process.stop();
            }
        }
    }

    Err(last_error)
}

fn read_connection(app: &AppHandle) -> Result<(u16, String), String> {
    let state = app.state::<ShellState>();
    let port = *state
        .port
        .lock()
        .map_err(|_| "shell state lock poisoned".to_string())?
        .as_ref()
        .ok_or_else(|| "backend port is not set".to_string())?;
    let token = state
        .token
        .lock()
        .map_err(|_| "shell state lock poisoned".to_string())?
        .clone()
        .ok_or_else(|| "backend token is not set".to_string())?;
    Ok((port, token))
}

fn create_main_window(
    app: &AppHandle,
    port: Option<u16>,
    token: Option<&str>,
) -> Result<WebviewWindow, Box<dyn Error>> {
    let mut config = app
        .config()
        .app
        .windows
        .iter()
        .find(|window| window.label == "main")
        .cloned()
        .ok_or_else(|| std::io::Error::other("tauri.conf.json has no main window"))?;

    if let Some(port) = port {
        config.url = WebviewUrl::External(format!("http://127.0.0.1:{port}").parse()?);
    } else if let Some(dev_url) = app.config().build.dev_url.clone() {
        config.url = WebviewUrl::External(dev_url);
    }

    let mut builder = WebviewWindowBuilder::from_config(app, &config)?;
    if let Some(token) = token {
        let port = port.ok_or_else(|| std::io::Error::other("backend port is not set"))?;
        let script = desktop_init_script(port, token);
        builder = builder.initialization_script(script.as_str());
    }

    Ok(builder.build()?)
}

fn create_splash(app: &AppHandle) -> Result<WebviewWindow, Box<dyn Error>> {
    let window = WebviewWindowBuilder::new(app, "splash", WebviewUrl::App("index.html".into()))
        .title("AI Media Renamer")
        .inner_size(420.0, 280.0)
        .resizable(false)
        .decorations(false)
        .always_on_top(true)
        .skip_taskbar(true)
        .center()
        .visible(true)
        .build()?;
    Ok(window)
}

fn desktop_init_script(port: u16, token: &str) -> String {
    let token = serde_json::to_string(token).unwrap_or_else(|_| "\"\"".to_string());
    let version =
        serde_json::to_string(env!("CARGO_PKG_VERSION")).unwrap_or_else(|_| "\"\"".to_string());
    format!(
        r#"
        (() => {{
          const expected = "http://127.0.0.1:{port}";
          if (window.location.origin !== expected) return;
          window.__AMR_DESKTOP__ = true;
          window.__AMR_DESKTOP_TOKEN__ = {token};
          window.__AMR_DESKTOP_PORT__ = {port};
          window.__AMR_DESKTOP_VERSION__ = {version};
        }})();
        "#
    )
}

fn spawn_ready_fallback(app: AppHandle) {
    std::thread::spawn(move || {
        std::thread::sleep(Duration::from_secs(10));

        let state = app.state::<ShellState>();
        if state.ready.load(Ordering::SeqCst) || state.failed.load(Ordering::SeqCst) {
            return;
        }

        settings::log("desktop_ready was not received within 10s; showing the main window");
        if let Some(window) = app.get_webview_window("main") {
            let _ = window.show();
            let _ = window.set_focus();
        }
        if let Some(splash) = app.get_webview_window("splash") {
            let _ = splash.close();
        }
    });
}

fn prompt_failure(app: AppHandle, error: String) {
    let main = app.clone();
    if let Err(err) = main.run_on_main_thread(move || show_failure_dialog(app, error)) {
        settings::log(&format!("could not show the failure dialog: {err}"));
    }
}

/// Non-blocking Retry / Open Logs / Quit dialog.
///
/// The splash window is hidden rather than closed: closing the last window
/// would let the event loop request an exit while the dialog is still open.
fn show_failure_dialog(app: AppHandle, error: String) {
    use tauri_plugin_dialog::{
        DialogExt, MessageDialogButtons, MessageDialogKind, MessageDialogResult,
    };

    if let Some(splash) = app.get_webview_window("splash") {
        let _ = splash.hide();
    }

    let data_dir = app
        .state::<ShellState>()
        .data_dir
        .lock()
        .unwrap_or_else(|poisoned| poisoned.into_inner())
        .clone()
        .unwrap_or_else(backend::resolve_data_dir);

    let message = format!(
        "AI Media Renamer could not start its backend.\n\n{error}\n\nLogs: {}",
        settings::logs_dir(&data_dir).display()
    );

    let app_for_callback = app.clone();
    app.dialog()
        .message(message)
        .title("AI Media Renamer")
        .kind(MessageDialogKind::Error)
        .buttons(MessageDialogButtons::YesNoCancelCustom(
            "Retry".to_string(),
            "Open Logs".to_string(),
            "Quit".to_string(),
        ))
        .show_with_result(move |result| match result {
            MessageDialogResult::Yes => retry_startup(app_for_callback),
            MessageDialogResult::Custom(ref label) if label.as_str() == "Retry" => {
                retry_startup(app_for_callback)
            }
            MessageDialogResult::No => {
                open_logs(&data_dir);
            }
            MessageDialogResult::Custom(ref label) if label.as_str() == "Open Logs" => {
                open_logs(&data_dir);
            }
            _ => quit(&app_for_callback),
        });
}

fn retry_startup(app: AppHandle) {
    if let Some(splash) = app.get_webview_window("splash") {
        let _ = splash.show();
        let _ = splash.set_focus();
    }
    settings::log("retrying backend startup");
    start_release(&app);
}

fn quit(app: &AppHandle) {
    let state = app.state::<ShellState>();
    state.failed.store(true, Ordering::SeqCst);
    app.exit(1);
}

fn open_logs(data_dir: &Path) {
    let logs = settings::logs_dir(data_dir);
    settings::log(&format!("opening logs folder {}", logs.display()));
    let _ = std::process::Command::new("explorer").arg(&logs).spawn();
}

pub fn stop_backend(app: &AppHandle) {
    let state = app.state::<ShellState>();
    let mut backend = state
        .backend
        .lock()
        .unwrap_or_else(|poisoned| poisoned.into_inner());

    if let Some(mut process) = backend.take() {
        settings::log("stopping backend");
        if let Err(err) = process.stop() {
            settings::log(&format!("backend stop failed: {err}"));
        }
    }
}
