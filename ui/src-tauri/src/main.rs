#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use tauri_plugin_shell::ShellExt;

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .setup(|app| {
            // Service is bundled in the DMG. Never launch a shell command or use the network
            // to download code. The service binds only to loopback; OpenCode remains optional.
            let (mut events, _child) = app.shell().sidecar("muse-service")?.spawn()?;
            tauri::async_runtime::spawn(async move {
                while let Some(event) = events.recv().await {
                    if let tauri_plugin_shell::process::CommandEvent::Stderr(bytes) = event {
                        eprintln!("service: {}", String::from_utf8_lossy(&bytes));
                    }
                }
            });
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running instinct_muse");
}
