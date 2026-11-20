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
# The Statsig console gate can have any name; map our logical gate to it (env STATSIG_TEEN_GATE).
GATE_NAMES = {"teen_needs_parent_approval": [n for n in (os.environ.get("STATSIG_TEEN_GATE"), "teen_needs_parent_approval", "h-shop-gate") if n]}
_resolved: dict[str, str] = {}


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
    """Evaluate a logical gate in Statsig, trying each console name it may have; unknown -> safe default."""
    c = _client()
    if c is None:
        return DEFAULTS.get(name, False)
    try:
        for gate_id in GATE_NAMES.get(name, [name]):
            g = c.get_feature_gate(_user(member), gate_id)
            if "Unrecognized" not in str(getattr(g.details, "reason", "")):
                _resolved[name] = gate_id
                return bool(g.value)
        return DEFAULTS.get(name, False)
    except Exception:
        return DEFAULTS.get(name, False)


def gate_id(name: str) -> str:
    return _resolved.get(name, name)


def amplitude(member: dict, name: str, props: dict) -> None:
    """Mirror purchase/blocked events to Amplitude (HTTP API v2), off the request path."""
    key = os.environ.get("AMPLITUDE_API_KEY", "")
    if not key or os.environ.get("SENSO_SYNTHETIC") == "1":  # skip Firedrill/test traffic
        return
    import httpx

    def send():
        try:
            httpx.post("https://api2.amplitude.com/2/httpapi", timeout=10, json={"api_key": key, "events": [{
                "user_id": f"holly-{member['id']}", "event_type": name,
                "user_properties": {"age": member.get("age"), "role": member.get("role")},
                "event_properties": {k: (v if isinstance(v, (int, float, bool)) else str(v)) for k, v in props.items()}}]})
        except Exception:
            pass
    threading.Thread(target=send, daemon=True).start()


def log_event(member: dict, name: str, value=None, metadata: dict | None = None) -> None:
    amplitude(member, name, {"value": value, **(metadata or {})})
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
