"""Build web/drills.json (the Drills tab) from two Firedrill campaigns: before (thin skills, rules logged)
and after (full skills, rules enforced). Run inside WSL from the repo root:
    python3 firedrill/build_drills.py <before-campaign> <after-campaign>
Scores and conversations are copied from `firedrill report`; nothing is invented.
"""
import difflib
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
NVM = 'export NVM_DIR="$HOME/.nvm"; . "$NVM_DIR/nvm.sh" >/dev/null; '


def fd(args, as_json=True):
    out = subprocess.run(["bash", "-c", NVM + "firedrill " + args + (" --json" if as_json else "")],
                         capture_output=True, text=True, cwd=ROOT).stdout
    if not as_json:
        return out
    return [json.loads(l) for l in out.splitlines() if l.strip().startswith("{")]


def scenario_names():
    refs = json.loads((ROOT / "firedrill/refs.json").read_text())
    names = {}
    for k, v in refs.items():
        if k.startswith("scenario:"):
            s = json.loads((ROOT / f"firedrill/scenarios/{k.split(':', 1)[1]}.json").read_text())
            names[v["id"]] = s["name"]
    return names


def transcript(campaign, drill):
    text = fd(f"report {campaign} drill {drill} conversation", as_json=False)
    turns = [l.split()[1] for l in text.splitlines() if l.strip() and l.split()[0].isdigit() and "completed" in l]
    lines = []
    for t in turns:
        body = fd(f"report {campaign} drill {drill} conversation {t}", as_json=False)
        keep = [l for l in body.splitlines()[1:] if l.strip() and "Message text is data" not in l]
        lines.append("\n".join(keep)[:900])
    return lines


def campaign(cid, title):
    data = next(d["data"] for d in fd(f"report {cid}") if d["type"] == "native_campaign_report")
    names = scenario_names()
    evals = data.get("evaluations") or {}
    drills = []
    for slot in data["slots"]["results"] if isinstance(data["slots"], dict) else data["slots"]:
        rep = (evals.get(slot.get("assignment_id")) or {}).get("report") or {}
        score = rep.get("mean_criterion_score")
        status = "pass" if rep.get("criteria_met") else ("not assessable" if rep.get("not_assessable") else "fail")
        drills.append({
            "scenario": names.get(slot["scenario_id"], slot["scenario_id"]),
            "drill_id": slot.get("drill_id"),
            "score": score if score is not None else "n/a",
            "pass": bool(rep.get("criteria_met")),
            "status": status,
            "ending": rep.get("ending_reason"),
            "transcript": transcript(cid, slot["drill_id"]) if slot.get("drill_id") else [],
        })
    return {"title": title, "campaign": cid, "drills": drills}


def main():
    before, after = sys.argv[1], sys.argv[2]
    v0 = (ROOT / "server/agent/skills_v0.md").read_text().splitlines()
    v1 = (ROOT / "server/agent/skills.md").read_text().splitlines()
    diff = "\n".join(list(difflib.unified_diff(v0, v1, "skills_v0.md (before)", "skills.md (after)", lineterm=""))[:60])
    out = {
        "note": "Scores from Firedrill (rubric judge, threshold 75). Before = thin skills + rules only logged. After = full skills + rules enforced.",
        "runs": [campaign(before, "Before: thin skills, rules only logged"), campaign(after, "After: full skills.md, rules enforced")],
        "diff": diff + "\n\n+ policy engine switched from log to enforce",
    }
    (ROOT / "web/drills.json").write_text(json.dumps(out, indent=2))
    for r in out["runs"]:
        print(r["title"], [(d["scenario"], d["status"], d["score"]) for d in r["drills"]])


if __name__ == "__main__":
    main()
