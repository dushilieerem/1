# -*- coding: utf-8 -*-
"""SVQuant 薄后端：因子文件在本目录 factor/，不存行情数据。

计算走同事 YGQuant ResearchEngine（前端代理 /yg-api）。
"""
from __future__ import annotations

import json
import mimetypes
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

HOST = "0.0.0.0"
PORT = 8766
ROOT = Path(__file__).resolve().parent
FACTOR_DIR = ROOT / "factor"


def _parse_body(handler: BaseHTTPRequestHandler) -> dict:
    length = int(handler.headers.get("Content-Length", 0))
    if length <= 0:
        return {}
    return json.loads(handler.rfile.read(length).decode("utf-8"))


class Handler(BaseHTTPRequestHandler):
    def _auth_header(self) -> str | None:
        for key in ("Authorization", "authorization", "AUTHORIZATION"):
            val = self.headers.get(key)
            if val:
                return val
        return None

    def _cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")

    def _send_json(self, payload: dict, status: int = 200) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self._cors()
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Vary", "Authorization")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _send_bytes(self, data: bytes, content_type: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self._cors()
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_file(self, path: Path) -> None:
        if not path.exists() or not path.is_file():
            self._send_json({"error": "not found"}, 404)
            return
        data = path.read_bytes()
        ctype = mimetypes.guess_type(str(path))[0] or "text/plain"
        if path.suffix in {".yaml", ".yml"}:
            ctype = "text/yaml; charset=utf-8"
        elif path.suffix == ".py":
            ctype = "text/x-python; charset=utf-8"
        self._send_bytes(data, ctype)

    def log_message(self, fmt: str, *args) -> None:
        print(f"[svquant] {self.command} {args[0] if args else ''}")

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/health":
            self._send_json(
                {
                    "ok": True,
                    "service": "svquant",
                    "port": PORT,
                    "factor_dir": str(FACTOR_DIR),
                    "note": "no market data stored; compute via YGQuant RE",
                }
            )
            return
        if path == "/api/factor/index":
            from services.auth_store import user_from_authorization
            from services.user_factor_store import filtered_index_yaml, resolve_db_user_id

            try:
                user = user_from_authorization(self._auth_header())
                owner_id = resolve_db_user_id(user) if user else None
            except Exception:
                owner_id = None
            raw = filtered_index_yaml(owner_id).encode("utf-8")
            self._send_bytes(raw, "text/yaml; charset=utf-8")
            return
        if path.startswith("/api/factor/file/"):
            name = unquote(path[len("/api/factor/file/") :])
            if ".." in name or "/" in name or "\\" in name:
                self._send_json({"error": "bad path"}, 400)
                return
            if name == "custom_lib.py":
                from services.auth_store import user_from_authorization
                from services.user_factor_store import custom_lib_source_for_user, resolve_db_user_id

                try:
                    user = user_from_authorization(self._auth_header())
                    owner_id = resolve_db_user_id(user) if user else None
                except Exception:
                    owner_id = None
                data = custom_lib_source_for_user(owner_id).encode("utf-8")
                self._send_bytes(data, "text/x-python; charset=utf-8")
                return
            self._send_file(FACTOR_DIR / name)
            return
        if path == "/api/factor/dashboard":
            from services.dashboard_store import query_metrics

            qs = parse_qs(urlparse(self.path).query)
            self._send_json(
                query_metrics(
                    universe=(qs.get("universe") or ["CSI300"])[0],
                    period=(qs.get("period") or ["3y"])[0],
                    filter_limit_up=(qs.get("filter_limit_up") or ["1"])[0] != "0",
                    filter_suspended=(qs.get("filter_suspended") or ["1"])[0] != "0",
                    library=(qs.get("library") or [None])[0] or None,
                )
            )
            return
        if path == "/api/factor/dashboard/status":
            from services.dashboard_store import read_job

            self._send_json(read_job())
            return
        if path == "/api/community/posts":
            from services.community_store import list_posts

            qs = parse_qs(urlparse(self.path).query)
            try:
                section = (qs.get("section") or [None])[0] or None
                q = (qs.get("q") or [None])[0] or None
                sort = (qs.get("sort") or ["views"])[0] or "views"
                limit = int((qs.get("limit") or ["50"])[0])
                offset = int((qs.get("offset") or ["0"])[0])
                self._send_json(
                    list_posts(
                        section=section, q=q, sort=sort, limit=limit, offset=offset
                    )
                )
            except ValueError as exc:
                self._send_json({"error": str(exc)}, 400)
            except Exception as exc:
                traceback.print_exc()
                self._send_json({"error": str(exc)}, 500)
            return
        if path == "/api/community/hot":
            from services.community_store import list_hot_posts

            qs = parse_qs(urlparse(self.path).query)
            try:
                limit = int((qs.get("limit") or ["10"])[0])
                section = (qs.get("section") or [None])[0]
                self._send_json(list_hot_posts(limit=limit, section=section))
            except ValueError as exc:
                self._send_json({"error": str(exc)}, 400)
            except Exception as exc:
                traceback.print_exc()
                self._send_json({"error": str(exc)}, 500)
            return
        if path == "/api/community/favorites":
            from services.auth_store import user_from_authorization
            from services.community_store import list_favorites

            qs = parse_qs(urlparse(self.path).query)
            try:
                user = user_from_authorization(self._auth_header())
                if not user:
                    self._send_json({"error": "未登录"}, 401)
                    return
                limit = int((qs.get("limit") or ["50"])[0])
                offset = int((qs.get("offset") or ["0"])[0])
                self._send_json(
                    list_favorites(int(user["id"]), limit=limit, offset=offset)
                )
            except Exception as exc:
                traceback.print_exc()
                self._send_json({"error": str(exc)}, 500)
            return
        if path == "/api/community/my-posts":
            from services.auth_store import user_from_authorization
            from services.community_store import list_my_posts

            qs = parse_qs(urlparse(self.path).query)
            try:
                user = user_from_authorization(self._auth_header())
                if not user:
                    self._send_json({"error": "未登录"}, 401)
                    return
                limit = int((qs.get("limit") or ["50"])[0])
                offset = int((qs.get("offset") or ["0"])[0])
                self._send_json(
                    list_my_posts(int(user["id"]), limit=limit, offset=offset)
                )
            except Exception as exc:
                traceback.print_exc()
                self._send_json({"error": str(exc)}, 500)
            return
        if path == "/api/community/notifications":
            from services.auth_store import user_from_authorization
            from services.community_store import list_notifications

            qs = parse_qs(urlparse(self.path).query)
            try:
                user = user_from_authorization(self._auth_header())
                if not user:
                    self._send_json({"error": "未登录"}, 401)
                    return
                typ = (qs.get("type") or [None])[0]
                limit = int((qs.get("limit") or ["50"])[0])
                offset = int((qs.get("offset") or ["0"])[0])
                self._send_json(
                    list_notifications(
                        int(user["id"]), typ=typ, limit=limit, offset=offset
                    )
                )
            except ValueError as exc:
                self._send_json({"error": str(exc)}, 400)
            except Exception as exc:
                traceback.print_exc()
                self._send_json({"error": str(exc)}, 500)
            return
        if path == "/api/community/notifications/unread-count":
            from services.auth_store import user_from_authorization
            from services.community_store import unread_notification_count

            try:
                user = user_from_authorization(self._auth_header())
                if not user:
                    self._send_json({"error": "未登录"}, 401)
                    return
                self._send_json(unread_notification_count(int(user["id"])))
            except Exception as exc:
                traceback.print_exc()
                self._send_json({"error": str(exc)}, 500)
            return
        if path == "/api/detect/projects":
            from services.auth_store import user_from_authorization
            from services.detect_store import list_projects
            from services.user_factor_store import resolve_db_user_id

            try:
                user = user_from_authorization(self._auth_header())
                if not user:
                    self._send_json({"error": "未登录"}, 401)
                    return
                qs = parse_qs(urlparse(self.path).query)
                visible = (qs.get("visible") or ["0"])[0] not in {"0", "false", "no"}
                uid = resolve_db_user_id(user)
                result = list_projects(uid, visible_only=visible)
                print(
                    f"[svquant] detect/projects user={user.get('username')} "
                    f"id={uid} count={len(result.get('projects', []))}"
                )
                self._send_json(result)
            except PermissionError as exc:
                self._send_json({"error": str(exc)}, 401)
            except Exception as exc:
                traceback.print_exc()
                self._send_json({"error": str(exc)}, 500)
            return
        if path == "/api/strategy/projects":
            from services.auth_store import user_from_authorization
            from services.strategy_store import list_projects as list_strategy_projects
            from services.user_factor_store import resolve_db_user_id

            try:
                user = user_from_authorization(self._auth_header())
                if not user:
                    self._send_json({"error": "未登录"}, 401)
                    return
                qs = parse_qs(urlparse(self.path).query)
                visible = (qs.get("visible") or ["0"])[0] not in {"0", "false", "no"}
                uid = resolve_db_user_id(user)
                self._send_json(list_strategy_projects(uid, visible_only=visible))
            except PermissionError as exc:
                self._send_json({"error": str(exc)}, 401)
            except Exception as exc:
                traceback.print_exc()
                self._send_json({"error": str(exc)}, 500)
            return
        if path.startswith("/api/strategy/projects/") and path.endswith("/runs"):
            from services.auth_store import user_from_authorization
            from services.strategy_store import list_runs as list_strategy_runs
            from services.user_factor_store import resolve_db_user_id

            mid = unquote(path[len("/api/strategy/projects/") : -len("/runs")]).strip("/")
            try:
                user = user_from_authorization(self._auth_header())
                if not user:
                    self._send_json({"error": "未登录"}, 401)
                    return
                self._send_json(list_strategy_runs(resolve_db_user_id(user), mid))
            except PermissionError as exc:
                self._send_json({"error": str(exc)}, 401)
            except Exception as exc:
                traceback.print_exc()
                self._send_json({"error": str(exc)}, 500)
            return
        if path.startswith("/api/strategy/projects/"):
            from services.auth_store import user_from_authorization
            from services.strategy_store import get_project as get_strategy_project
            from services.user_factor_store import resolve_db_user_id

            pid = unquote(path[len("/api/strategy/projects/") :]).strip("/")
            if "/" in pid:
                self._send_json({"error": "not found"}, 404)
                return
            try:
                user = user_from_authorization(self._auth_header())
                if not user:
                    self._send_json({"error": "未登录"}, 401)
                    return
                self._send_json(get_strategy_project(resolve_db_user_id(user), pid))
            except PermissionError as exc:
                self._send_json({"error": str(exc)}, 401)
            except KeyError:
                self._send_json({"error": "not found"}, 404)
            except Exception as exc:
                traceback.print_exc()
                self._send_json({"error": str(exc)}, 500)
            return
        if path.startswith("/api/strategy/runs/"):
            from services.auth_store import user_from_authorization
            from services.strategy_store import get_run as get_strategy_run
            from services.user_factor_store import resolve_db_user_id

            rid = unquote(path[len("/api/strategy/runs/") :]).strip("/")
            try:
                user = user_from_authorization(self._auth_header())
                if not user:
                    self._send_json({"error": "未登录"}, 401)
                    return
                self._send_json(get_strategy_run(resolve_db_user_id(user), rid))
            except PermissionError as exc:
                self._send_json({"error": str(exc)}, 401)
            except KeyError:
                self._send_json({"error": "not found"}, 404)
            except Exception as exc:
                traceback.print_exc()
                self._send_json({"error": str(exc)}, 500)
            return
        if path.startswith("/api/detect/projects/") and path.endswith("/runs"):
            from services.auth_store import user_from_authorization
            from services.detect_store import list_runs
            from services.user_factor_store import resolve_db_user_id

            mid = unquote(path[len("/api/detect/projects/") : -len("/runs")]).strip("/")
            try:
                user = user_from_authorization(self._auth_header())
                if not user:
                    self._send_json({"error": "未登录"}, 401)
                    return
                self._send_json(list_runs(resolve_db_user_id(user), mid))
            except PermissionError as exc:
                self._send_json({"error": str(exc)}, 401)
            except Exception as exc:
                traceback.print_exc()
                self._send_json({"error": str(exc)}, 500)
            return
        if path.startswith("/api/detect/projects/"):
            from services.auth_store import user_from_authorization
            from services.detect_store import get_project
            from services.user_factor_store import resolve_db_user_id

            pid = unquote(path[len("/api/detect/projects/") :]).strip("/")
            if "/" in pid:
                self._send_json({"error": "not found"}, 404)
                return
            try:
                user = user_from_authorization(self._auth_header())
                if not user:
                    self._send_json({"error": "未登录"}, 401)
                    return
                self._send_json(get_project(resolve_db_user_id(user), pid))
            except PermissionError as exc:
                self._send_json({"error": str(exc)}, 401)
            except KeyError:
                self._send_json({"error": "not found"}, 404)
            except Exception as exc:
                traceback.print_exc()
                self._send_json({"error": str(exc)}, 500)
            return
        if path.startswith("/api/detect/runs/"):
            from services.auth_store import user_from_authorization
            from services.detect_store import get_run
            from services.user_factor_store import resolve_db_user_id

            rid = unquote(path[len("/api/detect/runs/") :]).strip("/")
            try:
                user = user_from_authorization(self._auth_header())
                if not user:
                    self._send_json({"error": "未登录"}, 401)
                    return
                self._send_json(get_run(resolve_db_user_id(user), rid))
            except PermissionError as exc:
                self._send_json({"error": str(exc)}, 401)
            except KeyError:
                self._send_json({"error": "not found"}, 404)
            except Exception as exc:
                traceback.print_exc()
                self._send_json({"error": str(exc)}, 500)
            return
        if path.startswith("/api/community/posts/"):
            from services.auth_store import user_from_authorization
            from services.community_store import get_post, list_comments

            rest = unquote(path[len("/api/community/posts/") :]).strip("/")
            parts = [p for p in rest.split("/") if p]
            if not parts:
                self._send_json({"error": "invalid path"}, 400)
                return
            try:
                post_id = int(parts[0])
            except ValueError:
                self._send_json({"error": "invalid post id"}, 400)
                return
            try:
                if len(parts) == 1:
                    viewer = user_from_authorization(self._auth_header())
                    qs = parse_qs(urlparse(self.path).query)
                    bump_raw = (qs.get("bump") or ["1"])[0].strip().lower()
                    bump_view = bump_raw not in {"0", "false", "no"}
                    self._send_json(
                        get_post(
                            post_id,
                            bump_view=bump_view,
                            viewer_id=int(viewer["id"]) if viewer else None,
                        )
                    )
                    return
                if len(parts) == 2 and parts[1] == "comments":
                    viewer = user_from_authorization(self._auth_header())
                    self._send_json(
                        list_comments(
                            post_id,
                            viewer_id=int(viewer["id"]) if viewer else None,
                        )
                    )
                    return
                self._send_json({"error": "not found"}, 404)
            except KeyError:
                self._send_json({"error": "not found"}, 404)
            except Exception as exc:
                traceback.print_exc()
                self._send_json({"error": str(exc)}, 500)
            return
        if path == "/api/auth/me":
            from services.auth_store import me_response

            try:
                self._send_json(me_response(self._auth_header()))
            except PermissionError as exc:
                self._send_json({"error": str(exc)}, 401)
            except Exception as exc:
                traceback.print_exc()
                self._send_json({"error": str(exc)}, 500)
            return
        self._send_json({"error": "not found"}, 404)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        try:
            body = _parse_body(self)
        except json.JSONDecodeError:
            self._send_json({"error": "invalid JSON"}, 400)
            return
        if path == "/api/detect/projects":
            from services.auth_store import user_from_authorization
            from services.detect_store import create_project, upsert_project
            from services.user_factor_store import resolve_db_user_id

            try:
                user = user_from_authorization(self._auth_header())
                if not user:
                    self._send_json({"error": "未登录"}, 401)
                    return
                uid = resolve_db_user_id(user)
                if body.get("factorName") is not None or body.get("factor_name") is not None:
                    if not body.get("id") and not body.get("config"):
                        created = create_project(
                            uid,
                            factor_name=str(
                                body.get("factorName") or body.get("factor_name") or "custom_combo"
                            ),
                            description=str(body.get("description") or body.get("name") or ""),
                            display_name=(str(body["name"]) if body.get("name") else None),
                        )
                        print(
                            f"[svquant] detect/create user={user.get('username')} "
                            f"id={uid} name={created.get('project', {}).get('name')}"
                        )
                        self._send_json(created)
                        return
                self._send_json(upsert_project(uid, body))
            except PermissionError as exc:
                self._send_json({"error": str(exc)}, 401)
            except ValueError as exc:
                self._send_json({"error": str(exc)}, 400)
            except Exception as exc:
                traceback.print_exc()
                self._send_json({"error": str(exc)}, 500)
            return
        if path == "/api/detect/runs":
            from services.auth_store import user_from_authorization
            from services.detect_store import save_run
            from services.user_factor_store import resolve_db_user_id

            try:
                user = user_from_authorization(self._auth_header())
                if not user:
                    self._send_json({"error": "未登录"}, 401)
                    return
                self._send_json(save_run(resolve_db_user_id(user), body))
            except PermissionError as exc:
                self._send_json({"error": str(exc)}, 401)
            except KeyError as exc:
                self._send_json({"error": f"not found: {exc}"}, 404)
            except ValueError as exc:
                self._send_json({"error": str(exc)}, 400)
            except Exception as exc:
                traceback.print_exc()
                self._send_json({"error": str(exc)}, 500)
            return
        if path == "/api/strategy/projects":
            from services.auth_store import user_from_authorization
            from services.strategy_store import (
                create_project as create_strategy_project,
                upsert_project as upsert_strategy_project,
            )
            from services.user_factor_store import resolve_db_user_id

            try:
                user = user_from_authorization(self._auth_header())
                if not user:
                    self._send_json({"error": "未登录"}, 401)
                    return
                uid = resolve_db_user_id(user)
                if not body.get("id") and not body.get("config"):
                    created = create_strategy_project(
                        uid,
                        name=str(body.get("name") or body.get("description") or "未命名策略"),
                        description=str(body.get("description") or body.get("name") or ""),
                    )
                    self._send_json(created)
                    return
                self._send_json(upsert_strategy_project(uid, body))
            except PermissionError as exc:
                self._send_json({"error": str(exc)}, 401)
            except ValueError as exc:
                self._send_json({"error": str(exc)}, 400)
            except Exception as exc:
                traceback.print_exc()
                self._send_json({"error": str(exc)}, 500)
            return
        if path == "/api/strategy/runs":
            from services.auth_store import user_from_authorization
            from services.strategy_store import save_run as save_strategy_run
            from services.user_factor_store import resolve_db_user_id

            try:
                user = user_from_authorization(self._auth_header())
                if not user:
                    self._send_json({"error": "未登录"}, 401)
                    return
                self._send_json(save_strategy_run(resolve_db_user_id(user), body))
            except PermissionError as exc:
                self._send_json({"error": str(exc)}, 401)
            except KeyError as exc:
                self._send_json({"error": f"not found: {exc}"}, 404)
            except ValueError as exc:
                self._send_json({"error": str(exc)}, 400)
            except Exception as exc:
                traceback.print_exc()
                self._send_json({"error": str(exc)}, 500)
            return
        if path == "/api/auth/register":
            from services.auth_store import register_user

            try:
                self._send_json(
                    register_user(
                        username=str(body.get("username") or ""),
                        password=str(body.get("password") or ""),
                        email=(str(body["email"]) if body.get("email") else None),
                        display_name=(str(body["display_name"]) if body.get("display_name") else None),
                    )
                )
            except ValueError as exc:
                self._send_json({"error": str(exc)}, 400)
            except Exception as exc:
                traceback.print_exc()
                self._send_json({"error": str(exc)}, 500)
            return
        if path == "/api/auth/login":
            from services.auth_store import login_user

            try:
                self._send_json(
                    login_user(
                        username=str(body.get("username") or ""),
                        password=str(body.get("password") or ""),
                    )
                )
            except ValueError as exc:
                self._send_json({"error": str(exc)}, 401)
            except Exception as exc:
                traceback.print_exc()
                self._send_json({"error": str(exc)}, 500)
            return
        if path == "/api/factor/custom":
            from services.auth_store import user_from_authorization
            from services.factor_store import add_custom_factor
            from services.user_factor_store import resolve_db_user_id

            try:
                user = user_from_authorization(self._auth_header())
                if not user:
                    self._send_json({"error": "未登录"}, 401)
                    return
                self._send_json(
                    add_custom_factor(
                        user_id=resolve_db_user_id(user),
                        name=str(body.get("name") or ""),
                        body=str(body.get("body") or ""),
                        description=str(body.get("description") or ""),
                    )
                )
            except PermissionError as exc:
                self._send_json({"error": str(exc)}, 401)
            except ValueError as exc:
                self._send_json({"error": str(exc)}, 400)
            except Exception as exc:
                traceback.print_exc()
                self._send_json({"error": str(exc)}, 500)
            return
        if path == "/api/factor/custom/trial":
            from services.auth_store import user_from_authorization
            from services.factor_trial import trial_via_re

            try:
                user = user_from_authorization(self._auth_header())
                if not user:
                    self._send_json({"error": "未登录"}, 401)
                    return
                self._send_json(
                    trial_via_re(
                        body=str(body.get("body") or ""),
                        factor_name=str(body.get("name") or body.get("factor_name") or "trial_factor"),
                        universe=str(body.get("universe") or "CSI300"),
                        period=str(body.get("period") or "3m"),
                    )
                )
            except (ValueError, RuntimeError) as exc:
                self._send_json({"error": str(exc)}, 400)
            except Exception as exc:
                traceback.print_exc()
                self._send_json({"error": str(exc)}, 500)
            return
        if path == "/api/factor/dashboard/refresh":
            from services.dashboard_store import start_refresh

            try:
                self._send_json(
                    start_refresh(
                        universe=str(body.get("universe") or "CSI300"),
                        period=str(body.get("period") or "3y"),
                        filter_limit_up=bool(body.get("filter_limit_up", True)),
                        filter_suspended=bool(body.get("filter_suspended", True)),
                        limit=int(body["limit"]) if body.get("limit") is not None else None,
                    )
                )
            except Exception as exc:
                traceback.print_exc()
                self._send_json({"error": str(exc)}, 500)
            return
        if path == "/api/community/posts":
            from services.auth_store import user_from_authorization
            from services.community_store import create_post

            try:
                user = user_from_authorization(self._auth_header())
                if not user:
                    self._send_json({"error": "未登录"}, 401)
                    return
                self._send_json(
                    create_post(
                        int(user["id"]),
                        title=str(body.get("title") or ""),
                        body=str(body.get("body") or ""),
                        section=str(body.get("section") or ""),
                        code_snippet=(str(body["code_snippet"]) if body.get("code_snippet") else None),
                        author_role=str(user.get("role") or "user"),
                    )
                )
            except ValueError as exc:
                self._send_json({"error": str(exc)}, 400)
            except Exception as exc:
                traceback.print_exc()
                self._send_json({"error": str(exc)}, 500)
            return
        if path == "/api/community/notifications/read":
            from services.auth_store import user_from_authorization
            from services.community_store import mark_notifications_read

            try:
                user = user_from_authorization(self._auth_header())
                if not user:
                    self._send_json({"error": "未登录"}, 401)
                    return
                ids_raw = body.get("ids")
                ids = None
                if isinstance(ids_raw, list):
                    ids = [int(x) for x in ids_raw]
                self._send_json(
                    mark_notifications_read(
                        int(user["id"]),
                        ids=ids,
                        typ=body.get("type"),
                        all_unread=bool(body.get("all")),
                    )
                )
            except ValueError as exc:
                self._send_json({"error": str(exc)}, 400)
            except Exception as exc:
                traceback.print_exc()
                self._send_json({"error": str(exc)}, 500)
            return
        if path.startswith("/api/community/comments/") and path.endswith("/vote"):
            from services.auth_store import user_from_authorization
            from services.community_store import set_comment_vote

            rest = unquote(path[len("/api/community/comments/") : -len("/vote")]).strip(
                "/"
            )
            try:
                comment_id = int(rest)
            except ValueError:
                self._send_json({"error": "invalid comment id"}, 400)
                return
            try:
                user = user_from_authorization(self._auth_header())
                if not user:
                    self._send_json({"error": "未登录"}, 401)
                    return
                self._send_json(
                    set_comment_vote(
                        int(user["id"]), comment_id, int(body.get("value", 0))
                    )
                )
            except KeyError:
                self._send_json({"error": "not found"}, 404)
            except ValueError as exc:
                self._send_json({"error": str(exc)}, 400)
            except Exception as exc:
                traceback.print_exc()
                self._send_json({"error": str(exc)}, 500)
            return
        if path.startswith("/api/community/posts/"):
            from services.auth_store import user_from_authorization
            from services.community_store import add_favorite, create_comment

            rest = unquote(path[len("/api/community/posts/") :]).strip("/")
            parts = [p for p in rest.split("/") if p]
            if len(parts) != 2:
                self._send_json({"error": "not found"}, 404)
                return
            try:
                post_id = int(parts[0])
            except ValueError:
                self._send_json({"error": "invalid post id"}, 400)
                return
            try:
                user = user_from_authorization(self._auth_header())
                if not user:
                    self._send_json({"error": "未登录"}, 401)
                    return
                if parts[1] == "comments":
                    parent_raw = body.get("parent_id")
                    parent_id = None
                    if parent_raw is not None and str(parent_raw).strip() != "":
                        parent_id = int(parent_raw)
                    images = body.get("images")
                    if images is not None and not isinstance(images, list):
                        raise ValueError("images 格式错误")
                    self._send_json(
                        create_comment(
                            post_id,
                            int(user["id"]),
                            str(body.get("body") or ""),
                            parent_id=parent_id,
                            images=images,
                        )
                    )
                    return
                if parts[1] == "favorite":
                    self._send_json(add_favorite(int(user["id"]), post_id))
                    return
                self._send_json({"error": "not found"}, 404)
            except KeyError:
                self._send_json({"error": "not found"}, 404)
            except ValueError as exc:
                self._send_json({"error": str(exc)}, 400)
            except Exception as exc:
                traceback.print_exc()
                self._send_json({"error": str(exc)}, 500)
            return
        self._send_json({"error": "not found"}, 404)

    def do_PUT(self) -> None:
        path = urlparse(self.path).path
        try:
            body = _parse_body(self)
        except json.JSONDecodeError:
            self._send_json({"error": "invalid JSON"}, 400)
            return
        if path.startswith("/api/detect/projects/"):
            from services.auth_store import user_from_authorization
            from services.detect_store import upsert_project
            from services.user_factor_store import resolve_db_user_id

            pid = unquote(path[len("/api/detect/projects/") :]).strip("/")
            try:
                user = user_from_authorization(self._auth_header())
                if not user:
                    self._send_json({"error": "未登录"}, 401)
                    return
                body = {**body, "id": pid}
                self._send_json(upsert_project(resolve_db_user_id(user), body))
            except PermissionError as exc:
                self._send_json({"error": str(exc)}, 401)
            except Exception as exc:
                traceback.print_exc()
                self._send_json({"error": str(exc)}, 500)
            return
        if path.startswith("/api/strategy/projects/"):
            from services.auth_store import user_from_authorization
            from services.strategy_store import upsert_project as upsert_strategy_project
            from services.user_factor_store import resolve_db_user_id

            pid = unquote(path[len("/api/strategy/projects/") :]).strip("/")
            try:
                user = user_from_authorization(self._auth_header())
                if not user:
                    self._send_json({"error": "未登录"}, 401)
                    return
                body = {**body, "id": pid}
                self._send_json(upsert_strategy_project(resolve_db_user_id(user), body))
            except PermissionError as exc:
                self._send_json({"error": str(exc)}, 401)
            except Exception as exc:
                traceback.print_exc()
                self._send_json({"error": str(exc)}, 500)
            return
        if path.startswith("/api/community/posts/"):
            from services.auth_store import user_from_authorization
            from services.community_store import update_post

            rest = unquote(path[len("/api/community/posts/") :]).strip("/")
            parts = [p for p in rest.split("/") if p]
            if len(parts) != 1:
                self._send_json({"error": "not found"}, 404)
                return
            try:
                post_id = int(parts[0])
            except ValueError:
                self._send_json({"error": "invalid post id"}, 400)
                return
            try:
                user = user_from_authorization(self._auth_header())
                if not user:
                    self._send_json({"error": "未登录"}, 401)
                    return
                self._send_json(
                    update_post(
                        int(user["id"]),
                        post_id,
                        title=str(body.get("title") or ""),
                        body=str(body.get("body") or ""),
                        section=str(body.get("section") or ""),
                        code_snippet=(
                            str(body["code_snippet"]) if body.get("code_snippet") else None
                        ),
                        author_role=str(user.get("role") or "user"),
                    )
                )
            except PermissionError as exc:
                self._send_json({"error": str(exc)}, 403)
            except KeyError:
                self._send_json({"error": "not found"}, 404)
            except ValueError as exc:
                self._send_json({"error": str(exc)}, 400)
            except Exception as exc:
                traceback.print_exc()
                self._send_json({"error": str(exc)}, 500)
            return
        if path.startswith("/api/factor/custom/"):
            from services.auth_store import user_from_authorization
            from services.factor_store import update_custom_factor
            from services.user_factor_store import resolve_db_user_id

            name = unquote(path.rsplit("/", 1)[-1])
            try:
                user = user_from_authorization(self._auth_header())
                if not user:
                    self._send_json({"error": "未登录"}, 401)
                    return
                self._send_json(
                    update_custom_factor(
                        user_id=resolve_db_user_id(user),
                        name=name,
                        body=str(body.get("body") or ""),
                        description=str(body.get("description") or ""),
                    )
                )
            except PermissionError as exc:
                self._send_json({"error": str(exc)}, 401)
            except KeyError:
                self._send_json({"error": f"not found: {name}"}, 404)
            except ValueError as exc:
                self._send_json({"error": str(exc)}, 400)
            except Exception as exc:
                traceback.print_exc()
                self._send_json({"error": str(exc)}, 500)
            return
        self._send_json({"error": "not found"}, 404)

    def do_DELETE(self) -> None:
        path = urlparse(self.path).path
        if path.startswith("/api/community/posts/") and path.endswith("/favorite"):
            from services.auth_store import user_from_authorization
            from services.community_store import remove_favorite

            rest = unquote(path[len("/api/community/posts/") : -len("/favorite")]).strip("/")
            try:
                post_id = int(rest)
            except ValueError:
                self._send_json({"error": "invalid post id"}, 400)
                return
            try:
                user = user_from_authorization(self._auth_header())
                if not user:
                    self._send_json({"error": "未登录"}, 401)
                    return
                self._send_json(remove_favorite(int(user["id"]), post_id))
            except Exception as exc:
                traceback.print_exc()
                self._send_json({"error": str(exc)}, 500)
            return
        if path.startswith("/api/community/posts/"):
            from services.auth_store import user_from_authorization
            from services.community_store import delete_post

            rest = unquote(path[len("/api/community/posts/") :]).strip("/")
            parts = [p for p in rest.split("/") if p]
            if len(parts) != 1:
                self._send_json({"error": "not found"}, 404)
                return
            try:
                post_id = int(parts[0])
            except ValueError:
                self._send_json({"error": "invalid post id"}, 400)
                return
            try:
                user = user_from_authorization(self._auth_header())
                if not user:
                    self._send_json({"error": "未登录"}, 401)
                    return
                self._send_json(
                    delete_post(
                        int(user["id"]),
                        post_id,
                        author_role=str(user.get("role") or "user"),
                    )
                )
            except PermissionError as exc:
                self._send_json({"error": str(exc)}, 403)
            except KeyError:
                self._send_json({"error": "not found"}, 404)
            except Exception as exc:
                traceback.print_exc()
                self._send_json({"error": str(exc)}, 500)
            return
        if path.startswith("/api/detect/runs/"):
            from services.auth_store import user_from_authorization
            from services.detect_store import delete_run
            from services.user_factor_store import resolve_db_user_id

            rid = unquote(path[len("/api/detect/runs/") :]).strip("/")
            try:
                user = user_from_authorization(self._auth_header())
                if not user:
                    self._send_json({"error": "未登录"}, 401)
                    return
                self._send_json(delete_run(resolve_db_user_id(user), rid))
            except PermissionError as exc:
                self._send_json({"error": str(exc)}, 401)
            except KeyError:
                self._send_json({"error": "not found"}, 404)
            except Exception as exc:
                traceback.print_exc()
                self._send_json({"error": str(exc)}, 500)
            return
        if path.startswith("/api/strategy/runs/"):
            from services.auth_store import user_from_authorization
            from services.strategy_store import delete_run as delete_strategy_run
            from services.user_factor_store import resolve_db_user_id

            rid = unquote(path[len("/api/strategy/runs/") :]).strip("/")
            try:
                user = user_from_authorization(self._auth_header())
                if not user:
                    self._send_json({"error": "未登录"}, 401)
                    return
                self._send_json(delete_strategy_run(resolve_db_user_id(user), rid))
            except PermissionError as exc:
                self._send_json({"error": str(exc)}, 401)
            except KeyError:
                self._send_json({"error": "not found"}, 404)
            except Exception as exc:
                traceback.print_exc()
                self._send_json({"error": str(exc)}, 500)
            return
        if path.startswith("/api/detect/projects/"):
            from services.auth_store import user_from_authorization
            from services.detect_store import delete_project
            from services.user_factor_store import resolve_db_user_id

            pid = unquote(path[len("/api/detect/projects/") :]).strip("/")
            try:
                user = user_from_authorization(self._auth_header())
                if not user:
                    self._send_json({"error": "未登录"}, 401)
                    return
                self._send_json(delete_project(resolve_db_user_id(user), pid))
            except PermissionError as exc:
                self._send_json({"error": str(exc)}, 401)
            except KeyError:
                self._send_json({"error": "not found"}, 404)
            except Exception as exc:
                traceback.print_exc()
                self._send_json({"error": str(exc)}, 500)
            return
        if path.startswith("/api/strategy/projects/"):
            from services.auth_store import user_from_authorization
            from services.strategy_store import delete_project as delete_strategy_project
            from services.user_factor_store import resolve_db_user_id

            pid = unquote(path[len("/api/strategy/projects/") :]).strip("/")
            try:
                user = user_from_authorization(self._auth_header())
                if not user:
                    self._send_json({"error": "未登录"}, 401)
                    return
                self._send_json(delete_strategy_project(resolve_db_user_id(user), pid))
            except PermissionError as exc:
                self._send_json({"error": str(exc)}, 401)
            except KeyError:
                self._send_json({"error": "not found"}, 404)
            except Exception as exc:
                traceback.print_exc()
                self._send_json({"error": str(exc)}, 500)
            return
        if path.startswith("/api/factor/custom/"):
            from services.auth_store import user_from_authorization
            from services.factor_store import delete_custom_factor
            from services.user_factor_store import resolve_db_user_id

            name = unquote(path.rsplit("/", 1)[-1])
            try:
                user = user_from_authorization(self._auth_header())
                if not user:
                    self._send_json({"error": "未登录"}, 401)
                    return
                self._send_json(
                    delete_custom_factor(user_id=resolve_db_user_id(user), name=name)
                )
            except PermissionError as exc:
                self._send_json({"error": str(exc)}, 401)
            except KeyError:
                self._send_json({"error": f"not found: {name}"}, 404)
            except Exception as exc:
                traceback.print_exc()
                self._send_json({"error": str(exc)}, 500)
            return
        self._send_json({"error": "not found"}, 404)


