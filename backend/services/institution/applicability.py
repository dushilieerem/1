# -*- coding: utf-8 -*-
"""字段适用性：业务上不适用 != 数据缺失。

只放可审计的行业/公司口径，不放临时占位：
- 银行不适用销售客户集中度、量价、成本构成、渠道、对外担保；
- 公司级不适用需写清原因，后续应优先由 doc_extract 的 not_applicable 行覆盖。
"""
from __future__ import annotations

from typing import Any

BANK_NOT_APPLICABLE: dict[str, str] = {
    "top5_customers": "银行不披露销售客户集中度",
    "volume_price_split": "银行无量价/产销口径",
    "cost_structure": "银行无营业成本构成",
    "channel_data": "银行无经销/直销渠道口径",
    "guarantee": "银行对外担保不适用上市公司对外担保口径",
}

COMPANY_NOT_APPLICABLE: dict[str, dict[str, str]] = {
    "600519.SH": {
        "guarantee": "公司无对外担保业务，年报无对外担保章节",
        "cost_structure": "年报仅披露分行业/分产品营业成本，无成本项目构成",
    },
}


def not_applicable_fields(symbol: str, *, is_financial: bool = False) -> dict[str, str]:
    out: dict[str, str] = {}
    if is_financial:
        out.update(BANK_NOT_APPLICABLE)
    out.update(COMPANY_NOT_APPLICABLE.get(symbol, {}))
    return out
