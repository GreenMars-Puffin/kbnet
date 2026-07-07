"""On-demand source requests.

The hub drops request files in control/requests/; each cycle serves matching
non-personal files into outbox/sources/<id>/. Personal-flagged material is
never served — a request that touches it gets the non-personal remainder
plus a count of what stayed home.
"""
import datetime
import fnmatch
import json
import os
import shutil

from . import manifest as manifest_mod
from . import sanitize


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


def _iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def fulfill_requests(vault, notes, other_files, exchange, m, control, log):
    req_dir = os.path.join(exchange, "control", "requests")
    out_dir = os.path.join(exchange, "outbox", "sources")
    fulfilled = []
    if os.path.isdir(req_dir):
        for fname in sorted(os.listdir(req_dir)):
            if not fname.endswith(".json"):
                continue
            rid = fname[:-5]
            dest = os.path.join(out_dir, rid)
            if os.path.exists(os.path.join(dest, "_meta.json")):
                continue
            meta = _serve_one(
                vault, notes, other_files, os.path.join(req_dir, fname), dest, m, control
            )
            log(f"  request {rid}: served {len(meta['served'])} file(s), "
                f"{meta['personal_excluded']} personal kept home")
            fulfilled.append(rid)
    expired = _expire(out_dir, control.get("sources_ttl_days", 14))
    if expired:
        log(f"  expired {expired} old source request(s) from the outbox")
    return fulfilled


def _serve_one(vault, notes, other_files, req_path, dest, m, control):
    os.makedirs(dest, exist_ok=True)
    try:
        with open(req_path, encoding="utf-8") as f:
            req = json.load(f)
    except (OSError, ValueError) as e:
        meta = {"error": f"unreadable request: {e}", "served": [], "personal_excluded": 0}
        _write_meta(dest, meta)
        return meta

    max_results = int(req.get("max_results") or control.get("max_request_results", 50))
    max_bytes = int(control.get("max_source_file_mb", 5)) * 1024 * 1024
    extra_callouts = control.get("extra_personal_callouts", [])

    matched_md = []
    matched_other = []
    personal_excluded = 0

    patterns = [p.replace(os.sep, "/") for p in req.get("paths", [])]
    if patterns:
        for n in notes:
            if any(fnmatch.fnmatch(n.relpath, p) for p in patterns):
                if n.personal:
                    personal_excluded += 1
                else:
                    matched_md.append(n)
        for rel, path in other_files:
            if any(fnmatch.fnmatch(rel, p) for p in patterns):
                if manifest_mod.path_is_personal(rel, m):
                    personal_excluded += 1
                else:
                    matched_other.append((rel, path))

    query = (req.get("query") or "").strip().lower()
    if query:
        seen = {n.relpath for n in matched_md}
        for n in notes:
            if n.relpath in seen:
                continue
            if query in n.text.lower():
                if n.personal:
                    personal_excluded += 1
                else:
                    matched_md.append(n)

    served = []
    skipped_large = []
    for n in matched_md[:max_results]:
        text, _ = sanitize.strip_personal_callouts(n.text, extra_callouts)
        target = os.path.join(dest, n.relpath)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w", encoding="utf-8") as f:
            f.write(text)
        served.append(n.relpath)
    for rel, path in matched_other[: max(0, max_results - len(served))]:
        try:
            if os.path.getsize(path) > max_bytes:
                skipped_large.append(rel)
                continue
        except OSError:
            continue
        target = os.path.join(dest, rel)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copyfile(path, target)
        served.append(rel)

    truncated = max(0, len(matched_md) + len(matched_other) - len(served) - len(skipped_large))
    meta = {
        "request": req,
        "fulfilled_at": _iso(_now()),
        "served": served,
        "personal_excluded": personal_excluded,
        "skipped_large": skipped_large,
        "truncated": truncated,
    }
    _write_meta(dest, meta)
    return meta


def _write_meta(dest, meta):
    with open(os.path.join(dest, "_meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
        f.write("\n")


def _expire(out_dir, ttl_days):
    if not os.path.isdir(out_dir):
        return 0
    cutoff = _now() - datetime.timedelta(days=ttl_days)
    removed = 0
    for rid in os.listdir(out_dir):
        meta_path = os.path.join(out_dir, rid, "_meta.json")
        try:
            with open(meta_path, encoding="utf-8") as f:
                fulfilled_at = json.load(f).get("fulfilled_at", "")
            when = datetime.datetime.strptime(fulfilled_at, "%Y-%m-%dT%H:%M:%SZ").replace(
                tzinfo=datetime.timezone.utc
            )
        except (OSError, ValueError):
            continue
        if when < cutoff:
            shutil.rmtree(os.path.join(out_dir, rid), ignore_errors=True)
            removed += 1
    return removed
