# -*- coding: utf-8 -*-
"""资讯数据源清单与授权状态（P1-C07）。

授权结论属于法务/商务决策，本模块只提供**机器可读的清单**与当前状态，
避免代码里散落“能用/不能用”的口头判断。状态：
  confirmed       已有书面授权或公开许可
  review_required 待法务/商务确认（当前默认）
  blocked         明确不可用（无授权/技术不可达）
"""
from __future__ import annotations

from typing import Any

SOURCES: tuple[dict[str, Any], ...] = (
    {
        "id": "cls",
        "label": "财联社",
        "homepage": "https://www.cls.cn/",
        "authorization": "review_required",
        "note": "公开电报页抓取；商用/转载需确认授权",
    },
    {
        "id": "eastmoney",
        "label": "东方财富",
        "homepage": "https://www.eastmoney.com/",
        "authorization": "review_required",
        "note": "公开资讯页；正文转载边界待确认",
    },
    {
        "id": "em_research",
        "label": "东方财富·研报",
        "homepage": "https://data.eastmoney.com/report/",
        "authorization": "review_required",
        "note": "研报版权归原作者/机构；仅摘要与外链",
    },
    {
        "id": "em_policy",
        "label": "东方财富·政策",
        "homepage": "https://data.eastmoney.com/",
        "authorization": "review_required",
        "note": "公开政策栏目",
    },
    {
        "id": "cninfo",
        "label": "巨潮资讯",
        "homepage": "https://www.cninfo.com.cn/",
        "authorization": "review_required",
        "note": "上市公司公告；PDF 原文来自交易所披露",
    },
    {
        "id": "10jqka",
        "label": "同花顺",
        "homepage": "https://www.10jqka.com.cn/",
        "authorization": "review_required",
        "note": "公开摘要页",
    },
    {
        "id": "wallstreetcn",
        "label": "华尔街见闻",
        "homepage": "https://wallstreetcn.com/",
        "authorization": "review_required",
        "note": "公开电报页",
    },
    {
        "id": "bloomberg",
        "label": "彭博社",
        "homepage": "https://www.bloomberg.com/",
        "authorization": "blocked",
        "note": "无授权且大陆网络不可达；一期仅外链官网",
    },
)


def list_sources() -> dict[str, Any]:
    return {
        "ok": True,
        "items": list(SOURCES),
        "counts": {
            status: sum(1 for s in SOURCES if s["authorization"] == status)
            for status in ("confirmed", "review_required", "blocked")
        },
        "note": "review_required 的源在获得授权前仅限内部研究用途；上线前需法务确认",
    }
