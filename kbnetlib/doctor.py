"""`kbnet doctor` — one-paste diagnostics for remote support.

Prints everything needed to debug an install without touching the machine:
config, vault scan summary, manifest effect, exchange repo state (including
unpushed commits), a timed remote reachability test, persisted errors from
the last run, and the log tail.
"""
import json
import os
import subprocess
import time

from . import config, gitutil, manifest, scan


def _section(title):
    print(f"\n--- {title} ---")


def run():
    print("=== kbnet doctor ===")
    p = config.paths()
    try:
        cfg = config.load_local()
    except (SystemExit, OSError) as e:
        print(f"config: ERROR — {e}")
        return
    print(f"peer: {cfg['peer']}")
    print(f"ssh_443: {cfg.get('ssh_443', False)}")

    _section("vault")
    vault = os.path.expanduser(cfg["vault_path"])
    print(f"path: {vault}")
    if not os.path.isdir(vault):
        print("MISSING — the vault path doesn't exist. Re-run the installer "
              "with the right path.")
    else:
        t0 = time.time()
        notes, _others = scan.scan_vault(vault)
        m = manifest.load(vault)
        manifest.classify(notes, m)
        top = {}
        for n in notes:
            key = n.relpath.split("/")[0] if "/" in n.relpath else "(root)"
            top[key] = top.get(key, 0) + 1
        print(f"markdown notes: {len(notes)} (scanned in {time.time() - t0:.1f}s)")
        for key in sorted(top):
            print(f"  {key}/: {top[key]}")
        in_sync = [n for n in notes if not n.personal
                   and scan.in_folders(n.relpath, m["sync_folders"])]
        personal = sum(1 for n in notes if n.personal)
        print(f"manifest sync_folders: {m['sync_folders']}")
        print(f"would sync: {len(in_sync)} · personal (stays home): {personal}")

    _section("exchange")
    ex = cfg["exchange_path"]
    if not os.path.isdir(os.path.join(ex, ".git")):
        print(f"MISSING clone at {ex}")
    else:
        print(f"path: {ex}")
        status = subprocess.run(
            ["git", "-C", ex, "status", "-sb"], capture_output=True, text=True
        ).stdout.strip().splitlines()
        print(f"branch: {status[0] if status else '?'}")  # shows [ahead N] = unpushed
        log = subprocess.run(
            ["git", "-C", ex, "log", "--oneline", "-3"],
            capture_output=True, text=True,
        ).stdout.strip()
        for line in log.splitlines():
            print(f"  local: {line}")
        t0 = time.time()
        try:
            gitutil.git(ex, "ls-remote", "--heads", "origin")
            print(f"remote: reachable ({time.time() - t0:.1f}s)")
        except (RuntimeError, gitutil.AuthError) as e:
            print(f"remote: FAILED after {time.time() - t0:.1f}s")
            print(f"  {e}")

    _section("last run errors")
    try:
        with open(os.path.join(p["home"], "last-run-errors.json"), encoding="utf-8") as f:
            data = json.load(f)
        if data.get("errors"):
            print(f"as of {data.get('ts', '?')}:")
            for e in data["errors"]:
                print(f"  ! {e}")
        else:
            print(f"none recorded (as of {data.get('ts', '?')})")
    except (OSError, ValueError):
        print("no error file yet (agent hasn't run since this feature shipped)")

    _section("log tail (~/Library/Logs/kbnet.log)")
    try:
        with open(os.path.expanduser("~/Library/Logs/kbnet.log"), encoding="utf-8",
                  errors="replace") as f:
            for line in f.readlines()[-15:]:
                print(f"  {line.rstrip()}")
    except OSError:
        print("no log file")
