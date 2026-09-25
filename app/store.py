"""SQLite app state: conversations, messages, artifacts (Library), approvals, events.

The application service owns these records independently of any engine, so
engines stay swappable. Engine session IDs are stored on the conversation row;
the normalized transcript lives here, not in the engine.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    engine TEXT NOT NULL,
    model TEXT,
    engine_session_id TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id),
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS artifacts (
    id TEXT PRIMARY KEY,
    conversation_id TEXT REFERENCES conversations(id),
    kind TEXT NOT NULL,
    path TEXT NOT NULL,
    title TEXT NOT NULL,
    content TEXT,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS approvals (
    id TEXT PRIMARY KEY,
    conversation_id TEXT REFERENCES conversations(id),
    engine_permission_id TEXT,
    action TEXT NOT NULL,
    detail TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at REAL NOT NULL,
    resolved_at REAL
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT,
    type TEXT NOT NULL,
    payload TEXT NOT NULL,
    created_at REAL NOT NULL
);
"""


def _now() -> float:
    return time.time()


def _uid() -> str:
    return uuid.uuid4().hex[:16]


class Store:
    def __init__(self, path: str):
        self._lock = threading.Lock()
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        with self._lock, self._db:
            self._db.executescript(SCHEMA)

    def close(self) -> None:
        self._db.close()

    def _rows(self, sql: str, args: tuple = ()) -> list[dict[str, Any]]:
        with self._lock:
            cur = self._db.execute(sql, args)
            return [dict(r) for r in cur.fetchall()]

    def _one(self, sql: str, args: tuple = ()) -> dict[str, Any] | None:
        rows = self._rows(sql, args)
        return rows[0] if rows else None

    def _exec(self, sql: str, args: tuple = ()) -> None:
        with self._lock, self._db:
            self._db.execute(sql, args)

    # Conversations -----------------------------------------------------
    def create_conversation(self, title: str, engine: str, model: str | None = None,
                            engine_session_id: str | None = None) -> dict[str, Any]:
        cid, ts = _uid(), _now()
        self._exec(
            "INSERT INTO conversations (id, title, engine, model, engine_session_id, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?)",
            (cid, title, engine, model, engine_session_id, ts, ts))
        return self.get_conversation(cid)  # type: ignore[return-value]

    def get_conversation(self, cid: str) -> dict[str, Any] | None:
        return self._one("SELECT * FROM conversations WHERE id=?", (cid,))

    def list_conversations(self) -> list[dict[str, Any]]:
        return self._rows("SELECT * FROM conversations ORDER BY updated_at DESC")

    def set_engine_session(self, cid: str, engine_session_id: str) -> None:
        self._exec("UPDATE conversations SET engine_session_id=? WHERE id=?",
                   (engine_session_id, cid))

    def touch_conversation(self, cid: str, title: str | None = None) -> None:
        if title:
            self._exec("UPDATE conversations SET updated_at=?, title=? WHERE id=?",
                       (_now(), title, cid))
        else:
            self._exec("UPDATE conversations SET updated_at=? WHERE id=?", (_now(), cid))

    # Messages ----------------------------------------------------------
    def add_message(self, cid: str, role: str, content: str) -> dict[str, Any]:
        mid, ts = _uid(), _now()
        self._exec(
            "INSERT INTO messages (id, conversation_id, role, content, created_at) VALUES (?,?,?,?,?)",
            (mid, cid, role, content, ts))
        self.touch_conversation(cid)
        return {"id": mid, "conversation_id": cid, "role": role, "content": content, "created_at": ts}

    def list_messages(self, cid: str) -> list[dict[str, Any]]:
        return self._rows("SELECT * FROM messages WHERE conversation_id=? ORDER BY created_at", (cid,))

    # Artifacts (Library) -------------------------------------------------
    def add_artifact(self, kind: str, path: str, title: str, content: str | None = None,
                     conversation_id: str | None = None) -> dict[str, Any]:
        aid, ts = _uid(), _now()
        self._exec(
            "INSERT INTO artifacts (id, conversation_id, kind, path, title, content, created_at)"
            " VALUES (?,?,?,?,?,?,?)",
            (aid, conversation_id, kind, path, title, content, ts))
        return self.get_artifact(aid)  # type: ignore[return-value]

    def get_artifact(self, aid: str) -> dict[str, Any] | None:
        return self._one("SELECT * FROM artifacts WHERE id=?", (aid,))

    def find_artifact_by_path(self, path: str) -> dict[str, Any] | None:
        return self._one("SELECT * FROM artifacts WHERE path=?", (path,))

    def list_artifacts(self, kind: str | None = None) -> list[dict[str, Any]]:
        if kind:
            return self._rows("SELECT * FROM artifacts WHERE kind=? ORDER BY created_at DESC", (kind,))
        return self._rows("SELECT * FROM artifacts ORDER BY created_at DESC")

    # Approvals -----------------------------------------------------------
    def add_approval(self, action: str, detail: str, conversation_id: str | None = None,
                     engine_permission_id: str | None = None) -> dict[str, Any]:
        aid, ts = _uid(), _now()
        self._exec(
            "INSERT INTO approvals (id, conversation_id, engine_permission_id, action, detail, status, created_at)"
            " VALUES (?,?,?,?,?,'pending',?)",
            (aid, conversation_id, engine_permission_id, action, detail, ts))
        return self.get_approval(aid)  # type: ignore[return-value]

    def get_approval(self, aid: str) -> dict[str, Any] | None:
        return self._one("SELECT * FROM approvals WHERE id=?", (aid,))

    def resolve_approval(self, aid: str, status: str) -> dict[str, Any] | None:
        self._exec("UPDATE approvals SET status=?, resolved_at=? WHERE id=?",
                   (status, _now(), aid))
        return self.get_approval(aid)

    def list_approvals(self, status: str | None = None) -> list[dict[str, Any]]:
        if status:
            return self._rows("SELECT * FROM approvals WHERE status=? ORDER BY created_at DESC", (status,))
        return self._rows("SELECT * FROM approvals ORDER BY created_at DESC")

    # Event log -----------------------------------------------------------
    def log_event(self, type_: str, payload: dict[str, Any], conversation_id: str | None = None) -> None:
        self._exec("INSERT INTO events (conversation_id, type, payload, created_at) VALUES (?,?,?,?)",
                   (conversation_id, type_, json.dumps(payload), _now()))

    def list_events(self, conversation_id: str | None = None) -> list[dict[str, Any]]:
        if conversation_id:
            return self._rows("SELECT * FROM events WHERE conversation_id=? ORDER BY id", (conversation_id,))
        return self._rows("SELECT * FROM events ORDER BY id")
