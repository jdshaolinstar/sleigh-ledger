"""Shared app context: household + catalog + ledger + vendor clients."""
from __future__ import annotations

import copy
import json
import os
import pathlib
import threading

from dotenv import load_dotenv

ROOT = pathlib.Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
os.environ.setdefault("LLM_API_KEY", os.environ.get("OPENAI_API_KEY", ""))  # Cognee reads LLM_API_KEY
os.environ.setdefault("LLM_MODEL", "gpt-4o-mini")
os.environ.setdefault("TELEMETRY_DISABLED", "true")

from server.ledger.store import Ledger  # noqa: E402
from server.policy import engine  # noqa: E402
from server import flags  # noqa: E402


class Context:
    def __init__(self, household_file: str | None = None):
        hf = household_file or os.environ.get("HOUSEHOLD", "family")
        self.base_household = json.loads((ROOT / f"data/households/{hf}.json").read_text())
        self.catalog = json.loads((ROOT / "data/catalog/catalog.json").read_text())
        self.ledger = Ledger()
        self.llm_calls = 0
        self.call_cap = int(os.environ.get("CALL_CAP", "400"))
        self.lock = threading.Lock()
        self._senso = None
        self.search_cache: dict[str, list] = {}

    # --- household with live state (allocations, verification) ---------------------------------
    @property
    def household(self) -> dict:
        h = copy.deepcopy(self.base_household)
        alloc = self.ledger.get("allocations", {})
        verified = self.ledger.get("verified", {})
        for m in h["members"]:
            if m["id"] in alloc:
                m["allocation"] = alloc[m["id"]]
            m["verified"] = verified.get(m["id"], m.get("verified", False))
        return h

    def member(self, mid: str) -> dict | None:
        return engine.member(self.household, mid)

    @property
    def pot_unlocked(self) -> bool:
        return bool(self.ledger.get("pot_unlocked", os.environ.get("POT_UNLOCKED_DEFAULT", "0") == "1"))

    @property
    def policy_mode(self) -> str:
        return self.ledger.get("policy_mode", os.environ.get("POLICY_MODE", "enforce"))

    @property
    def skills_version(self) -> str:
        return self.ledger.get("skills_version", os.environ.get("SKILLS_VERSION", "v1"))

    def remaining(self, mid: str) -> float:
        m = self.member(mid)
        return float(m["allocation"]) - self.ledger.spent().get(m["id"], 0.0) if m else 0.0

    def store_for_sku(self, sku: str) -> dict | None:
        _, store = engine.find_product(self.catalog, sku)
        return store

    def store_from_title(self, title: str | None) -> dict | None:
        for s in self.catalog["stores"]:
            if title and title.startswith(s["name"]):
                return s
        return None

    @property
    def senso(self):
        if self._senso is None:
            from server.senso import Senso
            self._senso = Senso(synthetic=os.environ.get("SENSO_SYNTHETIC", "0") == "1")
        return self._senso

    def count_llm_call(self) -> None:
        with self.lock:
            self.llm_calls += 1
            if self.llm_calls > self.call_cap:
                raise RuntimeError(f"LLM call cap reached ({self.call_cap}). Raise CALL_CAP to continue.")

    def gate(self, name: str, member: dict) -> bool:
        return flags.check_gate(name, member)
