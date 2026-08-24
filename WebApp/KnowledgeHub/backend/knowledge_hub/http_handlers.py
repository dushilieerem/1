# -*- coding: utf-8 -*-
"""KnowledgeHub HTTP。

内网调试默认：**无 Token 也可调**（视为 admin），方便 Swagger Try it out。
若带了 Authorization，则仍校验必须为 admin。
前端页面本身仍可走登录门禁。
"""
from __future__ import annotations

import os
from typing import Any, Callable

from knowledge_hub import store
from knowledge_hub.chunking import list_strategies
from knowledge_hub.store import ensure_kh_schema

# 默认开放；设 KH_REQUIRE_AUTH=1 可恢复强制登录
_KH_REQUIRE_AUTH = os.environ.get("KH_REQUIRE_AUTH", "").strip() in ("1", "true", "TRUE", "yes")

_ANON_ADMIN = {
    "id": None,
    "username": "kh-anon",
    "role": "admin",
    "display_name": "知识库调试",
}


def _require_admin(user: dict[str, Any] | None) -> tuple[dict[str, Any] | None, int, str]:
    if user:
        if user.get("role") != "admin":
            return None, 403, "仅管理员可进入知识库平台"
        return user, 200, ""
    if _KH_REQUIRE_AUTH:
        return None, 401, "未登录"
    return dict(_ANON_ADMIN), 200, ""


def _actor_id(user: dict[str, Any] | None) -> int | None:
    """写入 created_by：无真实用户时用 NULL，避免 FK 撞 users.id=0。"""
    if not user:
        return None
    raw = user.get("id")
    if raw is None or raw == "" or raw == 0:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def handle_kh_get(
    path: str,
    *,
    user: dict[str, Any] | None,
    send_json: Callable[..., None],
) -> bool:
    if not path.startswith("/api/kh"):
        return False
    u, code, err = _require_admin(user)
    if not u:
        send_json({"error": err}, code)
        return True
    ensure_kh_schema()

    if path == "/api/kh/meta":
        send_json(
            {
                "pipelines": store.list_pipelines(),
                "chunkStrategies": list_strategies(),
            }
        )
        return True

    if path == "/api/kh/collections":
        send_json({"collections": store.list_collections()})
        return True

    if path.startswith("/api/kh/collections/") and path.endswith("/documents"):
        mid = path[len("/api/kh/collections/") : -len("/documents")].strip("/")
        try:
            coll_id = int(mid)
        except ValueError:
            send_json({"error": "无效知识库 id"}, 400)
            return True
        send_json({"documents": store.list_documents(coll_id), "collectionId": coll_id})
        return True

    if path.startswith("/api/kh/documents/") and path.endswith("/chunks"):
        mid = path[len("/api/kh/documents/") : -len("/chunks")].strip("/")
        try:
            doc_id = int(mid)
        except ValueError:
            send_json({"error": "无效文档 id"}, 400)
            return True
        send_json({"chunks": store.list_chunks(doc_id), "documentId": doc_id})
        return True

    if path.startswith("/api/kh/documents/") and path.endswith("/progress"):
        mid = path[len("/api/kh/documents/") : -len("/progress")].strip("/")
        try:
            doc_id = int(mid)
        except ValueError:
            send_json({"error": "无效文档 id"}, 400)
            return True
        send_json({"progress": store.get_ingest_progress(doc_id)})
        return True

    if path.startswith("/api/kh/documents/"):
        mid = path[len("/api/kh/documents/") :].strip("/")
        if mid.isdigit():
            doc = store.get_document(int(mid))
            if not doc:
                send_json({"error": "文档不存在"}, 404)
                return True
            chunks = store.list_chunks(int(mid))
            doc = {**doc, "chunkCount": len(chunks)}
            send_json({"document": doc})
            return True

    if path == "/api/kh/chats":
        send_json({"chats": store.list_chats()})
        return True

    if path.startswith("/api/kh/chats/") and path.endswith("/conversations"):
        mid = path[len("/api/kh/chats/") : -len("/conversations")].strip("/")
        try:
            chat_id = int(mid)
        except ValueError:
            send_json({"error": "无效聊天 id"}, 400)
            return True
        send_json(
            {
                "conversations": store.list_conversations(chat_id),
                "chatId": chat_id,
            }
        )
        return True

    if path.startswith("/api/kh/chats/") and path.endswith("/messages"):
        mid = path[len("/api/kh/chats/") : -len("/messages")].strip("/")
        try:
            chat_id = int(mid)
        except ValueError:
            send_json({"error": "无效聊天 id"}, 400)
            return True
        conv = store.ensure_default_conversation(chat_id)
        send_json(
            {
                "messages": store.list_chat_messages(chat_id),
                "chatId": chat_id,
                "conversationId": conv["id"],
            }
        )
        return True

    if path.startswith("/api/kh/conversations/") and path.endswith("/messages"):
        mid = path[len("/api/kh/conversations/") : -len("/messages")].strip("/")
        try:
            conversation_id = int(mid)
        except ValueError:
            send_json({"error": "无效会话 id"}, 400)
            return True
        conv = store.get_conversation(conversation_id)
        if not conv:
            send_json({"error": "conversation not found"}, 404)
            return True
        send_json(
            {
                "messages": store.list_conversation_messages(conversation_id),
                "conversationId": conversation_id,
                "chatId": conv["chatId"],
            }
        )
        return True

    if path == "/api/kh/files":
        send_json({"files": store.list_files()})
        return True

    if path == "/api/kh/model-providers":
        send_json({"providers": store.list_model_providers()})
        return True

    if path == "/api/kh/default-models":
        send_json(store.get_default_models())
        return True

    if path == "/api/kh/docs/outline":
        send_json(store.api_catalog())
        return True

    return False


