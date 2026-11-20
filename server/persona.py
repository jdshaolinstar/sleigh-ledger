"""Persona (sandbox) standard verification: a parent completes an inquiry to unlock the family pot.

Docs: https://docs.withpersona.com/api-introduction , https://docs.withpersona.com/embedded-flow
Sandbox runs no real checks. We store only the inquiry id and status in the ledger, never PII.
"""
from __future__ import annotations

import os

import httpx

BASE = "https://api.withpersona.com/api/v1"
VERSION = "2023-01-05"


def enabled() -> bool:
    return bool(os.environ.get("PERSONA_API_KEY")) and bool(os.environ.get("PERSONA_TEMPLATE_ID"))


def _h() -> dict:
    return {"Authorization": f"Bearer {os.environ['PERSONA_API_KEY']}", "Persona-Version": VERSION,
            "Content-Type": "application/json", "Accept": "application/json"}


def create_inquiry(reference_id: str) -> dict:
    body = {"data": {"attributes": {"inquiry-template-id": os.environ["PERSONA_TEMPLATE_ID"], "reference-id": reference_id}}}
    r = httpx.post(f"{BASE}/inquiries", headers=_h(), json=body, timeout=30)
    r.raise_for_status()
    d = r.json()["data"]
    return {"inquiry_id": d["id"], "status": d["attributes"].get("status")}


def session_token(inquiry_id: str) -> str | None:
    """Resume token so the embedded flow opens this exact inquiry."""
    r = httpx.post(f"{BASE}/inquiries/{inquiry_id}/resume", headers=_h(), timeout=30)
    if r.status_code >= 400:
        return None
    return (r.json().get("meta") or {}).get("session-token")


def status(inquiry_id: str) -> dict:
    r = httpx.get(f"{BASE}/inquiries/{inquiry_id}", headers=_h(), timeout=30)
    r.raise_for_status()
    a = r.json()["data"]["attributes"]
    return {"inquiry_id": inquiry_id, "status": a.get("status"), "reference_id": a.get("reference-id")}


def config() -> dict:
    return {"enabled": enabled(), "template_id": os.environ.get("PERSONA_TEMPLATE_ID"),
            "environment_id": os.environ.get("PERSONA_ENVIRONMENT_ID")}
