"""Section-level personal strip.

An Obsidian callout `> [!personal]` (plus any extra names configured via
control/config.json) is excised from anything kbnet exports or serves —
the escape hatch for the one personal paragraph inside a business page.
"""
import re

_CALLOUT_RE = re.compile(r"^\s*>\s*\[!([A-Za-z0-9_-]+)\]")


def strip_personal_callouts(text, extra_names=()):
    names = {"personal"} | {str(n).lower() for n in extra_names}
    out = []
    removed = 0
    in_callout = False
    for line in text.split("\n"):
        if in_callout:
            if line.lstrip().startswith(">"):
                continue
            in_callout = False
        m = _CALLOUT_RE.match(line)
        if m and m.group(1).lower() in names:
            in_callout = True
            removed += 1
            continue
        out.append(line)
    return "\n".join(out), removed
