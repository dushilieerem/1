# -*- coding: utf-8 -*-
"""H5 提醒：自然语言解析、落库、列表展示与收盘后触发。

边界：
- 只做提醒，不代下单、不给买卖建议；
- 价格类按收盘价检查，不提供盘中实时推送；
- 缺阈值必须追问，不猜测；数据源缺失的类型拒绝创建。

数据来源与字段口径与「自选与提醒」页一致：
invest_stocks（现价/涨跌幅/下次财报日）、md_valuation_daily（PE 分位）、
md_fund_flow_candidate（主力净流入）、md_daily_bar（成交额热度分位）、
fin_dividend（上次除权日）。
"""
from __future__ import annotations

import math
import re
from datetime import date, datetime, timedelta
from typing import Any

from services.invest import rules

TYPE_LABELS = {
    "price": ("价格提醒", "Price reminder"),
    "financial": ("财报提醒", "Earnings reminder"),
    "event": ("事件提醒", "Event reminder"),
    "valuation": ("估值提醒", "Valuation reminder"),
    "flow": ("资金提醒", "Fund-flow reminder"),
    "heat": ("热度提醒", "Heat reminder"),
}
STATUS_LABELS = {
    "active": ("生效中", "Active"),
    "paused": ("已暂停", "Paused"),
    "triggered": ("已触发", "Triggered"),
}
TYPE_ORDER = ["price", "financial", "event", "valuation", "flow", "heat"]

NOTICE = "价格提醒按收盘价判断，盘中不推送。"
COMPLIANCE = "只做提醒，不代下单，也不给买卖建议。"
DISCLAIMER = "收盘后检查 · 不提供盘中实时推送 · 非投资建议"


def _num(value: Any) -> float | None:
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    return n if math.isfinite(n) else None


def _norm(text: str) -> str:
    table = str.maketrans("０１２３４５６７８９．％：，　", "0123456789.%:, ")
    return re.sub(r"\s+", "", str(text or "").translate(table))


def _fmt_num(value: float, digits: int = 2) -> str:
    text = f"{value:,.{digits}f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def _type_label(t: str, en: bool = False) -> str:
    labels = TYPE_LABELS.get(t, TYPE_LABELS["price"])
    return labels[1] if en else labels[0]


def _status_label(status: str, en: bool = False) -> str:
    labels = STATUS_LABELS.get(status, STATUS_LABELS["active"])
    return labels[1] if en else labels[0]


def _signed(value: float, digits: int = 1) -> str:
    text = f"{value:+.{digits}f}"
    if text.startswith("-0.") and float(text) == 0:
        return text[1:]
    return text


# ---------------------------------------------------------------- 数据可用性
def type_availability(conn: Any) -> dict[str, dict[str, Any]]:
    """六类提醒的数据源可用性；缺失的类型前端置灰。"""
    probes = {
        "price": "SELECT 1 FROM invest_stocks WHERE price IS NOT NULL LIMIT 1",
        "financial": "SELECT 1 FROM invest_stocks WHERE next_report_date IS NOT NULL LIMIT 1",
        "event": "SELECT 1 FROM fin_dividend LIMIT 1",
        "valuation": "SELECT 1 FROM md_valuation_daily WHERE pe_ttm IS NOT NULL LIMIT 1",
        "flow": "SELECT 1 FROM md_fund_flow_daily LIMIT 1",
        "heat": "SELECT 1 FROM md_daily_bar LIMIT 1",
    }
    out: dict[str, dict[str, Any]] = {}
    for key in TYPE_ORDER:
        ok = False
        try:
            ok = conn.execute(probes[key]).fetchone() is not None
        except Exception:
            ok = False
        out[key] = {
            "label": _type_label(key),
            "label_en": _type_label(key, True),
            "available": ok,
            "note": "" if ok else "数据待接入",
        }
    return out


def _market_clause(market: str = "CN") -> str:
    return "market='US'" if rules.normalize_market(market) == "US" else "COALESCE(market,'CN')='CN'"


# ---------------------------------------------------------------- 解析
_TYPE_PATTERNS = [
    ("valuation", r"(?:PE|PB|估值).{0,8}分位|分位"),
    ("financial", r"财报|业绩|季报|中报|年报|一季报|三季报|披露"),
    ("event", r"公告|分红|除权|除息|解禁|停牌|复牌|股东大会"),
    ("flow", r"主力|北向|资金|净流入|净流出"),
    ("heat", r"热度|舆情|负面|情绪|新闻"),
]


def _detect_type(text: str) -> str:
    for key, pattern in _TYPE_PATTERNS:
        if re.search(pattern, text, re.I):
            return key
    return "price"


def _detect_condition(text: str, kind: str) -> str:
    if kind == "price":
        if re.search(r"跌停", text):
            return "limit_down"
        if re.search(r"涨停", text):
            return "limit_up"
        # “跌 5%” / “涨幅 ≥ 5%” 是涨跌幅条件，不是价格。
        if re.search(r"(跌幅|跌)[^0-9]{0,6}\d+(?:\.\d+)?\s*%", text):
            return "lte"
        if re.search(r"(涨幅|涨)[^0-9]{0,6}\d+(?:\.\d+)?\s*%", text):
            return "gte"
        if re.search(r"跌破|跌到|跌穿|下破|低于|小于|不超过", text):
            return "below"
        if re.search(r"涨破|突破|涨到|高于|大于|超过|站上", text):
            return "above"
        return "above"
    if kind == "valuation":
        return "lte" if re.search(r"低于|以下|跌到|跌破|小于|不超过|≤", text) else "gte"
    if kind == "flow":
        if re.search(r"连续\s*\d+\s*天", text):
            return "consecutive_outflow" if re.search(r"净流出|流出", text) else "consecutive_inflow"
        return "lte" if re.search(r"净流出|流出|低于|小于|不超过|≤", text) else "gte"
    if kind == "heat":
        return "lte" if re.search(r"低于|小于|不超过|≤", text) else "gte"
    if kind == "financial":
        return "on_date"
    return "announcement"


