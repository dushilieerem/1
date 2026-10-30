"""Deterministic demo seed for the Invest H5 MVP.

The seed intentionally looks like EOD market data, but it is synthetic.  It is
used only for local development/demo until the free-data ingestion job is
verified.  Every API response carries `dataSource` / `dataDate` so the UI can
label it correctly.
"""
from __future__ import annotations

import json
import math
import os
import random
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

DB_PATH = Path(os.getenv("INVEST_DB") or (Path(__file__).resolve().parent / "data" / "invest.db"))

STOCKS = [
    dict(code="300750", name="宁德时代", pinyin="ningdeshidai", industry="新能源", asset="stock",
         price=231.85, prev=233.00, shares=4.40e9, eps=19.13, bvps=72.45, dividend=0.55,
         base_volume=18_000_000, beta=1.12, report="2026-10-30", revenue=1100.0,
         growth=0.18, margin=0.256, net_margin=0.147, roe=17.6, margin_trend=-0.008),
    dict(code="600519", name="贵州茅台", pinyin="guizhoumaotai", industry="食品饮料", asset="stock",
         price=1486.00, prev=1495.20, shares=1.256e9, eps=59.90, bvps=174.80, dividend=2.10,
         base_volume=2_200_000, beta=0.72, report="2026-10-29", revenue=400.0,
         growth=0.12, margin=0.912, net_margin=0.505, roe=31.2, margin_trend=0.001),
    dict(code="600036", name="招商银行", pinyin="zhaoshangyinhang", industry="银行", asset="stock",
         price=42.80, prev=42.55, shares=25.2e9, eps=6.58, bvps=47.56, dividend=5.20,
         base_volume=55_000_000, beta=0.86, report="2026-10-28", revenue=700.0,
         growth=0.035, margin=0.0, net_margin=0.38, roe=15.1, margin_trend=0.0),
    dict(code="510300", name="沪深300ETF", pinyin="hushen300etf", industry="宽基", asset="etf",
         price=4.128, prev=4.112, shares=40.0e9, eps=None, bvps=None, dividend=1.10,
         base_volume=260_000_000, beta=1.00, report=None, revenue=0.0,
         growth=0.0, margin=0.0, net_margin=0.0, roe=0.0, margin_trend=0.0),
    dict(code="300308", name="中际旭创", pinyin="zhongjixuchuang", industry="光模块", asset="stock",
         price=186.20, prev=180.05, shares=1.12e9, eps=5.32, bvps=31.03, dividend=0.35,
         base_volume=9_000_000, beta=1.45, report="2026-10-27", revenue=62.0,
         growth=0.30, margin=0.302, net_margin=0.185, roe=22.4, margin_trend=0.004),
    dict(code="300014", name="亿纬锂能", pinyin="yiweilinen", industry="电池", asset="stock",
         price=48.60, prev=48.10, shares=2.05e9, eps=1.94, bvps=19.44, dividend=0.60,
         base_volume=28_000_000, beta=1.28, report="2026-10-26", revenue=120.0,
         growth=0.20, margin=0.172, net_margin=0.098, roe=13.6, margin_trend=-0.002),
    dict(code="002074", name="国轩高科", pinyin="guoxuangaoike", industry="电池", asset="stock",
         price=28.40, prev=27.95, shares=1.78e9, eps=0.71, bvps=15.78, dividend=0.30,
         base_volume=36_000_000, beta=1.35, report="2026-10-26", revenue=60.0,
         growth=0.15, margin=0.201, net_margin=0.055, roe=6.8, margin_trend=-0.003),
    dict(code="601318", name="中国平安", pinyin="zhongguopingan", industry="保险", asset="stock",
         price=52.30, prev=52.80, shares=18.2e9, eps=6.54, bvps=58.11, dividend=4.80,
         base_volume=48_000_000, beta=0.92, report="2026-10-27", revenue=1300.0,
         growth=0.05, margin=0.0, net_margin=0.12, roe=10.8, margin_trend=0.0),
    # Extra liquid names: makes search/screener meaningful beyond the demo portfolio.
    dict(code="000001", name="平安银行", pinyin="pinganyinhang", industry="银行", asset="stock",
         price=11.20, prev=11.15, shares=19.4e9, eps=2.20, bvps=21.00, dividend=5.10,
         base_volume=80_000_000, beta=0.88, report="2026-10-25", revenue=400.0,
         growth=0.03, margin=0.0, net_margin=0.25, roe=9.0, margin_trend=0.0),
    dict(code="000333", name="美的集团", pinyin="meidejituan", industry="家电", asset="stock",
         price=72.30, prev=71.80, shares=7.0e9, eps=5.10, bvps=28.00, dividend=4.00,
         base_volume=18_000_000, beta=0.86, report="2026-10-30", revenue=1000.0,
         growth=0.08, margin=0.26, net_margin=0.09, roe=20.0, margin_trend=0.001),
    dict(code="000858", name="五粮液", pinyin="wuliangye", industry="食品饮料", asset="stock",
         price=128.50, prev=129.10, shares=3.88e9, eps=8.40, bvps=35.00, dividend=3.60,
         base_volume=15_000_000, beta=0.78, report="2026-10-30", revenue=250.0,
         growth=0.10, margin=0.76, net_margin=0.36, roe=24.0, margin_trend=0.001),
    dict(code="002594", name="比亚迪", pinyin="biyadi", industry="新能源车", asset="stock",
         price=98.60, prev=97.90, shares=3.04e9, eps=4.10, bvps=25.00, dividend=1.20,
         base_volume=35_000_000, beta=1.18, report="2026-10-30", revenue=1700.0,
         growth=0.22, margin=0.20, net_margin=0.05, roe=18.0, margin_trend=-0.002),
    dict(code="300059", name="东方财富", pinyin="dongfangcaifu", industry="非银金融", asset="stock",
         price=24.80, prev=24.50, shares=15.8e9, eps=0.62, bvps=5.80, dividend=0.60,
         base_volume=180_000_000, beta=1.35, report="2026-10-28", revenue=110.0,
         growth=0.18, margin=0.60, net_margin=0.35, roe=12.0, margin_trend=0.002),
    dict(code="600030", name="中信证券", pinyin="zhongxinzhengquan", industry="非银金融", asset="stock",
         price=28.60, prev=28.20, shares=14.8e9, eps=1.30, bvps=19.00, dividend=2.20,
         base_volume=70_000_000, beta=1.10, report="2026-10-29", revenue=600.0,
         growth=0.09, margin=0.0, net_margin=0.28, roe=7.5, margin_trend=0.0),
    dict(code="600276", name="恒瑞医药", pinyin="hengruiyiyao", industry="医药", asset="stock",
         price=55.20, prev=54.80, shares=6.38e9, eps=1.10, bvps=8.50, dividend=0.80,
         base_volume=30_000_000, beta=0.95, report="2026-10-29", revenue=280.0,
         growth=0.12, margin=0.85, net_margin=0.22, roe=12.0, margin_trend=0.001),
    dict(code="600887", name="伊利股份", pinyin="yiligufen", industry="食品饮料", asset="stock",
         price=29.80, prev=29.60, shares=6.36e9, eps=1.90, bvps=9.50, dividend=4.20,
         base_volume=25_000_000, beta=0.82, report="2026-10-30", revenue=300.0,
         growth=0.04, margin=0.34, net_margin=0.09, roe=19.0, margin_trend=0.0),
    dict(code="601012", name="隆基绿能", pinyin="longjilvneng", industry="光伏", asset="stock",
         price=18.60, prev=18.30, shares=7.58e9, eps=0.50, bvps=9.00, dividend=0.50,
         base_volume=90_000_000, beta=1.25, report="2026-10-30", revenue=350.0,
         growth=0.02, margin=0.10, net_margin=0.02, roe=4.0, margin_trend=-0.004),
    dict(code="601166", name="兴业银行", pinyin="xingyeyinhang", industry="银行", asset="stock",
         price=20.40, prev=20.25, shares=20.8e9, eps=3.80, bvps=38.00, dividend=5.50,
         base_volume=60_000_000, beta=0.84, report="2026-10-28", revenue=550.0,
         growth=0.02, margin=0.0, net_margin=0.30, roe=10.5, margin_trend=0.0),
    dict(code="600900", name="长江电力", pinyin="changjiangdianli", industry="公用事业", asset="stock",
         price=29.20, prev=29.05, shares=24.5e9, eps=1.40, bvps=10.50, dividend=3.80,
         base_volume=40_000_000, beta=0.55, report="2026-10-30", revenue=250.0,
         growth=0.05, margin=0.55, net_margin=0.38, roe=14.0, margin_trend=0.001),
    dict(code="601899", name="紫金矿业", pinyin="zijinkuangye", industry="有色", asset="stock",
         price=18.20, prev=17.95, shares=26.0e9, eps=1.05, bvps=6.50, dividend=1.60,
         base_volume=120_000_000, beta=1.15, report="2026-10-30", revenue=900.0,
         growth=0.14, margin=0.18, net_margin=0.10, roe=16.0, margin_trend=0.002),
    # Theme constituents: AI compute / innovative drugs / low-altitude economy.
    dict(code="300502", name="新易盛", pinyin="xinyisheng", industry="光模块", asset="stock",
         price=180.00, prev=176.50, shares=1.0e9, eps=4.20, bvps=18.00, dividend=0.40,
         base_volume=30_000_000, beta=1.30, report="2026-10-28", revenue=120.0,
         growth=0.45, margin=0.38, net_margin=0.24, roe=28.0, margin_trend=0.003),
    dict(code="300394", name="天孚通信", pinyin="tianfutongxin", industry="光模块", asset="stock",
         price=120.00, prev=118.00, shares=0.55e9, eps=2.10, bvps=9.50, dividend=0.50,
         base_volume=18_000_000, beta=1.25, report="2026-10-29", revenue=45.0,
         growth=0.38, margin=0.52, net_margin=0.30, roe=24.0, margin_trend=0.002),
    dict(code="002463", name="沪电股份", pinyin="hudiangufen", industry="PCB", asset="stock",
         price=55.00, prev=54.20, shares=1.9e9, eps=1.80, bvps=7.20, dividend=1.00,
         base_volume=35_000_000, beta=1.15, report="2026-10-30", revenue=130.0,
         growth=0.30, margin=0.34, net_margin=0.18, roe=22.0, margin_trend=0.002),
    dict(code="601138", name="工业富联", pinyin="gongyefulian", industry="电子", asset="stock",
         price=32.00, prev=31.60, shares=19.8e9, eps=1.50, bvps=8.00, dividend=2.20,
         base_volume=100_000_000, beta=1.05, report="2026-10-29", revenue=5000.0,
         growth=0.18, margin=0.08, net_margin=0.04, roe=16.0, margin_trend=0.001),
    dict(code="603259", name="药明康德", pinyin="yaomingkangde", industry="医药", asset="stock",
         price=65.00, prev=64.00, shares=2.9e9, eps=3.20, bvps=20.00, dividend=0.90,
         base_volume=45_000_000, beta=1.00, report="2026-10-29", revenue=400.0,
         growth=0.12, margin=0.40, net_margin=0.22, roe=16.0, margin_trend=0.001),
    dict(code="688235", name="百济神州", pinyin="baijishenzhou", industry="医药", asset="stock",
         price=180.00, prev=177.00, shares=1.4e9, eps=1.00, bvps=15.00, dividend=0.00,
         base_volume=8_000_000, beta=1.10, report="2026-10-28", revenue=300.0,
         growth=0.35, margin=0.80, net_margin=0.08, roe=6.0, margin_trend=0.003),
    dict(code="002085", name="万丰奥威", pinyin="wanfengaoqi", industry="低空经济", asset="stock",
         price=18.00, prev=17.70, shares=2.1e9, eps=0.45, bvps=3.80, dividend=0.50,
         base_volume=60_000_000, beta=1.30, report="2026-10-29", revenue=160.0,
         growth=0.10, margin=0.20, net_margin=0.06, roe=12.0, margin_trend=0.001),
    dict(code="000099", name="中信海直", pinyin="zhongxinhaizhi", industry="低空经济", asset="stock",
         price=20.00, prev=19.70, shares=0.78e9, eps=0.55, bvps=5.20, dividend=0.80,
         base_volume=18_000_000, beta=1.20, report="2026-10-30", revenue=22.0,
         growth=0.12, margin=0.22, net_margin=0.12, roe=9.0, margin_trend=0.001),
    dict(code="688070", name="纵横股份", pinyin="zonghengfufen", industry="低空经济", asset="stock",
         price=42.00, prev=41.20, shares=0.12e9, eps=0.30, bvps=6.00, dividend=0.00,
         base_volume=4_000_000, beta=1.35, report="2026-10-29", revenue=6.0,
         growth=0.15, margin=0.45, net_margin=0.05, roe=4.0, margin_trend=0.001),
]

