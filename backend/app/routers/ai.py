# -*- coding: utf-8 -*-
"""AI 对外端点：助手对话（含流式）与语音转写。

所有模型调用经 `ai.router`（ADR-037）；本文件只做 HTTP 适配与状态码映射，
不出现供应商名，也不按错误文案猜测状态码。
"""
from __future__ import annotations

import base64
import json
import uuid
from typing import Any, Iterator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from ai.errors import AiError
from ai.gateway.ark_chat import list_ark_models, prepare_messages, strip_thinking
from ai.gateway.speech_transcribe import SpeechError, speech_ready, transcribe_bytes
from ai.router import run_task, stream_task
from ai.runtime import conversation_store
from ai.runtime.store import assert_quota_available, record_usage
from app.deps import require_user

router = APIRouter(tags=["ai"])


def _http_error(exc: AiError) -> HTTPException:
    """唯一的状态码映射点：按异常类型，不看错误文案。"""
    status = int(getattr(exc, "http_status", 502) or 502)
    return HTTPException(status_code=status, detail=str(exc) or "AI 服务调用失败")


def _assert_quota(user: dict[str, Any], *, need: int = 1) -> int:
    uid = int(user.get("id") or 0)
    if uid <= 0:
        return 0
    try:
        assert_quota_available(uid, need=need)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return uid


def _record(uid: int, skill: str, *, tokens_in: int = 0, tokens_out: int = 0) -> None:
    if uid <= 0:
        return
    try:
        record_usage(
            user_id=uid,
            run_id=uuid.uuid4().hex,
            skill=skill,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
        )
    except Exception:
        # 记账失败不影响已完成的 AI 响应。
        pass


def _validate_messages(messages: Any) -> list[dict[str, str]]:
    if not isinstance(messages, list) or not messages:
        raise HTTPException(status_code=400, detail="messages must be a non-empty array")
    out: list[dict[str, str]] = []
    for item in messages:
        if not isinstance(item, dict):
            raise HTTPException(status_code=400, detail="message item must be an object")
        role = str(item.get("role") or "").strip()
        content = str(item.get("content") or "").strip()
        if role not in {"user", "assistant", "system"} or not content:
            raise HTTPException(status_code=400, detail="message item requires valid role/content")
        out.append({"role": role, "content": content})
    return out


@router.get("/api/ai/chat/models")
def ai_chat_models() -> dict:
    return list_ark_models()


@router.get("/api/ai/speech/status")
def ai_speech_status() -> dict:
    return speech_ready()


def _sse_chat_frames(
    messages: list[dict[str, Any]],
    model: str | None,
    temperature: float,
    on_delta: Any = None,
) -> Iterator[bytes]:
    yield b'data: {"status":"start"}\n\n'
    try:
        for piece in stream_task(
            "assistant.chat",
            messages=messages,
            model=model,
            temperature=temperature,
        ):
            if on_delta is not None:
                on_delta(piece)
            payload = json.dumps({"delta": piece}, ensure_ascii=False).encode("utf-8")
            yield b"data: " + payload + b"\n\n"
        yield b"data: [DONE]\n\n"
    except AiError as exc:
        err = json.dumps({"error": str(exc)}, ensure_ascii=False).encode("utf-8")
        yield b"data: " + err + b"\n\n"
        yield b"data: [DONE]\n\n"
    except Exception as exc:  # noqa: BLE001 - 流已开始，只能以帧返回错误
        import traceback

        traceback.print_exc()
        err = json.dumps({"error": str(exc)}, ensure_ascii=False).encode("utf-8")
        yield b"data: " + err + b"\n\n"
        yield b"data: [DONE]\n\n"


def _last_user_content(messages: list[dict[str, Any]]) -> str:
    for msg in reversed(messages or []):
        if str(msg.get("role") or "") == "user":
            return str(msg.get("content") or "")
    return ""


def _persist_exchange(
    uid: int,
    conversation_id: int,
    *,
    user_text: str,
    reply: str,
    model: str | None = None,
    tokens_in: int = 0,
    tokens_out: int = 0,
) -> None:
    """落库失败不影响对话主链路。"""
    if uid <= 0:
        return
    try:
        if user_text:
            conversation_store.append_message(
                uid, conversation_id, role="user", content=user_text
            )
        if reply:
            conversation_store.append_message(
                uid,
                conversation_id,
                role="assistant",
                content=reply,
                model=model,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
            )
    except Exception:  # noqa: BLE001
        pass