def _event_kind(text: str) -> str:
    if re.search(r"分红|除权|除息", text):
        return "dividend"
    if re.search(r"解禁", text):
        return "unlock"
    if re.search(r"停牌|复牌", text):
        return "suspend"
    return "announcement"


def _threshold(text: str, kind: str, condition: str) -> tuple[float | None, str]:
    """返回 (阈值, 单位)。缺阈值返回 None，交由调用方追问。"""
    clean = re.sub(r"(?<!\d)\d{6}(?!\d)", " ", text)  # 先去掉 6 位代码
    if condition in {"limit_down", "limit_up"}:
        return None, ""
    if kind == "price" and condition in {"gte", "lte"}:
        m = re.search(r"(\d+(?:\.\d+)?)\s*%", clean)
        return (float(m.group(1)), "%") if m else (None, "%")
    if kind in {"valuation", "heat"}:
        m = re.search(r"(\d+(?:\.\d+)?)\s*(?:%|分位)", clean) or re.search(r"(\d+(?:\.\d+)?)", clean)
        return (float(m.group(1)), "分位") if m else (None, "分位")
    if kind == "flow":
        if condition in {"consecutive_outflow", "consecutive_inflow"}:
            m = re.search(r"连续\s*(\d+)\s*天", clean)
            return (float(m.group(1)), "天") if m else (None, "天")
        m = re.search(r"(\d+(?:\.\d+)?)\s*(亿|万)?", clean)
        if not m:
            return None, "万"
        value = float(m.group(1))
        if m.group(2) == "亿":
            value *= 10000
        if re.search(r"净流出|流出", text) or condition == "lte":
            value = -abs(value)
        else:
            value = abs(value)
        return value, "万"
    if kind == "financial":
        m = re.search(r"(?:提前|前)\s*(\d+)\s*天", clean)
        return (float(m.group(1)), "天") if m else (0.0, "天")
    if kind == "event":
        return None, ""
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:元|块)", clean) or re.search(r"(\d+(?:\.\d+)?)", clean)
    return (float(m.group(1)), "元") if m else (None, "元")


def _end_date(text: str) -> str | None:
    today = date.today()
    m = re.search(r"(20\d{2})-(\d{1,2})-(\d{1,2})", text)
    if m:
        return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    m = re.search(r"(\d{1,2})月(\d{1,2})日", text)
    if m:
        return f"{today.year:04d}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"
    if re.search(r"年底|年内", text):
        return f"{today.year:04d}-12-31"
    m = re.search(r"(\d+)\s*个月内", text)
    if m:
        return (today + timedelta(days=30 * int(m.group(1)))).isoformat()
    return None


def _note(kind: str, condition: str, threshold: float | None, unit: str, text: str) -> str:
    if threshold is None and kind in {"price", "valuation", "flow", "heat"} and condition not in {"limit_up", "limit_down"}:
        return "待补一个具体数值"
    if kind == "price":
        if condition == "limit_down":
            return "跌停时提醒"
        if condition == "limit_up":
            return "涨停时提醒"
        if unit == "%":
            return f"{'涨' if condition == 'gte' else '跌'} {_fmt_num(threshold or 0)}% 时提醒"
        return f"{'跌破' if condition == 'below' else '涨破'} {_fmt_num(threshold or 0)} 元时提醒"
    if kind == "valuation":
        return f"PE 分位 {'≤' if condition == 'lte' else '≥'} {_fmt_num(threshold or 0)}% 时提醒"
    if kind == "flow":
        if condition in {"consecutive_outflow", "consecutive_inflow"}:
            action = "净流出" if condition == "consecutive_outflow" else "净流入"
            return f"主力连续 {int(threshold or 0)} 天{action}时提醒"
        return f"主力净流入 {'≤' if condition == 'lte' else '≥'} {_fmt_num(threshold or 0)} 万时提醒"
    if kind == "heat":
        return f"热度 {'≤' if condition == 'lte' else '≥'} {_fmt_num(threshold or 0)} 分位时提醒"
    if kind == "financial":
        days = int(threshold or 0)
        return f"财报披露前 {days} 天提醒" if days else "财报披露日提醒"
    if condition == "dividend":
        return "除权除息时提醒"
    if condition == "unlock":
        return "解禁时提醒"
    if condition == "suspend":
        return "停复牌时提醒"
    return "有公告时提醒"


def _term(end_date: str | None) -> str:
    return f"至 {end_date}" if end_date else "长期有效"


def _symbols_in_text(conn: Any, text: str) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    for m in re.finditer(r"(?<!\d)(\d{6})(?!\d)", text):
        try:
            stock = rules.one(conn, "SELECT code, name FROM stocks WHERE code=?", (m.group(1),))
        except Exception:
            stock = None
        if stock:
            hits.append({"code": stock["code"], "name": stock.get("name") or stock["code"],
                         "start": m.start(), "end": m.end()})
    candidates: list[dict[str, Any]] = []
    try:
        candidates = rules.rows(
            conn,
            "SELECT code, name FROM stocks WHERE asset='stock' "
            "AND COALESCE(name,'')<>'' AND char_length(name)>=2 AND position(name in ?) > 0 "
            "ORDER BY char_length(name) DESC",
            (text,),
        )
    except Exception:
        candidates = []
    for row in candidates:
        name = str(row.get("name") or "")
        idx = text.find(name)
        if idx < 0:
            continue
        start, end = idx, idx + len(name)
        if any(not (end <= h["start"] or start >= h["end"]) for h in hits):
            continue
        hits.append({"code": row["code"], "name": name, "start": start, "end": end})
    hits.sort(key=lambda x: x["start"])
    # 同一标的只说了一次：按出现顺序去重。
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for hit in hits:
        if hit["code"] in seen:
            continue
        seen.add(hit["code"])
        out.append(hit)
    return out


