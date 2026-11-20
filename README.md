# Sleigh Ledger

**Elves with receipts, but no spoilers.**

Every family member gets a holiday-shopping elf. The elves shop a trusted store catalog, stay inside a shared
family budget and age rules, and keep an audit trail for every decision. Only the right people can read it:
parents see every receipt, while the person a gift is for sees only that a gift exists.

Built in one day at the Tokens& Personal Agents Hackathon (SF, Nov 20, 2026) for the challenge
*"Build a shopping agent with an audit trail."*

> All stores and products are fictional, and every checkout is **simulated**. No real purchases are made.

## What it does

- **Top-down 3D town.** Each family member's elf walks to the shops. A shop's sign flips to its name when an
  elf heads in, and a toast says *"Dad's elf just bought something at Toy Tower"* without saying what.
- **Family pot.** A parent loads the pot (e.g. $5,000) and sets each person's budget with sliders. Caps by age:
  12 and under $100, teens $250, adults up to the pot. Only a verified parent can move them.
- **Christmas lists from chats.** Each person tells their own elf what they like, own and don't want. The lists
  are shared with the family; gifts already bought show as *claimed* to other givers, never to the list's owner.
- **Household rules enforced in code**, not just in the prompt: budget, age rating (buyer and recipient),
  approved recipients, duplicates, stock, a locked pot, and parent approval for minors.
- **Receipts with the steps behind them.** Every purchase records the memory recalled, the catalog passages used,
  the fact-check verdict on the elf's own claim, each rule check and the feature-gate value.
- **Blocked attempts are visible to parents**, e.g. *"⛔ Alcohol (21+) attempt blocked: Lucy's elf tried Holiday
  sparkling wine gift set ($45) for Mom."*
- **Demo Menu** with forced playbooks (real rules, real Senso checks) to show rules passing and failing on cue.

## How the sponsors' tools are used

| Tool | Role |
|---|---|
| **Senso** (Context Layer) | The trusted store catalog and policies. The elf searches it (`/org/search/context`) and every receipt keeps the `content_id`, `version_id` and score of the passages used. Before buying, the elf's own claim (item, SKU, price, age rating) is fact-checked with `/org/evals/text`; a `conflict` blocks the purchase. |
| **Firedrill** | Simulated family members (a 14-year-old who wants an M-rated game, a 10-year-old over budget, an off-list friend, a parent shopping for a teen) drill the elf through `POST /chat` (`http.v1` driver). See `firedrill/`. |
| **Cognee** | Per-person Christmas-list memory built from chats (`remember` / `recall`). The giver's elf recalls the recipient's list before shopping. |
| **Persona** (sandbox) | A parent completes a Persona inquiry (hosted flow) to unlock the family pot. Only the inquiry id and status are stored. |
| **Statsig** | Feature gate `teen_needs_parent_approval` and purchase events. Falls back to a local default when no key is set (the receipt says which). |
| **OpenAI** (`gpt-5.4-mini`) | Runs the elves' tool loop. |

## Run it

```bash
python -m venv .venv && .venv/Scripts/pip install -r requirements.txt   # Windows path; use .venv/bin on macOS/Linux
cp .env.example .env    # add SENSO_API_KEY, OPENAI_API_KEY (+ optional Persona, Statsig)
python -m scripts.ingest_catalog --live     # load the fictional catalog into Senso
python -m scripts.seed --cognee             # seed the demo Christmas lists (marked as seeded)
python -m uvicorn server.app:app --port 8787
```

Open http://localhost:8787. Use **View as** to switch between family members, **Demo Menu** for forced
playbooks, and **Run the shopping day** to send all six elves out at once.

Tests: `python -m pytest -q tests`

## Layout

```
server/agent/      elf tool loop + skills.md (v1) and skills_v0.md (the thin "before" prompt)
server/policy/     household rules engine (deterministic)
server/ledger/     append-only events + purchases (SQLite)
server/memory/     Christmas lists (Cognee, with a local fallback)
server/senso.py    Senso REST client      server/persona.py  Persona sandbox client
server/flags.py    Statsig gates/events   server/playbooks.py  Demo Menu
web/               Three.js town + panel (no build step)
firedrill/         descriptor, personas, evaluations, scenarios
data/              fictional catalog + household config
```

## Honest notes

- Stores, products and family are fictional. Checkout is simulated.
- The Christmas lists in the demo are **seeded** "earlier chats", written by us.
- In Firedrill drills, the first chat message says who is chatting (it stands in for logging in); ages and budgets
  always come from the household record, never from the chat.
- Senso's fact-check only scores claims about the organization's own catalog, so the elf phrases its claim
  without the store's name.

## Credits

Built with Senso, Firedrill, Cognee, Persona, Statsig, OpenAI and Three.js. Fonts: Fraunces and Inter (Google Fonts).
