//! Shell-local state and logging.
//!
//! Shell preferences (`desktop.json`) are added in the tray/settings task; this
//! module currently owns the shell log under `<data_root>/logs/desktop-shell.log`.

use std::fs::{self, File, OpenOptions};
use std::io::Write;
use std::path::{Path, PathBuf};
use std::sync::{Mutex, OnceLock};
use std::time::{SystemTime, UNIX_EPOCH};

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
