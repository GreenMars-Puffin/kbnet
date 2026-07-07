#!/bin/bash
# kbnet end-to-end smoke test: throwaway vault + bare exchange repo, two full
# cycles, assertions on personal filtering, sanitization, requests, idempotence.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
export KBNET_HOME="$TMP/home"
mkdir -p "$KBNET_HOME"

fail() { echo "FAIL: $1"; exit 1; }

# --- fake vault -------------------------------------------------------------
VAULT="$TMP/vault"
mkdir -p "$VAULT/wiki/projects" "$VAULT/wiki/notes" "$VAULT/personal" "$VAULT/raw/meetings"

cat > "$VAULT/wiki/projects/acme.md" <<'EOF'
---
title: Acme Lease
scope: business
tags: [client, cre]
---
Acme is negotiating a lease at 540 Congress.

> [!personal] dentist thursday
> also anniversary dinner reservation

Rent target is $24/sf.
EOF

cat > "$VAULT/wiki/notes/beach-house.md" <<'EOF'
---
title: Beach House
scope: personal
---
Family beach house planning.
EOF

cat > "$VAULT/wiki/notes/tagged.md" <<'EOF'
Kid's soccer schedule #personal
EOF

cat > "$VAULT/personal/journal.md" <<'EOF'
Dear diary.
EOF

cat > "$VAULT/raw/meetings/2026-06-30-acme.md" <<'EOF'
Transcript: Acme meeting. Rent discussed at length.
EOF

# --- exchange repo (bare + seeded control) ----------------------------------
BARE="$TMP/exchange.git"
git init --bare --quiet -b main "$BARE"
SEED="$TMP/seed"
git clone --quiet "$BARE" "$SEED" 2>/dev/null
mkdir -p "$SEED/control/requests" "$SEED/outbox"
cat > "$SEED/control/config.json" <<'EOF'
{"tool_ref": "main", "sources_ttl_days": 14}
EOF
cat > "$SEED/control/requests/req-acme.json" <<'EOF'
{"paths": ["raw/meetings/*acme*"], "reason": "fact-check Acme lease claim"}
EOF
cat > "$SEED/control/requests/req-personal.json" <<'EOF'
{"paths": ["personal/*"], "reason": "must be refused"}
EOF
git -C "$SEED" add -A
git -C "$SEED" -c user.name=seed -c user.email=seed@test commit --quiet -m seed
git -C "$SEED" push --quiet origin main

git clone --quiet "$BARE" "$KBNET_HOME/exchange" 2>/dev/null
cat > "$KBNET_HOME/config.json" <<EOF
{"peer": "testpeer", "vault_path": "$VAULT", "exchange_url": "$BARE"}
EOF

# --- run cycle 1 -------------------------------------------------------------
python3 "$ROOT/kbnet.py" run

CHECK="$TMP/check"
git clone --quiet "$BARE" "$CHECK" 2>/dev/null

[ -f "$CHECK/outbox/kb/wiki/projects/acme.md" ] || fail "business note not exported"
grep -q "dentist" "$CHECK/outbox/kb/wiki/projects/acme.md" && fail "[!personal] callout leaked"
grep -q "Rent target" "$CHECK/outbox/kb/wiki/projects/acme.md" || fail "business content missing after sanitize"
[ ! -e "$CHECK/outbox/kb/wiki/notes/beach-house.md" ] || fail "scope:personal note leaked"
[ ! -e "$CHECK/outbox/kb/wiki/notes/tagged.md" ] || fail "#personal-tagged note leaked"
[ ! -e "$CHECK/outbox/kb/personal" ] || fail "personal folder exported"
[ ! -e "$CHECK/outbox/kb/raw" ] || fail "raw exported routinely (should be request-only)"

[ -f "$CHECK/outbox/sources/req-acme/raw/meetings/2026-06-30-acme.md" ] || fail "source request not fulfilled"
[ -f "$CHECK/outbox/sources/req-personal/_meta.json" ] || fail "personal request meta missing"
LEAKED=$(find "$CHECK/outbox/sources/req-personal" -type f ! -name "_meta.json" | wc -l | tr -d ' ')
[ "$LEAKED" = "0" ] || fail "personal source leaked via request"
grep -q '"personal_excluded": 1' "$CHECK/outbox/sources/req-personal/_meta.json" || fail "personal exclusion not recorded"

