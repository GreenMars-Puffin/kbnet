"""One kbnet cycle: pull control → scan → export → fulfill requests →
snapshot/heartbeat → local report → commit & push."""
import datetime
import json
import os
import subprocess
import time

from . import config, gitutil, manifest, report, sanitize, scan, snapshot, sources

EXCHANGE_URL_TEMPLATE = os.environ.get(
    "KBNET_EXCHANGE_URL_TEMPLATE", "git@github.com:GreenMars-Puffin/kbnet-{peer}.git"
)


def _norm_url(url):
    url = url.strip().rstrip("/")
    return url[:-4] if url.endswith(".git") else url


def _self_heal_exchange(cfg, exchange, errors, log):
    """If the exchange clone's origin is the TOOL repo (a bad URL entered at
    install), re-point it to the conventional exchange repo. Hands-free repair
    for the wrong-repo foot-gun."""
    origin = gitutil.git(exchange, "remote", "get-url", "origin", check=False)
    tool_origin = gitutil.git(
        config.paths()["tool"], "remote", "get-url", "origin", check=False
    )
    if not origin or not tool_origin or _norm_url(origin) != _norm_url(tool_origin):
        return
    correct = EXCHANGE_URL_TEMPLATE.format(peer=cfg["peer"])
    log(f"  exchange clone points at the tool repo (bad URL at install) — "
        f"re-pointing to {correct}")
    quarantine = exchange + ".misconfigured"
    if os.path.isdir(quarantine):
        import shutil
        shutil.rmtree(quarantine, ignore_errors=True)
    os.rename(exchange, quarantine)
    result = subprocess.run(
        ["git", "clone", "--quiet", correct, exchange],
        env=gitutil._env(), capture_output=True, text=True,
    )
    if result.returncode != 0:
        os.rename(quarantine, exchange)  # roll back, retry next run
        errors.append(f"exchange re-point failed: {result.stderr.strip()[:200]}")
        return
    cfg["exchange_url"] = correct
    persist = {k: v for k, v in cfg.items() if k != "exchange_path"}
    with open(config.paths()["config"], "w", encoding="utf-8") as f:
        json.dump(persist, f, indent=2)
        f.write("\n")
    log("  exchange repaired — config updated")


def run_cycle(log=print):
    started = time.time()
    cfg = config.load_local()
    peer = cfg["peer"]
    vault = os.path.expanduser(cfg["vault_path"])
    exchange = cfg["exchange_path"]
    errors = []

    if not os.path.isdir(vault):
        raise SystemExit(f"kbnet: vault not found at {vault}")
    if not os.path.isdir(os.path.join(exchange, ".git")):
        raise SystemExit(f"kbnet: exchange repo not found at {exchange} — re-run the installer")

    log(f"kbnet run · peer={peer}")
    _self_heal_exchange(cfg, exchange, errors, log)
    gitutil.sync_exchange(exchange, errors)
    control = config.load_control(exchange)

    if control.get("disabled"):
        log("  paused via control config — sending heartbeat only")
        health = snapshot.build_health(
            peer, started, {}, [], gitutil.tool_rev(), "", errors, disabled=True
        )
        snapshot.write_json(os.path.join(exchange, "outbox", "health.json"), health)
        gitutil.commit_push(exchange, peer, f"kbnet heartbeat (paused) {_today()}", errors)
        return health

    m = manifest.load(vault)
    if control.get("sync_folders_override"):
        m["sync_folders"] = list(control["sync_folders_override"])
    m_hash = manifest.manifest_hash(m)

    notes, other_files = scan.scan_vault(vault)
    manifest.classify(notes, m)
    personal_paths = sorted(n.relpath for n in notes if n.personal)

    export_stats = _export_kb(notes, exchange, m, control)
    log(f"  export: {export_stats['synced']} in sync "
        f"({export_stats['updated']} updated, {export_stats['removed']} removed), "
        f"{len(personal_paths)} personal kept home")

    fulfilled = sources.fulfill_requests(vault, notes, other_files, exchange, m, control, log)
    request_metas = _read_metas(exchange, fulfilled)

    snap = snapshot.build_snapshot(peer, notes, m, m_hash)
    snapshot.write_json(os.path.join(exchange, "outbox", "schema-snapshot.json"), snap)
    health = snapshot.build_health(
        peer, started, export_stats, fulfilled, gitutil.tool_rev(), m_hash, errors
    )
    snapshot.write_json(os.path.join(exchange, "outbox", "health.json"), health)

    report.write_report(vault, peer, export_stats, personal_paths, request_metas, errors)

    committed = gitutil.commit_push(exchange, peer, f"kbnet export {peer} {_today()}", errors)
    # Push failures land in `errors` after health.json is written, so persist
    # them locally where `status` / `doctor` can see them next time.
    _write_last_errors(errors)
    log(f"  {'pushed' if committed and not errors else 'done'} in {health['duration_s']}s"
        + (f" · {len(errors)} issue(s) noted" if errors else ""))
    return health


def _write_last_errors(errors):
    try:
        path = os.path.join(config.paths()["home"], "last-run-errors.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"ts": datetime.datetime.now().isoformat(timespec="seconds"),
                       "errors": errors}, f, indent=2)
            f.write("\n")
    except OSError:
        pass


def _export_kb(notes, exchange, m, control):
    out_dir = os.path.join(exchange, "outbox", "kb")
    extra_callouts = control.get("extra_personal_callouts", [])
    sync_folders = m.get("sync_folders", [])

    expected = {}
    personal_excluded = 0
    callouts_stripped = 0
    for n in notes:
        if not scan.in_folders(n.relpath, sync_folders):
            continue
        if n.personal:
            personal_excluded += 1
            continue
        text, stripped = sanitize.strip_personal_callouts(n.text, extra_callouts)
        callouts_stripped += stripped
        expected[n.relpath] = text

    updated = 0
    for rel, text in expected.items():
        target = os.path.join(out_dir, rel)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        try:
            with open(target, encoding="utf-8") as f:
                if f.read() == text:
                    continue
        except OSError:
            pass
        with open(target, "w", encoding="utf-8") as f:
            f.write(text)
        updated += 1

    removed = 0
    if os.path.isdir(out_dir):
        for root, dirs, files in os.walk(out_dir, topdown=False):
            for fname in files:
                path = os.path.join(root, fname)
                rel = os.path.relpath(path, out_dir).replace(os.sep, "/")
                if rel not in expected:
                    os.remove(path)
                    removed += 1
            if not os.listdir(root) and root != out_dir:
                os.rmdir(root)

    return {
        "synced": len(expected),
        "updated": updated,
        "removed": removed,
        "personal_excluded": personal_excluded,
        "callouts_stripped": callouts_stripped,
    }


def _read_metas(exchange, fulfilled):
    metas = []
    for rid in fulfilled:
        try:
            with open(
                os.path.join(exchange, "outbox", "sources", rid, "_meta.json"),
                encoding="utf-8",
            ) as f:
                metas.append((rid, json.load(f)))
        except (OSError, ValueError):
            metas.append((rid, {}))
    return metas


def _today():
    return datetime.date.today().isoformat()
