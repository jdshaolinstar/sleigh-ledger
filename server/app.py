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

from server import flags, persona, playbooks
from server.agent.elf import Elf
from server.context import Context
from server.ledger.store import view_purchase
from server.memory import wishes
from server.policy import engine

ROOT = pathlib.Path(__file__).resolve().parents[1]
ctx = Context()
app = FastAPI(title="Sleigh Ledger")


@app.middleware("http")
async def no_cache_static(request, call_next):
    resp = await call_next(request)
    if request.url.path == "/" or request.url.path.startswith("/web/"):
        resp.headers["Cache-Control"] = "no-store"  # always serve the latest UI during the demo
    return resp
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


@app.get("/health")
def health():
    return {"ok": True}


session_member: dict[str, str] = {}


@app.post("/chat")
def firedrill_chat_auto(body: dict = Body(...)):
    """Firedrill's http.v1 driver posts to one fixed path. The first message names who is chatting
    (stands in for the app's login). Ages and budgets always come from the household record."""
    message, session = str(body.get("message", "")), str(body.get("session") or "")
    mid = session_member.get(session)
    if not mid:
        low = message.lower()
        for m in ctx.household["members"]:
            if any(f"{w} {m['name'].lower()}" in low or low.startswith(m["name"].lower()) for w in ("i'm", "im", "i am", "it's", "its", "this is")):
                mid = m["id"]
                break
        if not mid:
            return {"reply": "Hi! I'm the family's shopping elf. Who am I talking to? (Mom, Dad, Jill, Sam, Bill or Lucy)"}
        session_member[session] = mid
    return {"reply": _chat(mid, message, session)}


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
        "pot_unlocked": ctx.pot_unlocked, "unlock_via": ctx.ledger.get("unlock_via", "seed"), "age_verified": ctx.ledger.get("age_verified", {}), "policy_mode": ctx.policy_mode, "skills_version": ctx.skills_version,
        "flags_source": flags.source(), "memory_backend": wishes.backend(),
        "lists": {mid: [n["text"] for n in notes] for mid, notes in lists.items()},
        "purchases": purchases,
        "stores": [{"id": s["id"], "name": s["name"], "kind": s["kind"]} for s in ctx.catalog["stores"]],
        "run": run_state, "llm_calls": ctx.llm_calls, "ledger_backend": ctx.ledger.backend,
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


LEDGER_SQL = """SELECT buyer,
       COUNT(*) AS receipts,
       SUM(CASE WHEN status = 'completed' THEN price ELSE 0 END) AS spent,
       SUM(CASE WHEN status = 'pending_approval' THEN price ELSE 0 END) AS held
FROM purchases GROUP BY buyer ORDER BY spent DESC"""
BLOCKED_SQL = """SELECT JSON_EXTRACT_STRING(data, 'label') AS rule, COUNT(*) AS attempts
FROM events WHERE kind = 'blocked' GROUP BY rule ORDER BY attempts DESC"""


@app.get("/api/ledger-sql")
def ledger_sql():
    """Live queries against the ledger, shown in the UI with the SQL itself."""
    out = {"backend": ctx.ledger.backend, "queries": []}
    for title, sql in (("Spend per family member", LEDGER_SQL), ("Blocked attempts by rule", BLOCKED_SQL)):
        q = sql if ctx.ledger.backend == "singlestore" else sql.replace("JSON_EXTRACT_STRING(data, 'label')", "json_extract(data, '$.label')")
        try:
            rows = ctx.ledger._q(q, (), "all")
        except Exception as e:
            rows = [{"error": str(e)[:200]}]
        out["queries"].append({"title": title, "sql": sql, "rows": rows})
    return out


@app.get("/api/playbooks")
def list_playbooks():
    return {"playbooks": playbooks.menu()}


@app.post("/api/playbook/{pid}")
def run_playbook(pid: str):
    if pid not in playbooks.PLAYBOOKS:
        raise HTTPException(404, "unknown playbook")

    def go():
        try:
            playbooks.run(ctx, pid)
        except Exception as e:
            ctx.ledger.event("error", "system", {"playbook": pid, "error": str(e)[:300]})
        flags.flush()

    threading.Thread(target=go, daemon=True).start()
    return {"started": pid}


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
    via = body.get("via") or "demo-no-persona"
    ctx.ledger.event("pot_unlocked", actor["id"], {"inquiry_id": inquiry, "status": status, "via": via},
                     vendor="persona" if via == "persona" else "ledger")
    ctx.ledger.put("unlock_via", via)
    return {"pot_unlocked": True}


@app.get("/api/persona/config")
def persona_config():
    return persona.config()


@app.post("/api/persona/inquiry")
def persona_inquiry(body: dict = Body(...)):
    actor = ctx.member(str(body.get("actor", "")))
    if not actor or actor["role"] != "parent":
        raise HTTPException(403, "Only a parent verifies.")
    if not persona.enabled():
        raise HTTPException(400, "Persona isn't configured (PERSONA_API_KEY + PERSONA_TEMPLATE_ID).")
    inq = persona.create_inquiry(actor["id"])
    token = persona.session_token(inq["inquiry_id"])
    url = f"https://inquiry.withpersona.com/verify?inquiry-id={inq['inquiry_id']}" + (f"&session-token={token}" if token else "")
    ctx.ledger.event("persona_inquiry", actor["id"], {"inquiry_id": inq["inquiry_id"], "status": inq["status"]}, vendor="persona")
    return inq | {"url": url}


@app.post("/api/persona/complete")
def persona_complete(body: dict = Body(...)):
    actor = ctx.member(str(body.get("actor", "")))
    if not actor or actor["role"] != "parent":
        raise HTTPException(403, "Only a parent verifies.")
    st = persona.status(str(body.get("inquiry_id")))
    ctx.ledger.event("persona_status", actor["id"], st, vendor="persona")
    if st["status"] in ("completed", "approved"):
        return unlock({"actor": actor["id"], "inquiry_id": st["inquiry_id"], "status": st["status"], "via": "persona"})
    return {"pot_unlocked": False, "status": st["status"]}


@app.post("/api/persona/relay/start")
def relay_start(body: dict = Body(...)):
    actor = ctx.member(str(body.get("actor", "")))
    if not actor:
        raise HTTPException(404, "unknown member")
    r = persona.relay_start(actor["id"])
    ctx.ledger.event("persona_relay_start", actor["id"], {"claim_type": r["claim_type"], "relay_id": r["id"]}, vendor="persona")
    return r


@app.post("/api/persona/relay/check")
def relay_check(body: dict = Body(...)):
    actor = ctx.member(str(body.get("actor", "")))
    if not actor:
        raise HTTPException(404, "unknown member")
    claim = persona.relay_claim(str(body.get("relay_id")))
    ctx.ledger.event("persona_claim", actor["id"], claim, vendor="persona")
    if claim.get("claim_result") != "passed":
        return {"pot_unlocked": ctx.pot_unlocked, "claim": claim}
    av = ctx.ledger.get("age_verified", {})
    av[actor["id"]] = claim["claim_type"]
    ctx.ledger.put("age_verified", av)
    out = {"claim": claim}
    if actor["role"] == "parent":
        out |= unlock({"actor": actor["id"], "inquiry_id": None, "status": f"relay {claim['claim_type']} passed", "via": "persona"})
    return out


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
