#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SVQuant Gitee WebHook 接收器（只用标准库，无第三方依赖）。

职责很窄：验证 Gitee 签名 → 判断事件类型 → 用 flock 串行地拉起 jobs 脚本。
真正干活（拉代码、跑测试、构建、部署、回滚）全在 scripts/ci/ 里，本进程不碰业务逻辑。

部署：见 deploy/webhook/README.md。默认只监听 127.0.0.1，由 Nginx 终止 TLS 后反代。

环境变量：
  WEBHOOK_HOST        监听地址，默认 127.0.0.1
  WEBHOOK_PORT        监听端口，默认 8788
  WEBHOOK_SECRET      签名密钥（推荐）；与 WEBHOOK_PASSWORD 二选一
  WEBHOOK_PASSWORD    明文密码（兼容旧配置，不推荐）
  WEBHOOK_BRANCH      需要跑 CI 的分支，默认 master
  WEBHOOK_TAG_PREFIX  需要触发部署的 tag 前缀，默认 v
  WEBHOOK_REPO_DIR    仓库路径，默认本文件向上两级
  WEBHOOK_LOG_DIR     任务日志目录，默认 <repo>/deploy/webhook-logs
  WEBHOOK_LOCK_FILE   flock 文件，默认 /tmp/svquant-webhook.lock
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import subprocess
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, unquote_plus

REPO_DIR = Path(os.environ.get("WEBHOOK_REPO_DIR") or Path(__file__).resolve().parents[2]).resolve()
HOST = os.environ.get("WEBHOOK_HOST", "127.0.0.1")
PORT = int(os.environ.get("WEBHOOK_PORT", "8788"))
SECRET = os.environ.get("WEBHOOK_SECRET", "").strip()
PASSWORD = os.environ.get("WEBHOOK_PASSWORD", "").strip()
BRANCH = os.environ.get("WEBHOOK_BRANCH", "master").strip()
TAG_PREFIX = os.environ.get("WEBHOOK_TAG_PREFIX", "v").strip()
LOG_DIR = Path(os.environ.get("WEBHOOK_LOG_DIR") or (REPO_DIR / "deploy" / "webhook-logs")).resolve()
LOCK_FILE = os.environ.get("WEBHOOK_LOCK_FILE", "/tmp/svquant-webhook.lock")
JOB_SCRIPT = REPO_DIR / "scripts" / "ci" / "webhook-job.sh"
MAX_BODY = 2 * 1024 * 1024
CLOCK_SKEW_MS = 3600 * 1000


def log(msg: str) -> None:
    print(f"[webhook] {msg}", flush=True)


def verify_signature(token: str, timestamp: str) -> bool:
    """按 Gitee 文档校验：HmacSHA256(timestamp + '\\n' + secret)，再 base64 + urlencode。"""
    if SECRET:
        try:
            ts = int(timestamp)
        except (TypeError, ValueError):
            return False
        if abs(int(time.time() * 1000) - ts) > CLOCK_SKEW_MS:
            return False
        mac = hmac.new(SECRET.encode("utf-8"), f"{timestamp}\n{SECRET}".encode("utf-8"), hashlib.sha256).digest()
        expected = base64.b64encode(mac).decode("ascii")
        # Gitee 传签名时做过 urlencode，这里兼容原样/已解码三种形态
        for cand in (token, unquote(token), unquote_plus(token)):
            if cand and hmac.compare_digest(cand, expected):
                return True
        return False
    if PASSWORD:
        return bool(token) and hmac.compare_digest(token, PASSWORD)
    return False


def classify(payload: dict) -> tuple[str, str, str] | None:
    """返回 (动作, 引用, sha)；不需要处理时返回 None。"""
    if payload.get("deleted") is True:
        return None
    ref = str(payload.get("ref") or "")
    after = str(payload.get("after") or "")
    if ref.startswith("refs/tags/"):
        tag = ref[len("refs/tags/"):]
        if TAG_PREFIX and not tag.startswith(TAG_PREFIX):
            return None
        return ("deploy", tag, after)
    if ref == f"refs/heads/{BRANCH}":
        return ("ci", BRANCH, after)
    return None


def lock_is_free() -> bool:
    return subprocess.run(["flock", "-n", LOCK_FILE, "true"], capture_output=True).returncode == 0


def start_job(action: str, ref: str, sha: str) -> Path:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    log_path = LOG_DIR / f"{stamp}-{action}-{ref.replace('/', '_')}.log"
    with open(log_path, "ab") as out:
        # flock 由子进程持有到任务结束，保证同一时刻只有一个任务在跑
        subprocess.Popen(
            ["flock", LOCK_FILE, "bash", str(JOB_SCRIPT), action, ref, sha],
            cwd=str(REPO_DIR),
            stdout=out,
            stderr=out,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
    return log_path


class Handler(BaseHTTPRequestHandler):
    server_version = "svquant-webhook/1.0"
    protocol_version = "HTTP/1.1"

    def _send(self, code: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path.split("?")[0] in ("/healthz", "/"):
            self._send(200, {"status": "ok"})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path.split("?")[0] not in ("/hooks/gitee", "/hooks/gitee/"):
            self._send(404, {"error": "not found"})
            return

        if not (SECRET or PASSWORD):
            log("拒绝：未配置 WEBHOOK_SECRET / WEBHOOK_PASSWORD")
            self._send(500, {"error": "webhook secret not configured"})
            return

        token = self.headers.get("X-Gitee-Token", "")
        timestamp = self.headers.get("X-Gitee-Timestamp", "")
        if not verify_signature(token, timestamp):
            log(f"签名校验失败 event={self.headers.get('X-Gitee-Event', '-')}")
            self._send(401, {"error": "invalid signature"})
            return

        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if length <= 0 or length > MAX_BODY:
            self._send(413, {"error": "invalid content length"})
            return

        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._send(400, {"error": "invalid json"})
            return

        target = classify(payload)
        if target is None:
            self._send(200, {"status": "ignored", "ref": payload.get("ref")})
            return

        action, ref, sha = target
        if not JOB_SCRIPT.is_file():
            self._send(500, {"error": f"missing {JOB_SCRIPT}"})
            return
        if not lock_is_free():
            log(f"忽略 {action} {ref}：已有任务在运行")
            self._send(429, {"status": "busy", "action": action, "ref": ref})
            return

        log_path = start_job(action, ref, sha)
        log(f"接受 {action} ref={ref} sha={sha[:8]} 日志={log_path.name}")
        self._send(202, {"status": "accepted", "action": action, "ref": ref, "log": log_path.name})

    def log_message(self, fmt: str, *args) -> None:  # 默认访问日志太吵，交给 journald
        return


def main() -> int:
    missing = [p for p in (JOB_SCRIPT,) if not p.is_file()]
    if missing:
        log(f"启动失败：缺少 {missing}")
        return 1
    if not (SECRET or PASSWORD):
        log("警告：未配置签名密钥或密码，所有请求都会被拒绝")

    server = ThreadingHTTPServer((HOST, PORT), Handler)
    log(f"监听 http://{HOST}:{PORT}  仓库={REPO_DIR}  分支={BRANCH}  tag 前缀={TAG_PREFIX}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
