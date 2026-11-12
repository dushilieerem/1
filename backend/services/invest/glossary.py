# -*- coding: utf-8 -*-
"""手机端术语库：静态结构化数据，口径稳定，不由模型生成。"""
from __future__ import annotations

import re
import unicodedata
from typing import Any

CATEGORIES = ("指标", "估值", "财务", "风险", "交易")

TERMS: tuple[dict[str, Any], ...] = (
    {
        "id": "pe_ttm",
        "term": "市盈率",
        "term_en": "P/E (TTM)",
        "aliases": ["PE", "P/E", "本益比", "市盈", "PE(TTM)", "滚动市盈率"],
        "category": "估值",
        "definition": "股价相对过去 12 个月每股收益的倍数，用来观察市场愿意为当前盈利付多少钱。",
        "how_to": "和自身历史分位、同行业公司对比；亏损或盈利剧烈波动时 PE 会失真。",
        "range": "没有统一合理区间；消费/稳定行业常见 15–30 倍，周期行业低 PE 也可能是高点。",
        "example": "PE 20 倍表示按当前盈利水平，约 20 年回本（不计增长与分红）。",
        "related": ["pb", "earnings_yield", "peg"],
    },
    {
        "id": "pb",
        "term": "市净率",
        "term_en": "P/B",
        "aliases": ["PB", "P/B", "市净"],
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
        "term": "净资产收益率",
        "term_en": "ROE",
        "aliases": ["ROE", "权益回报率", "净资产回报率"],
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
        "term_en": "Max drawdown",
        "aliases": ["最大回撤率", "回撤", "MDD"],
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
        "term_en": "Volatility",
        "aliases": ["波动", "标准差", "年化波动", "volatility"],
        "category": "风险",
        "definition": "收益波动的统计尺度，常用年化标准差表示。",
        "how_to": "高波动意味着短期价格分布更宽，不等于必然亏损；结合仓位与期限看。",
        "range": "A 股个股常见 20–50% 年化；低波动策略通常更低。",
        "example": "年化波动 30% 表示日收益波动大约在 1.9% 量级（粗略换算）。",
        "related": ["max_drawdown", "beta"],
    },
    {
        "id": "beta",
        "term": "贝塔",
        "term_en": "Beta",
        "aliases": ["Beta", "β", "贝塔系数"],
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
        "term_en": "Turnover",
        "aliases": ["周转率", "turnover"],
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
        "term_en": "Sharpe Ratio",
        "aliases": ["夏普", "夏普率", "夏普指数", "Sharpe", "Sharpe ratio"],
        "category": "指标",
        "definition": "超额收益 ÷ 收益波动，衡量单位风险获得的回报。",
        "how_to": "看统计区间、无风险利率与样本长度；高夏普可能来自低波动或短样本。",
        "range": ">1 通常较好；>2 需核查是否过拟合或样本太短。",
        "example": "年化超额 10%、波动 8%，夏普约 1.25（简化）。",
        "related": ["annual_return", "volatility"],
    },
    {
        "id": "sortino",
        "term": "索提诺比率",
        "term_en": "Sortino Ratio",
        "aliases": ["索提诺", "Sortino", "下行夏普"],
        "category": "指标",
        "definition": "超额收益 ÷ 下行波动，只惩罚亏损方向的波动。",
        "how_to": "看统计区间与下行波动口径；上行波动不计入分母，和夏普不能直接混用。",
        "range": ">1 通常较好；>2 需核查样本长度与是否只取到低波动区间。",
        "example": "年化超额 10%、下行波动 10%，索提诺约 1.0。",
        "related": ["sharpe", "max_drawdown"],
    },
    {
        "id": "information_ratio",
        "term": "信息比率",
        "term_en": "Information Ratio",
        "aliases": ["IR", "information ratio", "跟踪误差比"],
        "category": "指标",
        "definition": "相对基准的超额收益 ÷ 跟踪误差，衡量主动管理效率。",
        "how_to": "必须先看基准选择；基准不同，信息比率不可直接比较。",
        "range": ">0.5 通常算较好；>1 需核查样本与基准是否匹配。",
        "example": "年化超额 4%、跟踪误差 5%，信息比率约 0.8。",
        "related": ["alpha", "sharpe"],
    },
    {
        "id": "calmar",
        "term": "卡玛比率",
        "term_en": "Calmar Ratio",
        "aliases": ["Calmar", "卡玛"],
        "category": "指标",
        "definition": "年化收益 ÷ 最大回撤，衡量单位回撤换来的收益。",
        "how_to": "回撤是历史极值，样本越长越可能变大；结合回撤修复时间看。",
        "range": ">1 表示年化收益高于历史最大回撤；>3 需核查样本长短。",
        "example": "年化收益 18%、最大回撤 −24%，卡玛约 0.75。",
        "related": ["max_drawdown", "annual_return"],
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
        "term": "阿尔法",
        "term_en": "Alpha",
        "aliases": ["Alpha", "α", "超额收益"],
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


# 人话正文 / 例子 / 常见误用：只解释口径，不给投资建议。
EXPLAIN: dict[str, dict[str, str]] = {
    "pe_ttm": {
        "plain": "PE 就是“股价相当于过去一年每股收益的多少倍”，用来感受市场愿意为当前盈利付多少钱。",
        "example": "PE 20 倍，粗略理解为按当前盈利水平约 20 年回本，尚未计入增长和分红。",
        "misuse": "把低 PE 直接当成便宜。周期行业盈利处在高点时，PE 反而可能很低。",
    },
    "pb": {
        "plain": "PB 是“股价相当于每股净资产的多少倍”，常用于银行、保险、地产等重资产行业。",
        "example": "PB 0.8 表示市值低于账面净资产；但不代表资产没有被高估或减值。",
        "misuse": "只比 PB 不看 ROE 和资产质量，低 PB 也可能是“价值陷阱”。",
    },
    "dividend_yield": {
        "plain": "股息率 = 过去 12 个月现金分红 ÷ 当前股价，衡量持有期间拿到的现金回报比例。",
        "example": "股息率 4% 表示按当前股价，过去一年分红约为市值的 4%。",
        "misuse": "把一次性特别分红当成可持续股息；高股息也可能来自股价下跌。",
    },
    "roe": {
        "plain": "ROE 是“股东每投入 100 元净资产，一年能赚回多少”，衡量资本使用效率。",
        "example": "ROE 20% 表示每 100 元净资产一年赚约 20 元（会计口径）。",
        "misuse": "只看 ROE 高低，不看是否靠高杠杆或一次性收益撑起来。",
    },
    "gross_margin": {
        "plain": "毛利率是“每 100 元收入，扣掉直接成本后还剩多少”，反映产品定价和成本控制。",
        "example": "毛利率 50% 表示 100 元收入留下 50 元毛利，尚未扣费用和税。",
        "misuse": "把高毛利当成护城河；还要看费用率、周转和客户留存。",
    },
    "net_margin": {
        "plain": "净利率是“每 100 元收入，最后真正留下多少净利润”，已经扣掉成本、费用和税。",
        "example": "净利率 10% 表示 100 元收入最终留下 10 元净利。",
        "misuse": "只看单期净利率；一次性收益或减值会让单期数字失真。",
    },
    "free_cash_flow": {
        "plain": "自由现金流是“经营赚到的现金，扣掉维持和扩张所需资本开支后，真正可自由支配的部分”。",
        "example": "经营现金流 10 亿、资本开支 4 亿，自由现金流约 6 亿。",
        "misuse": "把会计利润当成现金；利润好但现金流差，需要看应收和存货。",
    },
    "operating_cash_flow": {
        "plain": "经营现金流是“主营业务实际收进来的现金”，比利润更难被会计处理修饰。",
        "example": "经营现金流为正且接近净利润，通常说明回款质量较好。",
        "misuse": "只看单季经营现金流；季节性行业需要看全年或滚动 12 个月。",
    },
    "revenue_yoy": {
        "plain": "营收同比是“本期收入比去年同期增长或下降了多少”，看业务规模的变化方向。",
        "example": "营收同比 +15% 表示本期收入比去年同期多 15%。",
        "misuse": "只看增速不看基数；低基数下的高增速可能不可持续。",
    },
    "profit_yoy": {
        "plain": "净利同比是“本期净利润比去年同期变化多少”，看盈利的变化方向。",
        "example": "净利同比 -10% 表示本期净利润比去年同期少 10%。",
        "misuse": "把一次性收益或减值造成的同比波动当成经营趋势。",
    },
    "max_drawdown": {
        "plain": "最大回撤是“从阶段高点到之后低点，最多跌了多少”，衡量持有过程有多难受。",
        "example": "最大回撤 -20% 表示历史最大的一次从高点到低点跌了 20%。",
        "misuse": "只看收益不看回撤；高收益可能伴随难以承受的波动。",
    },
    "volatility": {
        "plain": "波动率是“收益上下起伏的剧烈程度”，常用年化标准差表示。",
        "example": "年化波动率 25% 表示波动幅度大致处在这个量级，不是未来收益。",
        "misuse": "把低波动当成低风险；流动性风险和尾部风险不一定体现在波动率里。",
    },
    "beta": {
        "plain": "Beta 是“标的相对大盘的敏感度”：1 表示大致同步，大于 1 表示波动通常更大。",
        "example": "Beta 1.2 表示大盘涨跌 1% 时，标的平均波动约 1.2%（历史统计）。",
        "misuse": "把 Beta 当成未来涨跌预测；它只描述历史相对波动。",
    },
    "turnover": {
        "plain": "换手率是“一段时间内股票成交的频繁程度”，用成交量相对流通股本衡量。",
        "example": "换手率 5% 表示当天成交了约 5% 的流通股本。",
        "misuse": "把高换手当成热度越高越好；过高可能伴随情绪化交易。",
    },
    "volume_ratio": {
        "plain": "量比是“当前成交量相对过去一段时间平均成交量的倍数”，看成交是否异常放大。",
        "example": "量比 2 表示当前成交量约为近期均量的 2 倍。",
        "misuse": "只看放量不看价格方向；放量下跌和放量上涨含义不同。",
    },
    "sortino": {
        "plain": "索提诺比率是“每承担一单位下行波动，换来多少超额收益”，只惩罚亏钱方向的波动。",
        "example": "年化超额 10%、下行波动 10%，索提诺约 1.0。",
        "misuse": "把索提诺和夏普直接混用；两者分母不同，上行波动一个算、一个不算。",
    },
    "information_ratio": {
        "plain": "信息比率是“相对基准的超额收益，除以跟踪误差”，用来衡量主动管理效率。",
        "example": "年化超额 4%、跟踪误差 5%，信息比率约 0.8。",
        "misuse": "换一个基准还直接比较信息比率；基准不同，结论不可比。",
    },
    "calmar": {
        "plain": "卡玛比率是“年化收益除以最大回撤”，衡量每承受一单位历史最大回撤换来多少收益。",
        "example": "年化收益 18%、最大回撤 -24%，卡玛约 0.75。",
        "misuse": "样本太短时最大回撤被低估，卡玛会虚高。",
    },
    "sharpe": {
        "plain": "夏普比率是“每承担一单位波动，换来多少超额收益”，用来比较风险调整后的表现。",
        "example": "夏普 1 表示承担的波动与获得的超额收益大致匹配。",
        "misuse": "跨策略、跨样本期直接比夏普；计算频率和基准不同会失真。",
    },
    "annual_return": {
        "plain": "年化收益是“把一段时间的收益折算成一年的速度”，方便不同期限比较。",
        "example": "半年收益 10%，粗略年化约 21%（复利口径，不等于未来收益）。",
        "misuse": "把短期年化当成长期可持续收益；样本越短越不稳定。",
    },
    "alpha": {
        "plain": "Alpha 是“扣掉市场涨跌影响后，策略自己创造的超额收益”。",
        "example": "市场涨 10%、策略涨 13%、Beta 为 1，粗略 Alpha 约 3%。",
        "misuse": "把 Beta 暴露带来的收益当成 Alpha；风格暴露也会贡献收益。",
    },
    "risk_score": {
        "plain": "组合风险分是“把集中度、行业、穿透、相关性、估值和换手成本加权后的 0–100 分”。",
        "example": "分数越高代表持仓结构越集中；只反映结构，不预测盈亏。",
        "misuse": "把高分当成“不好”或低分当成“会涨”；它只描述结构风险。",
    },
    "concentration": {
        "plain": "集中度是“钱有多少压在少数标的或行业上”，常见指标是单票、前三大和前两大行业权重。",
        "example": "前三大持仓合计 60%，说明净值更容易被少数股票影响。",
        "misuse": "只看持仓数量判断分散；10 只同行业股票仍然可能高度集中。",
    },
}


EXPLAIN_EN: dict[str, dict[str, str]] = {
    "pe_ttm": {
        "plain_en": "Price divided by trailing 12-month earnings; how much investors pay for current profit.",
        "example_en": "PE 20x means about 20 years of current earnings, before growth and dividends.",
        "misuse_en": "Treating a low PE as cheap when earnings are cyclical or about to fall.",
    },
    "pb": {
        "plain_en": "Price relative to book value per share; common for banks, insurers and asset-heavy firms.",
        "example_en": "PB 0.8 means market value is below book value, not automatically a bargain.",
        "misuse_en": "Comparing PB across industries without checking asset quality and ROE.",
    },
    "dividend_yield": {
        "plain_en": "Cash dividends over the past 12 months divided by current price.",
        "example_en": "A 4% yield means dividends were about 4% of market value at the current price.",
        "misuse_en": "Assuming a high yield is safe; a falling price or one-off payout can inflate it.",
    },
    "roe": {
        "plain_en": "Net profit attributable to shareholders divided by equity; profit efficiency on shareholder capital.",
        "example_en": "ROE 20% means about 20 yuan of profit per 100 yuan of book equity.",
        "misuse_en": "Ignoring leverage or one-off gains behind a high ROE.",
    },
    "gross_margin": {
        "plain_en": "Revenue minus cost of goods sold, divided by revenue; pricing power and cost control.",
        "example_en": "90% gross margin leaves 90 yuan of gross profit per 100 yuan of revenue, before expenses and tax.",
        "misuse_en": "Treating high gross margin as a moat without checking expenses, turnover and retention.",
    },
    "net_margin": {
        "plain_en": "Net profit divided by revenue; what remains after costs, expenses and tax.",
        "example_en": "A 10% net margin leaves 10 yuan of net profit per 100 yuan of revenue.",
        "misuse_en": "Judging a single quarter without industry norms and one-off items.",
    },
    "free_cash_flow": {
        "plain_en": "Operating cash flow minus capital expenditure; cash the business can freely deploy.",
        "example_en": "10bn operating cash flow minus 4bn capex leaves about 6bn free cash flow.",
        "misuse_en": "Assuming negative FCF is always bad; heavy investment can justify it temporarily.",
    },
    "operating_cash_flow": {
        "plain_en": "Net cash generated by daily operations; the cash content of accounting profit.",
        "example_en": "8bn net profit but 3bn operating cash flow means part of profit has not turned into cash.",
        "misuse_en": "Ignoring receivables, inventory and revenue-recognition changes behind the gap.",
    },
    "revenue_yoy": {
        "plain_en": "Revenue growth versus the same period last year.",
        "example_en": "+12% revenue YoY means this period's revenue is 12% higher than a year ago.",
        "misuse_en": "Comparing growth without checking the base, acquisitions or price changes.",
    },
    "profit_yoy": {
        "plain_en": "Net profit growth versus the same period last year.",
        "example_en": "-8% profit YoY means attributable net profit is 8% lower than a year ago.",
        "misuse_en": "Reading high growth from a low base as durable.",
    },
    "max_drawdown": {
        "plain_en": "Largest peak-to-trough decline; a measure of holding experience and downside risk.",
        "example_en": "A fall from 100 to 70 is a -30% max drawdown.",
        "misuse_en": "Using past drawdown as a forecast of future losses.",
    },
    "volatility": {
        "plain_en": "How widely returns swing, usually annualized standard deviation.",
        "example_en": "25% annualized volatility describes the historical range, not future return.",
        "misuse_en": "Treating low volatility as low risk; liquidity and tail risk may not show up here.",
    },
    "beta": {
        "plain_en": "Sensitivity to the market: 1 moves roughly with it, above 1 usually swings more.",
        "example_en": "Beta 1.2 means a 1% market move was associated with about 1.2% average move historically.",
        "misuse_en": "Using beta as a price forecast; it describes historical relative movement only.",
    },
    "turnover": {
        "plain_en": "How actively a stock trades, measured against free-float shares.",
        "example_en": "5% turnover means about 5% of free-float shares traded that day.",
        "misuse_en": "Equating high turnover with a better outlook; it can reflect speculative trading.",
    },
    "volume_ratio": {
        "plain_en": "Current volume versus a recent average; shows whether trading is unusually heavy.",
        "example_en": "A ratio of 2 means volume is about twice the recent average.",
        "misuse_en": "Looking at volume without price direction; heavy selling and heavy buying differ.",
    },
    "sharpe": {
        "plain_en": "Excess return per unit of volatility; compares risk-adjusted performance.",
        "example_en": "Sharpe 1 means excess return roughly matches the volatility taken.",
        "misuse_en": "Comparing Sharpe across strategies, frequencies or benchmarks without adjustment.",
    },
    "annual_return": {
        "plain_en": "A return converted to a one-year pace for comparison across horizons.",
        "example_en": "10% in half a year is roughly 21% annualized (compounded, not a forecast).",
        "misuse_en": "Treating a short-sample annualized number as sustainable.",
    },
    "alpha": {
        "plain_en": "Excess return after removing the market move; what the strategy added on its own.",
        "example_en": "Market +10%, strategy +13% with beta 1 gives roughly +3% alpha.",
        "misuse_en": "Calling beta/style exposure alpha.",
    },
    "risk_score": {
        "plain_en": "A 0-100 structural risk score weighting concentration, sector, look-through, correlation, valuation and turnover cost.",
        "example_en": "A higher score means a more concentrated structure, not a prediction of loss.",
        "misuse_en": "Reading a high score as 'bad' or a low score as 'will rise'.",
    },
    "concentration": {
        "plain_en": "How much money sits in a few names or sectors; top holdings and top sectors are common measures.",
        "example_en": "Top three holdings at 60% means NAV is more sensitive to a few stocks.",
        "misuse_en": "Judging diversification by the number of holdings alone; ten same-sector names can still be concentrated.",
    },
}


# 展开区：公式、算例、常见误读、相近概念、产品位置。定义仍只来自词库。
DETAIL: dict[str, dict[str, Any]] = {
    "sharpe": {
        "formula": "S = (Rp − Rf) ÷ σp",
        "formula_vars": "Rp 年化组合收益、Rf 无风险利率、σp 年化波动率。",
        "calc_example": "年化 12%、无风险 2%、波动 15% → (12−2)÷15 = 0.67",
        "misreads": [
            {"myth": "高夏普不等于高收益", "why": "低波动策略天然夏普高，但绝对收益可能很低。"},
            {"myth": "短样本的夏普可信", "why": "3 个月算出 2.0，拉长到 3 年通常明显回落。"},
            {"myth": "加杠杆后还能直接比", "why": "夏普理论上不变，但实际承担的波动和回撤变了。"},
        ],
        "compare": [
            {"term": "夏普比率", "denominator": "全部波动", "when": "收益接近正态分布"},
            {"term": "索提诺比率", "denominator": "只算下行波动", "when": "更关注亏损"},
            {"term": "信息比率", "denominator": "跟踪误差", "when": "与基准比较"},
            {"term": "卡玛比率", "denominator": "最大回撤", "when": "关注极端回撤"},
        ],
        "where": "组合页 · 风险体检；回测报告 · 收益表现",
    },
    "sortino": {
        "formula": "Sortino = (Rp − Rf) ÷ σd",
        "formula_vars": "Rp 年化收益、Rf 无风险利率、σd 只统计低于目标收益的下行波动。",
        "calc_example": "年化 12%、无风险 2%、下行波动 10% → (12−2)÷10 = 1.0",
        "misreads": [
            {"myth": "索提诺一定比夏普高", "why": "上行波动被剔除，通常更高，但两者口径不同，不能横向替代。"},
            {"myth": "只看一个区间就下结论", "why": "样本区间不同，下行波动差异很大。"},
        ],
        "compare": [
            {"term": "夏普比率", "denominator": "全部波动", "when": "收益接近正态分布"},
            {"term": "索提诺比率", "denominator": "下行波动", "when": "更在意亏损"},
            {"term": "卡玛比率", "denominator": "最大回撤", "when": "关注极端回撤"},
        ],
        "where": "回测报告 · 风险指标",
    },
    "information_ratio": {
        "formula": "IR = (Rp − Rb) ÷ TE",
        "formula_vars": "Rp 组合年化收益、Rb 基准年化收益、TE 跟踪误差。",
        "calc_example": "年化超额 4%、跟踪误差 5% → 4÷5 = 0.8",
        "misreads": [
            {"myth": "换基准后还直接比", "why": "信息比率依赖基准，基准不同结论不可比。"},
            {"myth": "IR 高就是选股能力强", "why": "风格暴露和行业偏离也会贡献超额。"},
        ],
        "compare": [
            {"term": "信息比率", "denominator": "跟踪误差", "when": "与基准比较"},
            {"term": "夏普比率", "denominator": "全部波动", "when": "看绝对风险调整"},
        ],
        "where": "回测报告 · 相对基准表现",
    },
    "calmar": {
        "formula": "Calmar = 年化收益 ÷ |最大回撤|",
        "formula_vars": "分子为年化收益，分母取历史最大回撤的绝对值。",
        "calc_example": "年化 18%、最大回撤 −24% → 18÷24 = 0.75",
        "misreads": [
            {"myth": "回撤小就一定好", "why": "样本太短时最大回撤被低估，卡玛会虚高。"},
            {"myth": "卡玛高可以忽略修复时间", "why": "回撤修复可能很长，体验和卡玛不是一回事。"},
        ],
        "compare": [
            {"term": "卡玛比率", "denominator": "最大回撤", "when": "关注极端回撤"},
            {"term": "夏普比率", "denominator": "全部波动", "when": "看整体波动"},
        ],
        "where": "回测报告 · 收益回撤",
    },
    "pe_ttm": {
        "formula": "PE(TTM) = 总市值 ÷ 过去 12 个月归母净利润",
        "formula_vars": "TTM 为滚动 12 个月；亏损时 PE 为负或不可用。",
        "calc_example": "市值 200 亿、TTM 净利 10 亿 → PE = 20 倍",
        "misreads": [
            {"myth": "低 PE 就是便宜", "why": "周期行业盈利在顶点时 PE 反而很低，盈利下修后会被动抬升。"},
            {"myth": "亏损公司的 PE 是 0", "why": "亏损时 PE 为负或不可计算，不能参与估值比较。"},
        ],
        "compare": [
            {"term": "市盈率", "denominator": "净利润", "when": "盈利稳定"},
            {"term": "市净率", "denominator": "净资产", "when": "重资产或周期行业"},
            {"term": "股息率", "denominator": "股价", "when": "看现金回报"},
        ],
        "where": "个股透视 · 估值；条件选股 · PE 分位",
    },
    "pb": {
        "formula": "PB = 总市值 ÷ 归母净资产",
        "formula_vars": "净资产为最新报告期归母权益；轻资产公司账面价值参考意义较弱。",
        "calc_example": "市值 80 亿、净资产 100 亿 → PB = 0.8 倍",
        "misreads": [
            {"myth": "PB 低于 1 就是捡漏", "why": "资产可能减值，低 PB 也可能是市场对资产质量的折价。"},
            {"myth": "跨行业直接比 PB", "why": "银行与制造业的资产结构差异很大。"},
        ],
        "compare": [
            {"term": "市净率", "denominator": "净资产", "when": "银行、地产等重资产"},
            {"term": "市盈率", "denominator": "净利润", "when": "盈利稳定"},
            {"term": "净资产收益率", "denominator": "净资产", "when": "看资产使用效率"},
        ],
        "where": "个股透视 · 估值",
    },
    "roe": {
        "formula": "ROE = 归母净利润 ÷ 归母净资产",
        "formula_vars": "分母通常取期初期末平均净资产；高杠杆会抬高 ROE。",
        "calc_example": "净利 20 亿、净资产 100 亿 → ROE = 20%",
        "misreads": [
            {"myth": "ROE 越高越好", "why": "靠高负债或一次性收益抬高的 ROE 质量要打折。"},
            {"myth": "单年 ROE 可以代表长期", "why": "周期和会计处理会让单年数字失真，应看 3–5 年趋势。"},
        ],
        "compare": [
            {"term": "净资产收益率", "denominator": "净资产", "when": "看股东资本效率"},
            {"term": "毛利率", "denominator": "营业收入", "when": "看产品定价"},
            {"term": "净利率", "denominator": "营业收入", "when": "看最终盈利"},
        ],
        "where": "个股透视 · 财务；条件选股 · ROE",
    },
    "max_drawdown": {
        "formula": "MDD = min(净值 ÷ 历史峰值 − 1)",
        "formula_vars": "按日或按周净值计算；区间选择会显著影响结果。",
        "calc_example": "净值从 1.00 跌到 0.70 → 最大回撤 = −30%",
        "misreads": [
            {"myth": "历史最大回撤就是未来上限", "why": "未来可能出现更大的回撤，历史只描述发生过的情况。"},
            {"myth": "只看回撤不看修复时间", "why": "同样 −30%，修复 3 个月和 3 年体验完全不同。"},
        ],
        "compare": [
            {"term": "最大回撤", "denominator": "历史峰值", "when": "看极端风险"},
            {"term": "波动率", "denominator": "收益标准差", "when": "看日常波动"},
        ],
        "where": "组合页 · 风险体检；回测报告 · 收益表现",
    },
    "volatility": {
        "formula": "σ = 日收益标准差 × √252（年化）",
        "formula_vars": "252 为一年交易日数；不同频率需先统一再比较。",
        "calc_example": "日波动 1.9% → 年化约 1.9%×√252 ≈ 30%",
        "misreads": [
            {"myth": "低波动等于低风险", "why": "流动性风险与尾部风险不一定体现在波动率里。"},
            {"myth": "不同频率的波动直接比", "why": "日频、周频年化口径不同，必须先统一。"},
        ],
        "compare": [
            {"term": "波动率", "denominator": "收益标准差", "when": "看日常波动"},
            {"term": "最大回撤", "denominator": "历史峰值", "when": "看极端风险"},
            {"term": "贝塔", "denominator": "市场波动", "when": "看相对市场敏感度"},
        ],
        "where": "组合页 · 风险体检；回测报告 · 风险指标",
    },
    "beta": {
        "formula": "β = Cov(Rp, Rm) ÷ Var(Rm)",
        "formula_vars": "Rp 标的收益、Rm 市场基准收益；基准与区间会影响结果。",
        "calc_example": "市场涨 1%、标的平均涨 1.3% → Beta 约 1.3",
        "misreads": [
            {"myth": "Beta 能预测涨跌", "why": "它只描述历史相对波动，不包含方向判断。"},
            {"myth": "Beta 是固定属性", "why": "不同市场环境与统计区间下会变化。"},
        ],
        "compare": [
            {"term": "贝塔", "denominator": "市场波动", "when": "看相对敏感度"},
            {"term": "波动率", "denominator": "自身收益标准差", "when": "看自身波动"},
            {"term": "阿尔法", "denominator": "扣除市场后", "when": "看独立贡献"},
        ],
        "where": "个股透视 · 风险；组合页 · 风险体检",
    },
    "alpha": {
        "formula": "α = Rp − [Rf + β × (Rm − Rf)]",
        "formula_vars": "Rp 组合收益、Rf 无风险利率、Rm 市场收益、β 市场敏感度。",
        "calc_example": "组合 13%、市场 10%、β=1、Rf 忽略 → Alpha ≈ 3%",
        "misreads": [
            {"myth": "Alpha 高就是选股强", "why": "风格和行业暴露也会贡献超额，需要看归因。"},
            {"myth": "短期 Alpha 可以外推", "why": "短区间可能只是运气或单一风格。"},
        ],
        "compare": [
            {"term": "阿尔法", "denominator": "扣除市场后", "when": "看独立贡献"},
            {"term": "贝塔", "denominator": "市场波动", "when": "看相对敏感度"},
            {"term": "信息比率", "denominator": "跟踪误差", "when": "与基准比较"},
        ],
        "where": "回测报告 · 收益归因",
    },
    "gross_margin": {
        "formula": "毛利率 = (营业收入 − 营业成本) ÷ 营业收入",
        "formula_vars": "只扣直接成本，不含销售、管理、研发费用与税。",
        "calc_example": "收入 100、成本 40 → 毛利率 60%",
        "misreads": [
            {"myth": "高毛利就是护城河", "why": "还要看费用率、周转和客户留存。"},
            {"myth": "跨行业比毛利率", "why": "软件与零售的成本结构完全不同。"},
        ],
        "compare": [
            {"term": "毛利率", "denominator": "营业收入", "when": "看产品定价"},
            {"term": "净利率", "denominator": "营业收入", "when": "看最终盈利"},
        ],
        "where": "个股透视 · 财务",
    },
    "net_margin": {
        "formula": "净利率 = 净利润 ÷ 营业收入",
        "formula_vars": "已扣成本、费用、税与少数股东损益口径需统一。",
        "calc_example": "收入 100、净利 10 → 净利率 10%",
        "misreads": [
            {"myth": "单季净利率代表全年", "why": "季节性和一次性项目会让单季失真。"},
            {"myth": "净利率高就一定赚钱", "why": "还要看周转和资本占用，回报率由两者共同决定。"},
        ],
        "compare": [
            {"term": "净利率", "denominator": "营业收入", "when": "看最终盈利"},
            {"term": "毛利率", "denominator": "营业收入", "when": "看产品定价"},
            {"term": "净资产收益率", "denominator": "净资产", "when": "看资本效率"},
        ],
        "where": "个股透视 · 财务",
    },
    "dividend_yield": {
        "formula": "股息率 = 过去 12 个月每股分红 ÷ 当前股价",
        "formula_vars": "用现金分红口径；特别分红会抬高当期股息率。",
        "calc_example": "每股分红 1 元、股价 25 元 → 股息率 4%",
        "misreads": [
            {"myth": "高股息一定安全", "why": "股价下跌也会推高股息率，还需看分红可持续性。"},
            {"myth": "把特别分红当常态", "why": "一次性分红不能代表未来现金流。"},
        ],
        "compare": [
            {"term": "股息率", "denominator": "股价", "when": "看现金回报"},
            {"term": "市盈率", "denominator": "净利润", "when": "看盈利估值"},
        ],
        "where": "个股透视 · 分红；条件选股 · 股息率",
    },
    "turnover": {
        "formula": "换手率 = 成交股数 ÷ 流通股本",
        "formula_vars": "用流通股本而非总股本；不同板块口径需一致。",
        "calc_example": "成交 300 万股、流通 1 亿股 → 换手率 3%",
        "misreads": [
            {"myth": "换手越高越好", "why": "过高可能伴随情绪化交易和流动性风险。"},
            {"myth": "跨板块直接比换手", "why": "流通盘和涨跌幅制度不同，基准不一样。"},
        ],
        "compare": [
            {"term": "换手率", "denominator": "流通股本", "when": "看交易活跃度"},
            {"term": "量比", "denominator": "近期均量", "when": "看单日放量"},
        ],
        "where": "个股透视 · 行情；首页 · 行业热度",
    },
    "volume_ratio": {
        "formula": "量比 = 当日成交量 ÷ 过去 5 日平均成交量",
        "formula_vars": "不同软件可能用 5 日或 10 日均量，需确认口径。",
        "calc_example": "当日 200 万股、5 日均量 100 万股 → 量比 2.0",
        "misreads": [
            {"myth": "放量就是好事", "why": "放量下跌和放量上涨含义不同。"},
            {"myth": "单日量比能代表趋势", "why": "事件冲击会造成单日异常放量。"},
        ],
        "compare": [
            {"term": "量比", "denominator": "近期均量", "when": "看单日放量"},
            {"term": "换手率", "denominator": "流通股本", "when": "看交易活跃度"},
        ],
        "where": "个股透视 · 行情",
    },
}


def _with_explain(item: dict[str, Any]) -> dict[str, Any]:
    detail = DETAIL.get(str(item.get("id")), {})
    out = {
        **item,
        **EXPLAIN.get(str(item.get("id")), {}),
        **EXPLAIN_EN.get(str(item.get("id")), {}),
        **detail,
    }
    if not out.get("misreads") and out.get("misuse"):
        out["misreads"] = [{"myth": "常见误读", "why": out["misuse"]}]
    return out


_BRACKETS = re.compile(r"[【】\[\]「」()（）<>《》]")
_PUNCT = re.compile(r"[\s,，。.、；;：:!！?？·\"'“”‘’_/\\|-]+")
_BOUNDARY = re.compile(r"^[【】\[\]「」()（）<>《》\s,，。.、；;：:!！?？·\"'“”‘’]+|"
                       r"[【】\[\]「」()（）<>《》\s,，。.、；;：:!！?？·\"'“”‘’]+$")
_PREFIXES = ("请问一下", "帮我解释一下", "帮我解释", "解释一下", "介绍一下", "什么是", "什么叫", "啥是", "请问", "解释", "介绍")
_SUFFIXES = ("是什么意思", "是啥意思", "的含义是什么", "是什么意思啊", "怎么理解", "怎么算", "怎么看", "有什么用", "是什么", "是多少", "含义", "定义")
_STOP_WORDS = {"率", "比", "值", "数", "额", "线", "的", "了", "吗", "呢", "啊", "是", "什么", "怎么", "如何", "指标", "风险", "意思", "含义"}
_SHORT_ASCII = re.compile(r"^[a-z0-9.+/]{2,3}$")
_ASCII_ONLY = re.compile(r"^[a-z0-9.+/]+$")


def normalize(text: str) -> str:
    """全角→半角、小写、去空格与中英文标点，供匹配使用。"""
    raw = unicodedata.normalize("NFKC", str(text or "")).lower()
    return _PUNCT.sub("", raw)


def extract_query(text: str) -> str:
    """剥掉疑问模板词与括号，只留核心词。"""
    raw = _BRACKETS.sub(" ", str(text or "")).strip()
    raw = _BOUNDARY.sub("", raw)
    changed = True
    while changed:
        changed = False
        for prefix in _PREFIXES:
            if raw.startswith(prefix):
                raw = raw[len(prefix):].strip()
                changed = True
        for suffix in _SUFFIXES:
            if raw.endswith(suffix):
                raw = raw[: -len(suffix)].strip()
                changed = True
        raw = _BOUNDARY.sub("", raw)
    core = normalize(raw)
    return core or normalize(text)


def _levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def _entries() -> list[dict[str, Any]]:
    out = []
    for item in TERMS:
        out.append({
            "item": item,
            "id": normalize(str(item.get("id") or "")),
            "name": normalize(str(item.get("term") or "")),
            "aliases": [normalize(str(x)) for x in item.get("aliases") or [] if normalize(str(x))],
        })
    return out


def _hit(entry: dict[str, Any], layer: int) -> dict[str, Any]:
    return {"matched": _with_explain(entry["item"]), "layer": layer}


def _ambiguous(entries: list[dict[str, Any]], layer: int) -> dict[str, Any] | None:
    ids = {str(x["item"]["id"]) for x in entries}
    if len(ids) <= 1:
        return None
    return {"term": None, "layer": None, "ambiguous": [_with_explain(x["item"]) for x in entries]}


def _suggest(entries: list[dict[str, Any]], q: str, limit: int = 3) -> list[dict[str, Any]]:
    scored = []
    for entry in entries:
        variants = [entry["name"], *entry["aliases"]]
        distance = min((_levenshtein(q, v) for v in variants), default=99)
        common = max((len(set(q) & set(v)) for v in variants), default=0)
        length_gap = min((abs(len(q) - len(v)) for v in variants), default=99)
        scored.append((distance, -common, length_gap, str(entry["item"].get("term") or ""), entry))
    scored.sort(key=lambda x: (x[0], x[1], x[2], x[3]))
    return [_with_explain(x[4]["item"]) for x in scored[:limit]]


def lookup(text: str, *, category: str = "", model_term_id: str | None = None) -> dict[str, Any]:
    """分层匹配：精确 → 别名 → 包含 → 编辑距离 → 模型候选。命中即止。"""
    entries = _entries()
    core = extract_query(text)
    display = str(text or "").strip()
    result: dict[str, Any] = {
        "query": core,
        "display": display,
        "matched": None,
        "layer": None,
        "candidates": [],
    }
    if not core:
        result["candidates"] = [_with_explain(x["item"]) for x in entries[:3]]
        result["message"] = "没有识别到要查的术语，可以输入指标名称或简称。"
        return result

    # 1 精确：词条名或 ID
    exact = [e for e in entries if core in {e["name"], e["id"]}]
    amb = _ambiguous(exact, 1)
    if amb:
        result.update(amb)
        result["candidates"] = amb["ambiguous"]
        result["message"] = "有多个词条同名，请选择："
        return result
    if exact:
        result.update(_hit(exact[0], 1))
        return result

    # 2 别名
    alias_hits = [e for e in entries if core in e["aliases"]]
    amb = _ambiguous(alias_hits, 2)
    if amb:
        result.update(amb)
        result["candidates"] = amb["ambiguous"]
        result["message"] = "有多个词条匹配这个别名，请选择："
        return result
    if alias_hits:
        result.update(_hit(alias_hits[0], 2))
        return result

    # 3 包含：最短 2 字，长词优先；短英文缩写只接受前缀，不做任意包含。
    if len(core) >= 2 and core not in _STOP_WORDS:
        contains: list[tuple[dict[str, Any], int]] = []
        for entry in entries:
            for variant in [entry["name"], *entry["aliases"]]:
                if len(variant) < 2:
                    continue
                if _SHORT_ASCII.match(variant):
                    # PE / ROE / PB 这类短缩写不做任意包含，只允许带中文限定的“PE 分位”这类短语。
                    if not _ASCII_ONLY.match(core) and variant in core:
                        contains.append((entry, len(variant)))
                elif variant in core or core in variant:
                    contains.append((entry, len(variant)))
        if contains:
            best = max(score for _, score in contains)
            top = [entry for entry, score in contains if score == best]
            amb = _ambiguous(top, 3)
            if amb:
                result.update(amb)
                result["candidates"] = amb["ambiguous"]
                result["message"] = "命中了多个词条，请选择："
                return result
            result.update(_hit(top[0], 3))
            return result

    # 4 编辑距离：查询 ≥2 字，别名允许 2 字简称；短英文缩写不走模糊。
    if len(core) >= 2 and not _SHORT_ASCII.match(core):
        best_distance = 99
        best_entries: list[dict[str, Any]] = []
        for entry in entries:
            variants = [v for v in [entry["name"], *entry["aliases"]] if len(v) >= 2]
            distance = min((_levenshtein(core, v) for v in variants), default=99)
            if distance < best_distance:
                best_distance = distance
                best_entries = [entry]
            elif distance == best_distance and distance <= 1:
                best_entries.append(entry)
        if best_distance <= 1 and best_entries:
            amb = _ambiguous(best_entries, 4)
            if amb:
                result.update(amb)
                result["candidates"] = amb["ambiguous"]
                result["message"] = "像是这几个词条，请选择："
                return result
            result.update(_hit(best_entries[0], 4))
            return result

    # 5 模型归一：只接受词库中真实存在的 ID。
    model_key = normalize(str(model_term_id or ""))
    if model_key:
        for entry in entries:
            if entry["id"] == model_key:
                result.update(_hit(entry, 5))
                return result

    candidates = _suggest(entries, core)
    if category:
        same = [x for x in candidates if x.get("category") == category]
        candidates = (same + candidates)[:3]
    result["candidates"] = candidates
    result["message"] = f"没找到「{display or core}」的独立词条，你要找的是不是："
    return result


def list_terms(*, category: str = "", q: str = "") -> dict[str, Any]:
    cat = (category or "").strip()
    needle = normalize(q)
    items = []
    for item in TERMS:
        if cat and item["category"] != cat:
            continue
        if needle:
            haystack = normalize(" ".join(
                [item["term"], item["definition"], *(item.get("aliases") or []),
                 str(item.get("plain") or ""), str(item.get("misuse") or "")]
            ))
            if needle not in haystack:
                continue
        items.append(_with_explain(item))
    return {"items": items, "total": len(items), "categories": list(CATEGORIES)}


def find_term(text: str) -> dict[str, Any] | None:
    """兼容旧调用：返回命中词条，未命中返回 None。"""
    hit = lookup(text)
    result = hit.get("matched")
    if not result:
        candidates = hit.get("candidates") or []
        result = candidates[0] if len(candidates) == 1 else None
    return result


def term_ids() -> list[tuple[str, str]]:
    """给模型归一用的 (id, 名称) 清单，避免模型编造。"""
    return [(str(x["id"]), str(x["term"])) for x in TERMS]
