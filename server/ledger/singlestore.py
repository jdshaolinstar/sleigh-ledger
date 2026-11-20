"""SingleStore-backed ledger (same interface as the SQLite one). The family pot, allocations, every
event, receipt and blocked attempt are rows here, so a parent (or a judge) can query the audit trail with SQL."""
from __future__ import annotations

import ssl
import threading
import urllib.parse

import pymysql
import pymysql.cursors

from server.ledger.store import Ledger

SCHEMA = [
    """CREATE TABLE IF NOT EXISTS events (
        id BIGINT AUTO_INCREMENT PRIMARY KEY, ts DOUBLE, run_id VARCHAR(80), actor VARCHAR(64), kind VARCHAR(64),
        subject VARCHAR(128), vendor VARCHAR(32), data JSON)""",
    """CREATE TABLE IF NOT EXISTS purchases (
        id VARCHAR(16) PRIMARY KEY, ts DOUBLE, run_id VARCHAR(80), buyer VARCHAR(64), recipient_id VARCHAR(64),
        recipient_name VARCHAR(128), sku VARCHAR(16), item TEXT, store VARCHAR(64), price DOUBLE, status VARCHAR(32),
        receipt VARCHAR(16), evidence JSON)""",
    """CREATE TABLE IF NOT EXISTS kv (k VARCHAR(64) PRIMARY KEY, v JSON)""",
]


class SingleStoreLedger(Ledger):
    UPSERT_KV = "REPLACE INTO kv (k, v) VALUES (?, ?)"

    def __init__(self, url: str):  # noqa: super().__init__ not called: no SQLite file
        u = urllib.parse.urlparse(url)
        self.cfg = dict(host=u.hostname, port=u.port or 3306, user=u.username, password=urllib.parse.unquote(u.password or ""),
                        database=(u.path or "/sleigh").lstrip("/") or "sleigh", ssl={"ssl": ssl.create_default_context()},
                        connect_timeout=15, autocommit=True, cursorclass=pymysql.cursors.DictCursor)
        self.lock = threading.Lock()
        self.listeners = []
        self.backend = "singlestore"
        boot = dict(self.cfg)
        db = boot.pop("database")
        c = pymysql.connect(**boot)
        c.cursor().execute(f"CREATE DATABASE IF NOT EXISTS {db}")
        c.close()
        self.db = pymysql.connect(**self.cfg)
        for s in SCHEMA:
            self._q(s)

    def _q(self, sql: str, params: tuple = (), fetch: str | None = None):
        sql = sql.replace("?", "%s")
        with self.lock:
            self.db.ping(reconnect=True)
            with self.db.cursor() as cur:
                cur.execute(sql, params)
                if fetch == "lastrowid":
                    return cur.lastrowid
                if fetch == "one":
                    return cur.fetchone()
                if fetch == "all":
                    return list(cur.fetchall())
