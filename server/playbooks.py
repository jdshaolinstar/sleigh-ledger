"""Demo Menu playbooks: force one specific elf action so the demo shows rules passing and failing on cue.

These call the elf's real tools directly (no LLM choice), so they are deterministic. The Senso search,
Senso fact-check, household rules, Statsig gate and ledger all run for real. The UI labels them "forced".
"""
from __future__ import annotations

from server.agent.elf import Elf

# id -> (title, expected outcome, buyer, recipient, sku, search query, claim, reason, recall_first)
PLAYBOOKS = {
    "lucy-wine": ("Lucy (10) tries to buy wine for Mom", "blocked: alcohol 21+", "lucy", "mom", "CC-607",
                  "sparkling wine gift set", "The Holiday sparkling wine gift set (SKU CC-607) costs $45.00 and is suitable for ages 21+.",
                  "Mom likes cozy evenings.", False),
    "mom-wine": ("Mom buys Dad the wine set", "succeeds only after Persona 21+ check", "mom", "dad", "CC-607",
                 "sparkling wine gift set", "The Holiday sparkling wine gift set (SKU CC-607) costs $45.00 and is suitable for ages 21+.",
                 "Dad enjoys a holiday toast.", False),
    "bill-mature": ("Bill (14) tries Blood Harbor 4 for himself", "blocked: rated 17+", "bill", "bill", "BB-102",
                    "Blood Harbor 4 video game", "Blood Harbor 4 (SKU BB-102) costs $69.00 and is suitable for ages 17+.",
                    "Bill asked for it.", False),
    "lucy-budget": ("Lucy (10) tries a $120 jacket for Dad", "blocked: over her $100", "lucy", "dad", "TL-403",
                    "rain shell jacket", "The Rain shell jacket (SKU TL-403) costs $120.00 and is suitable for all ages.",
                    "Dad's rain jacket is falling apart.", True),
    "sam-offlist": ("Sam buys socks for Jordan (not approved)", "blocked: unapproved recipient", "sam", "Jordan", "TL-402",
                    "wool socks", "The Wool socks 3-pack (SKU TL-402) costs $22.00 and is suitable for all ages.",
                    "Jordan is a friend.", False),
    "jill-wrong-price": ("Jill's elf misquotes a price", "blocked: Senso fact-check conflict", "jill", "mom", "PQ-303",
                         "leather travel journal", "The Leather travel journal (SKU PQ-303) costs $28.00 and is suitable for ages 12+.",
                         "Mom might like journaling.", False),
    "mom-grip": ("Mom buys Bill grip tape + bearings", "succeeds (uses Bill's list)", "mom", "bill", "KF-502",
                 "skateboard grip tape and bearings", "The Grip tape and bearings kit (SKU KF-502) costs $34.00 and is suitable for ages 8+.",
                 "Bill already has a deck and needs new grip tape and bearings (his list).", True),
    "dad-duplicate": ("Dad buys Bill the same grip kit", "blocked: duplicate (run Mom's first)", "dad", "bill", "KF-502",
                      "skateboard grip tape and bearings", "The Grip tape and bearings kit (SKU KF-502) costs $34.00 and is suitable for ages 8+.",
                      "Bill likes skateboarding.", True),
    "bill-approval": ("Bill (14) buys Lucy an art kit", "waits for a parent's approval", "bill", "lucy", "TT-202",
                      "unicorn art studio kit", "The Unicorn art studio kit (SKU TT-202) costs $34.00 and is suitable for ages 6+.",
                      "Lucy loves drawing and unicorns.", True),
}


def run(ctx, pid: str) -> dict:
    title, expected, buyer, recipient, sku, query, claim, reason, recall_first = PLAYBOOKS[pid]
    elf = Elf(ctx, buyer, run_id=f"playbook:{pid}")
    ctx.ledger.event("playbook", buyer, {"playbook": pid, "title": title, "expected": expected, "forced": True})
    if recall_first and ctx.member(recipient):
        elf.t_recall_list(recipient)
        elf.t_claimed_for(recipient)
    elf.t_search_catalog(query)
    result = elf.t_buy_gift(sku, recipient, claim, reason)
    return {"playbook": pid, "title": title, "expected": expected, "result": result}


def menu() -> list[dict]:
    return [{"id": k, "title": v[0], "expected": v[1]} for k, v in PLAYBOOKS.items()]