def _build_reminder(code: str, name: str, seg: str) -> dict[str, Any]:
    kind = _detect_type(seg)
    condition = _detect_condition(seg, kind)
    if kind == "event" and condition == "announcement":
        condition = _event_kind(seg)
    threshold, unit = _threshold(seg, kind, condition)
    end_date = _end_date(seg)
    return {
        "symbol": code,
        "name": name,
        "type": kind,
        "type_label": _type_label(kind),
        "condition": condition,
        "threshold": threshold,
        "unit": unit,
        "note": _note(kind, condition, threshold, unit, seg),
        "end_date": end_date,
        "window": "until_date" if end_date else "long_term",
        "term": _term(end_date),
        "source": "ai",
    }


def _duplicate(conn: Any, user_id: int, rem: dict[str, Any]) -> bool:
    threshold = rem.get("threshold")
    try:
        row = rules.one(
            conn,
            "SELECT 1 FROM invest_event WHERE user_id=? AND code=? AND type=? "
            "AND condition_op=? AND COALESCE(threshold, -999999)=COALESCE(?, -999999) "
            "AND status IN ('active','paused') LIMIT 1",
            (user_id, rem["symbol"], rem["type"], rem["condition"], threshold),
        )
        return bool(row)
    except Exception:
        return False


def _confirm_text(reminders: list[dict[str, Any]], duplicates: set[int] | None = None) -> str:
    duplicates = duplicates or set()
    if len(reminders) == 1:
        rem = reminders[0]
        text = f"帮你盯着 {rem['name']}（{rem['symbol']}）\n{rem['note']} · {rem['term']}"
        return text + ("\n这条已经有了，不会重复创建。" if 0 in duplicates else "")
    lines = [f"帮你盯着这 {len(reminders)} 只："]
    for i, rem in enumerate(reminders, 1):
        suffix = "（已有）" if (i - 1) in duplicates else ""
        lines.append(f"{i}. {rem['name']}（{rem['symbol']}）{rem['note']}{suffix}")
    return "\n".join(lines)


def _suggestions(conn: Any, rem: dict[str, Any]) -> list[dict[str, Any]]:
    kind = rem["type"]
    price = None
    try:
        stock = rules.one(conn, "SELECT price FROM stocks WHERE code=?", (rem["symbol"],))
        price = _num((stock or {}).get("price"))
    except Exception:
        price = None
    if kind == "price":
        if price:
            return [
                {"label": f"跌破 {_fmt_num(price * 0.95)} 元", "text": f"跌破 {_fmt_num(price * 0.95)} 元"},
                {"label": "跌 5%", "text": "跌 5%"},
            ]
        return [{"label": "跌 5%", "text": "跌 5%"}, {"label": "涨 5%", "text": "涨 5%"}]
    if kind == "valuation":
        return [{"label": "PE 分位 ≤ 20%", "text": "PE 分位低于 20%"}, {"label": "PE 分位 ≤ 30%", "text": "PE 分位低于 30%"}]
    if kind == "flow":
        return [{"label": "净流出 5000 万", "text": "主力净流出 5000 万"}, {"label": "净流入 5000 万", "text": "主力净流入 5000 万"}]
    if kind == "heat":
        return [{"label": "热度 ≥ 90 分位", "text": "热度进 90 分位"}, {"label": "热度 ≥ 80 分位", "text": "热度进 80 分位"}]
    return []


def _has_buy_request(text: str) -> bool:
    return bool(re.search(r"帮我(?:买入|买|卖出|卖|下单|加仓|减仓)|代我下单", text))


