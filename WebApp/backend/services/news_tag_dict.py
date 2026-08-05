# -*- coding: utf-8 -*-
"""资讯主题 / 行业标签字典（C4 草案）：关键词命中 → themes / industries。"""
from __future__ import annotations

from typing import Iterable

# 题材：展示名 → 命中关键词（任一命中即挂标签）
THEME_KEYWORDS: dict[str, tuple[str, ...]] = {
    "CPO": ("CPO", "光模块", "光芯片", "硅光", "共封装光学"),
    "算力": ("算力", "AI算力", "智算", "GPU服务器", "液冷服务器"),
    "AI应用": ("AI应用", "大模型应用", "AIGC", "智能体", "Agent"),
    "CRO": ("CRO", "CXO", "药明", "临床研究"),
    "电子特气": ("电子特气", "特种气体", "高纯气体"),
    "人形机器人": ("人形机器人", "具身智能", "机器狗", "灵巧手"),
    "新能源": ("新能源", "光伏", "储能", "锂电", "动力电池", "宁德时代"),
    "半导体": ("半导体", "芯片", "晶圆", "光刻", "封测", "存储芯片", "HBM"),
    "消费电子": ("消费电子", "智能手机", "果链", "折叠屏"),
    "汽车": ("新能源汽车", "智能驾驶", "车联网", "自动驾驶", "整车"),
    "军工": ("军工", "国防", "航发", "卫星互联网"),
    "医药": ("医药", "创新药", "生物制药", "集采"),
    "金融": ("银行", "券商", "保险", "央行", "降准", "降息"),
    "地产": ("房地产", "楼市", "商品房", "土拍", "房企"),
    "宏观": ("宏观", "GDP", "CPI", "PMI", "美联储", "非农"),
    "海外": ("美股", "港股", "纳斯达克", "标普", "欧洲央行", "中东"),
    "中东冲突": ("中东", "伊朗", "霍尔木兹", "以色列", "加沙"),
    "法定公告": ("法定公告", "披露公告", "异动公告", "回购", "减持", "增持"),
}

# 申万风格粗行业：展示名 → 关键词
INDUSTRY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "电子": ("电子", "半导体", "芯片", "PCB", "消费电子", "光模块", "CPO"),
    "计算机": ("软件", "云计算", "信创", "网络安全", "算力", "AI应用"),
    "通信": ("通信", "5G", "光通信", "运营商", "基站"),
    "医药生物": ("医药", "生物", "疫苗", "CXO", "CRO", "中药"),
    "电力设备": ("光伏", "储能", "风电", "锂电", "新能源车", "充电桩"),
    "汽车": ("汽车", "整车", "零部件", "智能驾驶"),
    "机械设备": ("机械", "机器人", "机床", "工程机械", "人形机器人"),
    "国防军工": ("军工", "航空", "航天", "船舶", "兵器"),
    "银行": ("银行", "信贷", "净息差"),
    "非银金融": ("券商", "保险", "信托", "期货"),
    "房地产": ("房地产", "物业", "房企", "土拍"),
    "建筑装饰": ("基建", "建筑", "装修", "工程承包"),
    "食品饮料": ("白酒", "啤酒", "乳业", "食品", "饮料"),
    "传媒": ("传媒", "游戏", "广告", "影视", "直播"),
    "公用事业": ("电力", "水电", "燃气", "水务"),
    "交通运输": ("航运", "港口", "航空运输", "物流", "高铁"),
    "石油石化": ("原油", "石油", "炼化", "天然气", "布伦特", "WTI"),
    "有色金属": ("铜", "铝", "锂矿", "稀土", "黄金"),
    "钢铁": ("钢铁", "螺纹钢", "铁矿"),
    "煤炭": ("煤炭", "动力煤", "焦煤"),
}


def _uniq(seq: Iterable[str], *, limit: int = 8) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for x in seq:
        s = (x or "").strip()
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
        if len(out) >= limit:
            break
    return out


def match_labels(text: str, table: dict[str, tuple[str, ...]], *, limit: int = 8) -> list[str]:
    """在文本中按关键词表打标签（大小写不敏感的英文，中文原样）。"""
    if not text:
        return []
    blob = text
    blob_lower = text.lower()
    hit: list[str] = []
    for label, keys in table.items():
        for k in keys:
            if not k:
                continue
            if k.isascii():
                if k.lower() in blob_lower:
                    hit.append(label)
                    break
            elif k in blob:
                hit.append(label)
                break
    return _uniq(hit, limit=limit)


def enrich_news_tags(
    *,
    title: str = "",
    summary: str = "",
    body: str = "",
    themes: list[str] | None = None,
    industries: list[str] | None = None,
) -> tuple[list[str], list[str]]:
    """合并源站标签 + 字典命中。"""
    text = f"{title}\n{summary}\n{(body or '')[:2000]}"
    merged_themes = _uniq(
        list(themes or []) + match_labels(text, THEME_KEYWORDS),
        limit=8,
    )
    merged_industries = _uniq(
        list(industries or []) + match_labels(text, INDUSTRY_KEYWORDS),
        limit=6,
    )
    return merged_themes, merged_industries


def dict_snapshot() -> dict[str, list[str]]:
    """给前端 / 文档用的标签清单。"""
    return {
        "themes": list(THEME_KEYWORDS.keys()),
        "industries": list(INDUSTRY_KEYWORDS.keys()),
    }
