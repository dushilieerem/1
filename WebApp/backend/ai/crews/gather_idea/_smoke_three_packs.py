# -*- coding: utf-8 -*-
"""三问新题冒烟：完整证据包 → docs md。"""
from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path

from ai.crews.gather_idea.gather_agent import run_gather

OUT = Path(r"E:\SVQuant_docs\mvp_agent\AgentA-三问证据包冒烟-2026-08-18.md")
TOPICS = [
    "隔夜收益异象在 A 股还有没有金工复现？",
    "质量因子和盈利质量最近有哪些衰减讨论？",
    "订单流和高频微观结构因子有哪些公开线索？",
]


def main() -> None:
    packs: list[dict] = []
    for i, topic in enumerate(TOPICS, 1):
        print(f"\n===== [{i}/3] {topic} =====", flush=True)
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
                f"returned={stats.get('returned')} counts={stats.get('source_counts')} "
                f"digest_mode={stats.get('digest_mode')}",
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
        "# Agent A · 三问证据包冒烟结果",
        "",
        f"> 日期：{datetime.now().strftime('%Y-%m-%d %H:%M')}（本地）  ",
        "> 说明：三个**此前未测过**的宽泛问题各跑一轮 `run_gather`（`3y` / 20 条 / 四类全开 / `use_llm=true`）。  ",
        "> 对应检索口径：无站内库、论文领域过滤、PDF 前几页、必应优先帖子检索。  ",
        "> 下方为 digest + **完整 EvidencePack JSON**。",
        "",
        "## 总览",
        "",
        "| # | 问题 | 耗时(s) | retrieved | returned | digest_mode | source_counts | gaps |",
        "|---|------|---------|-----------|----------|-------------|---------------|------|",
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
                f"| {i} | {topic} | {p.get('_smoke_elapsed_sec')} | ERR | ERR | — | — | {p.get('error')} |"
            )
            continue
        st = p.get("stats") or {}
        gaps = "；".join(p.get("gaps") or []) or "—"
        lines.append(
            f"| {i} | {topic} | {p.get('_smoke_elapsed_sec')} | {st.get('retrieved')} | "
            f"{st.get('returned')} | {st.get('digest_mode')} | "
            f"`{json.dumps(st.get('source_counts') or {}, ensure_ascii=False)}` | {gaps} |"
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
        lines.extend(
            [
                f"**耗时**：{p.get('_smoke_elapsed_sec')} 秒",
                "",
                "### Digest（资料汇总）",
                "",
                p.get("digest") or "（空）",
                "",
            ]
        )
        bullets = p.get("digest_bullets") or []
        if bullets:
            lines.extend(["### Digest bullets（要点）", ""])
            for b in bullets:
                ids = ", ".join(b.get("item_ids") or [])
                lines.append(f"- {b.get('text')}  `{ids}`")
            lines.append("")
        dump = {k: v for k, v in p.items() if k != "_smoke_elapsed_sec"}
        lines.extend(["### 完整 EvidencePack（JSON）", "", "```json"])
        lines.append(json.dumps(dump, ensure_ascii=False, indent=2))
        lines.append("```")
        lines.append("")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nWROTE {OUT} bytes={OUT.stat().st_size}", flush=True)


if __name__ == "__main__":
    main()
