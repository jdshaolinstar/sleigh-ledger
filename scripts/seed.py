"""Seed the demo: reset the ledger and load each member's Christmas list from "earlier chats".

These notes are SEEDED (written by us, not from real conversations); the UI and video say so.
Usage: .venv/Scripts/python -m scripts.seed [--unlocked]
"""
from __future__ import annotations

import json
import pathlib
import sys

from server.context import Context
from server.memory import wishes

ROOT = pathlib.Path(__file__).resolve().parents[1]

EARLIER_CHATS = {
    "mom": ["I've been getting into making espresso at home lately.", "I love cozy things for winter evenings.",
            "Please, no more candles, I have too many."],
    "dad": ["I started hiking on weekends.", "My rain jacket is falling apart.", "I like history books."],
    "jill": ["I'm traveling a lot for work next year.", "I journal every morning.", "I'm trying to do more yoga."],
    "sam": ["I'm into skateboarding and streetwear.", "I already have a skateboard deck.", "I listen to music all day."],
    "bill": ["Skateboarding is my favorite thing right now.", "I already have a deck, I need new grip tape and bearings.",
             "I really want Blood Harbor 4.", "No socks please."],
    "lucy": ["I love dinosaurs!", "I like drawing and painting.", "Unicorns are cool."],
}


def main() -> None:
    ctx = Context()
    ctx.ledger.reset()
    notes = ROOT / "data/runtime/wishes.json"
    if notes.exists():
        notes.unlink()
    for mid, lines in EARLIER_CHATS.items():
        m = ctx.member(mid)
        for line in lines:
            r = wishes.remember(mid, m["name"], line, source="seeded earlier chat")
        print(mid, r)
    if "--unlocked" in sys.argv:
        ctx.ledger.put("pot_unlocked", True)
    print(json.dumps({k: len(v) for k, v in wishes.all_lists().items()}))


if __name__ == "__main__":
    main()
