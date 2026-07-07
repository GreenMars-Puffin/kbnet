"""Localhost setup UI: mark your personal areas, preview, save.

Binds 127.0.0.1 only. In --setup mode the server exits shortly after a
successful save so the installer can continue.
"""
import collections
import json
import os
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import config, manifest, scan

MAX_PREVIEW_PATHS = 400


class _State:
    def __init__(self):
        cfg = config.load_local()
        self.peer = cfg["peer"]
        self.vault = os.path.expanduser(cfg["vault_path"])
        self.setup_mode = False
        self.server = None
        self.rescan()

    def rescan(self):
        self.notes, self.other_files = scan.scan_vault(self.vault)

    def folder_summary(self, m):
        manifest.classify(self.notes, m)
        counts = collections.Counter()
        for n in self.notes:
            parts = n.relpath.split("/")[:-1]
            for depth in range(1, min(len(parts), 3) + 1):
                counts["/".join(parts[:depth])] += 1
        return [{"path": p, "notes": c} for p, c in sorted(counts.items())]

    def tag_summary(self):
        tags = collections.Counter()
        for n in self.notes:
            for t in n.tags:
                tags[t.lower()] += 1
        return [{"tag": t, "count": c} for t, c in tags.most_common(100)]

    def preview(self, m):
        manifest.classify(self.notes, m)
        personal = sorted(n.relpath for n in self.notes if n.personal)
        business = [n for n in self.notes if not n.personal]
        synced = [n.relpath for n in business
                  if scan.in_folders(n.relpath, m.get("sync_folders", []))]
        return {
            "personal_count": len(personal),
            "personal_paths": personal[:MAX_PREVIEW_PATHS],
            "personal_truncated": max(0, len(personal) - MAX_PREVIEW_PATHS),
            "business_count": len(business),
            "synced_count": len(synced),
            "sync_folders": m.get("sync_folders", []),
        }


def _merge_manifest(current, body):
    m = dict(current)
    for key in ("personal_folders", "personal_tags", "personal_frontmatter"):
        if key in body and isinstance(body[key], list):
            m[key] = [str(x).strip() for x in body[key] if str(x).strip()]
    return m


class Handler(BaseHTTPRequestHandler):
    state = None  # set by serve()

    def log_message(self, *args):
        pass

    def _send(self, code, payload, content_type="application/json"):
        body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        length = int(self.headers.get("Content-Length") or 0)
        try:
            return json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            return {}

    def do_GET(self):
        st = self.state
        if self.path in ("/", "/index.html"):
            html_path = os.path.join(os.path.dirname(__file__), "..", "ui", "index.html")
            with open(html_path, "rb") as f:
                self._send(200, f.read(), "text/html; charset=utf-8")
        elif self.path == "/api/state":
            m = manifest.load(st.vault)
            self._send(200, {
                "peer": st.peer,
                "vault": st.vault,
                "manifest": m,
                "folders": st.folder_summary(m),
                "tags": st.tag_summary(),
                "preview": st.preview(m),
                "setup_mode": st.setup_mode,
            })
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        st = self.state
        if self.path == "/api/preview":
            m = _merge_manifest(manifest.load(st.vault), self._body())
            self._send(200, st.preview(m))
        elif self.path == "/api/rescan":
            st.rescan()
            self._send(200, {"ok": True})
        elif self.path == "/api/save":
            m = _merge_manifest(manifest.load(st.vault), self._body())
            path = manifest.save(st.vault, m)
            self._send(200, {"ok": True, "path": path, "preview": st.preview(m)})
            if st.setup_mode and st.server:
                threading.Timer(1.5, st.server.shutdown).start()
        else:
            self._send(404, {"error": "not found"})


def serve(port=8765, open_browser=True, setup=False):
    state = _State()
    state.setup_mode = setup
    Handler.state = state
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    state.server = server
    url = f"http://127.0.0.1:{port}/"
    print(f"kbnet ui → {url}   (Ctrl-C to stop)")
    if open_browser:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    if setup:
        print("Personal areas saved — kbnet will honor them on every run. ✅")
