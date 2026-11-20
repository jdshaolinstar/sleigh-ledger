"""Christmas-list memory: what each person likes, already owns and doesn't want, built up over chats.

Backend: Cognee (knowledge-graph memory) when available and MEMORY_BACKEND=cognee; otherwise a local
JSON notes file, so the demo never breaks. Every recall returns which backend answered (for the audit).
"""
from __future__ import annotations

import asyncio
import json
import os
import pathlib
import threading

ROOT = pathlib.Path(__file__).resolve().parents[2]
NOTES = ROOT / "data/runtime/wishes.json"
_lock = threading.Lock()


def _load() -> dict:
    return json.loads(NOTES.read_text()) if NOTES.exists() else {}


def _save(d: dict) -> None:
    NOTES.parent.mkdir(parents=True, exist_ok=True)
    NOTES.write_text(json.dumps(d, indent=2))


def backend() -> str:
    return os.environ.get("MEMORY_BACKEND", "local")


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def remember(member_id: str, member_name: str, text: str, source: str = "chat") -> dict:
    with _lock:
        d = _load()
        d.setdefault(member_id, []).append({"text": text, "source": source})
        _save(d)
    if backend() == "cognee":
        try:
            import cognee  # noqa: F401
            _run(_cognee_remember(member_id, f"{member_name} said ({source}): {text}"))
            return {"backend": "cognee", "stored": True}
        except Exception as e:  # keep the local copy; report honestly
            return {"backend": "local", "stored": True, "cognee_error": str(e)[:200]}
    return {"backend": "local", "stored": True}


def recall(member_id: str, member_name: str, question: str | None = None) -> dict:
    notes = _load().get(member_id, [])
    if backend() == "cognee":
        try:
            q = question or f"What does {member_name} want for Christmas, what do they already own, and what don't they want?"
            answer = _run(_cognee_recall(member_id, q))
            return {"backend": "cognee", "answer": answer, "notes": [n["text"] for n in notes]}
        except Exception as e:
            return {"backend": "local", "notes": [n["text"] for n in notes], "cognee_error": str(e)[:200]}
    return {"backend": "local", "notes": [n["text"] for n in notes]}


def all_lists() -> dict:
    return _load()


async def _cognee_remember(member_id: str, text: str):
    import cognee
    ds = f"wishlist_{member_id}"
    if hasattr(cognee, "remember"):
        try:
            return await cognee.remember(text, dataset_name=ds)
        except TypeError:
            return await cognee.remember(text)
    await cognee.add(text, dataset_name=ds)
    await cognee.cognify(datasets=[ds])


async def _cognee_recall(member_id: str, question: str) -> str:
    import cognee
    ds = f"wishlist_{member_id}"
    if hasattr(cognee, "recall"):
        try:
            res = await cognee.recall(query_text=question, datasets=[ds])
        except TypeError:
            res = await cognee.recall(query_text=question)
    else:
        res = await cognee.search(query_text=question, datasets=[ds])
    parts = []
    for r in res or []:
        parts.append(getattr(r, "text", None) or (r.get("text") if isinstance(r, dict) else None) or str(r))
    return "\n".join(p for p in parts if p)[:1500]