def parse_query(
    conn: Any,
    query: str,
    current: dict[str, Any] | None = None,
    user_id: int | None = None,
) -> dict[str, Any]:
    """把一句话解析成提醒回显；缺字段返回 needs_input，绝不猜阈值。"""
    raw = str(query or "").strip()
    text = _norm(raw)
    availability = type_availability(conn)
    result: dict[str, Any] = {
        "ok": True,
        "action": "create_reminder",
        "query": raw,
        "reminders": [],
        "missing": [],
        "duplicates": [],
        "notice": NOTICE,
        "compliance": COMPLIANCE if _has_buy_request(text) else None,
        "type_availability": availability,
        "disclaimer": DISCLAIMER,
    }
    if not text:
        return {**result, "status": "needs_input", "missing": ["symbol"], "question": "要盯哪只？"}

    hits = _symbols_in_text(conn, text)
    if not hits and current and current.get("code"):
        hits = [{"code": str(current["code"]), "name": str(current.get("name") or current["code"]),
                 "start": -1, "end": -1, "from_memory": True}]
    if not hits:
        return {
            **result,
            "status": "needs_input",
            "missing": ["symbol"],
            "question": "要盯哪只？可以告诉我名称或代码。",
        }

    # 多标的：若每段都带数字，按段解析各自条件；否则共用同一条件。
    segment_map: list[tuple[dict[str, Any], str]] = []
    if len(hits) > 1:
        segmented = []
        for i, hit in enumerate(hits):
            start = 0 if i == 0 and hit["start"] >= 0 else max(0, hit["start"])
            end = hits[i + 1]["start"] if i + 1 < len(hits) and hits[i + 1]["start"] >= 0 else len(text)
            seg = text[start:end] if hit["start"] >= 0 else ""
            segmented.append((hit, seg))
        if all(re.search(r"\d", seg) for _, seg in segmented):
            segment_map = segmented
    if not segment_map:
        segment_map = [(hit, text) for hit in hits]

    reminders = [_build_reminder(hit["code"], hit["name"], seg) for hit, seg in segment_map]

    # “有大事”这类模糊条件：按文档建成公告 + 舆情组合。
    if len(reminders) == 1 and re.search(r"有大事|重大事件|发生什么|有事|重要消息", text):
        base = reminders[0]
        reminders = [
            {**base, "type": "event", "type_label": _type_label("event"), "condition": "announcement",
             "note": "有公告时提醒", "threshold": None, "unit": ""},
            {**base, "type": "heat", "type_label": _type_label("heat"), "condition": "gte",
             "threshold": 80.0, "unit": "分位", "note": "热度 ≥ 80 分位时提醒"},
        ]
        result["scope_note"] = "“有大事”按公告 + 热度组合提醒，之后可单独删改。"

    missing: list[str] = []
    suggestions: list[dict[str, Any]] = []
    duplicates: set[int] = set()
    warnings: list[str] = []
    for i, rem in enumerate(reminders):
        if user_id is not None and _duplicate(conn, int(user_id), rem):
            duplicates.add(i)
        kind = rem["type"]
        need_threshold = kind in {"price", "valuation", "flow", "heat"} and rem["condition"] not in {"limit_up", "limit_down"}
        if need_threshold and rem.get("threshold") is None:
            if "threshold" not in missing:
                missing.append("threshold")
            for item in _suggestions(conn, rem):
                suggestions.append({**item, "index": i})
        threshold = rem.get("threshold")
        if threshold is not None:
            if kind == "price" and rem["unit"] == "元" and threshold <= 0:
                warnings.append(f"{rem['name']} 的价格阈值不合理，请确认。")
            if kind == "price" and rem["unit"] == "%" and abs(threshold) > 100:
                warnings.append(f"{rem['name']} 的涨跌幅 {threshold:g}% 不合理，请确认。")
            if kind in {"valuation", "heat"} and not (0 <= threshold <= 100):
                warnings.append(f"{rem['name']} 的分位阈值应在 0–100% 之间，请确认。")
        if not availability.get(kind, {}).get("available", True):
            warnings.append(f"{_type_label(kind)}的数据源待接入，暂不能创建。")

    if missing:
        first = reminders[0]
        question = f"想提醒你的时候更准，补一个数：{first['name']}跌到多少提醒？比如 {(_suggestions(conn, first) or [{'label': '220 元'}])[0]['label']}。"
        return {
            **result,
            "status": "needs_input",
            "reminders": reminders,
            "missing": missing,
            "suggestions": suggestions,
            "duplicates": sorted(duplicates),
            "question": question,
            "warnings": warnings,
        }

    result.update({
        "status": "blocked" if any(not availability.get(r["type"], {}).get("available", True) for r in reminders) else "ready",
        "reminders": reminders,
        "duplicates": sorted(duplicates),
        "duplicate_note": "这条已经有了，不会重复创建。" if duplicates else "",
        "confirm_text": _confirm_text(reminders, duplicates),
        "warnings": warnings,
    })
    if any(not availability.get(r["type"], {}).get("available", True) for r in reminders):
        result["question"] = "该类提醒的数据源待接入，暂不能创建。"
    return result


