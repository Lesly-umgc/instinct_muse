"""Browser worker: headless Chromium via Playwright, returns accessibility-tree snapshots.

The agent reads the AX tree (roles + names), not raw DOM, which keeps pages small
and cuts down on hidden-text prompt injection.
Run: uvicorn browser.worker:app --port 8100
"""
import json

from fastapi import FastAPI
from playwright.async_api import async_playwright
from pydantic import BaseModel

app = FastAPI(title="Instinct Muse browser worker")


class SnapshotRequest(BaseModel):
    url: str


@app.post("/snapshot")
async def snapshot(req: SnapshotRequest) -> dict[str, str]:
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.goto(req.url, wait_until="domcontentloaded")
        tree = await page.accessibility.snapshot()
        await browser.close()
    return {"snapshot": json.dumps(tree, indent=1)}
