"""The ledger: append-only events + purchases + household state.

SQLite by default (data/runtime/ledger.db). The SQL is plain enough to point at SingleStore
(MySQL wire protocol) by setting SINGLESTORE_URL; see server/ledger/singlestore.py.
"""
from __future__ import annotations

import json
import os
import pathlib
import sqlite3
import threading
import time
import uuid
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[2]

SCHEMA = [
    """CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, run_id TEXT, actor TEXT, kind TEXT,
        subject TEXT, vendor TEXT, data TEXT)""",
    """CREATE TABLE IF NOT EXISTS purchases (
        id TEXT PRIMARY KEY, ts REAL, run_id TEXT, buyer TEXT, recipient_id TEXT, recipient_name TEXT,
        sku TEXT, item TEXT, store TEXT, price REAL, status TEXT, receipt TEXT, evidence TEXT)""",
    """CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT)""",
]


class Ledger:
    def __init__(self, path: str | None = None):
        p = pathlib.Path(path or os.environ.get("LEDGER_PATH", ROOT / "data/runtime/ledger.db"))
        p.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(p), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.lock = threading.Lock()
        with self.lock:
            for s in SCHEMA:
                self.db.execute(s)
            self.db.commit()
        self.listeners: list = []

    # --- kv state -------------------------------------------------------------------------
    def get(self, k: str, default: Any = None) -> Any:
        row = self.db.execute("SELECT v FROM kv WHERE k = ?", (k,)).fetchone()
        return json.loads(row["v"]) if row else default

    def put(self, k: str, v: Any) -> None:
        with self.lock:
            self.db.execute("INSERT OR REPLACE INTO kv (k, v) VALUES (?, ?)", (k, json.dumps(v)))
            self.db.commit()

    # --- events ---------------------------------------------------------------------------
    def event(self, kind: str, actor: str, data: dict, *, run_id: str = "", subject: str = "",
              vendor: str = "") -> dict:
        ev = {"ts": time.time(), "run_id": run_id, "actor": actor, "kind": kind, "subject": subject,
              "vendor": vendor, "data": data}
        with self.lock:
            cur = self.db.execute(
                "INSERT INTO events (ts, run_id, actor, kind, subject, vendor, data) VALUES (?,?,?,?,?,?,?)",
                (ev["ts"], run_id, actor, kind, subject, vendor, json.dumps(data, default=str)))
            self.db.commit()
            ev["id"] = cur.lastrowid
        for fn in list(self.listeners):
            try:
                fn(ev)
            except Exception:
                pass
        return ev

    def events(self, since_id: int = 0, limit: int = 500) -> list[dict]:
        rows = self.db.execute("SELECT * FROM events WHERE id > ? ORDER BY id LIMIT ?", (since_id, limit)).fetchall()
        return [dict(r) | {"data": json.loads(r["data"])} for r in rows]

    # --- purchases ------------------------------------------------------------------------
    def add_purchase(self, *, run_id: str, buyer: str, recipient_id: str, recipient_name: str, sku: str,
                     item: str, store: str, price: float, status: str, evidence: dict) -> dict:
        pid = "SL-" + uuid.uuid4().hex[:8].upper()
        receipt = pid if status == "completed" else ""
        with self.lock:
            self.db.execute(
                "INSERT INTO purchases (id, ts, run_id, buyer, recipient_id, recipient_name, sku, item, store, price,"
                " status, receipt, evidence) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (pid, time.time(), run_id, buyer, recipient_id, recipient_name, sku, item, store, price, status,
                 receipt, json.dumps(evidence, default=str)))
            self.db.commit()
        return self.purchase(pid)

    def purchase(self, pid: str) -> dict:
        r = self.db.execute("SELECT * FROM purchases WHERE id = ?", (pid,)).fetchone()
        return dict(r) | {"evidence": json.loads(r["evidence"])} if r else {}

    def set_status(self, pid: str, status: str) -> dict:
        with self.lock:
            self.db.execute("UPDATE purchases SET status = ?, receipt = CASE WHEN ? = 'completed' THEN id ELSE receipt END"
                            " WHERE id = ?", (status, status, pid))
            self.db.commit()
        return self.purchase(pid)

    def purchases(self) -> list[dict]:
        rows = self.db.execute("SELECT * FROM purchases ORDER BY ts").fetchall()
        return [dict(r) | {"evidence": json.loads(r["evidence"])} for r in rows]

    def spent(self) -> dict[str, float]:
        """Completed and pending purchases both hold budget (pending can't be double-spent)."""
        out: dict[str, float] = {}
        for r in self.db.execute("SELECT buyer, SUM(price) s FROM purchases WHERE status IN ('completed','pending_approval') GROUP BY buyer"):
            out[r["buyer"]] = float(r["s"] or 0)
        return out

    def claimed(self) -> set[tuple[str, str]]:
        return {(r["recipient_id"], r["sku"]) for r in self.db.execute(
            "SELECT recipient_id, sku FROM purchases WHERE status IN ('completed','pending_approval')")}

    def reset(self) -> None:
        with self.lock:
            for t in ("events", "purchases", "kv"):
                self.db.execute(f"DELETE FROM {t}")
            self.db.commit()


def view_purchase(p: dict, viewer: dict | None) -> dict:
    """Spoiler-free audit: parents see everything; a recipient sees that a gift exists, not what it is."""
    if viewer is None or viewer.get("role") == "parent" or viewer.get("id") == p["buyer"]:
        return p | {"hidden": False}
    if p["recipient_id"] == viewer.get("id"):
        return {"id": p["id"], "ts": p["ts"], "buyer": p["buyer"], "recipient_id": p["recipient_id"],
                "recipient_name": p["recipient_name"], "store": p["store"], "status": p["status"],
                "item": "A gift for you (hidden until Dec 25)", "price": None, "sku": None, "evidence": None,
                "receipt": p["receipt"], "hidden": True}
    # other givers see it, so nobody buys the same thing twice
    return p | {"hidden": False}
