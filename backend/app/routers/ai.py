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
) -> Iterator[bytes]:
    yield b'data: {"status":"start"}\n\n'
    try:
        for piece in stream_task(
            "assistant.chat",
            messages=messages,
            model=model,
            temperature=temperature,
        ):
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

    if want_stream:
        def _frames():
            try:
                yield from _sse_chat_frames(cleaned, model, temperature)
            finally:
                _record(uid, "assistant.chat")

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
    usage = data.get("usage") or {}
    return {
        "content": strip_thinking(str(data.get("content") or "")),
        "model": data.get("model") or model or "",
        "usage": {
            "promptTokens": usage.get("prompt_tokens"),
            "completionTokens": usage.get("completion_tokens"),
            "totalTokens": usage.get("total_tokens"),
        },
    }


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
