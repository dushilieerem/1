# -*- coding: utf-8 -*-
"""OpenAI 兼容 Embedding 客户端（百炼 / DashScope 等）。"""
from __future__ import annotations

import json
import math
import urllib.error
import urllib.request
from typing import Any

from services.db import get_conn


def get_role_credentials(role_key: str = "embedding") -> dict[str, str] | None:
    """读取默认角色对应的 base_url / api_key / model_name；缺配置返回 None。"""
    from knowledge_hub.store import ensure_kh_schema

    ensure_kh_schema()
    with get_conn() as conn:
        role = conn.execute(
            "SELECT provider_key, model_name FROM kh_default_models WHERE role_key = %s",
            (role_key,),
        ).fetchone()
        if not role or not (role.get("provider_key") or "").strip():
            return None
        if not (role.get("model_name") or "").strip():
            return None
        prov = conn.execute(
            """
            SELECT base_url, api_key FROM kh_model_providers
            WHERE provider_key = %s
            """,
            (role["provider_key"],),
        ).fetchone()
        if not prov:
            return None
        base = (prov.get("base_url") or "").strip().rstrip("/")
        key = (prov.get("api_key") or "").strip()
        if not base or not key:
            return None
        return {
            "providerKey": str(role["provider_key"]),
            "modelName": str(role["model_name"]).strip(),
            "baseUrl": base,
            "apiKey": key,
        }


def _post_json(
    url: str,
    payload: dict[str, Any],
    api_key: str,
    timeout: int = 120,
    retries: int = 3,
) -> dict[str, Any]:
    """优先 requests（避免 urllib IncompleteRead）；失败再回退 urllib。"""
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    last_err: Exception | None = None
    try:
        import requests

        for attempt in range(max(1, retries)):
            try:
                resp = requests.post(
                    url, json=payload, headers=headers, timeout=timeout
                )
                if resp.status_code >= 400:
                    raise RuntimeError(
                        f"Embedding HTTP {resp.status_code}: {resp.text[:500]}"
                    )
                return resp.json()
            except Exception as e:
                last_err = e
                if attempt + 1 >= retries:
                    break
    except ImportError:
        last_err = None

    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    for attempt in range(max(1, retries)):
        req = urllib.request.Request(
            url, data=data, method="POST", headers=headers
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read().decode("utf-8", errors="replace")
            return json.loads(body)
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")[:500]
            raise RuntimeError(f"Embedding HTTP {e.code}: {detail}") from e
        except Exception as e:
            last_err = e
            if attempt + 1 >= retries:
                break
    raise RuntimeError(f"Embedding 请求失败: {last_err}")


def embed_texts(
    texts: list[str],
    *,
    creds: dict[str, str] | None = None,
    batch_size: int = 4,
    on_progress: Any | None = None,
) -> list[list[float]]:
    """批量向量化；返回与 texts 等长的向量列表。

    on_progress(done, total) 每批回调一次，便于前端进度条。
    """
    if not texts:
        return []
    c = creds or get_role_credentials("embedding")
    if not c:
        raise RuntimeError("未配置默认 Embedding（供应商 / 模型 / Key）")
    url = f"{c['baseUrl']}/embeddings"
    total = len(texts)
    out: list[list[float]] = []
    for i in range(0, total, max(1, batch_size)):
        batch = texts[i : i + batch_size]
        # 空串用占位，避免接口拒收
        cleaned = [t if (t or "").strip() else " " for t in batch]
        payload = {"model": c["modelName"], "input": cleaned}
        data = _post_json(url, payload, c["apiKey"])
        items = data.get("data") or []
        items_sorted = sorted(items, key=lambda x: int(x.get("index", 0)))
        if len(items_sorted) != len(cleaned):
            raise RuntimeError(
                f"Embedding 条数不匹配: want={len(cleaned)} got={len(items_sorted)}"
            )
        for it in items_sorted:
            vec = it.get("embedding")
            if not isinstance(vec, list) or not vec:
                raise RuntimeError("Embedding 返回空向量")
            out.append([float(x) for x in vec])
        if on_progress is not None:
            try:
                on_progress(len(out), total)
            except Exception:
                pass
    return out


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na <= 0 or nb <= 0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))
