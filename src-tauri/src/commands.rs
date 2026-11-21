//! Commands exposed to the SPA through the desktop bridge.

use std::sync::atomic::Ordering;

use tauri::{AppHandle, Manager, State};

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
