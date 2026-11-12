# -*- coding: utf-8 -*-
"""国内语音识别：硅基流动 SenseVoice（OpenAI 兼容 transcriptions）。"""
from __future__ import annotations

import json
import os
import re
import uuid
import urllib.error
import urllib.request
from typing import Any

from ai.errors import AiError, AiNotConfigured
from services.core.env_config import env, load_env
from services.core.lan_http import urlopen_direct

load_env()

DEFAULT_MODEL = "FunAudioLLM/SenseVoiceSmall"
# SenseVoice 会夹带情感/事件标签
_TAG_RE = re.compile(r"<\|[^|]*\|>")


class SpeechError(AiError):
    """语音识别失败（沿用 ADR-037 的统一异常基类）。"""

    http_status = 400


class SpeechNotConfigured(AiNotConfigured, SpeechError):
    """语音识别未配置密钥（映射 503，但仍可被 `except SpeechError` 捕获）。"""


def _pull_windows_user_env(name: str) -> str:
    if os.name != "nt":
        return ""
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment") as key:
            val, _ = winreg.QueryValueEx(key, name)
            return str(val or "").strip()
    except Exception:
        return ""


def _silicon_key() -> str:
    for k in ("SILICONFLOW_API_KEY", "SILICON_FLOW_API_KEY"):
        v = (env(k) or _pull_windows_user_env(k) or "").strip()
        if v:
            return v
    return ""


def _base_url() -> str:
    return (
        env("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1")
        or "https://api.siliconflow.cn/v1"
    ).rstrip("/")


def _model() -> str:
    return (env("SPEECH_ASR_MODEL") or DEFAULT_MODEL).strip() or DEFAULT_MODEL


def speech_ready() -> dict[str, Any]:
    ok = bool(_silicon_key())
    return {
        "ok": ok,
        "provider": "siliconflow",
        "model": _model() if ok else None,
        "error": None if ok else "未配置 SILICONFLOW_API_KEY",
    }


def _clean_text(text: str) -> str:
    t = _TAG_RE.sub("", text or "")
    return re.sub(r"\s+", " ", t).strip()


def _build_multipart(
    *,
    file_name: str,
    file_bytes: bytes,
    content_type: str,
    model: str,
) -> tuple[bytes, str]:
    boundary = f"----SvSpeech{uuid.uuid4().hex}"
    chunks: list[bytes] = []

    def add_field(name: str, value: str) -> None:
        chunks.append(f"--{boundary}\r\n".encode())
        chunks.append(
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode()
        )
        chunks.append(value.encode("utf-8"))
        chunks.append(b"\r\n")

    def add_file(name: str, filename: str, data: bytes, ctype: str) -> None:
        chunks.append(f"--{boundary}\r\n".encode())
        chunks.append(
            (
                f'Content-Disposition: form-data; name="{name}"; '
                f'filename="{filename}"\r\n'
                f"Content-Type: {ctype}\r\n\r\n"
            ).encode()
        )
        chunks.append(data)
        chunks.append(b"\r\n")

    add_field("model", model)
    add_file("file", file_name, file_bytes, content_type)
    chunks.append(f"--{boundary}--\r\n".encode())
    return b"".join(chunks), boundary


def transcribe_bytes(
    audio: bytes,
    *,
    filename: str = "speech.webm",
    content_type: str = "audio/webm",
) -> dict[str, Any]:
    if not audio:
        raise SpeechError("音频为空")
    if len(audio) > 8 * 1024 * 1024:
        raise SpeechError("音频过大，请缩短说话时长")

    key = _silicon_key()
    if not key:
        raise SpeechNotConfigured("未配置 SILICONFLOW_API_KEY")

    model = _model()
    body, boundary = _build_multipart(
        file_name=filename or "speech.webm",
        file_bytes=audio,
        content_type=content_type or "application/octet-stream",
        model=model,
    )
    url = f"{_base_url()}/audio/transcriptions"
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        method="POST",
    )
    try:
        with urlopen_direct(req, timeout=90) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace")[:400]
        except Exception:
            pass
        raise SpeechError(
            f"语音识别失败 HTTP {exc.code}" + (f"：{detail}" if detail else "")
        ) from exc
    except Exception as exc:
        raise SpeechError(f"语音识别请求失败：{exc}") from exc

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SpeechError(f"识别响应无法解析：{raw[:200]}") from exc

    text = _clean_text(str(data.get("text") or ""))
    if not text:
        raise SpeechError("未识别出文字，请再说一次")
    return {"text": text, "model": model, "provider": "siliconflow"}
