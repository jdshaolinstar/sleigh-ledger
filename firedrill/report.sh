#!/usr/bin/env bash
# bash firedrill/report.sh <campaign> [drill-id ...]  -> summary, then conversation + results per drill
export NVM_DIR="$HOME/.nvm"; . "$NVM_DIR/nvm.sh" >/dev/null
C=$1; shift
for d in "$@"; do
  echo "==== $d"
  firedrill report "$C" drill "$d" conversation 2>&1 | tail -30
  firedrill report "$C" drill "$d" results 2>&1 | tail -20
done
