#!/usr/bin/env python3
import argparse
import json
import os
import socket
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

from tiny_service_panel.system import (
    collect_units,
    system_summary,
    unit_action,
    unit_logs,
    unit_status,
    load_metadata,
    update_metadata,
)

APP_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(APP_DIR, "static")


def json_bytes(obj):
    return json.dumps(obj, ensure_ascii=False).encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    server_version = "TinyServicePanel/0.2"

    def log_message(self, fmt, *args):
        sys.stderr.write("%s - - [%s] %s\n" % (self.client_address[0], self.log_date_time_string(), fmt % args))

    def send_bytes(self, status, body, content_type="application/octet-stream", cache="no-store", head_only=False):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        if not head_only:
            self.wfile.write(body)

    def send_json(self, obj, status=200, head_only=False):
        self.send_bytes(status, json_bytes(obj), "application/json; charset=utf-8", head_only=head_only)

    def read_json(self):
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length > 8192:
            raise ValueError("request too large")
        raw = self.rfile.read(length) if length else b"{}"
        return json.loads(raw.decode("utf-8") or "{}")

    def do_HEAD(self):
        self.route_get(head_only=True)

    def do_GET(self):
        self.route_get(head_only=False)

    def route_get(self, head_only=False):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)
        try:
            if path == "/" or path == "/index.html":
                with open(os.path.join(STATIC_DIR, "index.html"), "rb") as f:
                    self.send_bytes(200, f.read(), "text/html; charset=utf-8", head_only=head_only)
            elif path == "/app.js":
                with open(os.path.join(STATIC_DIR, "app.js"), "rb") as f:
                    self.send_bytes(200, f.read(), "application/javascript; charset=utf-8", head_only=head_only)
            elif path == "/style.css":
                with open(os.path.join(STATIC_DIR, "style.css"), "rb") as f:
                    self.send_bytes(200, f.read(), "text/css; charset=utf-8", head_only=head_only)
            elif path == "/api/summary":
                self.send_json(system_summary(), head_only=head_only)
            elif path == "/api/units":
                self.send_json(collect_units(qs.get("sort", ["memory"])[0], qs.get("dir", ["desc"])[0], qs.get("type", ["all"])[0]), head_only=head_only)
            elif path == "/api/metadata":
                self.send_json({"ok": True, "metadata": load_metadata()}, head_only=head_only)
            elif path == "/api/status":
                self.send_json(unit_status(qs.get("unit", [""])[0]), head_only=head_only)
            elif path == "/api/logs":
                lines = int(qs.get("lines", ["120"])[0])
                self.send_json(unit_logs(qs.get("unit", [""])[0], lines), head_only=head_only)
            else:
                self.send_json({"ok": False, "error": "not found"}, 404, head_only=head_only)
        except Exception as e:
            self.send_json({"ok": False, "error": str(e)}, 500, head_only=head_only)

    def do_POST(self):
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/api/action":
                data = self.read_json()
                self.send_json(unit_action(str(data.get("unit", "")), str(data.get("action", ""))))
            elif parsed.path == "/api/metadata":
                data = self.read_json()
                self.send_json(update_metadata(str(data.get("action", "")), str(data.get("unit", "")), str(data.get("note", ""))))
            else:
                self.send_json({"ok": False, "error": "not found"}, 404)
        except Exception as e:
            self.send_json({"ok": False, "error": str(e)}, 500)


def serve_host_port(host, port):
    httpd = ThreadingHTTPServer((host, port), Handler)
    httpd.serve_forever()


def serve_systemd_socket():
    import select
    sock = socket.socket(fileno=0)
    sock.setblocking(True)

    class SocketActivatedServer(ThreadingHTTPServer):
        allow_reuse_address = True
        def server_bind(self): pass
        def server_activate(self): pass
        def server_close(self): pass

    httpd = SocketActivatedServer(("127.0.0.1", 0), Handler, bind_and_activate=False)
    httpd.socket = sock
    httpd.server_address = sock.getsockname()
    idle = int(os.environ.get("TSP_IDLE_TIMEOUT", "60"))
    while True:
        ready, _, _ = select.select([sock], [], [], idle)
        if not ready:
            break
        httpd._handle_request_noblock()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--systemd-socket", action="store_true")
    args = ap.parse_args()
    if args.systemd_socket:
        serve_systemd_socket()
    else:
        serve_host_port(args.host, args.port)


if __name__ == "__main__":
    main()
