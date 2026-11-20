#!/usr/bin/env bash
export NVM_DIR="$HOME/.nvm"; . "$NVM_DIR/nvm.sh" >/dev/null
C=$1; D=$2
firedrill report "$C" drill "$D" evidence 2>&1 | tail -25
for t in $(firedrill report "$C" drill "$D" conversation 2>&1 | awk '/completed/ {print $2}'); do
  firedrill report "$C" drill "$D" conversation "$t" 2>&1 | sed -n '2,40p'
done
