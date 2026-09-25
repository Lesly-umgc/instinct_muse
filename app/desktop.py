"""Frozen macOS app-service entry point, launched by the desktop shell."""
import logging
import os
from pathlib import Path
import sys
import traceback

# Finder/Dock do not inherit the login shell PATH. Do not run shell startup
# scripts: they can have side effects and aren't needed to locate known CLIs.
home = Path.home()
extra = [home / ".opencode/bin", home / ".local/bin", home / ".bun/bin",
         home / ".npm-global/bin", home / ".npm/bin", home / "bin",
         Path("/opt/homebrew/bin"), Path("/usr/local/bin")]
os.environ["PATH"] = os.pathsep.join([*(str(p) for p in extra if p.is_dir()), os.environ.get("PATH", "")])

log_dir = home / ".instinct_muse"
log_dir.mkdir(parents=True, exist_ok=True)
logging.basicConfig(filename=log_dir / "service.log", level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s %(message)s", force=True)
log = logging.getLogger("instinct_muse.desktop")
log.info("Starting service, Python=%s", sys.version.split()[0])

if __name__ == "__main__":
    try:
        import uvicorn
        from app.main import app
        uvicorn.run(app, host="127.0.0.1", port=18764, log_level="info",
                    log_config=None, access_log=False)
    except BaseException:
        log.exception("Service startup failed")
        traceback.print_exc()
        raise
