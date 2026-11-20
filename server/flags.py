"""Statsig feature gates + events. Without STATSIG_SERVER_SECRET_KEY, falls back to local defaults
(and says so in the audit), so the demo still runs.

Gates:
  teen_needs_parent_approval  -> minors' purchases wait for a parent tap (default ON)
Events:
  gift_purchased, gift_blocked, allocation_changed
"""
from __future__ import annotations

import os
import threading

_statsig = None
_lock = threading.Lock()
DEFAULTS = {"teen_needs_parent_approval": True}


def _client():
    global _statsig
    key = os.environ.get("STATSIG_SERVER_SECRET_KEY", "")
    if not key or key.startswith("secret-..."):
        return None
    with _lock:
        if _statsig is None:
            from statsig_python_core import Statsig
            _statsig = Statsig(key)
            _statsig.initialize().wait()
    return _statsig


def _user(member: dict):
    from statsig_python_core import StatsigUser
    return StatsigUser(user_id=member["id"], custom={"age": member.get("age"), "role": member.get("role")})


def source() -> str:
    return "statsig" if _client() else "local-default"


def check_gate(name: str, member: dict) -> bool:
    c = _client()
    if c is None:
        return DEFAULTS.get(name, False)
    try:
        return bool(c.check_gate(_user(member), name))
    except Exception:
        return DEFAULTS.get(name, False)


def log_event(member: dict, name: str, value=None, metadata: dict | None = None) -> None:
    c = _client()
    if c is None:
        return
    try:
        c.log_event(user=_user(member), event_name=name, value=value,
                    metadata={k: str(v) for k, v in (metadata or {}).items()})
    except Exception:
        pass


def flush() -> None:
    c = _client()
    if c is not None:
        try:
            c.flush_events().wait()
        except Exception:
            pass
