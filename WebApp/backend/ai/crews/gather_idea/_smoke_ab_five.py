# -*- coding: utf-8 -*-
"""五问联动冒烟：Agent A 证据包 → Agent B 假设束 → md（含交给 C 的样例输入）。"""
from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path

from ai.crews.gather_idea.gather_agent import run_gather
from ai.crews.gather_idea.idea_agent import run_idea

OUT = Path(
    r"E:\quant-lab\SV\SVQuant\WebApp\docs\mvp_agent\AgentAB-五问联动冒烟-2026-08-18.md"
)

TOPICS = [
    "特质波动率（IVOL）在 A 股还有效吗？近三年金工和社区怎么说衰减？",
    "彩票股和 MAX 效应在 A 股还有没有横截面溢价？",
    "短期反转因子在 A 股拥挤后是否衰减？有哪些可检验线索？",
    "换手率与流动性因子近三年还有没有显著溢价？金工怎么讨论？",
    "隔夜收益异象在 A 股还有没有公开复现与衰减讨论？",
]


def _slim_pack(pack: dict) -> dict:
    """交给文档的 A 输出：保留 B 真正吃的字段，截断超长 snippet。"""
    items = []
    for it in pack.get("items") or []:
        if not isinstance(it, dict):
            continue
        items.append(
            {
                "id": it.get("id"),
                "source_type": it.get("source_type"),
                "source_label": it.get("source_label"),
                "title": it.get("title"),
                "url": it.get("url"),
                "published_at": it.get("published_at"),
                "snippet": (str(it.get("snippet") or ""))[:600],
            }
        )
    return {
        "ok": pack.get("ok"),
        "pack_id": pack.get("pack_id"),
        "query": pack.get("query"),
        "digest": pack.get("digest"),
        "digest_bullets": pack.get("digest_bullets"),
        "citations": pack.get("citations"),
        "gaps": pack.get("gaps"),
        "warnings": pack.get("warnings"),
        "stats": pack.get("stats"),
        "items": items,
    }


def _c_input_from_idea(idea: dict, *, pack_id: str, bundle_id: str) -> dict:
    """模拟人点「转成因子草稿」后交给 Agent C 的输入。"""
    return {
        "from_agent": "B",
        "to_agent": "C",
        "pack_id": pack_id,
        "bundle_id": bundle_id,
        "idea_id": idea.get("id"),
        "title": idea.get("title"),
        "thesis": idea.get("thesis"),
        "convertible": idea.get("convertible"),
        "confidence": idea.get("confidence"),
        "citation_ids": idea.get("citation_ids"),
        "factor_prompt": idea.get("factor_prompt"),
        "factor_spec": idea.get("factor_spec"),
        "validity_advice_only": idea.get("validity"),
        "note": "validity 仅为时段分析建议；C/检测页回测窗可由人另设（常近十年）",
    }