TOPICS = [
    dict(id="ai", name="AI 算力", summary="光模块 / 服务器 / 液冷。订单能见度与估值、拥挤度都在变化，先看历史分布。",
         heat=86, val=88, turn=87, code="300308", phase=0.4, base=1450.0, start=1000.0),
    dict(id="pharma", name="创新药", summary="出海授权与医保谈判催化，但个股研发失败率高、内部分化极大。",
         heat=72, val=63, turn=58, code="300750", phase=1.9, base=1180.0, start=980.0),
    dict(id="lowalt", name="低空经济", summary="政策催化密集，订单与适航进度尚未完全落地，主题波动大。",
         heat=68, val=74, turn=81, code="002074", phase=3.1, base=920.0, start=760.0),
]

NEWS = [
    ("n1", "三季报密集披露", "本周多家龙头披露三季报，关注毛利率与现金流。", "证券时报", "2026-10-27 08:30", "news", "300750", None, "https://www.stcn.com/"),
    ("n2", "北向资金动向", "近 5 日北向持股变化，新能源与食品饮料分化。", "东方财富", "2026-10-26 17:10", "news", None, None, "https://www.eastmoney.com/"),
    ("n3", "出口退税调整", "9 月起部分品类退税率调整，关注对制造业利润影响。", "财政部", "2026-10-25 15:00", "news", None, None, "https://www.mof.gov.cn/"),
    ("n4", "宁德时代三季报预约披露", "公司预约 10 月 30 日盘后披露 2026 年三季报。", "公司公告", "2026-10-24 19:20", "announcement", "300750", None, "https://www.cninfo.com.cn/"),
    ("n5", "海外云厂商上调资本开支指引", "光模块订单能见度延长，关注 Q4 交付节奏。", "公司公告", "2026-10-22 09:10", "news", "300308", "ai", "https://www.cninfo.com.cn/"),
    ("n6", "AI 算力板块成交额占比升至 8.6%", "板块拥挤度进入近一年 87% 分位。", "行情数据", "2026-10-24 16:00", "research", None, "ai", "https://www.eastmoney.com/"),
    ("n7", "瑞银下调 H 股目标价", "瑞银将宁德时代 H 股目标价下调至 730 港元，维持中性。", "瑞银研报", "2026-08-28 07:45", "research", "300750", None, "https://www.ubs.com/"),
    ("n8", "创新药出海授权首付款落地", "授权首付款与临床数据催化，关注后续里程碑。", "医药魔方", "2026-10-21 10:20", "news", None, "pharma", "https://www.pharmcube.com/"),
]