def handle_kh_post(
    path: str,
    body: dict[str, Any],
    *,
    user: dict[str, Any] | None,
    send_json: Callable[..., None],
) -> bool:
    if not path.startswith("/api/kh"):
        return False
    u, code, err = _require_admin(user)
    if not u:
        send_json({"error": err}, code)
        return True
    uid = _actor_id(u)

    if path == "/api/kh/collections":
        try:
            coll = store.create_collection(
                name=str(body.get("name") or ""),
                description=str(body.get("description") or ""),
                pipeline=str(body.get("pipeline") or "general"),
                chunk_strategy=body.get("chunkStrategy") or body.get("chunk_strategy"),
                created_by=uid,
            )
            send_json({"collection": coll})
        except ValueError as exc:
            send_json({"error": str(exc)}, 400)
        except Exception as exc:
            if "unique" in str(exc).lower() or "duplicate" in str(exc).lower():
                send_json({"error": "知识库名称已存在"}, 409)
            else:
                raise
        return True

    if path == "/api/kh/documents":
        try:
            doc = store.create_document(
                collection_id=int(body.get("collectionId") or body.get("collection_id") or 0),
                title=str(body.get("title") or ""),
                body=str(body.get("body") or body.get("text") or ""),
                chunk_strategy=body.get("chunkStrategy") or body.get("chunk_strategy"),
                source_type=str(body.get("sourceType") or body.get("source_type") or "text"),
                file_name=str(body.get("fileName") or body.get("file_name") or ""),
                file_size=int(body.get("fileSize") or body.get("file_size") or 0),
                created_by=uid,
                ingest=bool(body.get("ingest", True)),
                content_base64=body.get("contentBase64") or body.get("content_base64"),
            )
            send_json({"document": doc})
        except (ValueError, TypeError) as exc:
            send_json({"error": str(exc)}, 400)
        return True

    if path.startswith("/api/kh/documents/") and path.endswith("/ingest"):
        mid = path[len("/api/kh/documents/") : -len("/ingest")].strip("/")
        try:
            doc_id = int(mid)
            send_json(store.ingest_document(doc_id))
        except ValueError as exc:
            send_json({"error": str(exc)}, 400)
        return True

    if path == "/api/kh/search":
        try:
            raw_ids = body.get("collectionIds") or body.get("collection_ids") or []
            if body.get("collectionId") or body.get("collection_id"):
                raw_ids = list(raw_ids) + [
                    body.get("collectionId") or body.get("collection_id")
                ]
            cids = []
            for x in raw_ids:
                try:
                    cids.append(int(x))
                except (TypeError, ValueError):
                    continue
            result = store.search_chunks(
                query=str(body.get("query") or body.get("q") or ""),
                collection_ids=cids or None,
                top_k=int(body.get("topK") or body.get("top_k") or 8),
            )
            send_json(result)
        except ValueError as exc:
            send_json({"error": str(exc)}, 400)
        except (TypeError,) as exc:
            send_json({"error": str(exc)}, 400)
        return True

    if path == "/api/kh/ask":
        from knowledge_hub.llm import KhLlmError

        try:
            raw_ids = body.get("collectionIds") or body.get("collection_ids") or []
            if body.get("collectionId") or body.get("collection_id"):
                raw_ids = list(raw_ids) + [
                    body.get("collectionId") or body.get("collection_id")
                ]
            cids = []
            for x in raw_ids:
                try:
                    cids.append(int(x))
                except (TypeError, ValueError):
                    continue
            chat_raw = body.get("chatId") or body.get("chat_id")
            chat_id = int(chat_raw) if chat_raw not in (None, "") else None
            result = store.ask(
                query=str(body.get("query") or body.get("q") or ""),
                collection_ids=cids or None,
                chat_id=chat_id,
                top_k=int(body.get("topK") or body.get("top_k") or 5),
            )
            send_json(result)
        except KhLlmError as exc:
            send_json({"error": str(exc)}, 400)
        except ValueError as exc:
            send_json({"error": str(exc)}, 400)
        except KeyError:
            send_json({"error": "chat not found"}, 404)
        except (TypeError,) as exc:
            send_json({"error": str(exc)}, 400)
        return True

    if path == "/api/kh/chats":
        send_json(
            {
                "chat": store.create_chat(
                    name=str(body.get("name") or "未命名聊天"),
                    created_by=uid,
                )
            }
        )
        return True

    if path.startswith("/api/kh/chats/") and path.endswith("/conversations"):
        mid = path[len("/api/kh/chats/") : -len("/conversations")].strip("/")
        try:
            chat_id = int(mid)
            conv = store.create_conversation(
                chat_id, title=str(body.get("title") or "新会话")
            )
            send_json({"conversation": conv})
        except ValueError as exc:
            send_json({"error": str(exc)}, 400)
        except KeyError:
            send_json({"error": "chat not found"}, 404)
        return True

    if path.startswith("/api/kh/chats/") and path.endswith("/messages"):
        mid = path[len("/api/kh/chats/") : -len("/messages")].strip("/")
        try:
            chat_id = int(mid)
            meta = body.get("meta") if isinstance(body.get("meta"), dict) else {}
            msg = store.append_chat_message(
                chat_id,
                role=str(body.get("role") or "user"),
                content=str(body.get("content") or ""),
                meta=meta,
            )
            send_json({"message": msg})
        except ValueError as exc:
            send_json({"error": str(exc)}, 400)
        except KeyError:
            send_json({"error": "chat not found"}, 404)
        return True

    if path.startswith("/api/kh/conversations/") and path.endswith("/messages"):
        mid = path[len("/api/kh/conversations/") : -len("/messages")].strip("/")
        try:
            conversation_id = int(mid)
            meta = body.get("meta") if isinstance(body.get("meta"), dict) else {}
            msg = store.append_conversation_message(
                conversation_id,
                role=str(body.get("role") or "user"),
                content=str(body.get("content") or ""),
                meta=meta,
            )
            send_json({"message": msg})
        except ValueError as exc:
            send_json({"error": str(exc)}, 400)
        except KeyError:
            send_json({"error": "conversation not found"}, 404)
        return True

    if path == "/api/kh/files":
        try:
            cid = body.get("collectionId") or body.get("collection_id")
            f = store.create_file(
                title=str(body.get("title") or ""),
                body=str(body.get("body") or ""),
                file_name=str(body.get("fileName") or body.get("file_name") or ""),
                file_size=int(body.get("fileSize") or body.get("file_size") or 0),
                collection_id=int(cid) if cid else None,
                created_by=uid,
            )
            send_json({"file": f})
        except (ValueError, TypeError) as exc:
            send_json({"error": str(exc)}, 400)
        return True

    if path == "/api/kh/model-providers":
        try:
            send_json({"provider": store.upsert_model_provider(body)})
        except ValueError as exc:
            send_json({"error": str(exc)}, 400)
        return True

    if path == "/api/kh/default-models":
        send_json(store.set_default_models(body))
        return True

    return False


