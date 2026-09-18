# -*- coding: utf-8 -*-
"""模型网关：对话 / LLM / 语音。"""
from ai.gateway.ark_chat import ArkChatError, chat, iter_chat_stream, list_ark_models
from ai.gateway.llm_client import LlmError, chat_completions, llm_configured, llm_settings
from ai.gateway.speech_transcribe import SpeechError, speech_ready, transcribe_bytes

__all__ = [
    "ArkChatError",
    "chat",
    "iter_chat_stream",
    "list_ark_models",
    "LlmError",
    "chat_completions",
    "llm_configured",
    "llm_settings",
    "SpeechError",
    "speech_ready",
    "transcribe_bytes",
]
