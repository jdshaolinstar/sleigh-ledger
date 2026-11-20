"""Sleigh Ledger API + static town page.

Run:  .venv/Scripts/python -m uvicorn server.app:app --port 8787
Firedrill driver (http.v1): POST /chat/{member}  body {"message","session"} -> {"reply"}
"""
from __future__ import annotations

import pathlib
import threading
import uuid

from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from server import flags
from server.agent.elf import Elf
from server.context import Context
from server.ledger.store import view_purchase
from server.memory import wishes
from server.policy import engine

ROOT = pathlib.Path(__file__).resolve().parents[1]
ctx = Context()
app = FastAPI(title="Sleigh Ledger")
sessions: dict[str, list[dict]] = {}
run_state = {"running": False, "run_id": ""}

# Who shops for whom on the shopping day (kept small so a run is ~1 minute).
ASSIGNMENTS = [("mom", "bill"), ("dad", "jill"), ("jill", "mom"), ("sam", "dad"), ("bill", "lucy"), ("lucy", "sam")]


def _chat(member: str, message: str, session: str) -> str:
    m = ctx.member(member)
    if m is None:
        raise HTTPException(404, f"unknown member {member}")
    key = f"{m['id']}:{session or 'default'}"
    hist = sessions.get(key, [])
    ctx.ledger.event("chat_in", m["id"], {"message": message, "session": session})
    reply, hist = Elf(ctx, m["id"], run_id=f"chat:{key}").run(hist + [{"role": "user", "content": message}])
    sessions[key] = hist[-30:]
    ctx.ledger.event("chat_out", m["id"], {"reply": reply, "session": session})
    flags.flush()
    return reply


@app.post("/chat/{member}")
def firedrill_chat(member: str, body: dict = Body(...)):
    return {"reply": _chat(member, str(body.get("message", "")), str(body.get("session") or ""))}


@app.post("/api/chat/{member}")
def ui_chat(member: str, body: dict = Body(...)):
    return {"reply": _chat(member, str(body.get("message", "")), str(body.get("session") or "ui"))}


@app.get("/api/state")
def state(viewer: str = "mom"):
    h = ctx.household
    v = ctx.member(viewer)
    spent = ctx.ledger.spent()
    members = [m | {"spent": spent.get(m["id"], 0.0), "remaining": m["allocation"] - spent.get(m["id"], 0.0),
                    "cap": engine.age_cap(h, m["age"])} for m in h["members"]]
    lists = wishes.all_lists()
    purchases = [view_purchase(p, v) for p in ctx.ledger.purchases()]
    # registry view: who's claimed what on each list, hidden from the list owner
    return {
        "household": {"name": h["name"], "pot": h["pot"], "kind": h["kind"]},
        "members": members, "viewer": v,
        "pot_unlocked": ctx.pot_unlocked, "policy_mode": ctx.policy_mode, "skills_version": ctx.skills_version,
        "flags_source": flags.source(), "memory_backend": wishes.backend(),
        "lists": {mid: [n["text"] for n in notes] for mid, notes in lists.items()},
        "purchases": purchases,
        "stores": [{"id": s["id"], "name": s["name"], "kind": s["kind"]} for s in ctx.catalog["stores"]],
        "run": run_state, "llm_calls": ctx.llm_calls,
    }


@app.get("/api/events")
def events(since: int = 0):
    return {"events": ctx.ledger.events(since_id=since)}


@app.post("/api/allocations")
def set_allocations(body: dict = Body(...)):
    actor = ctx.member(str(body.get("actor", "")))
    if not actor or actor["role"] != "parent":
        raise HTTPException(403, "Only a parent can change allocations.")
    if not ctx.pot_unlocked:
        raise HTTPException(403, "Verify a parent with Persona first.")
    alloc = {k: float(v) for k, v in (body.get("allocations") or {}).items()}
    errors = engine.validate_allocations(ctx.household, alloc)
    if errors:
        raise HTTPException(400, " ".join(errors))
    merged = ctx.ledger.get("allocations", {}) | alloc
    ctx.ledger.put("allocations", merged)
    ctx.ledger.event("allocation_changed", actor["id"], {"allocations": alloc}, vendor="ledger")
    flags.log_event(actor, "allocation_changed", None, alloc)
    return {"ok": True, "allocations": merged}


@app.post("/api/approve/{pid}")
def approve(pid: str, body: dict = Body(...)):
    actor = ctx.member(str(body.get("actor", "")))
    if not actor or actor["role"] != "parent":
        raise HTTPException(403, "Only a parent can approve.")
    decision = "completed" if body.get("approve", True) else "declined"
    p = ctx.ledger.set_status(pid, decision)
    ctx.ledger.event("approval", actor["id"], {"purchase_id": pid, "decision": decision}, vendor="ledger")
    return p


@app.post("/api/run-day")
def run_day():
    if run_state["running"]:
        return run_state
    run_state.update(running=True, run_id="day-" + uuid.uuid4().hex[:6])

    def one(buyer: str, recipient: str):
        r = ctx.member(recipient)
        try:
            Elf(ctx, buyer, run_id=run_state["run_id"], autonomous=True).run([{"role": "user", "content":
                f"It's the family shopping day. Pick and buy one great gift for {r['name']} (age {r['age']}). "
                f"Check their Christmas list and what others already bought them first."}])
        except Exception as e:
            ctx.ledger.event("error", buyer, {"error": str(e)[:300]}, run_id=run_state["run_id"])

    def all_elves():
        ctx.ledger.event("run_start", "system", {"assignments": ASSIGNMENTS}, run_id=run_state["run_id"])
        threads = [threading.Thread(target=one, args=a, daemon=True) for a in ASSIGNMENTS]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        ctx.ledger.event("run_end", "system", {}, run_id=run_state["run_id"])
        flags.flush()
        run_state["running"] = False

    threading.Thread(target=all_elves, daemon=True).start()
    return run_state


@app.post("/api/mode")
def set_mode(body: dict = Body(...)):
    if "policy_mode" in body:
        ctx.ledger.put("policy_mode", body["policy_mode"])
    if "skills_version" in body:
        ctx.ledger.put("skills_version", body["skills_version"])
    return {"policy_mode": ctx.policy_mode, "skills_version": ctx.skills_version}


@app.post("/api/unlock")
def unlock(body: dict = Body(...)):
    """Called after a parent's Persona inquiry completes (see /api/persona/*)."""
    actor = ctx.member(str(body.get("actor", "")))
    if not actor or actor["role"] != "parent":
        raise HTTPException(403, "Only a parent can unlock the pot.")
    inquiry = body.get("inquiry_id")
    status = body.get("status", "")
    verified = ctx.ledger.get("verified", {})
    verified[actor["id"]] = True
    ctx.ledger.put("verified", verified)
    ctx.ledger.put("pot_unlocked", True)
    ctx.ledger.event("pot_unlocked", actor["id"], {"inquiry_id": inquiry, "status": status,
                                                   "via": body.get("via", "persona")}, vendor="persona")
    return {"pot_unlocked": True}


@app.post("/api/reset")
def reset(body: dict = Body(default={})):
    ctx.ledger.reset()
    sessions.clear()
    ctx.search_cache.clear()
    if body.get("unlocked"):
        ctx.ledger.put("pot_unlocked", True)
    return {"ok": True}


WEB = ROOT / "web"
if WEB.exists():
    app.mount("/web", StaticFiles(directory=WEB), name="web")


@app.get("/")
def index():
    return FileResponse(WEB / "index.html")
