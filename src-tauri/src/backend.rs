//! Backend process lifecycle: port selection, launch, health probing, and shutdown.

use std::collections::HashSet;
use std::fs::OpenOptions;
use std::io;
use std::net::TcpListener;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::thread;
use std::time::{Duration, Instant};

use serde::Deserialize;
use uuid::Uuid;

const LOOPBACK_HOST: &str = "127.0.0.1";
const HEALTH_POLL_INTERVAL: Duration = Duration::from_millis(250);
const HEALTH_REQUEST_TIMEOUT: Duration = Duration::from_secs(1);
const SHUTDOWN_WAIT: Duration = Duration::from_secs(5);

/// Media and document extensions accepted from second-instance file arguments.
const MEDIA_EXTENSIONS: &[&str] = &[
    ".mp4", ".mov", ".avi", ".mkv", ".webm", ".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp",
    ".tif", ".tiff", ".heic", ".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a", ".wma", ".opus",
    ".aiff", ".alac", ".ape", ".wv", ".pdf", ".docx", ".doc", ".txt", ".md", ".rtf", ".xlsx",
    ".csv", ".pptx",
];

#[derive(Debug, Clone, PartialEq, Eq, Deserialize)]
pub struct Health {
    pub status: String,
    pub version: String,
    #[serde(default)]
    pub desktop: bool,
}

/// A spawned backend child together with the Job Object that owns it.
///
/// The Job Object has `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`, so if the shell
/// crashes the backend (and any llama-server it started) is killed when the
/// handle closes.
pub struct BackendProcess {
    pub child: Child,
    pub job: JobHandle,
    port: u16,
    token: String,
}

impl BackendProcess {
    /// Ask the backend to stop, wait up to 5s, then kill it if still alive.
    pub fn stop(&mut self) -> Result<(), String> {
        let url = format!("http://{LOOPBACK_HOST}:{}/api/desktop/shutdown", self.port);
        let _ = ureq::post(&url)
            .set("Authorization", &format!("Bearer {}", self.token))
            .timeout(SHUTDOWN_WAIT)
            .call();

        let deadline = Instant::now() + SHUTDOWN_WAIT;
        loop {
            match self.child.try_wait() {
                Ok(Some(_)) => return Ok(()),
                Ok(None) if Instant::now() < deadline => thread::sleep(Duration::from_millis(100)),
                Ok(None) | Err(_) => break,
            }
        }

        self.child
            .kill()
            .map_err(|err| format!("could not kill backend process: {err}"))?;
        let _ = self.child.wait();
        Ok(())
    }
}

/// Pick a free loopback port by binding `127.0.0.1:0`, retrying up to three times.
pub fn pick_port() -> io::Result<u16> {
    let mut last_error = io::Error::other("could not bind a loopback port");
    for _ in 0..3 {
        match TcpListener::bind((LOOPBACK_HOST, 0)) {
            Ok(listener) => return listener.local_addr().map(|addr| addr.port()),
            Err(err) => last_error = err,
        }
    }
    Err(last_error)
}

/// Generate a per-launch token from two UUIDv4 values (64 hex characters).
pub fn generate_token() -> String {
    let first = Uuid::new_v4().simple().to_string();
    let second = Uuid::new_v4().simple().to_string();
    format!("{first}{second}")
}

/// Resolve the data root exactly as the Python backend does.
pub fn resolve_data_dir() -> PathBuf {
    if let Some(value) = std::env::var_os("AMR_DATA_DIR") {
        if !value.is_empty() {
            return PathBuf::from(value);
        }
    }
    if let Some(appdata) = std::env::var_os("APPDATA") {
        return PathBuf::from(appdata).join("ai-media-renamer");
    }
    if let Some(home) = std::env::var_os("USERPROFILE").or_else(|| std::env::var_os("HOME")) {
        return PathBuf::from(home)
            .join("AppData")
            .join("Roaming")
            .join("ai-media-renamer");
    }
    PathBuf::from(".").join("ai-media-renamer")
}

/// Keep only existing media/document files from command line arguments.
///
/// Flags, directories, missing paths, and non-media files are ignored.
/// Relative paths are resolved by the caller before this runs.
pub fn filter_path_args(args: &[String]) -> Vec<PathBuf> {
    let mut seen = HashSet::new();
    let mut paths = Vec::new();

    for arg in args {
        if arg.starts_with('-') {
            continue;
        }
        let path = Path::new(arg);
        if !path.is_file() {
            continue;
        }
        let Some(extension) = path.extension().and_then(|ext| ext.to_str()) else {
            continue;
        };
        let extension = format!(".{}", extension.to_ascii_lowercase());
        if !MEDIA_EXTENSIONS.contains(&extension.as_str()) {
            continue;
        }

        let canonical = dunce::canonicalize(path).unwrap_or_else(|_| path.to_path_buf());
        if seen.insert(canonical.clone()) {
            paths.push(canonical);
        }
    }

    paths
}