def main() -> None:
    if not FACTOR_DIR.exists():
        raise SystemExit(f"missing factor dir: {FACTOR_DIR}")
    try:
        from services.env_config import load_env

        load_env()
    except Exception:
        pass
    try:
        from services.auth_store import ensure_schema, seed_admin
        from services.community_store import ensure_posts_schema, seed_sample_posts
        from services.detect_store import ensure_detect_schema, reassign_misowned_named_projects
        from services.strategy_store import ensure_strategy_schema
        from services.user_factor_store import (
            ensure_user_factors_schema,
            migrate_legacy_custom_to_admin,
        )

        ensure_schema()
        seed_admin()
        ensure_posts_schema()
        n = seed_sample_posts()
        ensure_user_factors_schema()
        mig = migrate_legacy_custom_to_admin()
        ensure_detect_schema()
        ensure_strategy_schema()
        moved = reassign_misowned_named_projects()
        print("  auth  → postgres users 就绪")
        print(f"  community → posts 就绪" + (f"（种子 {n} 条）" if n else ""))
        print(
            f"  user_custom_factors 就绪"
            + (f"（迁移 {mig.get('migrated', 0)}）" if mig.get("migrated") else "")
        )
        print("  detect_projects / detect_runs 就绪")
        print("  strategy_projects / strategy_runs 就绪")
        if moved:
            print(f"  detect 错归属修正: {'; '.join(moved)}")
    except Exception as exc:
        print(f"  auth  → 初始化失败（登录将不可用）: {exc}")
    try:
        from services.dashboard_store import read_job

        job = read_job()
        if job.get("status") == "running":
            print(f"  dashboard job 仍为 running（{job.get('done')}/{job.get('total')}），可能是脚本在跑")
    except Exception:
        pass
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print("=" * 48)
    print(f"SVQuant API  http://{HOST}:{PORT}")
    print(f"  factor → {FACTOR_DIR}")
    print("  GET  /api/health")
    print("  POST /api/auth/register")
    print("  POST /api/auth/login")
    print("  GET  /api/auth/me")
    print("  GET  /api/factor/index")
    print("  GET  /api/factor/file/{name}.py")
    print("  POST /api/factor/custom")
    print("  PUT  /api/factor/custom/{name}")
    print("  POST /api/factor/custom/trial")
    print("  DELETE /api/factor/custom/{name}")
    print("  GET  /api/factor/dashboard")
    print("  GET  /api/factor/dashboard/status")
    print("  POST /api/factor/dashboard/refresh")
    print("  GET  /api/community/posts")
    print("  GET  /api/community/hot")
    print("  GET  /api/community/favorites")
    print("  GET  /api/community/my-posts")
    print("  GET  /api/community/notifications")
    print("  GET  /api/community/notifications/unread-count")
    print("  POST /api/community/notifications/read")
    print("  GET  /api/community/posts/{id}")
    print("  POST /api/community/posts")
    print("  PUT  /api/community/posts/{id}")
    print("  DELETE /api/community/posts/{id}")
    print("  GET  /api/community/posts/{id}/comments")
    print("  POST /api/community/posts/{id}/comments")
    print("  POST /api/community/comments/{id}/vote")
    print("  POST /api/community/posts/{id}/favorite")
    print("  DELETE /api/community/posts/{id}/favorite")
    print("  GET  /api/detect/projects")
    print("  POST /api/detect/projects")
    print("  PUT  /api/detect/projects/{id}")
    print("  DELETE /api/detect/projects/{id}")
    print("  GET  /api/detect/projects/{id}/runs")
    print("  POST /api/detect/runs")
    print("  GET  /api/detect/runs/{id}")
    print("  DELETE /api/detect/runs/{id}")
    print("  GET  /api/strategy/projects")
    print("  POST /api/strategy/projects")
    print("  PUT  /api/strategy/projects/{id}")
    print("  DELETE /api/strategy/projects/{id}")
    print("  GET  /api/strategy/projects/{id}/runs")
    print("  POST /api/strategy/runs")
    print("  GET  /api/strategy/runs/{id}")
    print("  DELETE /api/strategy/runs/{id}")
    print("=" * 48)
    server.serve_forever()


if __name__ == "__main__":
    main()