# ---------------------------------------------------------------- 当前值
class _Current:
    def __init__(self, conn: Any):
        self.conn = conn
        self._stocks: dict[str, dict[str, Any] | None] = {}
        self._pe: dict[str, float | None] = {}
        self._flow: dict[str, float | None] = {}
        self._heat: dict[str, float | None] = {}
        self._div: dict[str, str | None] = {}
        self._amount_ratio: dict[str, float | None] = {}
        self._bar_cache: dict[tuple[str, int], list[dict[str, Any]]] = {}

    def stock(self, code: str) -> dict[str, Any] | None:
        if code not in self._stocks:
            try:
                self._stocks[code] = rules.one(self.conn, "SELECT * FROM stocks WHERE code=?", (code,))
            except Exception:
                self._stocks[code] = None
        return self._stocks[code]

    def pe_percentile(self, code: str) -> float | None:
        if code in self._pe:
            return self._pe[code]
        stock = self.stock(code) or {}
        pe = _num(stock.get("pe_ttm"))
        value = None
        if pe is not None:
            try:
                vals = rules.rows(
                    self.conn,
                    "SELECT pe_ttm FROM (SELECT pe_ttm FROM md_valuation_daily "
                    "WHERE symbol=? ORDER BY trade_date DESC LIMIT 750) t",
                    (rules._with_suffix(code),),
                )
                clean = [_num(v.get("pe_ttm")) for v in vals]
                clean = [v for v in clean if v is not None]
                if clean:
                    value = rules.percentile(clean, pe)
            except Exception:
                value = None
        self._pe[code] = value
        return value

    def flow(self, code: str) -> float | None:
        if code in self._flow:
            return self._flow[code]
        value = None
        try:
            row = rules.one(
                self.conn,
                "SELECT main_net_inflow FROM md_fund_flow_daily WHERE symbol=? "
                "ORDER BY trade_date DESC LIMIT 1",
                (rules._with_suffix(code),),
            )
            amount = _num((row or {}).get("main_net_inflow"))
            value = amount / 1e4 if amount is not None else None
        except Exception:
            value = None
        self._flow[code] = value
        return value

    def flow_streak(self, code: str) -> tuple[int, int]:
        """返回 (连续净流入天数, 连续净流出天数)。"""
        try:
            rows = rules.rows(
                self.conn,
                "SELECT main_net_inflow FROM md_fund_flow_daily WHERE symbol=? "
                "ORDER BY trade_date DESC LIMIT 20",
                (rules._with_suffix(code),),
            )
        except Exception:
            return 0, 0
        inflow = outflow = 0
        for row in rows:
            amount = _num(row.get("main_net_inflow"))
            if amount is None:
                break
            if amount > 0 and outflow == 0:
                inflow += 1
            elif amount < 0 and inflow == 0:
                outflow += 1
            else:
                break
        return inflow, outflow

    def _bars(self, code: str, limit: int = 250) -> list[dict[str, Any]]:
        key = (code, limit)
        if key not in self._bar_cache:
            try:
                self._bar_cache[key] = rules.stock_bars(self.conn, code, limit=limit)
            except Exception:
                self._bar_cache[key] = []
        return self._bar_cache[key]

    def heat(self, code: str) -> float | None:
        if code in self._heat:
            return self._heat[code]
        value = None
        bars = self._bars(code)
        amounts = [_num(b.get("amount")) for b in bars]
        clean = [a for a in amounts if a is not None]
        if clean:
            value = rules.percentile(clean[:-1], clean[-1]) if len(clean) > 1 else None
        self._heat[code] = value
        return value

    def amount_ratio(self, code: str) -> float | None:
        if code in self._amount_ratio:
            return self._amount_ratio[code]
        bars = self._bars(code, limit=5)
        ratio = None
        if len(bars) >= 2:
            last = _num(bars[-1].get("amount"))
            prev = _num(bars[-2].get("amount"))
            if last and prev:
                ratio = last / prev - 1
        self._amount_ratio[code] = ratio
        return ratio

    def dividend_date(self, code: str) -> str | None:
        if code in self._div:
            return self._div[code]
        value = None
        try:
            row = rules.one(
                self.conn,
                "SELECT ex_date::text AS ex_date FROM fin_dividend WHERE symbol=? ORDER BY ex_date DESC LIMIT 1",
                (rules._with_suffix(code),),
            )
            value = str((row or {}).get("ex_date") or "")[:10] or None
        except Exception:
            value = None
        self._div[code] = value
        return value


def _current_info(ctx: _Current, rem: dict[str, Any]) -> dict[str, Any]:
    code = str(rem.get("code") or rem.get("symbol") or "")
    kind = str(rem.get("type") or "price")
    condition = str(rem.get("condition_op") or rem.get("condition") or "")
    stock = ctx.stock(code) or {}
    price = _num(stock.get("price"))
    prev = _num(stock.get("prev_close"))
    change = (price / prev - 1) * 100 if price and prev else None
    info: dict[str, Any] = {"value": None, "display": "", "extra": "", "change": change}
    if kind == "price":
        if condition in {"gte", "lte"}:
            info.update({"value": change, "display": f"{_signed(change)}%" if change is not None else ""})
        elif condition in {"limit_up", "limit_down"}:
            info.update({"value": change, "display": f"{_signed(change)}%" if change is not None else ""})
        else:
            info.update({"value": price, "display": f"{_fmt_num(price)} 元" if price is not None else ""})
            if price is not None and change is not None:
                info["extra"] = f"今日 {_signed(change)}%"
    elif kind == "valuation":
        pct = ctx.pe_percentile(code)
        pe = _num(stock.get("pe_ttm"))
        info.update({
            "value": pct,
            "display": f"{_fmt_num(pct, 1)}%" if pct is not None else "",
            "extra": f"PE {_fmt_num(pe)}" if pe is not None else "",
        })
    elif kind == "flow":
        if condition in {"consecutive_outflow", "consecutive_inflow"}:
            inflow, outflow = ctx.flow_streak(code)
            days = outflow if condition == "consecutive_outflow" else inflow
            action = "净流出" if condition == "consecutive_outflow" else "净流入"
            info.update({"value": float(days), "display": f"连续 {days} 天{action}" if days else ""})
        else:
            flow = ctx.flow(code)
            info.update({"value": flow, "display": f"{_fmt_num(flow)} 万" if flow is not None else ""})
    elif kind == "heat":
        heat = ctx.heat(code)
        info.update({"value": heat, "display": f"{_fmt_num(heat, 0)}%" if heat is not None else ""})
    elif kind == "financial":
        next_date = str(stock.get("next_report_date") or "")[:10]
        info.update({
            "value": None,
            "display": f"预计 {next_date[5:]}" if next_date else "",
            "extra": next_date,
        })
    elif kind == "event":
        ex_date = ctx.dividend_date(code)
        info.update({"value": None, "display": f"上次 {ex_date[5:]}" if ex_date else "", "extra": ex_date})
    return info


def _condition_phrase(rem: dict[str, Any]) -> str:
    kind = str(rem.get("type") or "price")
    condition = str(rem.get("condition_op") or rem.get("condition") or "")
    threshold = _num(rem.get("threshold"))
    if kind == "price":
        if condition == "limit_down":
            return "跌停"
        if condition == "limit_up":
            return "涨停"
        if rem.get("unit") == "%":
            return f"{'涨' if condition == 'gte' else '跌'} {_fmt_num(threshold or 0)}%"
        return f"{'跌破' if condition == 'below' else '涨破'} {_fmt_num(threshold or 0)} 元"
    if kind == "valuation":
        return f"PE 分位 {'≤' if condition == 'lte' else '≥'}{_fmt_num(threshold or 0)}%"
    if kind == "flow":
        if condition in {"consecutive_outflow", "consecutive_inflow"}:
            action = "净流出" if condition == "consecutive_outflow" else "净流入"
            return f"主力连续 {int(threshold or 0)} 天{action}"
        return f"主力净流入 {'≤' if condition == 'lte' else '≥'}{_fmt_num(threshold or 0)} 万"
    if kind == "heat":
        return f"热度 {'≤' if condition == 'lte' else '≥'}{_fmt_num(threshold or 0)} 分位"
    if kind == "financial":
        days = int(threshold or 0)
        return f"财报披露前 {days} 天" if days else "财报披露日"
    if condition == "dividend":
        return "分红除权"
    if condition == "unlock":
        return "解禁"
    if condition == "suspend":
        return "停复牌"
    return "公告"


