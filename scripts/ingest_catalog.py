"""Load the fictional store catalog into Senso (one doc per store) and wait until it is searchable.

Usage:  .venv/Scripts/python -m scripts.ingest_catalog            (dry run: prints the docs)
        .venv/Scripts/python -m scripts.ingest_catalog --live     (posts to Senso, uses credits)
"""
from __future__ import annotations

import json
import pathlib
import sys

from dotenv import load_dotenv

ROOT = pathlib.Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")


def store_doc(store: dict) -> tuple[str, str]:
    lines = [
        f"# {store['name']} ({store['kind']})",
        "Fictional store in the Sleigh Ledger demo town. Prices in USD.",
        "",
        f"Store id: {store['id']}",
        f"Returns policy: {store['returns']}",
        f"Shipping: {store['shipping']}",
        "",
        "## Products",
    ]
    for p in store["products"]:
        stock = "in stock" if p["stock"] > 0 else "OUT OF STOCK"
        age = "all ages" if p["min_age"] == 0 else f"ages {p['min_age']}+"
        lines.append(
            f"- SKU {p['sku']}: {p['name']}. Price ${p['price']:.2f}. Suitable for {age}. {stock}. "
            f"Tags: {', '.join(p['tags'])}. {p['desc']} Sold at {store['name']}."
        )
    return f"{store['name']} catalog and policies", "\n".join(lines)


def main() -> None:
    catalog = json.loads((ROOT / "data/catalog/catalog.json").read_text())
    docs = [store_doc(s) for s in catalog["stores"]]
    if "--live" not in sys.argv:
        for title, text in docs:
            print(f"=== {title} ===\n{text}\n")
        print(f"Dry run: {len(docs)} docs. Re-run with --live to post them to Senso.")
        return

    from server.senso import Senso

    s = Senso()
    print("org:", json.dumps(s.me())[:200])
    index = {}
    for title, text in docs:
        r = s.add_raw(title, text)
        print("added", title, {k: r.get(k) for k in ("id", "kb_node_id", "processing_status", "duplicate")})
        index[title] = r
    for title, r in index.items():
        if r.get("kb_node_id"):
            print("processed", title, s.wait_processed(r["kb_node_id"]))
    out = ROOT / "data/runtime"
    out.mkdir(parents=True, exist_ok=True)
    (out / "senso_index.json").write_text(json.dumps(index, indent=2))
    print("check:", json.dumps(s.search_context("skateboard gift for a 14 year old under $50", 3))[:800])


if __name__ == "__main__":
    main()