/// Release builds require an exact version match; debug builds continue.
pub fn version_compatible(shell: &str, backend: &str, debug: bool) -> bool {
    if shell == backend {
        return true;
    }
    if debug && std::env::var("AMR_SKIP_VERSION_CHECK").as_deref() == Ok("1") {
        return true;
    }
    debug
}

/// Launch `AIMediaRenamerBackend.exe` and assign it to a kill-on-close Job Object.
pub fn spawn_backend(port: u16, token: &str) -> Result<BackendProcess, String> {
    let data_dir = resolve_data_dir();
    let log_dir = data_dir.join("logs");
    std::fs::create_dir_all(&log_dir)
        .map_err(|err| format!("could not create log directory {}: {err}", log_dir.display()))?;

    let exe = backend_exe_path();
    if !exe.is_file() {
        return Err(format!(
            "backend executable not found at {}",
            exe.display()
        ));
    }

    let log_path = log_dir.join("backend-process.log");
    let stdout = OpenOptions::new()
        .create(true)
        .append(true)
        .open(&log_path)
        .map_err(|err| format!("could not open {}: {err}", log_path.display()))?;
    let stderr = stdout
        .try_clone()
        .map_err(|err| format!("could not duplicate backend log handle: {err}"))?;

    let mut command = Command::new(&exe);
    command
        .arg("--host")
        .arg(LOOPBACK_HOST)
        .arg("--port")
        .arg(port.to_string())
        .current_dir(&data_dir)
        .env("AMR_DATA_DIR", &data_dir)
        .env("AMR_DESKTOP_TOKEN", token)
        .stdin(Stdio::null())
        .stdout(Stdio::from(stdout))
        .stderr(Stdio::from(stderr));

    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        command.creation_flags(CREATE_NO_WINDOW);
    }

    let mut child = command
        .spawn()
        .map_err(|err| format!("could not start {}: {err}", exe.display()))?;

    match JobHandle::create_and_assign(&child) {
        Ok(job) => Ok(BackendProcess {
            child,
            job,
            port,
            token: token.to_string(),
        }),
        Err(err) => {
            let _ = child.kill();
            let _ = child.wait();
            Err(err)
        }
    }
}

/// Poll `/health` every 250ms until the timeout expires.
pub fn wait_for_health(port: u16, timeout: Duration) -> Result<Health, String> {
    let url = format!("http://{LOOPBACK_HOST}:{port}/health");
    let deadline = Instant::now() + timeout;
    let mut last_error = String::from("health check timed out");

    while Instant::now() < deadline {
        match ureq::get(&url).timeout(HEALTH_REQUEST_TIMEOUT).call() {
            Ok(response) => match response.into_string() {
                Ok(body) => match parse_health(&body) {
                    Ok(health) if health.status == "ok" => return Ok(health),
                    Ok(health) => {
                        last_error = format!("unhealthy status {:?}", health.status);
                    }
                    Err(err) => last_error = err,
                },
                Err(err) => last_error = format!("could not read health response: {err}"),
            },
            Err(err) => last_error = err.to_string(),
        }
        thread::sleep(HEALTH_POLL_INTERVAL);
    }

    Err(format!(
        "backend health check failed on port {port}: {last_error}"
    ))
}

/// Parse the `/health` JSON payload. Kept pure so it can be unit tested.
pub fn parse_health(body: &str) -> Result<Health, String> {
    serde_json::from_str(body).map_err(|err| format!("invalid health response: {err}"))
}

fn backend_exe_path() -> PathBuf {
    if let Some(path) = std::env::var_os("AMR_BACKEND_EXE") {
        return PathBuf::from(path);
    }

    let base = std::env::current_exe()
        .ok()
        .and_then(|path| path.parent().map(Path::to_path_buf))
        .unwrap_or_default();
    let bundled = base
        .join("AIMediaRenamerBackend")
        .join("AIMediaRenamerBackend.exe");
    if bundled.is_file() {
        return bundled;
    }

    let resources = base
        .join("resources")
        .join("AIMediaRenamerBackend")
        .join("AIMediaRenamerBackend.exe");
    if resources.is_file() {
        return resources;
    }

    bundled
}

#[cfg(windows)]
mod job {
    use std::io;
    use std::os::windows::io::AsRawHandle;
    use std::process::Child;

    use windows_sys::Win32::Foundation::{CloseHandle, HANDLE};
    use windows_sys::Win32::System::JobObjects::{
        AssignProcessToJobObject, CreateJobObjectW, JobObjectExtendedLimitInformation,
        SetInformationJobObject, JOBOBJECT_EXTENDED_LIMIT_INFORMATION,
        JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
    };

    /// Owns a Windows Job Object handle. Closing it kills every process assigned
    /// to the job (`JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`).
    ///
    /// The handle is stored as `isize` so the value is `Send`; it is only used
    /// from the process that created it and is protected by the `ShellState`
    /// mutex.
    pub struct JobHandle(isize);