[ -f "$CHECK/outbox/schema-snapshot.json" ] || fail "schema snapshot missing"
[ -f "$CHECK/outbox/health.json" ] || fail "health heartbeat missing"
grep -q '"count": 3' "$CHECK/outbox/schema-snapshot.json" || fail "personal count wrong in snapshot"
[ -f "$VAULT/kbnet/last-export-report.md" ] || fail "local sync report missing"
grep -q "Stayed home" "$VAULT/kbnet/last-export-report.md" || fail "report missing stayed-home section"

# --- run cycle 2: kb export must be byte-identical (idempotent) --------------
python3 "$ROOT/kbnet.py" run
CHECK2="$TMP/check2"
git clone --quiet "$BARE" "$CHECK2" 2>/dev/null
diff -r "$CHECK/outbox/kb" "$CHECK2/outbox/kb" >/dev/null || fail "kb export not idempotent"
[ -f "$CHECK2/outbox/sources/req-acme/_meta.json" ] || fail "fulfilled request lost on cycle 2"

# --- a note edit syncs, a note turned personal is withdrawn -------------------
echo "New paragraph about terms." >> "$VAULT/wiki/projects/acme.md"
python3 - "$VAULT/wiki/notes" <<'PY'
import sys, os
path = os.path.join(sys.argv[1], "flip.md")
open(path, "w").write("---\nscope: business\n---\nStarted business, going personal.\n")
PY
python3 "$ROOT/kbnet.py" run
python3 - "$VAULT/wiki/notes/flip.md" <<'PY'
import sys
open(sys.argv[1], "w").write("---\nscope: personal\n---\nStarted business, going personal.\n")
PY
python3 "$ROOT/kbnet.py" run
CHECK3="$TMP/check3"
git clone --quiet "$BARE" "$CHECK3" 2>/dev/null
grep -q "New paragraph" "$CHECK3/outbox/kb/wiki/projects/acme.md" || fail "edit didn't sync"
[ ! -e "$CHECK3/outbox/kb/wiki/notes/flip.md" ] || fail "note flipped to personal was not withdrawn"

# --- self-heal: exchange mistakenly cloned from the tool repo ------------------
export KBNET_HOME="$TMP/home2"
mkdir -p "$KBNET_HOME"
TOOLBARE="$TMP/toolrepo.git"
git init --bare --quiet -b main "$TOOLBARE"
TSEED="$TMP/tseed"
git clone --quiet "$TOOLBARE" "$TSEED" 2>/dev/null
printf 'tool\n' > "$TSEED/marker.txt"
git -C "$TSEED" add -A && git -C "$TSEED" -c user.name=t -c user.email=t@t commit --quiet -m tool
git -C "$TSEED" push --quiet origin main
git clone --quiet "$TOOLBARE" "$KBNET_HOME/tool" 2>/dev/null
git clone --quiet "$TOOLBARE" "$KBNET_HOME/exchange" 2>/dev/null   # the foot-gun
cat > "$KBNET_HOME/config.json" <<EOF
{"peer": "testpeer", "vault_path": "$VAULT", "exchange_url": "$TOOLBARE"}
EOF
export KBNET_EXCHANGE_URL_TEMPLATE="$BARE"
python3 "$ROOT/kbnet.py" run
ORIGIN=$(git -C "$KBNET_HOME/exchange" remote get-url origin)
[ "$ORIGIN" = "$BARE" ] || fail "self-heal didn't re-point exchange (origin=$ORIGIN)"
grep -q "\"exchange_url\": \"$BARE\"" "$KBNET_HOME/config.json" || fail "self-heal didn't fix config"
[ -d "$KBNET_HOME/exchange.misconfigured" ] || fail "misconfigured clone not quarantined"
CHECK4="$TMP/check4"; git clone --quiet "$BARE" "$CHECK4" 2>/dev/null
grep -q '"peer": "testpeer"' "$CHECK4/outbox/health.json" || fail "healed run didn't push heartbeat"
unset KBNET_EXCHANGE_URL_TEMPLATE

echo "PASS — all kbnet smoke checks green"
