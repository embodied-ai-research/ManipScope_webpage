#!/usr/bin/env python3
"""Serve ./site locally. Optional --watch rebuilds when content/, data/, templates/ or assets/ change.

    python3 scripts/serve.py            # http://localhost:8008
    python3 scripts/serve.py --watch    # rebuild on change (polls every 1 s)
"""
import argparse
import http.server
import os
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.dirname(HERE)
SITE = os.path.join(WEB, "site")
WATCH = ["content", "data", "templates", "assets", "site.yaml", "build.py"]


def snapshot():
    out = {}
    for w in WATCH:
        p = os.path.join(WEB, w)
        if os.path.isfile(p):
            out[p] = os.stat(p).st_mtime
        for root, _, files in os.walk(p):
            for f in files:
                fp = os.path.join(root, f)
                try:
                    out[fp] = os.stat(fp).st_mtime
                except OSError:
                    pass
    return out


def watcher():
    last = snapshot()
    while True:
        time.sleep(1)
        cur = snapshot()
        if cur != last:
            last = cur
            print("[watch] change detected, rebuilding…", flush=True)
            subprocess.call([sys.executable, os.path.join(WEB, "build.py")])


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=SITE, **k)

    def log_message(self, fmt, *args):
        sys.stderr.write("%s %s\n" % (self.address_string(), fmt % args))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8008)
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--watch", action="store_true")
    a = ap.parse_args()
    if not os.path.isdir(SITE):
        subprocess.check_call([sys.executable, os.path.join(WEB, "build.py")])
    if a.watch:
        threading.Thread(target=watcher, daemon=True).start()
    srv = http.server.ThreadingHTTPServer((a.host, a.port), Handler)
    print(f"serving {SITE} at http://localhost:{a.port}/  (Ctrl-C to stop)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
