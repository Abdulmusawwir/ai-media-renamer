//! Shell-local state and logging.
//!
//! Shell preferences (`desktop.json`) are added in the tray/settings task; this
//! module currently owns the shell log under `<data_root>/logs/desktop-shell.log`.

use std::fs::{self, File, OpenOptions};
use std::io::Write;
use std::path::{Path, PathBuf};
use std::sync::{Mutex, OnceLock};
use std::time::{SystemTime, UNIX_EPOCH};

use serde::{Deserialize, Serialize};

use tauri::Manager;

static LOG_FILE: OnceLock<Mutex<File>> = OnceLock::new();

pub fn logs_dir(data_dir: &Path) -> PathBuf {
    data_dir.join("logs")
}

pub fn shell_log_path(data_dir: &Path) -> PathBuf {
    logs_dir(data_dir).join("desktop-shell.log")
}

/// Open the shell log for append. Safe to call once at startup.
pub fn init_logging(data_dir: &Path) -> Result<(), String> {
    let dir = logs_dir(data_dir);
    fs::create_dir_all(&dir)
        .map_err(|err| format!("could not create log directory {}: {err}", dir.display()))?;

    let path = shell_log_path(data_dir);
    let file = OpenOptions::new()
        .create(true)
        .append(true)
        .open(&path)
        .map_err(|err| format!("could not open shell log {}: {err}", path.display()))?;
    let _ = LOG_FILE.set(Mutex::new(file));
    Ok(())
}

/// Write one timestamped shell log line. Falls back to stderr if the log could
/// not be opened.
pub fn log(message: &str) {
    let seconds = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_secs())
        .unwrap_or(0);

    if let Some(file) = LOG_FILE.get() {
        if let Ok(mut file) = file.lock() {
            let _ = writeln!(file, "[{seconds}] {message}");
            let _ = file.flush();
            return;
        }
    }

    eprintln!("[{seconds}] {message}");
}

/// Shell (tray/window) preferences persisted in the Tauri app config directory
/// as `desktop.json`. Kept separate from the Python `config.json` because it
/// describes the shell, not the backend.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct ShellSettings {
    #[serde(default = "default_close_to_tray")]
    pub close_to_tray: bool,
}

fn default_close_to_tray() -> bool {
    true
}

impl Default for ShellSettings {
    fn default() -> Self {
        Self {
            close_to_tray: true,
        }
    }
}

/// Path to `desktop.json` in the Tauri app config directory.
pub fn shell_settings_path(app: &tauri::AppHandle) -> Result<PathBuf, String> {
    let dir = app
        .path()
        .app_config_dir()
        .map_err(|err| format!("could not resolve app config directory: {err}"))?;
    fs::create_dir_all(&dir).map_err(|err| {
        format!(
            "could not create app config directory {}: {err}",
            dir.display()
        )
    })?;
    Ok(dir.join("desktop.json"))
}

/// Load shell settings, falling back to defaults when the file is missing or
/// malformed.
pub fn load_shell_settings(app: &tauri::AppHandle) -> ShellSettings {
    let path = match shell_settings_path(app) {
        Ok(path) => path,
        Err(_) => return ShellSettings::default(),
    };
    let contents = match fs::read_to_string(&path) {
        Ok(contents) => contents,
        Err(_) => return ShellSettings::default(),
    };
    serde_json::from_str(&contents).unwrap_or_default()
}

/// Persist shell settings, creating the parent directory if needed.
pub fn save_shell_settings(app: &tauri::AppHandle, settings: &ShellSettings) -> Result<(), String> {
    let path = shell_settings_path(app)?;
    let json = serde_json::to_string_pretty(settings)
        .map_err(|err| format!("could not serialize shell settings: {err}"))?;
    fs::write(&path, json)
        .map_err(|err| format!("could not write shell settings {}: {err}", path.display()))?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn default_close_to_tray_is_true() {
        let settings = ShellSettings::default();
        assert!(settings.close_to_tray);
    }

    #[test]
    fn missing_file_defaults_to_true() {
        let settings: ShellSettings = serde_json::from_str("{}").unwrap_or_default();
        assert!(settings.close_to_tray);
    }

    #[test]
    fn malformed_file_defaults_to_true() {
        let settings: ShellSettings = serde_json::from_str("{not json").unwrap_or_default();
        assert!(settings.close_to_tray);
    }

    #[test]
    fn round_trip_preserves_value() {
        let settings = ShellSettings {
            close_to_tray: false,
        };
        let json = serde_json::to_string(&settings).expect("serialize");
        let parsed: ShellSettings = serde_json::from_str(&json).expect("deserialize");
        assert!(!parsed.close_to_tray);
        assert_eq!(settings, parsed);
    }
}