@router.post("/api/ai/chat")
def ai_chat(
    body: dict[str, Any],
    user: dict = Depends(require_user),
):
    uid = _assert_quota(user)
    messages = _validate_messages(body.get("messages"))
    model = str(body.get("model") or "").strip() or None
    try:
        temperature = float(body.get("temperature", 0.7))
    except (TypeError, ValueError):
        temperature = 0.7
    want_stream = bool(body.get("stream"))

    try:
        cleaned = prepare_messages(messages)
    except AiError as exc:
        raise _http_error(exc) from exc

    # P1-A01：可选服务端会话；未显式给 id 且 persist=true 时自动新建
    conversation_id = 0
    try:
        conversation_id = int(body.get("conversation_id") or 0)
    except (TypeError, ValueError):
        conversation_id = 0
    if not conversation_id and body.get("persist") and uid > 0:
        first = _last_user_content(messages)
        conversation_id = int(
            conversation_store.create_conversation(
                uid, first_message=first, title=first
            )["id"]
        )

    if want_stream:
        parts: list[str] = []

        def _frames():
            try:
                yield from _sse_chat_frames(
                    cleaned, model, temperature, on_delta=parts.append
                )
            finally:
                _record(uid, "assistant.chat")
                if conversation_id:
                    _persist_exchange(
                        uid,
                        conversation_id,
                        user_text=_last_user_content(messages),
                        reply="".join(parts),
                        model=model,
                    )

        return StreamingResponse(
            _frames(),
            media_type="text/event-stream; charset=utf-8",
            headers={
                "Cache-Control": "no-cache, no-store",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    try:
        data = run_task(
            "assistant.chat",
            messages=cleaned,
            model=model,
            temperature=temperature,
        )
    except AiError as exc:
        raise _http_error(exc) from exc

    _record(uid, "assistant.chat", tokens_in=int(data.get("tokens_in") or 0), tokens_out=int(data.get("tokens_out") or 0))
    if conversation_id:
        _persist_exchange(
            uid,
            conversation_id,
            user_text=_last_user_content(messages),
            reply=str(data.get("content") or ""),
            model=str(data.get("model") or model or ""),
            tokens_in=int(data.get("tokens_in") or 0),
            tokens_out=int(data.get("tokens_out") or 0),
        )
    usage = data.get("usage") or {}
    return {
        "conversation_id": conversation_id or None,
        "content": strip_thinking(str(data.get("content") or "")),
        "model": data.get("model") or model or "",
        "usage": {
            "promptTokens": usage.get("prompt_tokens"),
            "completionTokens": usage.get("completion_tokens"),
            "totalTokens": usage.get("total_tokens"),
        },
    }


@router.get("/api/ai/conversations")
def ai_conversations_list(
    user: dict = Depends(require_user),
    limit: int = 20,
    offset: int = 0,
) -> dict:
    return conversation_store.list_conversations(
        int(user["id"]), limit=limit, offset=offset
    )


@router.post("/api/ai/conversations")
def ai_conversations_create(body: dict[str, Any], user: dict = Depends(require_user)) -> dict:
    return {
        "ok": True,
        "conversation": conversation_store.create_conversation(
            int(user["id"]),
            title=str(body.get("title") or ""),
            first_message=str(body.get("first_message") or ""),
        ),
    }


@router.get("/api/ai/conversations/{conversation_id}")
def ai_conversations_get(conversation_id: int, user: dict = Depends(require_user)) -> dict:
    item = conversation_store.get_conversation(int(user["id"]), conversation_id)
    if item is None:
        raise HTTPException(status_code=404, detail="not found")
    return item


@router.delete("/api/ai/conversations/{conversation_id}")
def ai_conversations_delete(conversation_id: int, user: dict = Depends(require_user)) -> dict:
    if not conversation_store.delete_conversation(int(user["id"]), conversation_id):
        raise HTTPException(status_code=404, detail="not found")
    return {"ok": True}


@router.post("/api/ai/speech/transcribe")
def ai_speech_transcribe(
    body: dict[str, Any],
    user: dict = Depends(require_user),
) -> dict:
    uid = _assert_quota(user)
    b64 = str(body.get("audio_base64") or "").strip()
    if not b64:
        raise HTTPException(status_code=400, detail="缺少 audio_base64")
    if "," in b64 and b64.lower().startswith("data:"):
        b64 = b64.split(",", 1)[1]
    try:
        audio = base64.b64decode(b64, validate=True)
    except Exception:
        raise HTTPException(status_code=400, detail="audio_base64 无效") from None
    if not audio:
        raise HTTPException(status_code=400, detail="audio_base64 无效")
    mime = str(body.get("mime") or "audio/webm").strip() or "audio/webm"
    ext = "webm"
    if "ogg" in mime:
        ext = "ogg"
    elif "mp4" in mime or "m4a" in mime or "aac" in mime:
        ext = "m4a"
    elif "mpeg" in mime or "mp3" in mime:
        ext = "mp3"
    elif "wav" in mime:
        ext = "wav"
    elif "caf" in mime:
        ext = "caf"
    try:
        out = transcribe_bytes(
            audio,
            filename=f"speech.{ext}",
            content_type=mime,
        )
        _record(uid, "assistant.speech")
        return out
    except SpeechError as exc:
        raise _http_error(exc) from exc
