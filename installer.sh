#!/bin/bash
# kbnet installer — one-time setup on a teammate's Mac. After this, kbnet
# runs and updates itself; nobody ever needs to touch this machine again.
set -euo pipefail

KBNET_HOME="${KBNET_HOME:-$HOME/.kbnet}"
TOOL_URL="${KBNET_TOOL_URL:-https://github.com/GreenMars-Puffin/kbnet.git}"
INTERVAL="${KBNET_INTERVAL:-3600}"

bold() { printf '\n\033[1m%s\033[0m\n' "$*"; }
say()  { printf '%s\n' "$*"; }
ask()  { local v; read -r -p "$1${2:+ [$2]}: " v; printf '%s' "${v:-${2:-}}"; }

bold "🌿 kbnet setup"
say "kbnet connects your knowledge base to the GreenMars company KB — and"
say "keeps your personal notes at home while it does it. Setup takes about"
say "ten minutes, once, and then it just quietly works."

command -v git >/dev/null 2>&1 || { say "git is required — run: xcode-select --install"; exit 1; }
command -v python3 >/dev/null 2>&1 || { say "python3 is required — run: xcode-select --install"; exit 1; }

PEER="${KBNET_PEER:-$(ask "Your kbnet name (first name, lowercase — e.g. casey)")}"
[ -n "$PEER" ] || { say "A name is required."; exit 1; }
VAULT="${KBNET_VAULT:-$(ask "Path to your vault" "$HOME/vault")}"
VAULT="${VAULT/#\~/$HOME}"
[ -d "$VAULT" ] || { say "Hmm, $VAULT doesn't exist — check the path and re-run."; exit 1; }
EXCHANGE_URL="${KBNET_EXCHANGE_URL:-$(ask "Exchange repo URL (Chris gives you this)" "git@github.com:GreenMars-Puffin/kbnet-$PEER.git")}"

mkdir -p "$KBNET_HOME"

if [ ! -d "$KBNET_HOME/tool/.git" ]; then
  bold "→ Fetching the kbnet tool"
  git clone --quiet "$TOOL_URL" "$KBNET_HOME/tool"
fi

KEY="$KBNET_HOME/id_kbnet"
if [ ! -f "$KEY" ]; then
  ssh-keygen -q -t ed25519 -N "" -C "kbnet-$PEER" -f "$KEY"
fi
bold "→ Send this key to Chris so he can connect your exchange repo:"
echo
cat "$KEY.pub"
echo
read -r -p "Press Enter once Chris says the key is added… " _

export GIT_SSH_COMMAND="ssh -i $KEY -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new"
until git ls-remote "$EXCHANGE_URL" >/dev/null 2>&1; do
  say "Can't reach the exchange repo yet — the key may still be propagating."
  read -r -p "Press Enter to try again (Ctrl-C to bail)… " _
done
if [ ! -d "$KBNET_HOME/exchange/.git" ]; then
  git clone --quiet "$EXCHANGE_URL" "$KBNET_HOME/exchange"
fi
unset GIT_SSH_COMMAND

python3 - "$PEER" "$VAULT" "$EXCHANGE_URL" "$KBNET_HOME" <<'PY'
import json, sys
peer, vault, url, home = sys.argv[1:5]
with open(f"{home}/config.json", "w") as f:
    json.dump({"peer": peer, "vault_path": vault, "exchange_url": url}, f, indent=2)
    f.write("\n")
PY

mkdir -p "$KBNET_HOME/shim" "$KBNET_HOME/bin"
cp "$KBNET_HOME/tool/shim/run.sh" "$KBNET_HOME/shim/run.sh"
chmod +x "$KBNET_HOME/shim/run.sh"
cat > "$KBNET_HOME/bin/kbnet" <<EOF
#!/bin/bash
export KBNET_HOME="$KBNET_HOME"
exec /usr/bin/python3 "$KBNET_HOME/tool/kbnet.py" "\$@"
EOF
chmod +x "$KBNET_HOME/bin/kbnet"

bold "→ Scheduling kbnet (runs about once an hour)"
LOG="$HOME/Library/Logs/kbnet.log"
PLIST="$HOME/Library/LaunchAgents/com.greenmars.kbnet.plist"
mkdir -p "$HOME/Library/Logs" "$HOME/Library/LaunchAgents"
sed -e "s|__KBNET_HOME__|$KBNET_HOME|g" \
    -e "s|__LOG__|$LOG|g" \
    -e "s|__INTERVAL__|$INTERVAL|g" \
    "$KBNET_HOME/tool/launchd/com.greenmars.kbnet.plist.template" > "$PLIST"
launchctl unload "$PLIST" 2>/dev/null || true
launchctl load -w "$PLIST"

bold "→ Last step: mark your personal areas"
say "A browser page will open. Anything you mark stays on this machine, always."
say "(Save on that page and setup finishes on its own.)"
"$KBNET_HOME/bin/kbnet" ui --setup

bold "✅ kbnet is set up!"
say "• It runs quietly about once an hour (and catches up after your Mac wakes)."
say "• Your plain-English sync report: $VAULT/kbnet/last-export-report.md"
say "• Change your personal areas any time: $KBNET_HOME/bin/kbnet ui"
say "• Check on it: $KBNET_HOME/bin/kbnet status"
