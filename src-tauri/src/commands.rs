//! Commands exposed to the SPA through the desktop bridge.

use std::sync::atomic::Ordering;

use tauri::{AppHandle, Manager, State};

use crate::settings::ShellSettings;
use crate::ShellState;

const RELEASE_PAGE: &str = "https://github.com/Abdulmusawwir/ai-media-renamer/releases/latest";

/// Called by the SPA once it has mounted. Shows the main window, closes the
/// splash, and navigates to the backend if the window is not already there.
#[tauri::command]
pub fn desktop_ready(app: AppHandle) -> Result<(), String> {
    let state = app.state::<ShellState>();
    let main = app
        .get_webview_window("main")
        .ok_or_else(|| "main window is not available".to_string())?;

    if let Some(port) = *state
        .port
        .lock()
        .map_err(|_| "shell state lock poisoned".to_string())?
    {
        let target = format!("http://127.0.0.1:{port}");
        let current = main.url().map(|url| url.to_string()).unwrap_or_default();
        if !current.starts_with(&target) {
            let url = target
                .parse()
                .map_err(|err| format!("invalid backend URL {target}: {err}"))?;
            main.navigate(url)
                .map_err(|err| format!("could not navigate to the backend: {err}"))?;
        }
    }

    main.show()
        .map_err(|err| format!("could not show the main window: {err}"))?;
    let _ = main.set_focus();

    if let Some(splash) = app.get_webview_window("splash") {
        let _ = splash.close();
    }

    state.ready.store(true, Ordering::SeqCst);
    Ok(())
}

/// Drain file paths queued by a second launch.
#[tauri::command]
pub fn pending_paths(state: State<'_, ShellState>) -> Vec<String> {
    let mut paths = state
        .pending_paths
        .lock()
        .unwrap_or_else(|poisoned| poisoned.into_inner());
    paths
        .drain(..)
        .map(|path| path.to_string_lossy().into_owned())
        .collect()
}

/// Release page used by the browser-mode update fallback.
#[tauri::command]
pub fn release_page_url() -> String {
    RELEASE_PAGE.to_string()
}

/// Busy-state snapshot returned by the backend's `/api/desktop/status`.
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct DesktopStatus {
    pub analysis_running: bool,
    pub commit_running: bool,
    pub model_downloads_running: bool,
    pub model_migration_running: bool,
    pub setup_running: bool,
    #[serde(default)]
    pub staging_count: usize,
}

/// Pure guard decision used by tray quit/setup/update flows.
pub fn should_block(status: &DesktopStatus) -> bool {
    status.analysis_running
        || status.commit_running
        || status.model_downloads_running
        || status.model_migration_running
        || status.setup_running
}

#[tauri::command]
pub fn get_shell_settings(app: AppHandle) -> ShellSettings {
    crate::settings::load_shell_settings(&app)
}

#[tauri::command]
pub fn set_close_to_tray(app: AppHandle, value: bool) -> Result<(), String> {
    let mut settings = crate::settings::load_shell_settings(&app);
    settings.close_to_tray = value;
    crate::settings::save_shell_settings(&app, &settings)
}

#[tauri::command]
pub fn open_logs(app: AppHandle) -> Result<(), String> {
    let data_dir = {
        let state = app.state::<ShellState>();
        state
            .data_dir
            .lock()
            .ok()
            .and_then(|guard| guard.clone())
            .unwrap_or_else(crate::backend::resolve_data_dir)
    };
    let logs = crate::settings::logs_dir(&data_dir);
    let _ = std::process::Command::new("explorer").arg(&logs).spawn();
    Ok(())
}

#[tauri::command]
pub fn open_data_folder(app: AppHandle) -> Result<(), String> {
    let data_dir = {
        let state = app.state::<ShellState>();
        state
            .data_dir
            .lock()
            .ok()
            .and_then(|guard| guard.clone())
            .unwrap_or_else(crate::backend::resolve_data_dir)
    };
    let _ = std::process::Command::new("explorer")
        .arg(&data_dir)
        .spawn();
    Ok(())
}

#[tauri::command]
pub fn get_backend_status(app: AppHandle) -> Result<DesktopStatus, String> {
    let (port, token) = {
        let state = app.state::<ShellState>();
        let port = *state
            .port
            .lock()
            .map_err(|_| "shell state lock poisoned".to_string())?;
        let token = state
            .token
            .lock()
            .map_err(|_| "shell state lock poisoned".to_string())?
            .clone();
        (port, token)
    };
    let port = port.ok_or_else(|| "backend is not running".to_string())?;
    let token = token.unwrap_or_default();
    let url = format!("http://127.0.0.1:{port}/api/desktop/status");
    let mut request = ureq::get(&url);
    if !token.is_empty() {
        request = request.set("Authorization", &format!("Bearer {token}"));
    }
    let response = request
        .timeout(std::time::Duration::from_secs(5))
        .call()
        .map_err(|err| format!("could not read desktop status: {err}"))?;
    let body = response
        .into_string()
        .map_err(|err| format!("could not read desktop status body: {err}"))?;
    serde_json::from_str(&body).map_err(|err| format!("invalid desktop status: {err}"))
}

#[tauri::command]
pub fn restart_app(app: AppHandle) {
    let state = app.state::<ShellState>();
    state.quitting.store(true, Ordering::SeqCst);
    {
        let mut backend = state
            .backend
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner());
        if let Some(mut process) = backend.take() {
            let _ = process.stop();
        }
    }
    let mut command = std::process::Command::new(std::env::current_exe().unwrap_or_default());
    for arg in std::env::args().skip(1) {
        command.arg(arg);
    }
    let _ = command.spawn();
    app.exit(0);
}

#[tauri::command]
pub fn quit_app(app: AppHandle) -> Result<(), String> {
    let state = app.state::<ShellState>();
    state.quitting.store(true, Ordering::SeqCst);
    {
        let mut backend = state
            .backend
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner());
        if let Some(mut process) = backend.take() {
            let _ = process.stop();
        }
    }
    app.exit(0);
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn status(
        analysis: bool,
        commit: bool,
        downloads: bool,
        migration: bool,
        setup: bool,
    ) -> DesktopStatus {
        DesktopStatus {
            analysis_running: analysis,
            commit_running: commit,
            model_downloads_running: downloads,
            model_migration_running: migration,
            setup_running: setup,
            staging_count: 0,
        }
    }

    #[test]
    fn should_block_when_analysis_running() {
        assert!(should_block(&status(true, false, false, false, false)));
    }

    #[test]
    fn should_block_when_commit_running() {
        assert!(should_block(&status(false, true, false, false, false)));
    }

    #[test]
    fn should_block_when_downloads_running() {
        assert!(should_block(&status(false, false, true, false, false)));
    }

    #[test]
    fn should_block_when_migration_running() {
        assert!(should_block(&status(false, false, false, true, false)));
    }

    #[test]
    fn should_block_when_setup_running() {
        assert!(should_block(&status(false, false, false, false, true)));
    }

    #[test]
    fn should_not_block_when_idle() {
        assert!(!should_block(&status(false, false, false, false, false)));
    }
}