def handle_kh_put(
    path: str,
    body: dict[str, Any],
    *,
    user: dict[str, Any] | None,
    send_json: Callable[..., None],
) -> bool:
    if not path.startswith("/api/kh"):
        return False
    u, code, err = _require_admin(user)
    if not u:
        send_json({"error": err}, code)
        return True

    if path.startswith("/api/kh/conversations/"):
        mid = path[len("/api/kh/conversations/") :].strip("/")
        if not mid or "/" in mid:
            return False
        try:
            send_json(
                {"conversation": store.update_conversation(int(mid), body)}
            )
        except ValueError as exc:
            send_json({"error": str(exc)}, 400)
        except KeyError:
            send_json({"error": "not found"}, 404)
        return True

    if path.startswith("/api/kh/chats/"):
        mid = path[len("/api/kh/chats/") :].strip("/")
        if not mid or "/" in mid:
            return False
        try:
            chat_id = int(mid)
            send_json({"chat": store.update_chat(chat_id, body)})
        except ValueError as exc:
            send_json({"error": str(exc)}, 400)
        except KeyError:
            send_json({"error": "not found"}, 404)
        return True

    if path.startswith("/api/kh/collections/"):
        mid = path[len("/api/kh/collections/") :].strip("/")
        if not mid or "/" in mid:
            return False
        try:
            send_json({"collection": store.update_collection(int(mid), body)})
        except ValueError as exc:
            send_json({"error": str(exc)}, 400)
        except KeyError:
            send_json({"error": "知识库不存在"}, 404)
        except Exception as exc:
            if "unique" in str(exc).lower() or "duplicate" in str(exc).lower():
                send_json({"error": "知识库名称已存在"}, 409)
            else:
                raise
        return True

    if path.startswith("/api/kh/documents/"):
        mid = path[len("/api/kh/documents/") :].strip("/")
        if not mid or "/" in mid:
            return False
        try:
            send_json({"document": store.update_document(int(mid), body)})
        except ValueError as exc:
            send_json({"error": str(exc)}, 400)
        except KeyError:
            send_json({"error": "文档不存在"}, 404)
        return True

    if path == "/api/kh/default-models":
        send_json(store.set_default_models(body))
        return True

    return False


