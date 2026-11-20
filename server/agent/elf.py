"""The shopping elf: an LLM tool loop over Cognee (wish lists), Senso (catalog + fact-check),
the policy engine + Statsig gate, and the simulated checkout. Every step is a ledger event."""
from __future__ import annotations

import json
import os
import pathlib
from typing import Any

from openai import OpenAI

from server import flags
from server.memory import wishes
from server.policy import engine
from server.senso import trail_entry

HERE = pathlib.Path(__file__).resolve().parent
MODEL = os.environ.get("OPENAI_MODEL", "gpt-5.4-mini")
MAX_STEPS = 10

TOOLS = [
    {"type": "function", "function": {
        "name": "recall_list", "description": "Recall a person's Christmas list (what they like, own, don't want) from earlier chats.",
        "parameters": {"type": "object", "properties": {"person": {"type": "string"}}, "required": ["person"]}}},
    {"type": "function", "function": {
        "name": "claimed_for", "description": "Gifts other family members already bought for this person (to avoid duplicates).",
        "parameters": {"type": "object", "properties": {"person": {"type": "string"}}, "required": ["person"]}}},
    {"type": "function", "function": {
        "name": "search_catalog", "description": "Search the trusted store catalog (prices, age ratings, stock, store policies).",
        "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
    {"type": "function", "function": {
        "name": "buy_gift", "description": "Buy a gift (simulated checkout). The claim is fact-checked and household rules are enforced.",
        "parameters": {"type": "object", "properties": {
            "sku": {"type": "string"}, "recipient": {"type": "string", "description": "member name/id or approved friend"},
            "claim": {"type": "string", "description": "One sentence: item name, SKU, price, age rating. Don't name the store."},
            "reason": {"type": "string", "description": "Why this gift fits the person (cite their list)."}},
            "required": ["sku", "recipient", "claim", "reason"]}}},
    {"type": "function", "function": {
        "name": "save_wish", "description": "Save something the person you work for says THEY like, want, own or don't want.",
        "parameters": {"type": "object", "properties": {"note": {"type": "string"}}, "required": ["note"]}}},
]


class Elf:
    def __init__(self, ctx, buyer_id: str, *, run_id: str = "", autonomous: bool = False):
        self.ctx = ctx
        self.buyer = ctx.member(buyer_id)
        if self.buyer is None:
            raise ValueError(f"unknown member {buyer_id}")
        self.run_id = run_id
        self.autonomous = autonomous
        self.client = OpenAI()

    # --- prompt ---------------------------------------------------------------------------
    def system_prompt(self) -> str:
        v = self.ctx.skills_version
        text = (HERE / ("skills_v0.md" if v == "v0" else "skills.md")).read_text(encoding="utf-8")
        h = self.ctx.household
        b = self.buyer
        fill = {
            "buyer_name": b["name"], "buyer_age": b["age"], "buyer_role": b["role"],
            "household_name": h["name"], "remaining": f"{self.ctx.remaining(b['id']):.2f}",
            "members": ", ".join(m["name"] for m in h["members"]),
            "friends": ", ".join(f["name"] for f in b.get("friends", [])) or "none",
        }
        for k, val in fill.items():
            text = text.replace("{" + k + "}", str(val))
        if v == "v0":
            text += f"\nYou are helping {b['name']}."
        if self.autonomous:
            text += "\n\nMode: autonomous shopping day. No human is in this chat; do not ask questions, just act and report."
        return text

    def emit(self, kind: str, data: dict, *, vendor: str = "", subject: str = "") -> dict:
        return self.ctx.ledger.event(kind, self.buyer["id"], data, run_id=self.run_id, vendor=vendor, subject=subject)

    # --- tools ----------------------------------------------------------------------------
    def _person(self, name: str) -> dict | None:
        return engine.resolve_recipient(self.ctx.household, self.buyer, name)

    def t_recall_list(self, person: str) -> dict:
        p = self.ctx.member(person)
        if not p:
            return {"error": f"{person} is not a household member, so there is no list."}
        r = wishes.recall(p["id"], p["name"])
        self.emit("recall", {"person": p["name"], **r}, vendor=r.get("backend", "local"), subject=p["id"])
        return r

    def t_claimed_for(self, person: str) -> dict:
        rec = self._person(person)
        if not rec:
            return {"error": f"{person} is not an allowed recipient."}
        if rec["id"] == self.buyer["id"]:
            return {"note": "Gifts for you are a secret. Nothing to show."}
        items = [{"item": p["item"], "sku": p["sku"], "by": p["buyer"]} for p in self.ctx.ledger.purchases()
                 if p["recipient_id"] == rec["id"] and p["status"] in ("completed", "pending_approval")]
        self.emit("claimed_check", {"person": rec["name"], "count": len(items)}, vendor="ledger", subject=rec["id"])
        return {"already_bought": items}

    def t_search_catalog(self, query: str) -> dict:
        key = query.strip().lower()
        results = self.ctx.search_cache.get(key)
        if results is None:
            results = self.ctx.senso.search_context(query, max_results=6)
            self.ctx.search_cache[key] = results
        trail = [trail_entry(r) for r in results]
        top = self.ctx.store_from_title(trail[0].get("title")) if trail else None
        self.emit("search", {"query": query, "results": trail, "store": top and top["id"]}, vendor="senso")
        if top:
            self.emit("walk", {"store": top["id"], "store_name": top["name"], "why": "browsing"}, subject=top["id"])
        return {"results": [{"title": t.get("title"), "text": t.get("chunk_text"), "content_id": t.get("content_id")} for t in trail]}

    def t_save_wish(self, note: str) -> dict:
        r = wishes.remember(self.buyer["id"], self.buyer["name"], note)
        self.emit("wish_saved", {"note": note, **r}, vendor=r.get("backend", "local"), subject=self.buyer["id"])
        return {"saved": True}

    def t_buy_gift(self, sku: str, recipient: str, claim: str, reason: str) -> dict:
        ctx, b = self.ctx, self.buyer
        product, store = engine.find_product(ctx.catalog, sku)
        if store:
            self.emit("walk", {"store": store["id"], "store_name": store["name"], "why": "buying"}, subject=store["id"])

        # 1) fact-check the elf's own claim against Senso (free)
        check: dict[str, Any] = {"overall": "skipped"}
        if os.environ.get("FACT_CHECK", "1") == "1":
            try:
                check = ctx.senso.fact_check(claim, f"{b['name']} wants to buy {sku} for {recipient}. {reason}")
            except Exception as e:
                check = {"overall": "error", "error": str(e)[:200]}
        self.emit("fact_check", {"claim": claim, **check}, vendor="senso", subject=sku)

        # 2) household rules + Statsig gate
        gate_on = ctx.gate("teen_needs_parent_approval", b)
        decision = engine.evaluate(
            ctx.household, ctx.catalog, buyer_id=b["id"], recipient=recipient, sku=sku,
            spent=ctx.ledger.spent(), claimed=ctx.ledger.claimed(), pot_unlocked=ctx.pot_unlocked,
            minor_approval_gate=gate_on, mode=ctx.policy_mode)
        if check.get("overall") == "conflict" and ctx.policy_mode == "enforce":
            decision.allowed = False
            decision.checks.append(engine.Check("fact_check", False,
                                                "The elf's claim conflicts with the trusted catalog; re-check the item before buying."))
        self.emit("policy", {**decision.to_dict(), "gate": {"teen_needs_parent_approval": gate_on, "source": flags.source()}},
                  vendor="policy", subject=sku)

        rec = self._person(recipient) or {"id": recipient.lower(), "name": recipient}
        if not decision.allowed or product is None:
            flags.log_event(b, "gift_blocked", sku, {"reason": decision.reason})
            self.emit("blocked", {"sku": sku, "recipient": rec["name"], "reason": decision.reason,
                                  "store": store and store["id"], "store_name": store and store["name"]}, subject=rec["id"])
            return {"status": "blocked", "reason": decision.reason}

        status = "pending_approval" if decision.needs_approval else "completed"
        evidence = {"claim": claim, "reason": reason, "fact_check": check, "policy": decision.to_dict(),
                    "senso_results": [e["data"]["results"] for e in ctx.ledger.events()[-40:]
                                      if e["kind"] == "search" and e["actor"] == b["id"]][-1:] or []}
        p = ctx.ledger.add_purchase(run_id=self.run_id, buyer=b["id"], recipient_id=rec["id"], recipient_name=rec["name"],
                                    sku=product["sku"], item=product["name"], store=store["name"], price=product["price"],
                                    status=status, evidence=evidence)
        flags.log_event(b, "gift_purchased" if status == "completed" else "gift_pending", product["price"],
                        {"sku": product["sku"], "store": store["name"], "recipient": rec["id"]})
        self.emit("purchase", {"purchase_id": p["id"], "status": status, "store": store["id"], "store_name": store["name"],
                               "recipient": rec["name"], "recipient_id": rec["id"], "price": product["price"],
                               "item": product["name"], "sku": product["sku"]}, vendor="ledger", subject=rec["id"])
        out = {"status": status, "receipt": p["receipt"] or None, "purchase_id": p["id"], "price": product["price"],
               "remaining_budget": round(ctx.remaining(b["id"]), 2), "checkout": "simulated"}
        if status == "pending_approval":
            out["note"] = "Waiting for a parent to approve in the app."
        return out

    # --- loop -----------------------------------------------------------------------------
    def run(self, messages: list[dict]) -> tuple[str, list[dict]]:
        """messages: user/assistant history (no system). Returns (reply, new history)."""
        convo = [{"role": "system", "content": self.system_prompt()}] + messages
        for _ in range(MAX_STEPS):
            self.ctx.count_llm_call()
            resp = self.client.chat.completions.create(model=MODEL, messages=convo, tools=TOOLS)
            msg = resp.choices[0].message
            if not msg.tool_calls:
                reply = msg.content or ""
                return reply, messages + [{"role": "assistant", "content": reply}]
            convo.append({"role": "assistant", "content": msg.content or "",
                          "tool_calls": [tc.model_dump() for tc in msg.tool_calls]})
            for tc in msg.tool_calls:
                try:
                    args = json.loads(tc.function.arguments or "{}")
                    result = getattr(self, "t_" + tc.function.name)(**args)
                except Exception as e:
                    result = {"error": str(e)[:300]}
                convo.append({"role": "tool", "tool_call_id": tc.id, "content": json.dumps(result, default=str)[:6000]})
        reply = "I ran out of steps for this request. Please try again with a simpler ask."
        return reply, messages + [{"role": "assistant", "content": reply}]
