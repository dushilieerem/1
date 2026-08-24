"""iFinD 原始 JSON 响应缓存。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol


class JsonClient(Protocol):
    def post(self, path: str, payload: dict) -> dict: ...


def save_json_response(raw_path: Path, response: dict) -> None:
    """原子保存 iFinD 原始 JSON 响应。"""
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = raw_path.with_suffix(raw_path.suffix + ".tmp")
    with temporary_path.open("w", encoding="utf-8") as stream:
        json.dump(response, stream, ensure_ascii=False)
    temporary_path.replace(raw_path)


def load_or_fetch_json(client: JsonClient, raw_path: Path, path: str, payload: dict) -> dict:
    """优先重放已落盘响应；首次请求成功后立即保存，再交给调用方解析。"""
    if raw_path.is_file():
        with raw_path.open("r", encoding="utf-8") as stream:
            response = json.load(stream)
        if not isinstance(response, dict):
            raise ValueError(f"iFinD 原始响应不是 JSON 对象：{raw_path}")
        return response

    response = client.post(path, payload)
    save_json_response(raw_path, response)
    return response