def _distance(rem: dict[str, Any], current: float | None) -> float | None:
    threshold = _num(rem.get("threshold"))
    if current is None or not threshold:
        return None
    return (current - threshold) / threshold * 100


def detail_text(rem: dict[str, Any], info: dict[str, Any], en: bool = False) -> str:
    phrase = _condition_phrase(rem)
    current = info.get("value")
    if en:
        return f"{phrase} · current {info.get('display') or '—'}"
    parts = [phrase]
    if info.get("display"):
        parts.append(f"现价 {info['display']}" if rem.get("type") == "price" and rem.get("unit") != "%" else f"当前 {info['display']}")
    elif rem.get("type") == "financial" and info.get("display"):
        parts.append(info["display"])
    if rem.get("type") == "price" and rem.get("unit") != "%" and current is not None:
        dist = _distance(rem, current)
        if dist is not None:
            parts.append(f"距触发 {_signed(dist)}%")
    if info.get("extra") and rem.get("type") == "price" and rem.get("unit") != "%":
        parts.append(info["extra"])
    return " · ".join(parts)


def serialize(conn: Any, event: dict[str, Any], ctx: _Current, watch_codes: set[str], en: bool = False) -> dict[str, Any]:
    code = str(event.get("code") or "")
    kind = str(event.get("type") or "价格")
    type_key = _type_key(kind)
    rem = {
        **event,
        "type": type_key,
        "condition_op": event.get("condition_op") or _legacy_condition(type_key),
        "threshold": _num(event.get("threshold")),
    }
    info = _current_info(ctx, rem)
    name = str(event.get("name") or code)
    legacy = not event.get("condition_op") and event.get("threshold") is None and bool(event.get("note"))
    detail = str(event.get("note") or "")
    if legacy and info.get("display"):
        detail = f"{detail} · 当前 {info['display']}"
    return {
        "id": event.get("id"),
        "code": code,
        "name": name,
        "type": type_key,
        "type_label": _type_label(type_key, en),
        "condition": rem["condition_op"],
        "threshold": rem["threshold"],
        "unit": event.get("unit") or "",
        "note": event.get("note") or _condition_phrase(rem),
        "end_date": event.get("end_date"),
        "term": _term(event.get("end_date")),
        "status": event.get("status") or "active",
        "status_label": _status_label(str(event.get("status") or "active"), en),
        "source": event.get("source") or "manual",
        "source_label": "AI 创建" if (event.get("source") or "manual") == "ai" else "",
        "created_at": event.get("created_at"),
        "updated_at": event.get("updated_at"),
        "current_value": info.get("value"),
        "current_display": info.get("display"),
        "legacy": legacy,
        "detail": detail if legacy else detail_text(rem, info, en),
        "watchlisted": code in watch_codes,
        "title": f"{name} · {_type_label(type_key, en)}",
    }


def _type_key(label: str) -> str:
    mapping = {
        "价格": "price", "价格提醒": "price", "price": "price",
        "财报": "financial", "财报提醒": "financial", "financial": "financial",
        "公告": "event", "事件": "event", "事件提醒": "event", "event": "event",
        "估值": "valuation", "估值分位": "valuation", "估值提醒": "valuation", "valuation": "valuation",
        "资金": "flow", "资金提醒": "flow", "flow": "flow",
        "热度": "heat", "舆情异常": "heat", "热度提醒": "heat", "heat": "heat",
    }
    return mapping.get(str(label or ""), "price")


def _legacy_condition(kind: str) -> str:
    return {"financial": "on_date", "event": "announcement"}.get(kind, "above")


# ---------------------------------------------------------------- 列表 / 创建 / 管理
def _watch_codes(conn: Any, user_id: int) -> set[str]:
    try:
        return {str(r["code"]) for r in rules.rows(conn, "SELECT code FROM watchlist WHERE user_id=?", (user_id,))}
    except Exception:
        return set()


def _name_map(conn: Any, codes: list[str]) -> dict[str, str]:
    if not codes:
        return {}
    out: dict[str, str] = {}
    try:
        for row in rules.rows(
            conn,
            "SELECT code, name FROM stocks WHERE code = ANY(?)",
            (codes,),
        ):
            out[str(row["code"])] = str(row.get("name") or row["code"])
    except Exception:
        pass
    return out


def list_reminders(conn: Any, user_id: int, market: str = "CN", en: bool = False) -> list[dict[str, Any]]:
    try:
        events = rules.rows(
            conn,
            "SELECT * FROM invest_event WHERE user_id=? ORDER BY created_at DESC, id DESC LIMIT 200",
            (user_id,),
        )
    except Exception:
        return []
    names = _name_map(conn, [str(e.get("code")) for e in events])
    watch_codes = _watch_codes(conn, user_id)
    ctx = _Current(conn)
    out: list[dict[str, Any]] = []
    for event in events:
        event["name"] = names.get(str(event.get("code"))) or event.get("code")
        out.append(serialize(conn, event, ctx, watch_codes, en))
    # 同一标的聚在一起，组内按创建时间倒序；组间按最新一条排序。
    groups: dict[str, list[dict[str, Any]]] = {}
    order: list[str] = []
    for item in out:
        code = str(item["code"])
        if code not in groups:
            groups[code] = []
            order.append(code)
        groups[code].append(item)
    return [item for code in order for item in groups[code]]


