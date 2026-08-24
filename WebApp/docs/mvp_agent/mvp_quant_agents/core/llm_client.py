"""LLM 客户端：OpenAI 兼容接口，支持 mock 模式与 L3 出站闸。

- mock=true：不调用任何外部接口，返回结构化桩（用于零成本验证全链路）。
- mock=false：调用 base_url 指向的国内合规零留存端点。
- 任何出站内容先过 compliance.route；命中 L3 且 enforce 开启则抛错阻断。
"""
from __future__ import annotations
import os
import json
from core.compliance import route

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None


class LLMClient:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.llm_cfg = cfg.get("llm", {})
        self.comp_cfg = cfg.get("compliance", {})
        self.mock = bool(self.llm_cfg.get("mock", True))
        self.client = None
        if not self.mock:
            if OpenAI is None:
                raise RuntimeError("未安装 openai 包：pip install openai")
            key = os.environ.get("QUANT_LLM_API_KEY", self.llm_cfg.get("api_key", ""))
            self.client = OpenAI(base_url=self.llm_cfg["base_url"], api_key=key)

    def chat(self, role: str, stage: str, prompt: str) -> str:
        # 出站前合规闸
        if not self.mock and self.comp_cfg.get("enforce_l3", True):
            r = route(prompt)
            if r["decision"] == "blocked":
                raise PermissionError(
                    f"[L3 拦截] {role}/{stage} 内容含专有 alpha({r['hits']})，"
                    f"禁止出网。改走本地模型或先脱敏。")
        if self.mock:
            return self._mock(role, stage, prompt)
        resp = self.client.chat.completions.create(
            model=self.llm_cfg["model"],
            temperature=float(self.llm_cfg.get("temperature", 0.2)),
            messages=[
                {"role": "system", "content": f"你是量化投研系统中的「{role}」Agent。"},
                {"role": "user", "content": prompt},
            ],
        )
        return resp.choices[0].message.content or ""

    def _mock(self, role: str, stage: str, prompt: str) -> str:
        """结构化桩：返回 JSON 字符串，便于 Agent 解析与演示。"""
        payload = {
            "role": role, "stage": stage,
            "summary": f"[{role}] 在 {stage} 阶段基于上下文完成推理（mock 模式，未花 token）。",
            "confidence": 0.82,
        }
        return json.dumps(payload, ensure_ascii=False)
