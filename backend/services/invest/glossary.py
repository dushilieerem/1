# -*- coding: utf-8 -*-
"""手机端术语库：静态结构化数据，口径稳定，不由模型生成。"""
from __future__ import annotations

from typing import Any

CATEGORIES = ("指标", "估值", "财务", "风险", "交易")

TERMS: tuple[dict[str, Any], ...] = (
    {
        "id": "pe_ttm",
        "term": "PE(TTM)",
        "aliases": ["市盈率", "PE", "滚动市盈率"],
        "category": "估值",
        "definition": "股价相对过去 12 个月每股收益的倍数，用来观察市场愿意为当前盈利付多少钱。",
        "how_to": "和自身历史分位、同行业公司对比；亏损或盈利剧烈波动时 PE 会失真。",
        "range": "没有统一合理区间；消费/稳定行业常见 15–30 倍，周期行业低 PE 也可能是高点。",
        "example": "PE 20 倍表示按当前盈利水平，约 20 年回本（不计增长与分红）。",
        "related": ["pb", "earnings_yield", "peg"],
    },
    {
        "id": "pb",
        "term": "PB",
        "aliases": ["市净率"],
        "category": "估值",
        "definition": "股价相对每股净资产的倍数，常用于银行、保险、地产等重资产行业。",
        "how_to": "看 PB 与 ROE 是否匹配：高 ROE 通常支撑更高 PB；低 PB 可能意味着资产质量折价。",
        "range": "银行常见 0.4–1.5 倍；制造业差异很大，不能跨行业直接比较。",
        "example": "PB 0.8 表示市值低于账面净资产，但不代表一定便宜，需看资产是否减值。",
        "related": ["pe_ttm", "roe"],
    },
    {
        "id": "dividend_yield",
        "term": "股息率",
        "aliases": ["分红率", "dividend yield"],
        "category": "估值",
        "definition": "过去 12 个月现金分红 ÷ 当前股价，衡量持有期现金回报。",
        "how_to": "看连续性和可持续性：一次性特别分红会抬高股息率；高股息也可能来自股价下跌。",
        "range": "A 股常见 0–6%；超过 8% 需核查是否一次性或周期高点。",
        "example": "股息率 4% 表示按当前股价，过去一年分红约为市值的 4%。",
        "related": ["pe_ttm", "payout_ratio"],
    },
    {
        "id": "roe",
        "term": "ROE",
        "aliases": ["净资产收益率"],
        "category": "财务",
        "definition": "归母净利润 ÷ 归母净资产，衡量股东投入资本的盈利效率。",
        "how_to": "看 3–5 年趋势与杠杆：高 ROE 若靠高负债或一次性收益，质量要打折。",
        "range": "长期 15% 以上通常较优秀；银行/地产等杠杆行业需结合风险看。",
        "example": "ROE 20% 表示每 100 元净资产一年赚 20 元（会计口径）。",
        "related": ["pb", "roic", "gross_margin"],
    },
    {
        "id": "gross_margin",
        "term": "毛利率",
        "aliases": ["gross margin"],
        "category": "财务",
        "definition": "营业收入扣除营业成本后的毛利 ÷ 营业收入，反映产品定价与成本控制。",
        "how_to": "和同行业、自身历史比；高毛利不等于护城河，需看费用率、周转与客户留存。",
        "range": "软件/品牌消费常见 50%+；制造/零售常见 10–30%。",
        "example": "毛利率 90% 表示每 100 元收入留下 90 元毛利，尚未扣费用与税。",
        "related": ["net_margin", "roe", "moat"],
    },
    {
        "id": "net_margin",
        "term": "净利率",
        "aliases": ["销售净利率"],
        "category": "财务",
        "definition": "净利润 ÷ 营业收入，反映扣掉成本、费用与税后的最终盈利能力。",
        "how_to": "与毛利率一起看：毛利率高但净利率低，通常意味着费用或减值侵蚀。",
        "range": "行业差异大；长期稳定比单期高低更重要。",
        "example": "净利率 10% 表示每 100 元收入最终留下 10 元净利。",
        "related": ["gross_margin", "roe"],
    },
    {
        "id": "free_cash_flow",
        "term": "自由现金流",
        "aliases": ["FCF", "free cash flow"],
        "category": "财务",
        "definition": "经营现金流减去资本开支，代表企业可自由支配的现金。",
        "how_to": "看多年累计是否为正、与净利润是否匹配；持续为负需解释扩张或经营问题。",
        "range": "没有统一区间；重资产扩张期可能阶段性为负。",
        "example": "经营现金流 10 亿、资本开支 4 亿，自由现金流约 6 亿。",
        "related": ["operating_cash_flow", "net_margin"],
    },
    {
        "id": "operating_cash_flow",
        "term": "经营现金流",
        "aliases": ["OCF", "经营活动现金流"],
        "category": "财务",
        "definition": "企业日常经营活动产生的现金净流入，反映利润的现金含量。",
        "how_to": "与净利润对比：长期 OCF 低于净利润，需关注应收、存货与收入确认。",
        "range": "没有统一区间；应与利润和资本开支一起看。",
        "example": "净利润 8 亿、经营现金流 3 亿，说明部分利润尚未变成现金。",
        "related": ["free_cash_flow", "net_margin"],
    },
    {
        "id": "revenue_yoy",
        "term": "营收同比",
        "aliases": ["收入同比", "revenue growth"],
        "category": "财务",
        "definition": "本期营业收入相对上年同期的增长率，用于观察业务规模变化。",
        "how_to": "结合基数和行业周期；并表、提价、渠道变化会扭曲同比。",
        "range": "没有统一标准；连续负增长需解释原因。",
        "example": "营收同比 +12% 表示本期收入比去年同期高 12%。",
        "related": ["profit_yoy", "gross_margin"],
    },
    {
        "id": "profit_yoy",
        "term": "净利同比",
        "aliases": ["归母净利同比", "profit growth"],
        "category": "财务",
        "definition": "本期归母净利润相对上年同期的增长率。",
        "how_to": "和营收同比一起看：营收增长但净利下滑，可能是费用、减值或价格竞争。",
        "range": "没有统一标准；低基数会造成高同比。",
        "example": "净利同比 -8% 表示本期归母净利比去年同期低 8%。",
        "related": ["revenue_yoy", "net_margin"],
    },
    {
        "id": "max_drawdown",
        "term": "最大回撤",
        "aliases": ["回撤", "MDD"],
        "category": "风险",
        "definition": "从阶段高点到之后低点的最大跌幅，衡量持有体验与下行风险。",
        "how_to": "看回撤发生的背景、修复时间与是否伴随基本面恶化；历史回撤不预测未来。",
        "range": "宽基指数历史常见 −20% 到 −40%；个股差异更大。",
        "example": "从 100 跌到 70，最大回撤为 −30%。",
        "related": ["volatility", "beta"],
    },
    {
        "id": "volatility",
        "term": "波动率",
        "aliases": ["年化波动", "volatility"],
        "category": "风险",
        "definition": "收益波动的统计尺度，常用年化标准差表示。",
        "how_to": "高波动意味着短期价格分布更宽，不等于必然亏损；结合仓位与期限看。",
        "range": "A 股个股常见 20–50% 年化；低波动策略通常更低。",
        "example": "年化波动 30% 表示日收益波动大约在 1.9% 量级（粗略换算）。",
        "related": ["max_drawdown", "beta"],
    },
    {
        "id": "beta",
        "term": "Beta",
        "aliases": ["贝塔", "β"],
        "category": "风险",
        "definition": "标的相对市场基准的敏感度；1 表示大致同涨同跌，大于 1 表示波动放大。",
        "how_to": "看统计区间与基准；Beta 会随市场环境变化，不是固定属性。",
        "range": "<0.8 低敏感、0.8–1.2 中等、1.2–1.5 较高、≥1.5 高。",
        "example": "Beta 1.3 表示市场涨跌 1%，标的平均波动约 1.3%（历史统计）。",
        "related": ["volatility", "max_drawdown"],
    },
    {
        "id": "turnover",
        "term": "换手率",
        "aliases": ["turnover"],
        "category": "交易",
        "definition": "一段时间内成交股数 ÷ 流通股本，衡量交易活跃度。",
        "how_to": "和自身历史、同行业比；异常放大可能伴随事件或情绪化交易。",
        "range": "A 股日换手常见 0.5–5%；持续 >10% 需关注炒作与流动性风险。",
        "example": "换手率 3% 表示当天约 3% 的流通股发生交易。",
        "related": ["volume_ratio", "heat"],
    },
    {
        "id": "volume_ratio",
        "term": "量比",
        "aliases": ["成交量比"],
        "category": "交易",
        "definition": "当日成交量相对过去一段时间平均成交量的倍数。",
        "how_to": "结合价格方向看：放量上涨/下跌的含义不同；单日量比容易受事件影响。",
        "range": ">1.5 视为明显放量；<0.7 视为缩量。",
        "example": "量比 2.0 表示成交量为近期均量的两倍。",
        "related": ["turnover"],
    },
    {
        "id": "sharpe",
        "term": "夏普比率",
        "aliases": ["Sharpe"],
        "category": "指标",
        "definition": "超额收益 ÷ 收益波动，衡量单位风险获得的回报。",
        "how_to": "看统计区间、无风险利率与样本长度；高夏普可能来自低波动或短样本。",
        "range": ">1 通常较好；>2 需核查是否过拟合或样本太短。",
        "example": "年化超额 10%、波动 8%，夏普约 1.25（简化）。",
        "related": ["annual_return", "volatility"],
    },
    {
        "id": "annual_return",
        "term": "年化收益",
        "aliases": ["annual return", "年化"],
        "category": "指标",
        "definition": "把区间收益折算成一年的复合增长率，便于不同期限比较。",
        "how_to": "必须看区间与是否扣费；短期高年化不能外推。",
        "range": "没有统一标准；与回撤、波动一起看。",
        "example": "半年收益 10%，粗略年化约 21%（复利口径）。",
        "related": ["sharpe", "max_drawdown"],
    },
    {
        "id": "alpha",
        "term": "Alpha",
        "aliases": ["超额收益", "α"],
        "category": "指标",
        "definition": "扣除市场（Beta）影响后的超额收益，衡量策略/选股的独立贡献。",
        "how_to": "看基准、统计显著性与费用；短区间 Alpha 可能是运气或风格暴露。",
        "range": "没有统一标准；需结合信息比率与回撤。",
        "example": "市场涨 10%、策略涨 13%、Beta=1，粗略 Alpha 约 3%。",
        "related": ["beta", "sharpe"],
    },
    {
        "id": "risk_score",
        "term": "组合风险分",
        "aliases": ["风险评分"],
        "category": "风险",
        "definition": "按集中度、行业暴露与历史回撤综合得到的 0–100 分，分数越高越集中/波动。",
        "how_to": "看构成而不是只看分数；分数低也可能有单一事件风险。",
        "range": "本产品规则：20–95；≥65 标为“偏集中”。",
        "example": "前三大持仓 70%、最大行业 35%，风险分通常较高。",
        "related": ["concentration", "max_drawdown"],
    },
    {
        "id": "concentration",
        "term": "集中度",
        "aliases": ["持仓集中度"],
        "category": "风险",
        "definition": "前几大持仓或单一行业占组合的比例，衡量分散程度。",
        "how_to": "结合标的相关性与行业链条；数量多不等于分散。",
        "range": "本产品：最大行业 ≥24%、前三大 ≥60% 会触发提示。",
        "example": "前三大持仓合计 65%，单一股票事件会明显影响净值。",
        "related": ["risk_score"],
    },
)


def list_terms(*, category: str = "", q: str = "") -> dict[str, Any]:
    cat = (category or "").strip()
    term = (q or "").strip().lower()
    items = []
    for item in TERMS:
        if cat and item["category"] != cat:
            continue
        if term:
            haystack = " ".join(
                [item["term"], item["definition"], *item.get("aliases", [])]
            ).lower()
            if term not in haystack:
                continue
        items.append(item)
    return {"items": items, "total": len(items), "categories": list(CATEGORIES)}


def find_term(text: str) -> dict[str, Any] | None:
    raw = (text or "").strip().lower()
    if not raw:
        return None
    for item in TERMS:
        names = [item["term"], *item.get("aliases", [])]
        if any(name.lower() in raw for name in names):
            return item
    return None
