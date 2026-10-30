"""Verify the SVQuant account-reuse adapter without a real SVQuant server."""
from __future__ import annotations

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import auth  # noqa: E402


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        if self.path == "/api/auth/me" and self.headers.get("authorization") == "Bearer good":
            payload = {"ok": True, "user": {"id": 7, "username": "alice", "display_name": "Alice",
                                            "role": "user", "status": "active"}}
            raw = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
            return
        raw = json.dumps({"detail": "登录已失效"}).encode()
        self.send_response(401)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("content-length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        is_register = self.path == "/api/auth/register"
        if body.get("username") == "alice" and body.get("password") == "secret":
            payload = {"ok": True, "user": {"id": 7, "username": "alice", "display_name": "Alice",
                                            "role": "user", "status": "active"}, "token": "svq-token"}
            raw = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
            return
        if is_register and body.get("username") == "bob" and body.get("password") == "secret":
            payload = {"ok": True, "user": {"id": 8, "username": "bob", "display_name": "Bob",
                                            "role": "user", "status": "active"}}
            raw = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
            return
        raw = json.dumps({"detail": "用户名或密码错误"}).encode()
        self.send_response(401 if not is_register else 400)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, *args):
        pass


def test_svquant_proxy_login(monkeypatch):
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        monkeypatch.setattr(auth, "SVQUANT_BASE", f"http://127.0.0.1:{server.server_port}")
        out = auth.login("alice", "secret")
        assert out["mode"] == "svquant"
        assert out["user"]["username"] == "alice"
        assert auth.user_from_authorization(f"Bearer {out['token']}")["id"] == 7
        try:
            auth.login("alice", "wrong")
            assert False, "should reject"
        except ValueError:
            pass
        reg = auth.register("bob", "secret", "bob@example.com", "Bob")
        assert reg["mode"] == "svquant"
        assert reg["user"]["username"] == "bob"
        assert auth.user_from_authorization(f"Bearer {reg['token']}")["id"] == 8

        sso = auth.sso("good")
        assert sso["mode"] == "svquant-sso"
        assert sso["user"]["username"] == "alice"
        try:
            auth.sso("bad")
            assert False, "should reject"
        except ValueError:
            pass
    finally:
        server.shutdown()
