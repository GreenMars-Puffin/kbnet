"""The local sync report — written into the owner's vault, for their eyes.

Friendly and honest: what stayed home, what synced, what was shared on
request. This is the standing audit trail that makes kbnet trustworthy.
"""
import datetime
import os

MAX_LISTED = 200

FOOTER = (
    "\n---\n"
    "*Spot something personal that shouldn't have left? Tell Chris — it will be "
    "treated as private, removed from the company KB, and we'll fix the sorting "
    "so it doesn't happen again. GreenMars has no interest in personal "
    "information; keeping it home is kbnet's first job.*\n"
)


def write_report(vault, peer, export_stats, personal_paths, request_metas, errors):
    kbnet_dir = os.path.join(vault, "kbnet")
    os.makedirs(kbnet_dir, exist_ok=True)
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

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
            + (f" · errors {len(errors)}" if errors else "")
            + "\n"
        )
    return report_path
