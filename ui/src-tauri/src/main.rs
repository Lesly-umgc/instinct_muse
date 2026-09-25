#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

// The Python app service (uvicorn) runs as a sidecar / separate process and
// serves the API on 127.0.0.1:8000. The Tauri shell loads the built UI, which
// talks to that loopback API. Tauri's capability system gates frontend access
// to native APIs; it is NOT a sandbox for agent commands - tool approvals live
// in the app service's broker.
fn main() {
    tauri::Builder::default()
        .run(tauri::generate_context!())
        .expect("error while running instinct_muse");
}
