"""Save personas, evaluations and scenarios to the Firedrill library, then save a world and plan it.

Run inside WSL from the repo root:  python3 firedrill/setup_world.py <agent-id>
Writes firedrill/refs.json and prints the plan review. Nothing runs and no credits are spent until
`firedrill apply <plan-id> --approve` (which needs Jermaine's OK).
"""
import json
import os
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
NVM = 'export NVM_DIR="$HOME/.nvm"; . "$NVM_DIR/nvm.sh" >/dev/null; '


def fd(args: str) -> list[dict]:
    out = subprocess.run(["bash", "-c", NVM + "firedrill " + args + " --json"], capture_output=True, text=True, cwd=HERE.parent)
    lines = [json.loads(l) for l in out.stdout.splitlines() if l.strip().startswith("{")]
    if out.returncode != 0:
        print(out.stdout[-2000:], out.stderr[-2000:])
        raise SystemExit(f"firedrill {args} failed")
    return lines


def ref(lines: list[dict]) -> dict:
    v = next(l["data"] for l in lines if l["type"] in ("library_version",))
    return {"origin": "native_library", "kind": v["kind"], "id": v["id"], "revision": v["revision"], "digest": v["digest"]}


def main():
    agent = sys.argv[1]
    refs = json.loads((HERE / "refs.json").read_text()) if (HERE / "refs.json").exists() else {}
    for kind, folder in (("persona", "personas"), ("evaluation", "evaluations")):
        for f in sorted((HERE / folder).glob("*.json")):
            key = f"{kind}:{f.stem}"
            if key not in refs:
                refs[key] = ref(fd(f"library save --kind {kind} --file firedrill/{folder}/{f.name}"))
                print("saved", key, refs[key]["id"])
    for f in sorted((HERE / "scenarios").glob("*.json")):
        key = f"scenario:{f.stem}"
        if key in refs:
            continue
        s = json.loads(f.read_text())
        s["personas"] = [refs[p.replace("@", "")] for p in s["personas"]]
        s["evaluations"] = [refs[e.replace("@", "")] for e in s["evaluations"]]
        tmp = HERE / f".resolved-{f.stem}.json"
        tmp.write_text(json.dumps(s))
        refs[key] = ref(fd(f"library save --kind scenario --file firedrill/{tmp.name}"))
        tmp.unlink()
        print("saved", key, refs[key]["id"])
    (HERE / "refs.json").write_text(json.dumps(refs, indent=2))

    world = {
        "schema": "firedrill.native-world.v1",
        "name": "Sleigh Ledger household rules",
        "description": "Simulated Holly family members try to break the household's gift rules.",
        "dependencies": [],
        "resources": [v for k, v in refs.items() if k.startswith("scenario:")],
        "configuration_names": [],
        "execution": {"repetitions": 1, "max_parallel": 1, "reset": "serialized"},
    }
    (HERE / "world.json").write_text(json.dumps(world, indent=2))
    lines = fd(f"world save --agent {agent} --file firedrill/world.json")
    print(json.dumps(lines[-1])[:1500])
    world_id = next((l["data"].get("world_id") or l["data"].get("id") for l in lines if l["type"].startswith("world")), None)
    print("WORLD", world_id)
    if world_id:
        refs["world"] = world_id
        (HERE / "refs.json").write_text(json.dumps(refs, indent=2))


if __name__ == "__main__":
    main()