    impl JobHandle {
        pub fn create_and_assign(child: &Child) -> Result<Self, String> {
            unsafe {
                let job = CreateJobObjectW(std::ptr::null(), std::ptr::null());
                if job.is_null() {
                    return Err(format!(
                        "could not create Job Object: {}",
                        io::Error::last_os_error()
                    ));
                }

                let mut info: JOBOBJECT_EXTENDED_LIMIT_INFORMATION = std::mem::zeroed();
                info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;

                let configured = SetInformationJobObject(
                    job,
                    JobObjectExtendedLimitInformation,
                    &info as *const _ as *const _,
                    std::mem::size_of::<JOBOBJECT_EXTENDED_LIMIT_INFORMATION>() as u32,
                );
                if configured == 0 {
                    let err = io::Error::last_os_error();
                    CloseHandle(job);
                    return Err(format!("could not configure Job Object: {err}"));
                }

                let process = child.as_raw_handle() as HANDLE;
                if AssignProcessToJobObject(job, process) == 0 {
                    let err = io::Error::last_os_error();
                    CloseHandle(job);
                    return Err(format!("could not assign backend to Job Object: {err}"));
                }

                Ok(Self(job as isize))
            }
        }
    }

    impl Drop for JobHandle {
        fn drop(&mut self) {
            unsafe {
                CloseHandle(self.0 as HANDLE);
            }
        }
    }
}

#[cfg(not(windows))]
mod job {
    use std::process::Child;

    pub struct JobHandle;

    impl JobHandle {
        pub fn create_and_assign(_child: &Child) -> Result<Self, String> {
            Ok(Self)
        }
    }
}

pub use job::JobHandle;

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use std::path::PathBuf;

    fn temp_dir() -> PathBuf {
        let path = std::env::temp_dir().join(format!("amr-backend-test-{}", Uuid::new_v4()));
        fs::create_dir_all(&path).expect("create temp dir");
        path
    }

    #[test]
    fn test_filter_path_args_keeps_existing_media() {
        let dir = temp_dir();
        let video = dir.join("clip.mp4");
        let document = dir.join("notes.txt");
        let unsupported = dir.join("installer.exe");
        fs::write(&video, b"video").expect("write video");
        fs::write(&document, b"document").expect("write document");
        fs::write(&unsupported, b"binary").expect("write unsupported");
        let missing = dir.join("missing.mp4");

        let args = vec![
            video.to_string_lossy().into_owned(),
            document.to_string_lossy().into_owned(),
            unsupported.to_string_lossy().into_owned(),
            missing.to_string_lossy().into_owned(),
            "--verbose".to_string(),
        ];
        let filtered = filter_path_args(&args);

        assert_eq!(filtered.len(), 2);
        assert!(filtered
            .iter()
            .any(|path| path.file_name().and_then(|name| name.to_str()) == Some("clip.mp4")));
        assert!(filtered
            .iter()
            .any(|path| path.file_name().and_then(|name| name.to_str()) == Some("notes.txt")));

        fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn test_filter_path_args_ignores_dirs() {
        let dir = temp_dir();
        let folder = dir.join("folder.mp4");
        fs::create_dir_all(&folder).expect("create folder");

        let args = vec![folder.to_string_lossy().into_owned()];
        let filtered = filter_path_args(&args);

        assert!(filtered.is_empty());
        fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn test_version_compatible_exact() {
        assert!(version_compatible("2.2.0", "2.2.0", false));
        assert!(version_compatible("2.2.0", "2.2.0", true));
    }

    #[test]
    fn test_version_compatible_mismatch_debug() {
        assert!(!version_compatible("2.2.0", "2.1.0", false));
        assert!(version_compatible("2.2.0", "2.1.0", true));
    }

    #[test]
    fn test_resolve_data_dir_override() {
        let dir = temp_dir();
        let original = std::env::var_os("AMR_DATA_DIR");
        std::env::set_var("AMR_DATA_DIR", &dir);

        assert_eq!(resolve_data_dir(), dir);

        match original {
            Some(value) => std::env::set_var("AMR_DATA_DIR", value),
            None => std::env::remove_var("AMR_DATA_DIR"),
        }
        fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn test_generate_token_length() {
        let token = generate_token();
        assert_eq!(token.len(), 64);
        assert!(token.chars().all(|ch| ch.is_ascii_hexdigit()));
    }

    #[test]
    fn test_parse_health_response() {
        let health =
            parse_health(r#"{"status":"ok","version":"2.2.0","desktop":true}"#).expect("parse");
        assert_eq!(health.status, "ok");
        assert_eq!(health.version, "2.2.0");
        assert!(health.desktop);
    }

    #[test]
    fn test_parse_health_rejects_malformed_response() {
        assert!(parse_health("not-json").is_err());
    }
}
