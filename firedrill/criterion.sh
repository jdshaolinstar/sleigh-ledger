#!/usr/bin/env bash
export NVM_DIR="$HOME/.nvm"; . "$NVM_DIR/nvm.sh" >/dev/null
firedrill report "$1" drill "$2" results "$3" --json 2>/dev/null | python3 -c '
import sys, json
for l in sys.stdin:
    if l.startswith("{"):
        d = json.loads(l)["data"]
        s = json.dumps(d)
        print(s[:3000])
'
