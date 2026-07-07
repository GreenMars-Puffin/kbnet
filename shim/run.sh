#!/bin/bash
# kbnet shim — installed once, never edited. The agent updates itself from git,
# so maintenance never requires touching this machine.
set -u
KBNET_HOME="${KBNET_HOME:-$HOME/.kbnet}"
export KBNET_HOME
TOOL="$KBNET_HOME/tool"
CONTROL="$KBNET_HOME/exchange/control/config.json"

REF="main"
if [ -f "$CONTROL" ]; then
  R=$(/usr/bin/python3 -c 'import json,sys;print(json.load(open(sys.argv[1])).get("tool_ref") or "main")' "$CONTROL" 2>/dev/null)
  [ -n "${R:-}" ] && REF="$R"
fi

if [ -d "$TOOL/.git" ]; then
  /usr/bin/git -C "$TOOL" fetch --quiet origin 2>/dev/null || true
  if /usr/bin/git -C "$TOOL" show-ref --quiet "refs/remotes/origin/$REF"; then
    /usr/bin/git -C "$TOOL" checkout --quiet "$REF" 2>/dev/null || true
    /usr/bin/git -C "$TOOL" reset --hard --quiet "origin/$REF" 2>/dev/null || true
  else
    # tag or sha pin
    /usr/bin/git -C "$TOOL" checkout --quiet "$REF" 2>/dev/null || true
  fi
fi

exec /usr/bin/python3 "$TOOL/kbnet.py" run
