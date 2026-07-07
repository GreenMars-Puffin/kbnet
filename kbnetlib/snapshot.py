"""Schema snapshot + health heartbeat written to the exchange outbox."""
import collections
import datetime
import json
import os


def _now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _bucket(relpath, depth=2):
    parts = relpath.split("/")[:-1]
    if not parts:
        return "(root)"
    return "/".join(parts[:depth])


def build_snapshot(peer, notes, m, m_hash):
    folders = collections.Counter()
    tags = collections.Counter()
    fm_keys = collections.Counter()
    personal_by_folder = collections.Counter()
    personal = 0
    for n in notes:
        bucket = _bucket(n.relpath)
        folders[bucket] += 1
        for t in n.tags:
            tags[t.lower()] += 1
        for k in n.fm:
            fm_keys[k] += 1
        if n.personal:
            personal += 1
            personal_by_folder[bucket.split("/")[0]] += 1
    total = len(notes)
    return {
        "generated_at": _now(),
        "peer": peer,
        "total_md": total,
        "folders": dict(sorted(folders.items())),
        "tags": dict(tags.most_common(200)),
        "frontmatter_keys": dict(fm_keys.most_common(100)),
        "personal": {
            "count": personal,
            "share": round(personal / total, 3) if total else 0,
            "by_top_folder": dict(sorted(personal_by_folder.items())),
        },
        "sync_folders": m.get("sync_folders", []),
        "manifest_hash": m_hash,
    }


def write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=False)
        f.write("\n")


def build_health(peer, started, export_stats, fulfilled, tool_rev, m_hash, errors, disabled=False):
    return {
        "peer": peer,
        "ran_at": _now(),
        "duration_s": round(__import__("time").time() - started, 1),
        "tool_rev": tool_rev,
        "manifest_hash": m_hash,
        "disabled": disabled,
        "export": export_stats,
        "requests_fulfilled": fulfilled,
        "errors": errors,
    }
