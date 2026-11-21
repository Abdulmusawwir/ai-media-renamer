//! System tray, close-to-tray, and safe lifecycle entry points.

use tauri::menu::{Menu, MenuItem};
use tauri::tray::{MouseButton, TrayIconBuilder, TrayIconEvent};
use tauri::{AppHandle, Emitter, Manager};
use tauri_plugin_dialog::DialogExt;

use crate::backend;
use crate::commands::{get_backend_status, should_block};
use crate::settings::logs_dir;
use crate::ShellState;

pub fn build_tray(app: &AppHandle) -> tauri::Result<()> {
    let menu = Menu::with_items(
        app,
        &[
            &MenuItem::with_id(app, "show", "Show", true, None::<&str>)?,
            &MenuItem::with_id(
                app,
                "check_updates",
                "Check for Updates",
                true,
                None::<&str>,
            )?,
            &MenuItem::with_id(app, "setup", "Setup & Dependencies", true, None::<&str>)?,
            &MenuItem::with_id(app, "open_logs", "Open Logs", true, None::<&str>)?,
            &MenuItem::with_id(app, "open_data", "Open Data Folder", true, None::<&str>)?,
            &MenuItem::with_id(app, "quit", "Quit", true, None::<&str>)?,
        ],
    )?;

    let icon = app
        .default_window_icon()
        .cloned()
        .expect("default window icon is required for the tray");

    let _tray = TrayIconBuilder::with_id("main-tray")
        .icon(icon)
        .menu(&menu)
        .show_menu_on_left_click(false)
        .on_menu_event(|app, event| match event.id().as_ref() {
            "show" => show_main(app),
            "check_updates" => {
                if let Some(window) = app.get_webview_window("main") {
                    let _ = window.emit("desktop://check-updates", ());
                }
            }
            "setup" => run_setup(app.clone()),
            "open_logs" => open_logs(app),
            "open_data" => open_data_folder(app),
            "quit" => {
                let _ = crate::commands::quit_app(app.clone());
            }
            _ => {}
        })
        .on_tray_icon_event(|tray, event| {
            if let TrayIconEvent::DoubleClick {
                button: MouseButton::Left,
                ..
            } = event
            {
                show_main(tray.app_handle());
            }
        })
        .build(app)?;

    Ok(())
}

fn show_main(app: &AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.show();
        let _ = window.unminimize();
        let _ = window.set_focus();
    }
}

fn open_logs(app: &AppHandle) {
    let data_dir = resolve_data_dir(app);
    let logs = logs_dir(&data_dir);
    let _ = std::process::Command::new("explorer").arg(&logs).spawn();
}

fn open_data_folder(app: &AppHandle) {
    let data_dir = resolve_data_dir(app);
    let _ = std::process::Command::new("explorer")
        .arg(&data_dir)
        .spawn();
}

fn resolve_data_dir(app: &AppHandle) -> std::path::PathBuf {
    let state = app.state::<ShellState>();
    state
        .data_dir
        .lock()
        .ok()
        .and_then(|guard| guard.clone())
        .unwrap_or_else(backend::resolve_data_dir)
}

pub fn run_setup(app: AppHandle) {
    let app = app.clone();
    std::thread::spawn(move || {
        let busy = get_backend_status(app.clone())
            .map(|status| should_block(&status))
            .unwrap_or(false);
        if busy {
            let app_for_continue = app.clone();
            app.dialog()
                .message("An operation is still running. Setup may interrupt it.")
                .title("AI Media Renamer")
                .kind(tauri_plugin_dialog::MessageDialogKind::Warning)
                .buttons(tauri_plugin_dialog::MessageDialogButtons::OkCancelCustom(
                    "Continue".to_string(),
                    "Stay".to_string(),
                ))
                .show_with_result(move |result| {
                    if matches!(result, tauri_plugin_dialog::MessageDialogResult::Ok) {
                        run_setup_now(app_for_continue);
                    }
                });
            return;
        }
        run_setup_now(app);
    });
}

fn run_setup_now(app: AppHandle) {
    crate::stop_backend(&app);
    let exe = backend::backend_exe_path();
    let data_dir = resolve_data_dir(&app);
    let mut command = std::process::Command::new(&exe);
    command
        .arg("--setup")
        .arg("--no-launch")
        .arg("--no-update-check")
        .current_dir(&data_dir)
        .env("AMR_DATA_DIR", &data_dir);
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x08000000;
        command.creation_flags(CREATE_NO_WINDOW);
    }
    let status = command.status();
    let success = status.map(|s| s.success()).unwrap_or(false);
    if success {
        crate::commands::restart_app(app);
    } else {
        let app_for_retry = app.clone();
        app.dialog()
            .message("Setup did not complete successfully.")
            .title("AI Media Renamer")
            .kind(tauri_plugin_dialog::MessageDialogKind::Error)
            .buttons(tauri_plugin_dialog::MessageDialogButtons::OkCancelCustom(
                "Retry".to_string(),
                "Quit".to_string(),
            ))
            .show_with_result(move |result| {
                if matches!(result, tauri_plugin_dialog::MessageDialogResult::Ok) {
                    run_setup(app_for_retry.clone());
                } else {
                    let _ = crate::commands::quit_app(app_for_retry.clone());
                }
            });
    }
}