def reminder_summary(conn: Any, user_id: int, market: str = "CN") -> dict[str, Any]:
    items = list_reminders(conn, user_id, market)
    return {
        "items": items,
        "count": len(items),
        "active": sum(1 for x in items if x["status"] == "active"),
    }


def create_reminders(
    conn: Any,
    user_id: int,
    reminders: list[dict[str, Any]],
    *,
    add_watchlist: list[str] | None = None,
    source: str = "ai",
) -> dict[str, Any]:
    created: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    errors: list[str] = []
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for raw in reminders or []:
        if not isinstance(raw, dict):
            continue
        code = str(raw.get("symbol") or raw.get("code") or "").strip()
        name = str(raw.get("name") or "").strip()
        if not code and name:
            try:
                stock = rules.one(conn, "SELECT code, name FROM stocks WHERE name=? LIMIT 1", (name,))
            except Exception:
                stock = None
            if stock:
                code, name = str(stock["code"]), str(stock.get("name") or name)
        if not code:
            errors.append("缺少标的")
            continue
        try:
            stock = rules.one(conn, "SELECT code, name FROM stocks WHERE code=?", (code,))
        except Exception:
            stock = None
        if not stock:
            errors.append(f"未收录标的：{name or code}")
            continue
        name = name or str(stock.get("name") or code)
        kind = str(raw.get("type") or "price")
        if kind not in TYPE_LABELS:
            kind = _type_key(kind)
        condition = str(raw.get("condition") or _legacy_condition(kind))
        threshold = _num(raw.get("threshold"))
        if kind in {"price", "valuation", "flow", "heat"} and condition not in {"limit_up", "limit_down"} and threshold is None:
            errors.append(f"{name} 缺少阈值")
            continue
        rem = {
            "symbol": code, "name": name, "type": kind, "condition": condition,
            "threshold": threshold, "unit": str(raw.get("unit") or ""),
        }
        if _duplicate(conn, user_id, rem):
            skipped.append({**rem, "reason": "这条已经有了"})
            continue
        note = str(raw.get("note") or "").strip() or _note(kind, condition, threshold, rem["unit"], "")
        end_date = str(raw.get("end_date") or "").strip() or None
        cur = conn.execute(
            "INSERT INTO invest_event (user_id, code, type, condition, status, created_at, "
            "condition_op, threshold, unit, note, end_date, source, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?) RETURNING id",
            (user_id, code, _type_label(kind).replace("提醒", ""), note, "active", now,
             condition, threshold, rem["unit"], note, end_date, source, now),
        )
        row = cur.fetchone()
        rem_id = row["id"] if row else None
        created.append({
            **rem, "id": rem_id, "note": note, "end_date": end_date,
            "term": _term(end_date), "source": source, "status": "active",
            "type_label": _type_label(kind),
        })

    added_watch = 0
    for code in add_watchlist or []:
        try:
            cur = conn.execute(
                "INSERT INTO invest_watchlist (user_id, code, group_name, created_at) VALUES (?,?,?,?) "
                "ON CONFLICT (user_id, code) DO NOTHING",
                (user_id, str(code), "默认", now),
            )
            added_watch += max(0, int(getattr(cur, "rowcount", 0) or 0))
        except Exception:
            pass
    conn.commit()

    items = list_reminders(conn, user_id)
    count = len(items)
    watch_codes = _watch_codes(conn, user_id)
    return {
        "ok": True,
        "created": created,
        "skipped": skipped,
        "errors": errors,
        "added_watchlist": added_watch,
        "count": count,
        "watchlist_count": len(watch_codes),
        "items": items,
        "disclaimer": DISCLAIMER,
    }


def update_reminder(conn: Any, user_id: int, reminder_id: int, payload: dict[str, Any]) -> dict[str, Any] | None:
    try:
        event = rules.one(
            conn,
            "SELECT * FROM invest_event WHERE id=? AND user_id=?",
            (reminder_id, user_id),
        )
    except Exception:
        event = None
    if not event:
        return None
    sets: list[str] = []
    args: list[Any] = []
    if "threshold" in payload:
        threshold = _num(payload.get("threshold"))
        if threshold is None:
            raise ValueError("阈值不能为空")
        sets.append("threshold=?")
        args.append(threshold)
    if "condition" in payload:
        sets.append("condition_op=?")
        args.append(str(payload.get("condition")))
    if "end_date" in payload:
        sets.append("end_date=?")
        args.append(str(payload.get("end_date") or "").strip() or None)
    if "note" in payload and str(payload.get("note") or "").strip():
        sets.append("note=?")
        args.append(str(payload.get("note")).strip())
        sets.append("condition=?")
        args.append(str(payload.get("note")).strip())
    if not sets:
        return None
    sets.append("updated_at=?")
    args.append(date.today().isoformat())
    args.extend([reminder_id, user_id])
    conn.execute(f"UPDATE invest_event SET {', '.join(sets)} WHERE id=? AND user_id=?", tuple(args))
    conn.commit()
    items = list_reminders(conn, user_id)
    return next((x for x in items if int(x["id"]) == int(reminder_id)), None)


