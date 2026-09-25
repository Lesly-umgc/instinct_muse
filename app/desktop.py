"""Frozen macOS app-service entry point, launched by the desktop shell."""
import os
from pathlib import Path

# macOS Finder starts GUI apps with a short PATH, not the user's shell PATH.
# Find the common CLI install locations without sourcing shell startup scripts.
home = Path.home()
extra = [home / ".opencode/bin", home / ".local/bin", home / ".bun/bin",
         home / ".npm-global/bin", Path("/opt/homebrew/bin"), Path("/usr/local/bin")]
os.environ["PATH"] = os.pathsep.join([*(str(p) for p in extra if p.is_dir()), os.environ.get("PATH", "")])

import uvicorn
from app.main import app

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")
