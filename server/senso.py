"""Senso Context Layer client (REST). Docs: https://docs.senso.ai/docs/overview

Senso is the elves' source of truth for store facts. Every search result's ids go into the audit trail,
and every claim is fact-checked with /org/evals/text before a purchase.
"""
from __future__ import annotations

import os
import time
from typing import Any

import httpx

BASE = "https://apiv2.senso.ai/api/v1"


class SensoError(RuntimeError):
    pass


class Senso:
    def __init__(self, api_key: str | None = None, synthetic: bool = False, timeout: float = 30.0):
        self.key = api_key or os.environ.get("SENSO_API_KEY", "")
        if not self.key:
            raise SensoError("SENSO_API_KEY is not set")
        headers = {"X-API-Key": self.key, "Content-Type": "application/json"}
        if synthetic:
            headers["X-Senso-Signals"] = "off"  # test/Firedrill traffic should not file content-gap reports
        self.http = httpx.Client(base_url=BASE, headers=headers, timeout=timeout)

    def _req(self, method: str, path: str, **kw) -> Any:
        r = self.http.request(method, path, **kw)
        if r.status_code >= 400 and r.status_code != 409:
            raise SensoError(f"{method} {path} -> {r.status_code}: {r.text[:300]}")
        return r.json() if r.content else {}

    def me(self) -> dict:
        return self._req("GET", "/org/me")

    def add_raw(self, title: str, text: str) -> dict:
        r = self.http.post("/org/kb/raw", json={"title": title, "text": text})
        if r.status_code == 409:
            return {"duplicate": True, "title": title}
        if r.status_code >= 400:
            raise SensoError(f"add_raw {title} -> {r.status_code}: {r.text[:300]}")
        return r.json()

    def node(self, kb_node_id: str) -> dict:
        return self._req("GET", f"/org/kb/nodes/{kb_node_id}")

    def wait_processed(self, kb_node_id: str, timeout_s: float = 180) -> str:
        end = time.time() + timeout_s
        while time.time() < end:
            n = self.node(kb_node_id)
            status = (n.get("content") or {}).get("processing_status") or n.get("processing_status")
            if status in ("complete", "failed"):
                return status
            time.sleep(5)
        return "timeout"

    def search_context(self, query: str, max_results: int = 6) -> list[dict]:
        data = self._req("POST", "/org/search/context",
                         json={"query": query, "max_results": max_results, "search_type": "hybrid"})
        return data.get("results", [])

    def search_answer(self, query: str, max_results: int = 5) -> dict:
        return self._req("POST", "/org/search", json={"query": query, "max_results": max_results})

    def fact_check(self, text: str, question: str, poll_s: float = 90) -> dict:
        """POST /org/evals/text (kb_accuracy). wait=true holds ~1 min; on 202 we poll /org/evals/runs/{id}.

        author: "ai_assistant" only checks claims tied to *our* org, and the stores are separate
        fictional brands, so default to "organization" (prices/policies count as ours). Override with
        SENSO_FACTCHECK_AUTHOR once tested live.
        """
        author = os.environ.get("SENSO_FACTCHECK_AUTHOR", "organization")
        run = self._req("POST", "/org/evals/text", json={
            "text": text, "question": question[:2000], "author": author,
            "evaluator": "kb_accuracy", "wait": True, "title": "Elf purchase claim",
        })
        end = time.time() + poll_s
        while run.get("status") not in ("completed", "failed", "gated") and run.get("eval_run_id") and time.time() < end:
            time.sleep(5)
            run = self._req("GET", f"/org/evals/runs/{run['eval_run_id']}")
        return summarize_check(run)


def summarize_check(run: dict) -> dict:
    claims = [{
        "claim": c.get("claim_text"),
        "verdict": c.get("verdict"),
        "reasoning": (c.get("reasoning") or "")[:300],
        "quote": (c.get("quote") or "")[:300],
    } for c in run.get("claims") or []]
    verdicts = [c["verdict"] for c in claims]
    if "conflict" in verdicts:
        overall = "conflict"
    elif verdicts and all(v in ("verified", "not_verifiable") for v in verdicts) and "verified" in verdicts:
        overall = "verified"
    elif "unsupported" in verdicts:
        overall = "unsupported"
    else:
        overall = run.get("status") or "unknown"
    return {"eval_run_id": run.get("eval_run_id"), "status": run.get("status"), "overall": overall,
            "accuracy_pct": run.get("accuracy_pct"), "claims": claims}


def trail_entry(result: dict) -> dict:
    """The fields we keep from each Senso passage for the audit trail."""
    keep = ("content_id", "kb_node_id", "version_id", "content_chunk_id", "title", "score", "rank", "chunk_text")
    out = {k: result.get(k) for k in keep if k in result}
    if "chunk_text" in out and out["chunk_text"]:
        out["chunk_text"] = out["chunk_text"][:600]
    return out