PERIODS = ["2024Q4", "2025Q1", "2025Q2", "2025Q3", "2025Q4", "2026Q1", "2026Q2", "2026Q3"]
PERIOD_END = {
    "2024Q4": date(2024, 12, 31), "2025Q1": date(2025, 3, 31), "2025Q2": date(2025, 6, 30),
    "2025Q3": date(2025, 9, 30), "2025Q4": date(2025, 12, 31), "2026Q1": date(2026, 3, 31),
    "2026Q2": date(2026, 6, 30), "2026Q3": date(2026, 9, 30),
}


def trading_days(end: date, count: int) -> list[date]:
    out: list[date] = []
    cur = end
    while len(out) < count:
        if cur.weekday() < 5:
            out.append(cur)
        cur -= timedelta(days=1)
    return list(reversed(out))


def fmt(d: date) -> str:
    return d.isoformat()


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        DROP TABLE IF EXISTS stocks;
        DROP TABLE IF EXISTS bars;
        DROP TABLE IF EXISTS financials;
        DROP TABLE IF EXISTS valuations;
        DROP TABLE IF EXISTS topics;
        DROP TABLE IF EXISTS topic_bars;
        DROP TABLE IF EXISTS topic_stocks;
        DROP TABLE IF EXISTS news;
        DROP TABLE IF EXISTS watchlist;
        DROP TABLE IF EXISTS events;
        DROP TABLE IF EXISTS event_logs;
        DROP TABLE IF EXISTS portfolio;
        DROP TABLE IF EXISTS portfolio_meta;
        DROP TABLE IF EXISTS risk_profiles;
        DROP TABLE IF EXISTS auth_events;

        CREATE TABLE stocks (
          code TEXT PRIMARY KEY, name TEXT, pinyin TEXT, industry TEXT, asset TEXT,
          price REAL, prev_close REAL, open REAL, high REAL, low REAL,
          market_cap REAL, pe_ttm REAL, pb REAL, dividend_yield REAL,
          turnover REAL, volume REAL, amount REAL, beta REAL,
          next_report_date TEXT, updated_at TEXT
        );
        CREATE TABLE bars (
          code TEXT, date TEXT, open REAL, high REAL, low REAL, close REAL,
          volume REAL, amount REAL, PRIMARY KEY (code, date)
        );
        CREATE TABLE financials (
          code TEXT, period TEXT, revenue REAL, revenue_yoy REAL, net_profit REAL,
          profit_yoy REAL, gross_margin REAL, roe REAL, ocf REAL,
          report_date TEXT, PRIMARY KEY (code, period)
        );
        CREATE TABLE valuations (
          code TEXT, date TEXT, pe_ttm REAL, pb REAL, PRIMARY KEY (code, date)
        );
        CREATE TABLE topics (
          id TEXT PRIMARY KEY, name TEXT, summary TEXT, heat REAL,
          valuation_percentile REAL, turnover_percentile REAL, updated_at TEXT
        );
        CREATE TABLE topic_bars (
          topic_id TEXT, date TEXT, close REAL, turnover REAL, valuation REAL,
          PRIMARY KEY (topic_id, date)
        );
        CREATE TABLE topic_stocks (
          topic_id TEXT, code TEXT, PRIMARY KEY (topic_id, code)
        );
        CREATE TABLE news (
          id TEXT PRIMARY KEY, title TEXT, summary TEXT, source TEXT,
          published_at TEXT, kind TEXT, code TEXT, topic_id TEXT, url TEXT
        );
        CREATE TABLE watchlist (
          user_id INTEGER, code TEXT, group_name TEXT, created_at TEXT,
          PRIMARY KEY (user_id, code)
        );
        CREATE TABLE events (
          id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, code TEXT,
          type TEXT, condition TEXT, status TEXT, created_at TEXT
        );
        CREATE TABLE event_logs (
          id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, code TEXT,
          title TEXT, detail TEXT, triggered_at TEXT, read INTEGER
        );
        CREATE TABLE portfolio (
          user_id INTEGER, code TEXT, shares REAL, cost REAL, weight REAL,
          target_weight REAL, industry TEXT, PRIMARY KEY (user_id, code)
        );
        CREATE TABLE portfolio_meta (
          user_id INTEGER PRIMARY KEY, trade_cost_pct REAL, annual_turnover REAL,
          impact_cost_pct REAL, updated_at TEXT
        );
        CREATE TABLE risk_profiles (
          user_id INTEGER PRIMARY KEY, level TEXT, score INTEGER, answers TEXT, updated_at TEXT
        );
        CREATE TABLE auth_events (
          id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, action TEXT,
          username TEXT, ip TEXT, detail TEXT
        );
        CREATE TABLE meta (
          key TEXT PRIMARY KEY, value TEXT
        );
        CREATE TABLE indices (
          code TEXT PRIMARY KEY, name TEXT, price REAL, prev_close REAL, updated_at TEXT
        );
        """
    )


def seed(force: bool = False) -> Path:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if DB_PATH.exists() and not force:
        return DB_PATH
    if DB_PATH.exists():
        DB_PATH.unlink()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    create_schema(conn)

    days = trading_days(date(2026, 10, 23), 750)
    now = datetime(2026, 10, 26, 18, 30).isoformat(timespec="seconds")

    for s in STOCKS:
        rng = random.Random(s["code"])
        n = len(days)
        start = s["price"] * (0.58 + rng.random() * 0.12)
        phase = rng.random() * 6.28
        raw: list[float] = []
        for i in range(n):
            trend = start * (s["price"] / start) ** (i / (n - 1))
            wave = 1 + 0.055 * math.sin(i / 34 + phase) + rng.gauss(0, 0.011)
            raw.append(trend * wave)
            if s["code"] == "300750":
                raw[-1] *= 1 + 0.34 * math.exp(-((i - 610) / 70) ** 2)
        scale = s["price"] / raw[-1]
        closes = [x * scale for x in raw]
        closes[-1] = s["price"]
        closes[-2] = s["prev"]

        bars: list[tuple] = []
        for i, d in enumerate(days):
            close = closes[i]
            prev = closes[i - 1] if i else close
            if i == n - 1:
                open_ = s["price"] * 0.995
                high = s["price"] * 1.010
                low = s["price"] * 0.990
            else:
                open_ = prev * (1 + rng.gauss(0, 0.004))
                high = max(open_, close) * (1 + abs(rng.gauss(0, 0.006)))
                low = min(open_, close) * (1 - abs(rng.gauss(0, 0.006)))
            vol = s["base_volume"] * (1 + 0.35 * math.sin(i / 22 + phase) + rng.uniform(-0.15, 0.35))
            vol = max(vol, s["base_volume"] * 0.25)
            bars.append((s["code"], fmt(d), round(open_, 3), round(high, 3), round(low, 3),
                         round(close, 3), round(vol, 0), round(vol * close, 2)))
        conn.executemany("INSERT INTO bars VALUES (?,?,?,?,?,?,?,?)", bars)

        last = bars[-1]
        vol = last[6]
        pe = s["price"] / s["eps"] if s["eps"] else None
        pb = s["price"] / s["bvps"] if s["bvps"] else None
        conn.execute(
            "INSERT INTO stocks VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (s["code"], s["name"], s["pinyin"], s["industry"], s["asset"], s["price"], s["prev"],
             last[2], last[3], last[4], round(s["price"] * s["shares"], 0), pe, pb, s["dividend"],
             round(vol / s["shares"] * 100, 2) if s["shares"] else 0, vol, last[7], s["beta"],
             s["report"], now),
        )

        if s["asset"] != "etf":
            for i, d in enumerate(days):
                if s["eps"]:
                    eps_t = s["eps"] * (1 + s["growth"]) ** ((i - n + 1) / 250)
                    bvps_t = s["bvps"] * (1 + max(s["growth"], 0.02)) ** ((i - n + 1) / 250)
                    conn.execute("INSERT INTO valuations VALUES (?,?,?,?)",
                                 (s["code"], fmt(d), round(closes[i] / eps_t, 2), round(closes[i] / bvps_t, 2)))

            for idx, period in enumerate(PERIODS):
                growth = s["growth"] + rng.uniform(-0.02, 0.02)
                revenue = s["revenue"] * (1 + s["growth"]) ** (idx / 4)
                net_margin = s["net_margin"] + rng.uniform(-0.006, 0.006)
                margin = s["margin"] + s["margin_trend"] * (idx - 3) + rng.uniform(-0.003, 0.003)
                report = PERIOD_END[period] + timedelta(days=30)
                if period == "2026Q3" and s["report"]:
                    report = date.fromisoformat(s["report"])
                conn.execute("INSERT INTO financials VALUES (?,?,?,?,?,?,?,?,?,?)",
                             (s["code"], period, round(revenue, 1), round(growth * 100, 1),
                              round(revenue * net_margin, 1), round(growth * 100 + rng.uniform(1, 6), 1),
                              round(max(margin, 0) * 100, 2), round(s["roe"] + rng.uniform(-1, 1), 1),
                              round(revenue * net_margin * rng.uniform(0.8, 1.2), 1), fmt(report)))

    for t in TOPICS:
        rng = random.Random(t["id"])
        n = len(days)
        bars = []
        for i, d in enumerate(days):
            close = t["start"] * (t["base"] / t["start"]) ** (i / (n - 1)) * (
                1 + 0.05 * math.sin(i / 38 + t["phase"]) + rng.gauss(0, 0.010))
            val = 55 + 28 * math.sin(i / 44 + t["phase"]) + 7 * math.sin(i / 13) + rng.gauss(0, 2)
            turn = 52 + 24 * math.sin(i / 29 + t["phase"] + 0.8) + rng.gauss(0, 3)
            val = min(96, max(8, val))
            turn = min(97, max(6, turn))
            bars.append((t["id"], fmt(d), round(close, 2), round(turn, 1), round(val, 1)))
        conn.executemany("INSERT INTO topic_bars VALUES (?,?,?,?,?)", bars)
        conn.execute("INSERT INTO topics VALUES (?,?,?,?,?,?,?)",
                     (t["id"], t["name"], t["summary"], t["heat"], t["val"], t["turn"], now))

    for topic_id, codes in {
        "ai": ["300308", "300502", "300394", "002463", "601138"],
        "pharma": ["600276", "603259", "688235"],
        "lowalt": ["002085", "000099", "688070"],
    }.items():
        conn.executemany("INSERT INTO topic_stocks VALUES (?,?)", [(topic_id, c) for c in codes])

    for row in NEWS:
        conn.execute("INSERT INTO news VALUES (?,?,?,?,?,?,?,?,?)", row)

    conn.executemany(
        "INSERT INTO watchlist VALUES (?,?,?,?)",
        [(1, "300750", "核心", now), (1, "600519", "核心", now),
         (1, "510300", "宽基", now), (1, "300308", "观察", now)],
    )
    conn.executemany(
        "INSERT INTO events (user_id, code, type, condition, status, created_at) VALUES (?,?,?,?,?,?)",
        [(1, "300750", "价格", "收盘价跌破 220 元", "active", now),
         (1, "300750", "财报", "三季报 10-30 披露", "active", now),
         (1, "ai", "热度", "热度进入 90% 分位", "active", now)],
    )
    conn.executemany(
        "INSERT INTO event_logs (user_id, code, title, detail, triggered_at, read) VALUES (?,?,?,?,?,?)",
        [(1, "ai", "AI 算力 · 热度", "进入 87% 分位，收盘后更新", "2026-10-25 18:35", 0),
         (1, "300750", "宁德时代 · 价格", "收盘 231.85 元，未触发 220 元阈值", "2026-10-24 18:32", 1)],
    )

    holdings = [
        ("600036", 4845, 38.20, 24.0, 20.0, "银行"),
        ("300750", 894, 252.00, 24.0, 20.0, "新能源"),
        ("600519", 116, 1620.00, 20.0, 20.0, "食品饮料"),
        ("510300", 46046, 3.95, 22.0, 30.0, "宽基"),
        ("CASH", 86400, 1.00, 10.0, 10.0, "现金"),
    ]
    conn.executemany("INSERT INTO portfolio VALUES (?,?,?,?,?,?,?)",
                     [(1, c, sh, cost, w, tw, ind) for c, sh, cost, w, tw, ind in holdings])
    conn.execute("INSERT INTO portfolio_meta VALUES (?,?,?,?,?)", (1, 0.4, 35.0, 0.08, now))
    conn.execute("INSERT INTO risk_profiles VALUES (?,?,?,?,?)",
                 (1, "稳健型", 62, json.dumps({"horizon": "3-5年", "lossTolerance": "10%"}, ensure_ascii=False), now))
    conn.execute("INSERT OR REPLACE INTO meta VALUES ('source', 'seed')")
    conn.execute("INSERT OR REPLACE INTO meta VALUES ('updated_at', ?)", (now,))
    conn.executemany("INSERT INTO indices VALUES (?,?,?,?,?)", [
        ("000300", "沪深 300", 4128.6, 4100.7, now),
        ("399006", "创业板指", 2214.8, 2190.3, now),
    ])

    conn.commit()
    conn.close()
    return DB_PATH


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    path = seed(force=args.force)
    print(f"seeded {path}")