def main() -> None:
    rows: list[dict] = []
    for i, topic in enumerate(TOPICS, 1):
        print(f"\n===== [{i}/5] A: {topic} =====", flush=True)
        row: dict = {"topic": topic}
        t0 = time.time()
        try:
            pack = run_gather(
                {
                    "topic": topic,
                    "themes": [],
                    "time_window": {"preset": "3y"},
                    "max_items": 20,
                    "use_llm": True,
                    "sources": {
                        "news": True,
                        "report": True,
                        "paper": True,
                        "post": True,
                    },
                },
                user_id=1,
            )
            a_sec = round(time.time() - t0, 1)
            pack = dict(pack)
            row["a_sec"] = a_sec
            row["pack"] = pack
            st = pack.get("stats") or {}
            print(
                f"A ok {a_sec}s returned={st.get('returned')} "
                f"counts={st.get('source_counts')} digest={st.get('digest_mode')}",
                flush=True,
            )
        except Exception as exc:  # noqa: BLE001
            row["a_error"] = str(exc)
            row["a_sec"] = round(time.time() - t0, 1)
            print(f"A FAIL: {exc}", flush=True)
            rows.append(row)
            continue

        print(f"===== [{i}/5] B =====", flush=True)
        t1 = time.time()
        try:
            bundle = run_idea(
                {
                    "pack": pack,
                    "preference": {"focus": "factor"},
                    "max_ideas": 5,
                },
                user_id=1,
            )
            b_sec = round(time.time() - t1, 1)
            bundle = dict(bundle)
            row["b_sec"] = b_sec
            row["bundle"] = bundle
            bst = bundle.get("stats") or {}
            ideas = bundle.get("ideas") or []
            conv = sum(1 for x in ideas if x.get("convertible"))
            print(
                f"B ok {b_sec}s mode={bst.get('idea_mode')} "
                f"ideas={len(ideas)} convertible={conv}",
                flush=True,
            )
        except Exception as exc:  # noqa: BLE001
            row["b_error"] = str(exc)
            row["b_sec"] = round(time.time() - t1, 1)
            print(f"B FAIL: {exc}", flush=True)
        rows.append(row)

    lines: list[str] = [
        "# Agent A→B · 五问联动冒烟",
        "",
        f"> 日期：{datetime.now().strftime('%Y-%m-%d %H:%M')}（本地）  ",
        "> 链路：每题先 `run_gather`（A）→ 再 `run_idea`（B，focus 写死 factor）。  ",
        "> 参数：时间窗 `3y` · max_items=20 · 四类来源全开 · A/B 均尽量走 LLM。  ",
        "> **confidence（low/mid/high）**：模型对「这条假设有多靠谱」的自评，不是优先级，也不等于可转。  ",
        "> **validity**：仅「哪段可能更好」的分析建议；下游回测可不采用。  ",
        "> A 的 EvidencePack 在文中为**精简版**（snippet≤600）；B 的 IdeaBundle 与「交给 C 的样例」为完整结构。",
        "",
        "## 总览",
        "",
        "| # | 问题 | A耗时(s) | A条数 | A来源 | B耗时(s) | B模式 | 假设数 | 可转 |",
        "|---|------|----------|-------|-------|----------|-------|--------|------|",
    ]
    for i, row in enumerate(rows, 1):
        topic = row["topic"]
        if row.get("a_error"):
            lines.append(
                f"| {i} | {topic} | {row.get('a_sec')} | ERR | — | — | — | — | — |"
            )
            continue
        pack = row["pack"]
        st = pack.get("stats") or {}
        counts = json.dumps(st.get("source_counts") or {}, ensure_ascii=False)
        if row.get("b_error"):
            lines.append(
                f"| {i} | {topic} | {row.get('a_sec')} | {st.get('returned')} | "
                f"`{counts}` | {row.get('b_sec')} | ERR | — | — |"
            )
            continue
        bundle = row["bundle"]
        bst = bundle.get("stats") or {}
        ideas = bundle.get("ideas") or []
        conv = sum(1 for x in ideas if x.get("convertible"))
        lines.append(
            f"| {i} | {topic} | {row.get('a_sec')} | {st.get('returned')} | "
            f"`{counts}` | {row.get('b_sec')} | {bst.get('idea_mode')} | "
            f"{len(ideas)} | {conv} |"
        )
    lines.extend(["", "---", ""])

    for i, row in enumerate(rows, 1):
        topic = row["topic"]
        lines.extend([f"## 问题 {i}", "", f"**问题**：{topic}", ""])
        if row.get("a_error"):
            lines.extend([f"**A 失败**：{row['a_error']}", ""])
            continue

        pack = row["pack"]
        st = pack.get("stats") or {}
        lines.extend(
            [
                "### Agent A · 证据包（B 的输入）",
                "",
                f"- pack_id：`{pack.get('pack_id')}`",
                f"- 耗时：{row.get('a_sec')} s · digest_mode：`{st.get('digest_mode')}`",
                f"- 条数：retrieved={st.get('retrieved')} / returned={st.get('returned')}",
                f"- 来源配比：`{json.dumps(st.get('source_counts') or {}, ensure_ascii=False)}`",
                "",
                "#### Digest",
                "",
                pack.get("digest") or "（空）",
                "",
            ]
        )
        gaps = pack.get("gaps") or []
        if gaps:
            lines.extend(["#### Gaps", ""])
            for g in gaps:
                lines.append(f"- {g}")
            lines.append("")

        slim = _slim_pack(pack)
        lines.extend(
            [
                "#### EvidencePack（精简 JSON，作为 B 输入）",
                "",
                "```json",
                json.dumps(slim, ensure_ascii=False, indent=2),
                "```",
                "",
            ]
        )

        if row.get("b_error"):
            lines.extend([f"**B 失败**：{row['b_error']}", ""])
            continue

        bundle = row["bundle"]
        bst = bundle.get("stats") or {}
        ideas = bundle.get("ideas") or []
        lines.extend(
            [
                "### Agent B · 研究假设束（人审后可转一条给 C）",
                "",
                f"- bundle_id：`{bundle.get('bundle_id')}`",
                f"- 耗时：{row.get('b_sec')} s · idea_mode：`{bst.get('idea_mode')}`",
                f"- tokens：in={bst.get('tokens_in')} / out={bst.get('tokens_out')} · model=`{bst.get('llm_model')}`",
                "",
            ]
        )
        warns = bundle.get("warnings") or []
        if warns:
            lines.extend(["#### Warnings", ""])
            for w in warns:
                lines.append(f"- {w}")
            lines.append("")
        bgaps = bundle.get("gaps") or []
        if bgaps:
            lines.extend(["#### B Gaps", ""])
            for g in bgaps:
                lines.append(f"- {g}")
            lines.append("")

        lines.extend(
            [
                "#### IdeaBundle（完整 JSON）",
                "",
                "```json",
                json.dumps(
                    {
                        "ok": bundle.get("ok"),
                        "bundle_id": bundle.get("bundle_id"),
                        "pack_id": bundle.get("pack_id"),
                        "ideas": ideas,
                        "gaps": bundle.get("gaps"),
                        "warnings": bundle.get("warnings"),
                        "stats": bundle.get("stats"),
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                "```",
                "",
            ]
        )

        pick = next((x for x in ideas if x.get("convertible")), None)
        if pick:
            c_in = _c_input_from_idea(
                pick,
                pack_id=str(bundle.get("pack_id") or pack.get("pack_id")),
                bundle_id=str(bundle.get("bundle_id")),
            )
            lines.extend(
                [
                    "#### 交给 Agent C 的样例输入（首条可转假设）",
                    "",
                    "```json",
                    json.dumps(c_in, ensure_ascii=False, indent=2),
                    "```",
                    "",
                ]
            )
        else:
            lines.extend(["#### 交给 Agent C 的样例输入", "", "本轮无 `convertible=true` 假设。", ""])

        lines.append("---")
        lines.append("")

    lines.extend(
        [
            "## 读卡说明",
            "",
            "| UI 标签 | 含义 |",
            "|---------|------|",
            "| 可转因子草稿 / 暂不转因子 | `convertible`：能否写成日频量价因子交给 C |",
            "| low / mid / high | `confidence`：模型自评证据与逻辑把握，**不是**紧急度 |",
            "| 建议可能更好的时段 | `validity`：分析建议；检测页可另设近十年 |",
            "",
            "*不构成投资建议。*",
            "",
        ]
    )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nWROTE {OUT} bytes={OUT.stat().st_size}", flush=True)


if __name__ == "__main__":
    main()
