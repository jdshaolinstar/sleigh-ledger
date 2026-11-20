#!/usr/bin/env bash
# Run inside WSL: bash firedrill/register.sh   (from the repo root)
set -e
export NVM_DIR="$HOME/.nvm"; . "$NVM_DIR/nvm.sh" >/dev/null
cd "$(dirname "$0")/.."
ID=$(node -e 'const c=require("crypto"),f=require("fs");const p=f.realpathSync(process.argv[1]);const s=f.statSync(p,{bigint:true});console.log(c.createHash("sha256").update("firedrill.root-identity.v1\0").update(p).update("\0").update(`${s.dev}:${s.ino}`).digest("hex"))' .)
AD=$(sha256sum server/app.py | cut -d' ' -f1)
echo "root identity: $ID"
cat > firedrill/descriptor.json <<EOF
{
  "schema": "firedrill.local-descriptor.v1",
  "source_roots": [{"alias": "app", "identity_sha256": "$ID"}],
  "services": [{"alias": "agent", "root_alias": "app", "role": "agent", "depends_on": [], "configuration": []}],
  "entry_service": "agent",
  "driver": {"profile": "http.v1", "adapter_sha256": "$AD", "authentication": "anonymous", "state_domains": ["proc"]},
  "state_domains": [{"alias": "proc", "service_alias": "agent", "kind": "process", "location": "local", "reset": "fresh-process", "concurrency": "serial", "hook_sha256": null}],
  "dependencies": []
}
EOF
if [ $# -gt 0 ]; then
  firedrill register --descriptor firedrill/descriptor.json --declared-agent-name "Claude Code" "$@"
else
  firedrill register --descriptor firedrill/descriptor.json --name "Sleigh Ledger elf" --declared-agent-name "Claude Code"
fi
