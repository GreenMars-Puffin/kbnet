"""Vault scan: every markdown note (with frontmatter + tags) plus other files."""
import os

from . import frontmatter

SKIP_DIRS = {".git", ".obsidian", ".trash", ".smart-env", "node_modules", "kbnet"}
SKIP_FILES = {".DS_Store"}


class Note:
    __slots__ = ("relpath", "path", "fm", "tags", "text", "personal")

    def __init__(self, relpath, path, fm, tags, text):
        self.relpath = relpath
        self.path = path
        self.fm = fm
        self.tags = tags
        self.text = text
        self.personal = False


def scan_vault(vault):
    """Return (notes, other_files) where other_files is [(relpath, abspath)]."""
    notes = []
    other_files = []
    for root, dirs, files in os.walk(vault):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not d.startswith("."))
        for fname in sorted(files):
            if fname in SKIP_FILES or fname.startswith("."):
                continue
            path = os.path.join(root, fname)
            rel = os.path.relpath(path, vault).replace(os.sep, "/")
            if not fname.endswith(".md"):
                other_files.append((rel, path))
                continue
            try:
                with open(path, encoding="utf-8", errors="replace") as f:
                    text = f.read()
            except OSError:
                continue
            fm, body = frontmatter.split_frontmatter(text)
            tags = frontmatter.collect_tags(fm, body)
            notes.append(Note(rel, path, fm, tags, text))
    return notes, other_files


def in_folders(relpath, folders):
    rel = relpath.replace(os.sep, "/")
    for folder in folders:
        f = str(folder).strip().strip("/")
        if f in ("", "."):
            return True
        if rel == f or rel.startswith(f + "/"):
            return True
    return False
