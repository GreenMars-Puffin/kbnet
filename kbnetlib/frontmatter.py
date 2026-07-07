"""Minimal frontmatter + tag extraction. Stdlib only.

Parses the YAML subset staff vaults actually use: top-level `key: value`
scalars, inline lists `[a, b]`, and block lists. Nested mappings are
skipped rather than crashed on — kbnet only needs the flat keys
(scope, personal, tags, ...) for classification.
"""
import re

_TAG_RE = re.compile(r"(?<![\w#])#([A-Za-z][\w/-]*)")
_KV_RE = re.compile(r"^([^:#]+):\s*(.*)$")


def _clean(value):
    return value.strip().strip("\"'").strip()


def parse_simple_yaml(src):
    data = {}
    current_key = None
    for raw in src.split("\n"):
        if not raw.strip() or raw.strip().startswith("#"):
            continue
        stripped = raw.strip()
        if stripped.startswith("- ") or stripped == "-":
            if current_key is not None:
                if not isinstance(data.get(current_key), list):
                    data[current_key] = []
                item = _clean(stripped[1:])
                if item:
                    data[current_key].append(item)
            continue
        if raw[0] in " \t":
            continue  # nested mapping — out of scope
        m = _KV_RE.match(stripped)
        if not m:
            continue
        key = m.group(1).strip().lower()
        val = m.group(2).strip()
        current_key = key
        if val == "":
            data[key] = []
        elif val.startswith("[") and val.endswith("]"):
            data[key] = [_clean(x) for x in val[1:-1].split(",") if _clean(x)]
        else:
            data[key] = _clean(val)
    return data


def split_frontmatter(text):
    """Return (frontmatter_dict, body)."""
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return {}, text
    for i in range(1, len(lines)):
        if lines[i].strip() in ("---", "..."):
            return parse_simple_yaml("\n".join(lines[1:i])), "\n".join(lines[i + 1:])
    return {}, text


def collect_tags(fm, body):
    tags = set()
    t = fm.get("tags")
    if isinstance(t, str):
        tags.update(x.strip().lstrip("#") for x in re.split(r"[,\s]+", t) if x.strip())
    elif isinstance(t, list):
        tags.update(str(x).lstrip("#") for x in t)
    for m in _TAG_RE.finditer(body):
        tags.add(m.group(1))
    return {t for t in tags if t}