def handle_kh_delete(
    path: str,
    *,
    user: dict[str, Any] | None,
    send_json: Callable[..., None],
) -> bool:
    if not path.startswith("/api/kh"):
        return False
    u, code, err = _require_admin(user)
    if not u:
        send_json({"error": err}, code)
        return True

    if path.startswith("/api/kh/collections/"):
        mid = path[len("/api/kh/collections/") :].strip("/")
        if not mid or "/" in mid:
            return False
        try:
            ok = store.delete_collection(int(mid))
        except ValueError:
            send_json({"error": "无效 id"}, 400)
            return True
        send_json({"ok": True} if ok else {"error": "not found"}, 200 if ok else 404)
        return True

    if path.startswith("/api/kh/documents/"):
        mid = path[len("/api/kh/documents/") :].strip("/")
        if not mid or "/" in mid:
            return False
        try:
            ok = store.delete_document(int(mid))
        except ValueError:
            send_json({"error": "无效 id"}, 400)
            return True
        send_json({"ok": True} if ok else {"error": "not found"}, 200 if ok else 404)
        return True

    if path.startswith("/api/kh/conversations/"):
        mid = path[len("/api/kh/conversations/") :].strip("/")
        if mid.endswith("/messages"):
            cid = mid[: -len("/messages")].strip("/")
            try:
                conversation_id = int(cid)
                deleted = store.clear_conversation_messages(conversation_id)
                send_json({"ok": True, "deleted": deleted})
            except ValueError:
                send_json({"error": "无效 id"}, 400)
            except KeyError:
                send_json({"error": "conversation not found"}, 404)
            return True
        if not mid or "/" in mid:
            return False
        try:
            ok = store.delete_conversation(int(mid))
        except ValueError:
            send_json({"error": "无效 id"}, 400)
            return True
        send_json({"ok": True} if ok else {"error": "not found"}, 200 if ok else 404)
        return True

    if path.startswith("/api/kh/chats/"):
        mid = path[len("/api/kh/chats/") :].strip("/")
        if mid.endswith("/messages"):
            cid = mid[: -len("/messages")].strip("/")
            try:
                chat_id = int(cid)
                deleted = store.clear_chat_messages(chat_id)
                send_json({"ok": True, "deleted": deleted})
            except ValueError:
                send_json({"error": "无效 id"}, 400)
            return True
        if "/" in mid:
            return False
        try:
            ok = store.delete_chat(int(mid))
        except ValueError:
            send_json({"error": "无效 id"}, 400)
            return True
        send_json({"ok": True} if ok else {"error": "not found"}, 200 if ok else 404)
        return True

    if path.startswith("/api/kh/files/"):
        mid = path[len("/api/kh/files/") :].strip("/")
        if not mid or "/" in mid:
            return False
        try:
            ok = store.delete_file(int(mid))
        except ValueError:
            send_json({"error": "无效 id"}, 400)
            return True
        send_json({"ok": True} if ok else {"error": "not found"}, 200 if ok else 404)
        return True

    if path.startswith("/api/kh/model-providers/"):
        key = path[len("/api/kh/model-providers/") :].strip("/")
        if not key or "/" in key:
            return False
        ok = store.delete_model_provider(key)
        send_json({"ok": True} if ok else {"error": "not found"}, 200 if ok else 404)
        return True

    return False
