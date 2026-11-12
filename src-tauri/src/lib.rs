//! Tauri desktop shell for AI Media Renamer.

mod backend;
mod commands;
mod settings;

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
pub struct ShellState {
    pub backend: Mutex<Option<BackendProcess>>,
    pub port: Mutex<Option<u16>>,
    pub token: Mutex<Option<String>>,
    pub pending_paths: Mutex<Vec<PathBuf>>,
    pub ready: AtomicBool,
    pub failed: AtomicBool,
    pub data_dir: Mutex<Option<PathBuf>>,
}

impl Default for ShellState {
    fn default() -> Self {
        Self {
            backend: Mutex::new(None),
            port: Mutex::new(None),
            token: Mutex::new(None),
            pending_paths: Mutex::new(Vec::new()),
            ready: AtomicBool::new(false),
            failed: AtomicBool::new(false),
            data_dir: Mutex::new(None),
        }
    }
}

enum FailureChoice {
    Retry,
    Quit,
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
            commands::release_page_url
        ])
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
    let _ = settings::init_logging(&data_dir);

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

    if cfg!(debug_assertions) {
        settings::log("debug build: backend is not spawned; loading the Vite dev server");
        let window = create_main_window(&handle, None, None)?;
        window.show()?;
        window.set_focus()?;
        return Ok(());
    }

    let mut splash = Some(create_splash(&handle)?);
    loop {
        match start_backend(&handle) {
            Ok(()) => break,
            Err(err) => {
                settings::log(&format!("backend startup failed: {err}"));
                if let Some(window) = splash.take() {
                    let _ = window.close();
                }
                match show_failure_dialog(&handle, &err, &data_dir) {
                    FailureChoice::Retry => {
                        splash = Some(create_splash(&handle)?);
                    }
                    FailureChoice::Quit => {
                        let state = handle.state::<ShellState>();
                        state.failed.store(true, Ordering::SeqCst);
                        handle.exit(1);
                        return Ok(());
                    }
                }
            }
        }
    }

    let (port, token) = read_connection(&handle)?;
    create_main_window(&handle, Some(port), Some(&token))?;
    spawn_ready_fallback(handle.clone());
    Ok(())
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
        }
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
                if !backend::version_compatible(shell_version, &health.version, cfg!(debug_assertions))
                {
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
                        .map_err(|_| "shell state lock poisoned".to_string())? =
                        Some(token);
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
        builder = builder.initialization_script(&script);
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
    let version = serde_json::to_string(env!("CARGO_PKG_VERSION"))
        .unwrap_or_else(|_| "\"\"".to_string());
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

fn show_failure_dialog(app: &AppHandle, error: &str, data_dir: &Path) -> FailureChoice {
    use tauri_plugin_dialog::{
        DialogExt, MessageDialogButtons, MessageDialogKind, MessageDialogResult,
    };

    loop {
        let message = format!(
            "AI Media Renamer could not start its backend.\n\n{error}\n\nLogs: {}",
            settings::logs_dir(data_dir).display()
        );
        let result = app
            .dialog()
            .message(message)
            .title("AI Media Renamer")
            .kind(MessageDialogKind::Error)
            .buttons(MessageDialogButtons::YesNoCancelCustom(
                "Retry".to_string(),
                "Open Logs".to_string(),
                "Quit".to_string(),
            ))
            .blocking_show_with_result();

        match result {
            MessageDialogResult::Yes => return FailureChoice::Retry,
            MessageDialogResult::No => open_logs(data_dir),
            MessageDialogResult::Custom(ref label) if label == "Retry" => {
                return FailureChoice::Retry;
            }
            MessageDialogResult::Custom(ref label) if label == "Open Logs" => {
                open_logs(data_dir);
            }
            _ => return FailureChoice::Quit,
        }
    }
}

fn open_logs(data_dir: &Path) {
    let logs = settings::logs_dir(data_dir);
    settings::log(&format!("opening logs folder {}", logs.display()));
    let _ = std::process::Command::new("explorer").arg(&logs).spawn();
}

fn stop_backend(app: &AppHandle) {
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
