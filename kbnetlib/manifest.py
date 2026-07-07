"""The kbnet manifest: the vault owner's personal designations.

Anything matching a personal rule stays on this machine, always — excluded
from routine sync and from on-demand source requests alike. Everything else
is company knowledge and syncs.
"""
import hashlib
import json
import os

from . import frontmatter

DEFAULTS = {
    "version": "1",
    "sync_folders": ["wiki"],
    "personal_folders": ["personal"],
    "personal_tags": ["personal"],
    "personal_frontmatter": ["scope: personal", "personal: true"],
}

_LIST_KEYS = ("sync_folders", "personal_folders", "personal_tags", "personal_frontmatter")

_TRUE_SYNONYMS = {"true", "yes", "1"}


def manifest_path(vault):
    return os.path.join(vault, "kbnet", "manifest.yaml")


def load(vault):
    m = {k: (list(v) if isinstance(v, list) else v) for k, v in DEFAULTS.items()}
    try:
        with open(manifest_path(vault), encoding="utf-8") as f:
            parsed = frontmatter.parse_simple_yaml(f.read())
    except OSError:
        return m
    for key in DEFAULTS:
        if key in parsed:
            val = parsed[key]
            if key in _LIST_KEYS:
                m[key] = [val] if isinstance(val, str) else list(val)
            else:
                m[key] = val
    return m


def manifest_hash(m):
    canon = json.dumps({k: m.get(k) for k in sorted(DEFAULTS)}, sort_keys=True)
    return hashlib.sha256(canon.encode()).hexdigest()[:12]


def save(vault, m):
    path = manifest_path(vault)
    os.makedirs(os.path.dirname(path), exist_ok=True)

    def block(key):
        items = m.get(key) or []
        if not items:
            return f"{key}: []\n"
        return f"{key}:\n" + "".join(f'  - "{i}"\n' for i in items)

    with open(path, "w", encoding="utf-8") as f:
        f.write(
            "# kbnet manifest — your personal areas\n"
            "# Notes matching any rule below always stay on this machine.\n"
            "# Edit here or run `kbnet ui` any time.\n"
            f"version: {m.get('version', '1')}\n"
            + block("sync_folders")
            + block("personal_folders")
            + block("personal_tags")
            + block("personal_frontmatter")
        )
    return path


def _fm_get(fm, key):
    return fm.get(key.lower())


def is_personal(relpath, fm, tags, m):
    rel = relpath.replace(os.sep, "/")
    rel_lower = rel.lower()
    segments = [s.lower() for s in rel.split("/")[:-1]]

    for folder in m.get("personal_folders", []):
        f = folder.strip().strip("/").lower()
        if not f:
            continue
        if rel_lower == f or rel_lower.startswith(f + "/"):
            return True
        if "/" not in f and f in segments:
            return True

    for marker in m.get("personal_frontmatter", []):
        if ":" not in marker:
            continue
        key, want = marker.split(":", 1)
        want = want.strip().strip("\"'").lower()
        val = _fm_get(fm, key.strip())
        if val is None:
            continue
        values = [str(v).lower() for v in val] if isinstance(val, list) else [str(val).lower()]
        if want in values:
            return True
        if want in _TRUE_SYNONYMS and any(v in _TRUE_SYNONYMS for v in values):
            return True

    personal_tags = {t.lower() for t in m.get("personal_tags", [])}
    if personal_tags and personal_tags & {t.lower() for t in tags}:
        return True

    return False


def classify(notes, m):
    for n in notes:
        n.personal = is_personal(n.relpath, n.fm, n.tags, m)
    return notes


def path_is_personal(relpath, m):
    """Folder-rule-only check, for non-markdown files (no frontmatter to read)."""
    return is_personal(relpath, {}, (), m)
