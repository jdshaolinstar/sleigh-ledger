"""Household rules, enforced in code (not only in the prompt).

The elf's skills.md shapes how it talks; this module decides what it may actually buy.
mode="enforce" blocks failed purchases; mode="log" records the checks but lets everything through
(used for the "before" Firedrill run, so the fail -> fix -> pass story is honest).
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class Check:
    name: str
    ok: bool
    detail: str


@dataclass
class Decision:
    allowed: bool
    needs_approval: bool
    checks: list[Check] = field(default_factory=list)
    mode: str = "enforce"

    @property
    def failed(self) -> list[Check]:
        return [c for c in self.checks if not c.ok]

    @property
    def reason(self) -> str:
        if self.failed:
            return "; ".join(c.detail for c in self.failed)
        if self.needs_approval:
            return "Allowed after a parent approves."
        return "All household rules pass."

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "needs_approval": self.needs_approval,
            "mode": self.mode,
            "reason": self.reason,
            "checks": [asdict(c) for c in self.checks],
        }


def find_product(catalog: dict, sku: str) -> tuple[dict, dict] | tuple[None, None]:
    for store in catalog["stores"]:
        for p in store["products"]:
            if p["sku"].upper() == sku.upper():
                return p, store
    return None, None


def member(household: dict, member_id: str) -> dict | None:
    key = member_id.strip().lower()
    return next((m for m in household["members"] if m["id"] == key or m["name"].lower() == key), None)


def age_cap(household: dict, age: int) -> float | None:
    for band in sorted(household["age_caps"], key=lambda b: b["max_age"]):
        if age <= band["max_age"]:
            return band["cap"]
    return None


def resolve_recipient(household: dict, buyer: dict, recipient: str) -> dict | None:
    """A recipient is another household member, or one of the buyer's parent-approved friends."""
    m = member(household, recipient)
    if m:
        return {"id": m["id"], "name": m["name"], "age": m["age"], "kind": "member"}
    for f in buyer.get("friends", []):
        if f["name"].lower() == recipient.strip().lower():
            return {"id": f"friend:{f['name'].lower()}", "name": f["name"], "age": f["age"], "kind": "friend"}
    return None


def evaluate(
    household: dict,
    catalog: dict,
    *,
    buyer_id: str,
    recipient: str,
    sku: str,
    spent: dict[str, float],
    claimed: set[tuple[str, str]],
    pot_unlocked: bool,
    minor_approval_gate: bool = True,
    mode: str = "enforce",
) -> Decision:
    checks: list[Check] = []
    buyer = member(household, buyer_id)
    if buyer is None:
        return Decision(False, False, [Check("buyer", False, f"'{buyer_id}' is not in the household.")], mode)

    checks.append(Check("pot_unlocked", pot_unlocked,
                        "Family pot is unlocked by a verified parent." if pot_unlocked
                        else "Family pot is locked until a parent verifies their identity."))

    rec = resolve_recipient(household, buyer, recipient)
    checks.append(Check("recipient_allowed", rec is not None,
                        f"{rec['name']} is an allowed recipient." if rec
                        else f"'{recipient}' is not a household member or an approved friend of {buyer['name']}; ask a parent."))

    product, store = find_product(catalog, sku)
    if product is None:
        checks.append(Check("item_exists", False, f"No item with SKU {sku} in the trusted catalog."))
        return _decide(checks, False, mode)
    checks.append(Check("in_stock", product["stock"] > 0,
                        f"{product['name']} is in stock." if product["stock"] > 0
                        else f"{product['name']} is out of stock at {store['name']}."))

    min_age = product["min_age"]
    checks.append(Check("buyer_age", buyer["age"] >= min_age,
                        f"{buyer['name']} ({buyer['age']}) may buy items rated {min_age}+." if buyer["age"] >= min_age
                        else f"{product['name']} is rated {min_age}+; {buyer['name']} is {buyer['age']} (household record)."))
    if rec:
        checks.append(Check("recipient_age", rec["age"] >= min_age,
                            f"Suitable for {rec['name']} ({rec['age']})." if rec["age"] >= min_age
                            else f"{product['name']} is rated {min_age}+; {rec['name']} is {rec['age']}."))

    remaining = float(buyer["allocation"]) - float(spent.get(buyer["id"], 0.0))
    checks.append(Check("budget", product["price"] <= remaining + 1e-9,
                        f"${product['price']:.2f} fits {buyer['name']}'s remaining ${remaining:.2f}." if product["price"] <= remaining + 1e-9
                        else f"${product['price']:.2f} exceeds {buyer['name']}'s remaining ${remaining:.2f}."))

    if rec and household["rules"].get("one_gift_per_sku_per_recipient", True):
        dup = (rec["id"], product["sku"]) in claimed
        checks.append(Check("not_duplicate", not dup,
                            "Nobody has bought this for them yet." if not dup
                            else f"Someone already bought {product['name']} for {rec['name']}."))

    needs_approval = bool(minor_approval_gate and household["rules"].get("minors_need_parent_approval") and buyer["age"] < 18)
    return _decide(checks, needs_approval, mode)


def _decide(checks: list[Check], needs_approval: bool, mode: str) -> Decision:
    ok = all(c.ok for c in checks)
    allowed = ok or mode == "log"
    return Decision(allowed=allowed, needs_approval=needs_approval and allowed, checks=checks, mode=mode)


def validate_allocations(household: dict, allocations: dict[str, float]) -> list[str]:
    """Slider changes: each member under their age cap, and the total under the pot."""
    errors = []
    total = 0.0
    for m in household["members"]:
        amt = float(allocations.get(m["id"], m["allocation"]))
        if amt < 0:
            errors.append(f"{m['name']}: allocation can't be negative.")
        cap = age_cap(household, m["age"])
        if cap is not None and amt > cap:
            errors.append(f"{m['name']} is {m['age']}: the cap for that age is ${cap:.0f}.")
        total += amt
    if total > household["pot"] + 1e-9:
        errors.append(f"Allocations total ${total:.0f}, more than the ${household['pot']:.0f} pot.")
    return errors
