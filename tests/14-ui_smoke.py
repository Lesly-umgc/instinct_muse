"""Drive the built UI with real browser clicks and typed search text.

This is a Linux/browser regression check, not an installed macOS app test.
Run after `cd ui && npm ci && npm run build` with:
`python -m playwright install chromium && python tests/ui_smoke.py`.
"""
from __future__ import annotations

import os
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

from app.store import Store

BASE = "http://127.0.0.1:18764"


def main() -> None:
    with tempfile.TemporaryDirectory() as directory:
        db = str(Path(directory) / "test.db")
        store = Store(db)
        conv = store.create_conversation("Search target chat", "zen_api")
        store.add_message(conv["id"], "assistant", "Unique lighthouse phrase")
        store.add_artifact("document", str(Path(directory) / "lighthouse.md"),
                           "lighthouse.md", "A sample document")
        store.create_goal("Lighthouse goal")
        store.add_idea("Lighthouse idea", "A useful idea")
        store.close()
        env = {**os.environ, "DB_PATH": db, "OPENCODE_BINARY": "/bin/false"}
        server = subprocess.Popen([os.environ.get("MUSE_TEST_PYTHON", "python"), "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1",
                                   "--port", "18764"], env=env)
        try:
            for _ in range(80):
                try:
                    urllib.request.urlopen(BASE + "/health", timeout=1)
                    break
                except OSError:
                    time.sleep(.25)
            else:
                raise RuntimeError("test service did not start")

            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True, executable_path=os.environ.get("MUSE_TEST_CHROME") or None, args=["--no-sandbox"] if os.environ.get("MUSE_TEST_CHROME") else [])
                page = browser.new_page(viewport={"width": 1280, "height": 800})
                page.goto(BASE, wait_until="networkidle")
                search = page.get_by_role("button", name="Search", exact=True)
                search.click()
                page.get_by_role("textbox", name="Search", exact=True).fill("Lighthouse")
                page.get_by_role("button", name="Open artifact: lighthouse.md").click()
                page.get_by_text("A sample document").wait_for(timeout=5000)
                page.get_by_role("button", name="Close", exact=True).click()
                search.click()
                page.get_by_role("textbox", name="Search", exact=True).fill("Lighthouse")
                page.get_by_role("button", name="Open goal: Lighthouse goal").click()
                page.get_by_role("heading", name="Lighthouse goal").last.wait_for(timeout=5000)
                page.get_by_role("button", name="Close", exact=True).click()
                search.click()
                page.get_by_role("textbox", name="Search", exact=True).fill("Lighthouse")
                page.get_by_role("button", name="Open idea: Lighthouse idea").click()
                page.get_by_role("dialog", name="Lighthouse idea").wait_for(timeout=5000)
                page.get_by_role("button", name="Close idea").click()
                search.click()
                page.get_by_role("textbox", name="Search", exact=True).fill("Lighthouse")
                page.get_by_role("button", name="Open chat: Search target chat").click()
                page.get_by_text("Unique lighthouse phrase").wait_for(timeout=5000)
                browser.close()
            print("PASS: search opened exact chat, artifact, goal and idea by UI click")
        finally:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=5)


if __name__ == "__main__":
    main()
