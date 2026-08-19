# -*- coding: utf-8 -*-
"""一次性冒烟：五问完整证据包 → docs md。"""
from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path

from ai.crews.gather_idea.gather_agent import run_gather

OUT = Path(r"E:\quant-lab\SV\SVQuant\WebApp\docs\mvp_agent\AgentA-五问证据包冒烟-2026-08-18.md")
TOPICS = [
    "经典股票异象这几年还有效吗？有没有明显衰减或风格切换？",
    "金工和学术现在还在盯哪些量价或微观结构方向？",
    "低波动异象在 A 股还成立吗？近期有哪些讨论？",
    "换手率与流动性因子有哪些可检验的研究线索？",
    "动量和反转因子在不同市况下怎么用？",
]


def main() -> None:
    packs: list[dict] = []
    for i, topic in enumerate(TOPICS, 1):
        print(f"\n===== [{i}/5] {topic} =====", flush=True)
        t0 = time.time()
        try:
            pack = run_gather(
                {
                    "topic": topic,
                    "themes": [],
                    "time_window": {"preset": "3y"},
                    "max_items": 20,
                    "use_llm": True,
                    "sources": {"news": True, "report": True, "paper": True, "post": True},
                },
                user_id=1,
            )
            elapsed = round(time.time() - t0, 1)
            pack = dict(pack)
            pack["_smoke_elapsed_sec"] = elapsed
            packs.append(pack)
            stats = pack.get("stats") or {}
            print(
                f"ok elapsed={elapsed}s retrieved={stats.get('retrieved')} "
                f"returned={stats.get('returned')} counts={stats.get('source_counts')}",
                flush=True,
            )
            for it in pack.get("items") or []:
                if it.get("source_type") == "paper":
                    print(
                        f"  paper snip_len={len(it.get('snippet') or '')} | {(it.get('title') or '')[:60]}",
                        flush=True,
                    )
        except Exception as exc:  # noqa: BLE001
            print(f"FAIL: {exc}", flush=True)
            packs.append(
                {
                    "topic": topic,
                    "error": str(exc),
                    "_smoke_elapsed_sec": round(time.time() - t0, 1),
                }
            )

    lines: list[str] = [
        "# Agent A · 五问证据包冒烟结果",
        "",
        f"> 日期：{datetime.now().strftime('%Y-%m-%d %H:%M')}（本地）  ",
        "> 说明：对 5 个宽泛问题各跑一轮 `run_gather`（`time_window=3y`，`max_items=20`，四类全开，`use_llm=true`）。  ",
        "> 下方为**完整 EvidencePack**（含 digest / items / citations / gaps / warnings / stats）。  ",
        "> 论文正文：开放获取 PDF / arXiv 会尽量抽前几页；付费墙论文可能仍只有摘要。",
        "",
        "## 总览",
        "",
        "| # | 问题 | 耗时(s) | retrieved | returned | source_counts | gaps |",
        "|---|------|---------|-----------|----------|---------------|------|",
    ]
    for i, p in enumerate(packs, 1):
        topic = (
            (p.get("query") or {}).get("topic")
            if isinstance(p.get("query"), dict)
            else p.get("topic")
        )
        topic = topic or TOPICS[i - 1]
        if p.get("error"):
            lines.append(
                f"| {i} | {topic} | {p.get('_smoke_elapsed_sec')} | ERR | ERR | — | {p.get('error')} |"
            )
            continue
        st = p.get("stats") or {}
        gaps = "；".join(p.get("gaps") or []) or "—"
        lines.append(
            f"| {i} | {topic} | {p.get('_smoke_elapsed_sec')} | {st.get('retrieved')} | "
            f"{st.get('returned')} | `{json.dumps(st.get('source_counts') or {}, ensure_ascii=False)}` | {gaps} |"
        )
    lines.append("")

    for i, p in enumerate(packs, 1):
        topic = (
            (p.get("query") or {}).get("topic")
            if isinstance(p.get("query"), dict)
            else p.get("topic")
        )
        topic = topic or TOPICS[i - 1]
        lines.extend([f"## 问题 {i}", "", f"**问题**：{topic}", ""])
        if p.get("error"):
            lines.extend([f"**失败**：{p.get('error')}", ""])
            continue
        lines.extend([f"**耗时**：{p.get('_smoke_elapsed_sec')} 秒", "", "### Digest", "", p.get("digest") or "（空）", ""])
        bullets = p.get("digest_bullets") or []
        if bullets:
            lines.extend(["### Digest bullets", ""])
            for b in bullets:
                ids = ", ".join(b.get("item_ids") or [])
                lines.append(f"- {b.get('text')}  `{ids}`")
            lines.append("")
        lines.extend(["### 完整 EvidencePack（JSON）", ""])
        dump = {k: v for k, v in p.items() if k != "_smoke_elapsed_sec"}
        lines.append("```json")
        lines.append(json.dumps(dump, ensure_ascii=False, indent=2))
        lines.append("```")
        lines.append("")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nWROTE {OUT} bytes={OUT.stat().st_size}", flush=True)


if __name__ == "__main__":
    main()
