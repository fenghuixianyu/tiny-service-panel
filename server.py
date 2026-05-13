#!/usr/bin/env python3
import argparse
from http import cookies
import hashlib
import hmac
import json
import os
import secrets
import socket
import sys
import time
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
AUTH_COOKIE_NAME = os.environ.get("TSP_COOKIE_NAME", "tsp_auth")
AUTH_HASH = os.environ.get("TSP_AUTH_HASH", "").strip()
AUTH_SECRET = os.environ.get("TSP_SECRET", "").strip()
AUTH_COOKIE_DAYS = int(os.environ.get("TSP_AUTH_COOKIE_DAYS", "30") or "30")
AUTH_COOKIE_SECURE = os.environ.get("TSP_COOKIE_SECURE", "0") == "1"
AUTH_ENABLED = bool(AUTH_HASH and AUTH_SECRET)


def json_bytes(obj):
    return json.dumps(obj, ensure_ascii=False).encode("utf-8")


def _password_hash(password, salt_hex, iterations):
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), iterations).hex()


def verify_password(password):
    try:
        algo, iterations_s, salt_hex, expected = AUTH_HASH.split("$", 3)
        iterations = int(iterations_s)
    except ValueError:
        return False
    if algo != "pbkdf2_sha256":
        return False
    actual = _password_hash(password, salt_hex, iterations)
    return hmac.compare_digest(actual, expected)


def _auth_signature(body):
    return hmac.new(AUTH_SECRET.encode("utf-8"), body.encode("utf-8"), hashlib.sha256).hexdigest()


def make_auth_token():
    ts = str(int(time.time()))
    nonce = secrets.token_urlsafe(16)
    body = f"v1.{ts}.{nonce}"
    return f"{body}.{_auth_signature(body)}"


def verify_auth_token(token):
    if not AUTH_ENABLED or not token:
        return False
    parts = token.split(".")
    if len(parts) != 4 or parts[0] != "v1":
        return False
    body = ".".join(parts[:3])
    if not hmac.compare_digest(_auth_signature(body), parts[3]):
        return False
    try:
        ts = int(parts[1])
    except ValueError:
        return False
    max_age = max(1, AUTH_COOKIE_DAYS) * 86400
    return 0 <= time.time() - ts <= max_age


def parse_cookie(header):
    jar = cookies.SimpleCookie()
    try:
        jar.load(header or "")
    except cookies.CookieError:
        return {}
    return {key: morsel.value for key, morsel in jar.items()}


class Handler(BaseHTTPRequestHandler):
    server_version = "TinyServicePanel/0.3"

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

    def is_authenticated(self):
        if not AUTH_ENABLED:
            return True
        token = parse_cookie(self.headers.get("Cookie", "")).get(AUTH_COOKIE_NAME, "")
        return verify_auth_token(token)

    def send_auth_required(self, head_only=False):
        self.send_json({"ok": False, "error": "auth required"}, 401, head_only=head_only)

    def set_auth_cookie(self, remember=True):
        morsel = cookies.SimpleCookie()
        morsel[AUTH_COOKIE_NAME] = make_auth_token()
        morsel[AUTH_COOKIE_NAME]["path"] = "/"
        morsel[AUTH_COOKIE_NAME]["httponly"] = True
        morsel[AUTH_COOKIE_NAME]["samesite"] = "Lax"
        if remember:
            morsel[AUTH_COOKIE_NAME]["max-age"] = str(max(1, AUTH_COOKIE_DAYS) * 86400)
        if AUTH_COOKIE_SECURE:
            morsel[AUTH_COOKIE_NAME]["secure"] = True
        for item in morsel.values():
            self.send_header("Set-Cookie", item.OutputString())

    def clear_auth_cookie(self):
        morsel = cookies.SimpleCookie()
        morsel[AUTH_COOKIE_NAME] = ""
        morsel[AUTH_COOKIE_NAME]["path"] = "/"
        morsel[AUTH_COOKIE_NAME]["max-age"] = "0"
        morsel[AUTH_COOKIE_NAME]["httponly"] = True
        morsel[AUTH_COOKIE_NAME]["samesite"] = "Lax"
        if AUTH_COOKIE_SECURE:
            morsel[AUTH_COOKIE_NAME]["secure"] = True
        for item in morsel.values():
            self.send_header("Set-Cookie", item.OutputString())

    def send_login_success(self, remember=True):
        body = json_bytes({"ok": True, "remember_days": AUTH_COOKIE_DAYS if remember else 0})
        self.send_response(200)
        self.set_auth_cookie(remember=remember)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def send_logout_success(self):
        body = json_bytes({"ok": True})
        self.send_response(200)
        self.clear_auth_cookie()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

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
            elif path == "/api/auth/status":
                self.send_json({"ok": True, "enabled": AUTH_ENABLED, "authenticated": self.is_authenticated(), "remember_days": AUTH_COOKIE_DAYS}, head_only=head_only)
            elif path == "/api/summary":
                if not self.is_authenticated():
                    return self.send_auth_required(head_only=head_only)
                self.send_json(system_summary(), head_only=head_only)
            elif path == "/api/units":
                if not self.is_authenticated():
                    return self.send_auth_required(head_only=head_only)
                self.send_json(collect_units(qs.get("sort", ["memory"])[0], qs.get("dir", ["desc"])[0], qs.get("type", ["all"])[0]), head_only=head_only)
            elif path == "/api/metadata":
                if not self.is_authenticated():
                    return self.send_auth_required(head_only=head_only)
                self.send_json({"ok": True, "metadata": load_metadata()}, head_only=head_only)
            elif path == "/api/status":
                if not self.is_authenticated():
                    return self.send_auth_required(head_only=head_only)
                self.send_json(unit_status(qs.get("unit", [""])[0]), head_only=head_only)
            elif path == "/api/logs":
                if not self.is_authenticated():
                    return self.send_auth_required(head_only=head_only)
                lines = int(qs.get("lines", ["120"])[0])
                self.send_json(unit_logs(qs.get("unit", [""])[0], lines), head_only=head_only)
            else:
                self.send_json({"ok": False, "error": "not found"}, 404, head_only=head_only)
        except Exception as e:
            self.send_json({"ok": False, "error": str(e)}, 500, head_only=head_only)

    def do_POST(self):
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/api/auth/login":
                data = self.read_json()
                password = str(data.get("password", ""))
                remember = bool(data.get("remember", True))
                if not AUTH_ENABLED:
                    self.send_json({"ok": True, "auth": "disabled"})
                elif verify_password(password):
                    self.send_login_success(remember=remember)
                else:
                    self.send_json({"ok": False, "error": "密码错误"}, 401)
            elif parsed.path == "/api/auth/logout":
                self.send_logout_success()
            elif parsed.path == "/api/action":
                if not self.is_authenticated():
                    return self.send_auth_required()
                data = self.read_json()
                self.send_json(unit_action(str(data.get("unit", "")), str(data.get("action", ""))))
            elif parsed.path == "/api/metadata":
                if not self.is_authenticated():
                    return self.send_auth_required()
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
