# -*- coding: utf-8 -*-
from __future__ import annotations

import base64
import json
from typing import Any, Iterator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.deps import require_user
from ai.gateway.ark_chat import ArkChatError, chat as ark_chat, iter_chat_stream, list_ark_models
from ai.gateway.speech_transcribe import SpeechError, speech_ready, transcribe_bytes

router = APIRouter(tags=["ai"])


@router.get("/api/ai/chat/models")
def ai_chat_models() -> dict:
    return list_ark_models()


@router.get("/api/ai/speech/status")
def ai_speech_status() -> dict:
    return speech_ready()


def _sse_chat_frames(
    messages: list,
    model: str | None,
    temperature: float,
) -> Iterator[bytes]:
    yield b'data: {"status":"start"}\n\n'
    try:
        for piece in iter_chat_stream(
            messages=messages,
            model=model,
            temperature=temperature,
        ):
            payload = json.dumps({"delta": piece}, ensure_ascii=False).encode("utf-8")
            yield b"data: " + payload + b"\n\n"
        yield b"data: [DONE]\n\n"
    except ArkChatError as exc:
        err = json.dumps({"error": str(exc)}, ensure_ascii=False).encode("utf-8")
        yield b"data: " + err + b"\n\n"
        yield b"data: [DONE]\n\n"
    except Exception as exc:
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
    _ = user
    messages = body.get("messages")
    if not isinstance(messages, list):
        raise HTTPException(status_code=400, detail="messages 须为数组")
    model = str(body.get("model") or "").strip() or None
    try:
        temperature = float(body.get("temperature", 0.7))
    except (TypeError, ValueError):
        temperature = 0.7
    want_stream = bool(body.get("stream"))

    if want_stream:
        return StreamingResponse(
            _sse_chat_frames(messages, model, temperature),
            media_type="text/event-stream; charset=utf-8",
            headers={
                "Cache-Control": "no-cache, no-store",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    try:
        return ark_chat(
            messages=messages,
            model=model,
            temperature=temperature,
        )
    except ArkChatError as exc:
        msg = str(exc)
        code = 503 if "未配置" in msg else 502
        raise HTTPException(status_code=code, detail=msg) from exc


@router.post("/api/ai/speech/transcribe")
def ai_speech_transcribe(
    body: dict[str, Any],
    user: dict = Depends(require_user),
) -> dict:
    _ = user
    b64 = str(body.get("audio_base64") or "").strip()
    if not b64:
        raise HTTPException(status_code=400, detail="缺少 audio_base64")
    if "," in b64 and b64.lower().startswith("data:"):
        b64 = b64.split(",", 1)[1]
    try:
        audio = base64.b64decode(b64, validate=False)
    except Exception:
        raise HTTPException(status_code=400, detail="audio_base64 无效") from None
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
        return transcribe_bytes(
            audio,
            filename=f"speech.{ext}",
            content_type=mime,
        )
    except SpeechError as exc:
        msg = str(exc)
        code = 503 if "未配置" in msg else 400
        raise HTTPException(status_code=code, detail=msg) from exc
