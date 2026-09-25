#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::{fs::{self, OpenOptions}, io::Write, path::PathBuf};
use tauri_plugin_shell::{process::CommandEvent, ShellExt};

fn log_path() -> PathBuf {
    let home = std::env::var_os("HOME").unwrap_or_else(|| ".".into());
    PathBuf::from(home).join(".instinct_muse").join("desktop.log")
}

fn log_line(path: &PathBuf, line: &str) {
    if let Some(parent) = path.parent() { let _ = fs::create_dir_all(parent); }
    if let Ok(mut file) = OpenOptions::new().create(true).append(true).open(path) {
        let _ = writeln!(file, "{}", line);
    }
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .setup(|app| {
            let path = log_path();
            log_line(&path, "--- Instinct Muse starting ---");
            // Report an occupied port before starting; never reuse another app's service.
            match std::net::TcpListener::bind("127.0.0.1:18764") {
                Ok(listener) => drop(listener),
                Err(error) => {
                    log_line(&path, &format!("Port 18764 is unavailable: {}", error));
                    return Ok(()); // UI shows the health/identity failure and log path.
                }
            }
            let (mut events, child) = match app.shell().sidecar("muse-service")?.spawn() {
                Ok(started) => started,
                Err(error) => {
                    log_line(&path, &format!("Sidecar spawn failed: {}", error));
                    return Ok(());
                }
            };
            log_line(&path, &format!("service spawned (pid {})", child.pid()));
            tauri::async_runtime::spawn(async move {
                let _child = child;
                while let Some(event) = events.recv().await {
                    match event {
                        CommandEvent::Stderr(bytes) => log_line(&path, &format!("service stderr: {}", String::from_utf8_lossy(&bytes).trim_end())),
                        CommandEvent::Stdout(bytes) => log_line(&path, &format!("service stdout: {}", String::from_utf8_lossy(&bytes).trim_end())),
                        CommandEvent::Terminated(status) => log_line(&path, &format!("service exited: {:?}", status)),
                        _ => {}
                    }
                }
            });
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running instinct_muse");
}
