"""The local sync report — written into the owner's vault, for their eyes.

Friendly and honest: what stayed home, what synced, what was shared on
request, and anything the company KB deleted on arrival because it looked
personal. This is the standing audit trail that makes kbnet trustworthy.
"""
import datetime
import hashlib
import json
import os

MAX_LISTED = 200

FOOTER = (
    "\n---\n"
    "*Spot something personal that shouldn't have left? Tell Chris — it will be "
    "treated as private, removed from the company KB, and we'll fix the sorting "
    "so it doesn't happen again. GreenMars has no interest in personal "
    "information; keeping it home is kbnet's first job.*\n"
)


def _sha12(text):
    return hashlib.sha256(text.encode()).hexdigest()[:12]


def resolve_purge_notices(exchange, exported):
    """Match the hub's purge notices to files this vault is still sharing.

    The hub writes control/notices/personal-purge.json with hashed ids only
    (sha256('<kind>:<path>')[:12]) plus the digest of the content it deleted.
    A file is listed while that same content is still being shared; once it is
    marked personal, edited, or deleted, it drops off the list. Never raises —
    the report must not break a sync cycle.

    exported: {relpath: text} exactly as written to outbox/kb this cycle.
    Returns [(relpath, date)] sorted by path.
    """
    try:
        with open(os.path.join(exchange, "control", "notices", "personal-purge.json"),
                  encoding="utf-8") as f:
            items = json.load(f).get("items") or []
        shared = {}
        for rel, text in exported.items():
            shared[_sha12(f"kb:{rel}")] = (rel, _sha12(text))
        src_root = os.path.join(exchange, "outbox", "sources")
        if os.path.isdir(src_root):
            for rid in sorted(os.listdir(src_root)):
                rid_dir = os.path.join(src_root, rid)
                for root, _dirs, files in os.walk(rid_dir):
                    for fname in files:
                        path = os.path.join(root, fname)
                        rel = os.path.relpath(path, rid_dir).replace(os.sep, "/")
                        if rel == "_meta.json":
                            continue
                        with open(path, encoding="utf-8", errors="replace") as f:
                            shared[_sha12(f"sources:{rid}/{rel}")] = (rel, _sha12(f.read()))
        found = {}
        for item in items:
            if not isinstance(item, dict):
                continue
            match = shared.get(item.get("id"))
            if match and match[1] == item.get("digest"):
                found[match[0]] = str(item.get("date") or "")
        return sorted(found.items())
    except Exception:  # noqa: BLE001
        return []


def write_report(vault, peer, export_stats, personal_paths, request_metas, errors,
                 purge_notices=None):
    kbnet_dir = os.path.join(vault, "kbnet")
    os.makedirs(kbnet_dir, exist_ok=True)
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    purge_notices = purge_notices or []

    lines = [
        "# kbnet — your latest sync report",
        f"*Ran {now} · this report lives only in your vault*",
        "",
        "kbnet shares your business knowledge with the GreenMars KB and keeps "
        "your personal notes at home. Here's exactly what happened this run.",
        "",
        f"## Stayed home (personal) — {len(personal_paths)} note(s)",
    ]
    if personal_paths:
        for p in personal_paths[:MAX_LISTED]:
            lines.append(f"- `{p}`")
        if len(personal_paths) > MAX_LISTED:
            lines.append(f"- …and {len(personal_paths) - MAX_LISTED} more")
    else:
        lines.append("*(none matched your personal areas — run `kbnet ui` if that "
                     "doesn't look right)*")

    lines += [
        "",
        "## Synced to the GreenMars KB",
        f"- **{export_stats['synced']}** business note(s) in sync "
        f"({export_stats['updated']} updated, {export_stats['removed']} removed this run)",
    ]
    if export_stats.get("personal_excluded"):
        lines.append(
            f"- {export_stats['personal_excluded']} note(s) inside your sync folders "
            "were personal, so they stayed home"
        )
    if export_stats.get("callouts_stripped"):
        lines.append(
            f"- {export_stats['callouts_stripped']} personal callout section(s) were "
            "trimmed out of shared notes before syncing"
        )

    if purge_notices:
        lines += [
            "",
            f"## Deleted by the company KB as personal — {len(purge_notices)} file(s)",
            "*(These synced, the company KB judged them personal, and it deleted them on "
            "arrival without keeping a copy. Mark each one personal — or wrap just the "
            "personal part in a `> [!personal]` callout — so it stays home next time. "
            "If one is really business, tell Chris.)*",
        ]
        for rel, date in purge_notices[:MAX_LISTED]:
            lines.append(f"- `{rel}`" + (f" — {date}" if date else ""))

    if request_metas:
        lines += ["", "## Source notes shared on request"]
        lines.append(
            "*(Now and then the company KB double-checks a fact against the "
            "original notes behind it.)*"
        )
        for rid, meta in request_metas:
            reason = (meta.get("request") or {}).get("reason", "no reason given")
            lines.append(f"- **{rid}** — {reason}: {len(meta.get('served', []))} file(s)")
            for rel in meta.get("served", [])[:20]:
                lines.append(f"  - `{rel}`")
            if meta.get("personal_excluded"):
                lines.append(
                    f"  - *({meta['personal_excluded']} personal note(s) matched but "
                    "stayed home)*"
                )

    if errors:
        lines += ["", "## Hiccups"]
        lines += [f"- {e}" for e in errors]
        lines.append("*(kbnet retries on its own — nothing for you to do)*")

    lines.append(FOOTER)
    report_path = os.path.join(kbnet_dir, "last-export-report.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    with open(os.path.join(kbnet_dir, "history.log"), "a", encoding="utf-8") as f:
        f.write(
            f"{now} · synced {export_stats['synced']} "
            f"({export_stats['updated']} updated) · personal kept home "
            f"{len(personal_paths)} · requests fulfilled {len(request_metas)}"
            + (f" · deleted by company KB as personal {len(purge_notices)}"
               if purge_notices else "")
            + (f" · errors {len(errors)}" if errors else "")
            + "\n"
        )
    return report_path
