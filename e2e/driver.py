"""End-to-end driver for the Instinct Muse macOS app, run on a CI Mac runner.

Stages:
  main          health, engine, model list, CORS preflight, chat turn, auto-title,
                file-creation artifact, delete conversation
  arm-restart   create a chat and send one slow message fire-and-forget; the
                workflow kills the app right after, then relaunches it
  post-restart  the interrupted-turn sweep must have marked that chat

Usage: python3 e2e/driver.py --stage main [--base http://127.0.0.1:18764]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import urllib.request

import websockets

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}", flush=True)
    if not ok:
        summarize_and_exit()


def summarize_and_exit() -> None:
    failed = [r for r in RESULTS if not r[1]]
    print(f"--- {len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed ---", flush=True)
    sys.exit(1 if failed else 0)


def req(base: str, method: str, path: str, body: dict | None = None,
        timeout: float = 60.0) -> tuple[int, object]:
    r = urllib.request.Request(
        base + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json"}, method=method)
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            raw = resp.read().decode()
            return resp.status, json.loads(raw) if raw else ""
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:400]


async def wait_health(base: str, tries: int = 90) -> bool:
    for _ in range(tries):
        try:
            status, _ = req(base, "GET", "/health", timeout=5)
            if status == 200:
                return True
        except OSError:
            pass
        await asyncio.sleep(2)
    return False


async def ws_turn(base: str, cid: str, text: str, timeout: float = 600.0) -> dict:
    ws_base = base.replace("http", "ws", 1)
    async with websockets.connect(f"{ws_base}/ws/conversations/{cid}") as ws:
        await ws.send(json.dumps({"type": "message", "text": text}))
        async with asyncio.timeout(timeout):
            async for raw in ws:
                if json.loads(raw).get("type") == "message_done":
                    break
    status, conv = req(base, "GET", f"/api/conversations/{cid}")
    assert status == 200, f"conversation fetch after turn: {status} {conv}"
    return conv  # type: ignore[return-value]


def last_assistant_text(conv: dict) -> str:
    for m in reversed(conv.get("messages", [])):
        if m.get("role") == "assistant":
            return m.get("text", "")
    return ""


async def stage_main(base: str) -> None:
    check("service healthy", await wait_health(base), base)

    status, engines = req(base, "GET", "/api/engines")
    oc = [e for e in engines.get("engines", []) if e.get("id") == "opencode_server"]  # type: ignore[union-attr]
    check("opencode_server engine available", bool(oc and oc[0].get("available")),
          (oc[0].get("detail") or oc[0].get("reason", "")) if oc else "engine missing")

    status, models = req(base, "GET", "/api/models?engine=opencode_server", timeout=120)
    mlist = models.get("models", []) if status == 200 else []  # type: ignore[union-attr]
    spark = [m for m in mlist if m.get("model_id") == "muse-spark-1.3-contributor-free"]
    check("Muse Spark 1.3 Free listed", bool(spark),
          spark[0]["label"] if spark else f"{len(mlist)} models, none matched")

    # CORS preflight regression (v0.1.5): the Tauri webview origin must be
    # allowed to DELETE, or every webview delete dies with 'Load failed'.
    r = urllib.request.Request(base + "/api/conversations/nope", method="OPTIONS", headers={
        "Origin": "https://tauri.localhost",
        "Access-Control-Request-Method": "DELETE",
        "Access-Control-Request-Headers": "content-type"})
    try:
        with urllib.request.urlopen(r, timeout=10) as resp:
            allow, code = resp.headers.get("access-control-allow-methods", ""), resp.status
    except urllib.error.HTTPError as e:
        allow, code = e.headers.get("access-control-allow-methods", ""), e.code
    check("CORS preflight allows DELETE from tauri origin",
          code == 200 and ("DELETE" in allow or "*" in allow), f"{code} allow={allow}")

    status, conv = req(base, "POST", "/api/conversations",
                       {"title": "New chat", "engine": "opencode_server",
                        "model": "opencode/muse-spark-1.3-contributor-free"})
    cid = conv.get("id") if status == 201 else None  # type: ignore[union-attr]
    check("create conversation", status == 201 and bool(cid), str(conv)[:120])

    conv = await ws_turn(base, cid, "Reply with exactly: E2E_CHAT_OK")
    check("chat reply received", "E2E_CHAT_OK" in last_assistant_text(conv),
          last_assistant_text(conv)[:80])

    status, clist = req(base, "GET", "/api/conversations")
    mine = [c for c in clist.get("conversations", []) if c.get("id") == cid]  # type: ignore[union-attr]
    check("auto-title applied", bool(mine and mine[0].get("title") not in ("", "New chat")),
          mine[0].get("title", "?") if mine else "conversation missing")

    status, before = req(base, "GET", "/api/artifacts")
    n_before = len(before.get("artifacts", []))  # type: ignore[union-attr]
    await ws_turn(base, cid,
        "Create a text file named e2e_artifact.txt containing exactly 'hello muse'. Then stop.")
    for _ in range(30):
        status, appr = req(base, "GET", "/api/approvals?status=pending")
        pending = appr.get("approvals", [])  # type: ignore[union-attr]
        if not pending:
            break
        for a in pending:
            req(base, "POST", f"/api/approvals/{a['id']}", {"decision": "allow"})
        await asyncio.sleep(2)
    status, after = req(base, "GET", "/api/artifacts")
    n_after = len(after.get("artifacts", []))  # type: ignore[union-attr]
    check("file creation captured as artifact", n_after > n_before,
          f"{n_before} -> {n_after} artifacts")

    status, _ = req(base, "DELETE", f"/api/conversations/{cid}")
    status2, clist = req(base, "GET", "/api/conversations")
    gone = all(c.get("id") != cid for c in clist.get("conversations", []))  # type: ignore[union-attr]
    check("delete conversation", status == 204 and gone, f"delete={status} gone={gone}")

    summarize_and_exit()


async def stage_arm_restart(base: str) -> None:
    check("service healthy", await wait_health(base), base)
    status, conv = req(base, "POST", "/api/conversations",
                       {"title": "e2e-restart", "engine": "opencode_server",
                        "model": "opencode/muse-spark-1.3-contributor-free"})
    cid = conv.get("id") if status == 201 else None  # type: ignore[union-attr]
    check("restart chat created", bool(cid), str(conv)[:120])
    with open("/tmp/e2e_restart_cid", "w") as f:
        f.write(cid)
    # Fire and forget: the service runs the turn in the background, so closing
    # the socket does not cancel it. The workflow kills the app right after.
    ws_base = base.replace("http", "ws", 1)
    async with websockets.connect(f"{ws_base}/ws/conversations/{cid}") as ws:
        await ws.send(json.dumps({"type": "message", "text":
            "Write a detailed 1500-word essay about the history of personal computing."}))
        await asyncio.sleep(0.3)
    print(f"armed restart test with cid={cid}", flush=True)
    summarize_and_exit()


async def stage_post_restart(base: str) -> None:
    check("service healthy after relaunch", await wait_health(base), base)
    with open("/tmp/e2e_restart_cid") as f:
        cid = f.read().strip()
    status, conv = req(base, "GET", f"/api/conversations/{cid}")
    text = last_assistant_text(conv) if status == 200 else ""
    check("interrupted turn marked after restart",
          "interrupted when the app quit" in text, text[:100])
    summarize_and_exit()


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:18764")
    ap.add_argument("--stage", required=True,
                    choices=["main", "arm-restart", "post-restart"])
    args = ap.parse_args()
    if args.stage == "main":
        await stage_main(args.base)
    elif args.stage == "arm-restart":
        await stage_arm_restart(args.base)
    else:
        await stage_post_restart(args.base)


if __name__ == "__main__":
    asyncio.run(main())
