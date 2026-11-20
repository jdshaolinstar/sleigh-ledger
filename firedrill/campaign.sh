#!/usr/bin/env bash
# bash firedrill/campaign.sh <world-id>   -> plans, applies (approved by Jermaine) and prints the campaign id
export NVM_DIR="$HOME/.nvm"; . "$NVM_DIR/nvm.sh" >/dev/null
P=$(firedrill plan --world "$1" 2>&1 | tee /tmp/plan.log | sed -n 's/^Plan //p' | head -1)
grep -E "stimate|nresolved" /tmp/plan.log
echo "plan=$P"
[ -n "$P" ] && timeout 300 firedrill apply "$P" --approve --follow 2>&1 | grep -E "stimate|Campaign|rror|efused"
