#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::{
    fs::{self, OpenOptions},
    io::{BufRead, BufReader, Write},
    path::PathBuf,
    process::{Child, Command, Stdio},
    sync::{Arc, Mutex},
    thread,
};

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

/// The service ships unpacked (PyInstaller onedir) next to the app executable
/// so every Mach-O in the bundle is signed with the same identity.
fn service_exe() -> Option<PathBuf> {
    let exe = std::env::current_exe().ok()?;
    let dir = exe.parent()?; // Contents/MacOS
    let candidate = dir.join("muse-service").join("muse-service");
    candidate.is_file().then_some(candidate)
}

fn pipe_to_log<R: std::io::Read + Send + 'static>(stream: R, path: PathBuf, tag: &'static str) {
    thread::spawn(move || {
        for line in BufReader::new(stream).lines().map_while(Result::ok) {
            log_line(&path, &format!("service {}: {}", tag, line));
        }
    });
}

fn main() {
    let service_child: Arc<Mutex<Option<Child>>> = Arc::new(Mutex::new(None));
    let app = tauri::Builder::default()
        .setup({
            let service_child = Arc::clone(&service_child);
            move |_app| {
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
                let Some(service) = service_exe() else {
                    log_line(&path, "Bundled service not found next to the app executable");
                    return Ok(());
                };
                log_line(&path, &format!("Spawning service: {}", service.display()));
                let mut child = match Command::new(&service)
                    .stdout(Stdio::piped())
                    .stderr(Stdio::piped())
                    .spawn()
                {
                    Ok(child) => child,
                    Err(error) => {
                        log_line(&path, &format!("Service spawn failed: {}", error));
                        return Ok(());
                    }
                };
                log_line(&path, &format!("service spawned (pid {})", child.id()));
                if let Some(stdout) = child.stdout.take() { pipe_to_log(stdout, path.clone(), "stdout"); }
                if let Some(stderr) = child.stderr.take() { pipe_to_log(stderr, path.clone(), "stderr"); }
                *service_child.lock().unwrap() = Some(child);
                Ok(())
            }
        })
        .build(tauri::generate_context!())
        .expect("error while building instinct_muse");
    app.run(move |_handle, event| {
        if let tauri::RunEvent::Exit = event {
            // Never orphan the service: it holds port 18764 for the next launch.
            if let Some(child) = service_child.lock().unwrap().as_mut() {
                let _ = child.kill();
                let _ = child.wait();
            }
        }
    });
}