def toggle_reminder(conn: Any, user_id: int, reminder_id: int) -> dict[str, Any] | None:
    event = rules.one(
        conn,
        "SELECT id, status FROM invest_event WHERE id=? AND user_id=?",
        (reminder_id, user_id),
    )
    if not event:
        return None
    next_status = "paused" if event.get("status") == "active" else "active"
    conn.execute(
        "UPDATE invest_event SET status=?, updated_at=? WHERE id=? AND user_id=?",
        (next_status, date.today().isoformat(), reminder_id, user_id),
    )
    conn.commit()
    return {"ok": True, "status": next_status, "status_label": _status_label(next_status)}


def delete_reminder(conn: Any, user_id: int, reminder_id: int) -> bool:
    cur = conn.execute("DELETE FROM invest_event WHERE id=? AND user_id=?", (reminder_id, user_id))
    conn.commit()
    return bool(getattr(cur, "rowcount", 0))


# ---------------------------------------------------------------- 触发
def _met(rem: dict[str, Any], info: dict[str, Any]) -> bool:
    kind = rem["type"]
    condition = rem["condition"]
    threshold = _num(rem.get("threshold"))
    current = _num(info.get("value"))
    if kind == "price" and condition in {"limit_down", "limit_up"}:
        change = _num(info.get("change"))
        return change is not None and (change <= -9.8 if condition == "limit_down" else change >= 9.8)
    if kind == "financial":
        return _financial_met(info, int(threshold or 0))
    if current is None or threshold is None:
        return False
    if condition in {"below", "lte"}:
        return current <= threshold
    if condition in {"above", "gte", "consecutive_inflow", "consecutive_outflow"}:
        return current >= threshold
    return False


def _financial_met(info: dict[str, Any], days: int) -> bool:
    raw = str(info.get("extra") or "")[:10]
    if not raw:
        return False
    try:
        target = date.fromisoformat(raw)
    except ValueError:
        return False
    delta = (target - date.today()).days
    return 0 <= delta <= max(0, int(days))


def _push_detail(conn: Any, rem: dict[str, Any], info: dict[str, Any]) -> str:
    phrase = _condition_phrase(rem)
    display = info.get("display") or "—"
    extra = info.get("extra") or ""
    ctx = _Current(conn)
    ratio = ctx.amount_ratio(str(rem.get("code") or ""))
    parts = [f"现价 {display}" if rem["type"] == "price" and rem.get("unit") != "%" else f"当前 {display}"]
    if extra:
        parts.append(extra)
    if ratio is not None:
        parts.append(f"成交额较前日{'放大' if ratio >= 0 else '缩小'} {abs(ratio) * 100:.0f}%")
    head = "，".join(parts)
    tail = {
        "below": f"已跌破你设置的 {phrase}，可查看当日资金与公告。",
        "above": f"已涨破你设置的 {phrase}，可查看当日资金与公告。",
        "lte": f"已达到你设置的 {phrase}，可查看当日资金与公告。",
        "gte": f"已达到你设置的 {phrase}，可查看当日资金与公告。",
    }.get(str(rem.get("condition_op") or rem.get("condition")), f"已触发 {phrase}，可查看当日资金与公告。")
    return f"{head}。{tail}"


def evaluate(conn: Any, user_id: int, persist: bool = True) -> dict[str, Any]:
    """收盘后检查用户提醒；同一条件只提醒一次。"""
    try:
        events = rules.rows(
            conn,
            "SELECT * FROM invest_event WHERE user_id=? AND status='active' ORDER BY id DESC LIMIT 200",
            (user_id,),
        )
    except Exception:
        events = []
    names = _name_map(conn, [str(e.get("code")) for e in events])
    ctx = _Current(conn)
    triggered: list[dict[str, Any]] = []
    inserted = 0
    for event in events:
        event["name"] = names.get(str(event.get("code"))) or event.get("code")
        rem = {
            **event,
            "type": _type_key(str(event.get("type") or "价格")),
            "condition": event.get("condition_op") or _legacy_condition(_type_key(str(event.get("type") or "价格"))),
            "condition_op": event.get("condition_op") or _legacy_condition(_type_key(str(event.get("type") or "价格"))),
            "threshold": _num(event.get("threshold")),
        }
        if rem["type"] == "event":
            continue
        info = _current_info(ctx, rem)
        if not _met(rem, info):
            continue
        title = f"{_type_label(rem['type'])} {event['name']} {_condition_phrase(rem)}"
        detail = _push_detail(conn, rem, info)
        triggered.append({"id": event.get("id"), "code": event.get("code"), "title": title, "detail": detail})
        if persist:
            today = date.today().isoformat()
            exists = rules.one(
                conn,
                "SELECT 1 FROM invest_event_log WHERE user_id=? AND code=? AND title=? AND triggered_at LIKE ?",
                (user_id, event.get("code"), title, f"{today}%"),
            )
            if exists:
                continue
            conn.execute(
                "INSERT INTO invest_event_log (user_id, code, title, detail, triggered_at, read, source) "
                "VALUES (?,?,?,?,?,FALSE,?)",
                (user_id, event.get("code"), title, detail,
                 datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                 "ai" if (event.get("source") or "manual") == "ai" else "scan"),
            )
            conn.execute(
                "UPDATE invest_event SET status='triggered', updated_at=? WHERE id=?",
                (today, event.get("id")),
            )
            inserted += 1
    if persist:
        conn.commit()
    return {
        "ok": True,
        "triggered": triggered,
        "inserted": inserted,
        "checked": len(events),
        "note": "收盘后检查；不提供盘中实时推送。",
    }


__all__ = [
    "TYPE_LABELS", "NOTICE", "COMPLIANCE", "DISCLAIMER",
    "type_availability", "parse_query", "create_reminders", "list_reminders",
    "reminder_summary", "update_reminder", "toggle_reminder", "delete_reminder",
    "evaluate",
]
