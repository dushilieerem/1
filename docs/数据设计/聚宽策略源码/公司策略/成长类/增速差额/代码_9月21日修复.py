# ============================================================
# 增速差额策略 —— 完全对齐 BigQuant 版本的聚宽复现版
# 目标：复现 BigQuant 收益（累计平仓盈亏约 5922 万 / 50万本金）
#
# 与 BigQuant bigquant版本.py 逐条对齐的要点：
#  1. 行业池：BigQuant 用申万2021(13行业)；聚宽无 SW2021，用申万2014 同口径映射
#  2. 打分：score = 1.5*市值分位 + 营收增速分位 - 0.3*净利增速分位 - PS3年分位
#  3. 净利口径：扣非净利 TTM 同比 = 归母净利TTM - 非经常性损益（对齐原版 net_profit_deducted_ttm_yoy）
#  4. PS 分位：m_pct_rank(ps_ttm, 1256) ≈ 近60个月末 PS 序列的滚动分位（估值表每日查询）
#  5. 调仓：每日重算 score/候选，每日执行买卖
#  6. 基准资金：每半年(6/15、12/15)更新；单票目标 = 半年基准/5
#  7. 补仓：6/25、12/25
#  8. 买入/卖出条件：与 BigQuant 完全一致
#  9. 费用：买0.0003 + 卖0.0013(含印花税0.001) + 最低5元；开盘价成交
# ============================================================

import pandas as pd
import numpy as np
from datetime import date, timedelta
import warnings
import bisect
warnings.filterwarnings('ignore')

from jqdata import *
from jqdata import finance

# ============================================================
# 行业映射：申万2021(BigQuant) → 申万2014(聚宽 get_industry_stocks)
# ============================================================
ALLOWED_INDUSTRY_CODES = [
    "801010",  # 农林牧渔  (SW2021:110000)
    "801050",  # 有色金属  (SW2021:240000)
    "801080",  # 电子      (SW2021:270000)
    "801880",  # 汽车      (SW2021:280000)
    "801110",  # 家用电器  (SW2021:330000)
    "801120",  # 食品饮料  (SW2021:340000)
    "801140",  # 轻工制造  (SW2021:360000)
    "801150",  # 医药生物  (SW2021:370000)
    "801170",  # 交通运输  (SW2021:420000)
    "801200",  # 商贸零售  (SW2021:450000)
    "801720",  # 建筑装饰  (SW2021:620000)
    "801890",  # 机械设备  (SW2021:640000)
    "801750",  # 计算机    (SW2021:710000)
]

INDUSTRY_NAME_MAP = {
    "801010": "农林牧渔", "801050": "有色金属", "801080": "电子",
    "801880": "汽车", "801110": "家用电器", "801120": "食品饮料",
    "801140": "轻工制造", "801150": "医药生物", "801170": "交通运输",
    "801200": "商贸零售", "801720": "建筑装饰", "801890": "机械设备",
    "801750": "计算机",
}

# ============================================================
# 策略参数（对齐 BigQuant）
# ============================================================
CAPITAL = 500000          # 初始资金；须与聚宽回测设置保持一致
MAX_HOLDINGS = 5          # 持仓上限
MAX_PER_INDUSTRY = 2      # 单行业持仓上限
MAX_SINGLE_POSITION = 0.30  # 单票最大仓位（等额分配时的硬上限）
BUY_COOLDOWN_DAYS = 30    # 买入冷却期（交易日）

# 交易安全参数：兼容聚宽科创板委托规则，并防止买入金额与佣金合计超过可用现金。
STAR_MARKET_PROTECTION_PCT = 0.02
CASH_RESERVE_RATIO = 0.005
BUY_COMMISSION_RATE = 0.0003
MIN_COMMISSION = 5.0
MIN_ORDER_VALUE = 100.0

# ============ 消融实验开关（True=启用该条件，False=关闭） ============
BUY_CONDITIONS = {
    'c1': True,   # 近两年营收TTM增速>净利TTM增速+10%且为正（对齐原版）
    'c2': True,   # 成本/销售费用增速至少一项超过营收增速（去掉研发费用；cost_incr>op_yoy or sale_incr>op_yoy）
    'c3': True,   # PS 近5年分位<10%
    'c4': True,   # 毛利率TTM同比在±20%以内（对齐原版 -0.2<gp_yoy<0.2）
    'c5': True,   # MA60>MA250（对齐原版）
    'c6': False,  # 营收规模+增速筛选（扩展开关，默认关闭=保持原版逻辑）
}
REVENUE_MIN_TTM = 5e8      # c6 TTM营收下限（元）；0=不限制
REVENUE_GROWTH_MIN = 0.15  # c6 营收增速下限
SELL_CONDITIONS = {
    'sell_ps_high': False, # 原策略未启用；仅保留为可选的估值止盈开关
    'sell_ps_nt': True,    # PS>50%分位 且 净利TTM增速>=50% 卖出（对齐原版平仓条件3）
    'sell4': True,         # 移动止损/动态止盈：盈利>=1%启动，开盘价较持有期最高价回落>=10%清仓（对齐原版平仓条件4）
    'sell5': True,         # 基本面恶化：营收/净利/毛利率TTM同比均<-50% 卖出（对齐原版平仓条件5）
    'sell6': True,         # 趋势恶化：MA60<MA250 卖出（对齐原版平仓条件6）
}
SELL4_MIN_PROFIT = 0.01  # 移动止损启动阈值：盈利>=1%（对齐原版 current_open > buy_price*1.01）
SELL4_DROP = 0.10        # 移动止损回撤阈值：开盘价较持有期最高价回落>=10%（对齐原版 drop_pct>=0.10）
HALF_UPDATE_DAYS = [(6, 15), (12, 15)]   # 半年基准资金更新日
REBALANCE_DAYS = [(6, 25), (12, 25)]     # 固定调仓补仓日
PS_HIST_MONTHS = 60       # PS 历史窗口 ≈ 1256 交易日（约5年）
PS_HIST_DAYS = 1256       # PS 历史每日窗口（对齐原版 m_pct_rank(ps_ttm, 1256)）
LIST_DAYS_MIN = 756       # 上市天数下限（约3年）


def _to_date(value):
    """把聚宽可能返回的 date/datetime/Timestamp 统一成 datetime.date。"""
    if value is None:
        return None
    if isinstance(value, date) and not hasattr(value, 'date'):
        return value
    if hasattr(value, 'date'):
        return value.date()
    return pd.Timestamp(value).date()


def _next_trade_day(target):
    """返回不早于 target 的首个回测交易日；区间外返回 None，避免节假日死循环。"""
    target = _to_date(target)
    idx = bisect.bisect_left(g.trading_days, target)
    return g.trading_days[idx] if idx < len(g.trading_days) else None


def _valid_price(value):
    try:
        value = float(value)
        return np.isfinite(value) and value > 0
    except Exception:
        return False


def _current_snapshot(current_data, stock):
    """聚宽当前行情是按需加载对象，必须直接按代码读取，不能先做 in 判断。"""
    try:
        return current_data[stock]
    except Exception as exc:
        log.warning('[行情跳过] %s 当前行情不可用：%s' % (stock, exc))
        return None


def _is_star_market(stock):
    return str(stock).split('.')[0].startswith(('688', '689'))


def _star_market_style(stock, is_buy, snapshot):
    """为科创板市价委托附加方向正确的2%保护限价。"""
    if not _is_star_market(stock):
        return None
    if snapshot is None or not _valid_price(snapshot.last_price):
        return None
    last_price = float(snapshot.last_price)
    if is_buy:
        protect_price = last_price * (1.0 + STAR_MARKET_PROTECTION_PCT)
        if _valid_price(snapshot.high_limit):
            protect_price = min(protect_price, float(snapshot.high_limit))
    else:
        protect_price = last_price * (1.0 - STAR_MARKET_PROTECTION_PCT)
        if _valid_price(snapshot.low_limit):
            protect_price = max(protect_price, float(snapshot.low_limit))
    protect_price = round(protect_price, 2)
    # 聚宽文档明确支持限价风格；保护价本质也是限价，避免把价格误传给市价风格。
    return LimitOrderStyle(protect_price) if _valid_price(protect_price) else None


def safe_order_target_value(context, stock, target_value, current_data=None):
    """安全目标市值委托：检查停牌、涨跌停，并处理科创板保护限价。"""
    current_data = current_data or get_current_data()
    snapshot = _current_snapshot(current_data, stock)
    if snapshot is None or snapshot.paused or not _valid_price(snapshot.last_price):
        log.warning('[交易跳过] %s 停牌或价格无效' % stock)
        return None
    position = context.portfolio.positions[stock] if stock in context.portfolio.positions else None
    current_value = 0.0 if position is None else float(position.total_amount) * float(snapshot.last_price)
    is_buy = float(target_value) > current_value
    if is_buy and _valid_price(snapshot.high_limit) and snapshot.last_price >= snapshot.high_limit:
        log.warning('[交易跳过] %s 已涨停，无法买入' % stock)
        return None
    if not is_buy and _valid_price(snapshot.low_limit) and snapshot.last_price <= snapshot.low_limit:
        log.warning('[交易跳过] %s 已跌停，无法卖出' % stock)
        return None
    style = _star_market_style(stock, is_buy, snapshot)
    if _is_star_market(stock) and style is None:
        log.warning('[交易跳过] %s 无法生成科创板保护限价' % stock)
        return None
    if style is None:
        return order_target_value(stock, target_value)
    return order_target_value(stock, target_value, style=style)


def _safe_buy_value(requested_value, available_cash):
    """将可用现金换算为包含现金缓冲与预计佣金后的最大证券买入额。"""
    requested_value = max(0.0, float(requested_value))
    available_cash = max(0.0, float(available_cash))
    cash_reserve = max(MIN_COMMISSION, available_cash * CASH_RESERVE_RATIO)
    max_value = max(0.0, (available_cash - cash_reserve - MIN_COMMISSION) /
                    (1.0 + BUY_COMMISSION_RATE))
    return min(requested_value, max_value)


def safe_order_value(context, stock, requested_value, current_data=None, available_cash=None):
    """安全金额买入；返回(order, 实际委托市值, 委托后估算剩余现金)。"""
    current_data = current_data or get_current_data()
    snapshot = _current_snapshot(current_data, stock)
    if snapshot is None or snapshot.paused or not _valid_price(snapshot.last_price):
        return None, 0.0, max(0.0, float(available_cash or 0.0))
    if _valid_price(snapshot.high_limit) and snapshot.last_price >= snapshot.high_limit:
        log.warning('[交易跳过] %s 已涨停，无法买入' % stock)
        return None, 0.0, max(0.0, float(available_cash or 0.0))
    if available_cash is None:
        available_cash = context.portfolio.available_cash
    safe_value = _safe_buy_value(requested_value, available_cash)
    if safe_value < MIN_ORDER_VALUE:
        log.warning('[交易跳过] %s 可安全使用资金不足：%.2f' % (stock, safe_value))
        return None, 0.0, max(0.0, float(available_cash))
    style = _star_market_style(stock, True, snapshot)
    if _is_star_market(stock) and style is None:
        log.warning('[交易跳过] %s 无法生成科创板保护限价' % stock)
        return None, 0.0, max(0.0, float(available_cash))
    order = order_value(stock, safe_value) if style is None else order_value(stock, safe_value, style=style)
    fee = max(MIN_COMMISSION, safe_value * BUY_COMMISSION_RATE)
    remaining_cash = max(0.0, float(available_cash) - safe_value - fee)
    return order, safe_value, remaining_cash

def initialize(context):
    set_option('use_real_price', True)
    set_option('avoid_future_data', True)
    set_benchmark('000300.XSHG')
    # 费用对齐 BigQuant PerOrder(buy_cost=0.0003, sell_cost=0.0013, min_cost=5)
    # 卖出 0.0013 = 印花税0.001 + 佣金0.0003
    set_order_cost(OrderCost(open_tax=0, close_tax=0.001, open_commission=0.0003,
                             close_commission=0.0003, close_today_commission=0,
                             min_commission=5), type='stock')
    set_slippage(FixedSlippage(0))

    g.max_holdings = MAX_HOLDINGS
    g.max_per_industry = MAX_PER_INDUSTRY
    g.buy_cooldown_days = BUY_COOLDOWN_DAYS
    g.last_buy_dates = {}       # instrument -> 上次买入日期(str)
    g.buy_prices = {}           # instrument -> 买入价(open)
    g.highest_prices = {}       # instrument -> 持有期最高价(当日 high，移动止损跟踪)
    g.industry_holdings = {}    # 行业代码 -> 持仓数
    g.half_yearly_base_capital = CAPITAL
    g.current_half_year = None
    # 交易日列表初始化一次：起点提前近60个月（PS 历史月末采样需要回测前的历史交易日，否则 ps_3y 分位全为默认0.5）
    run_start = _to_date(context.run_params.start_date)
    run_end = _to_date(context.run_params.end_date)
    g.run_end_date = run_end
    trade_days = get_trade_days(
        start_date=run_start - timedelta(days=PS_HIST_MONTHS * 31),
        end_date=run_end)
    g.trading_days = sorted({_to_date(d) for d in trade_days})

    g.factor_df = None          # 每日更新的因子表（含财务/MA/PS历史/估值）
    g.industry_cache_date = None  # 行业成分缓存日期（低频变化，7天复用）
    g.securities_cache = None     # 上市信息缓存
    g.securities_cache_date = None
    g.industry_map = {}         # code -> 行业
    g.universe_date = None
    g.fin_cache = None          # 利润表缓存（首次全量，之后增量追加新财报）
    g.last_pub_date = None      # 已处理的最新财报公告日
    g.ps_hist = None            # (旧PS月度缓存，不再使用)
    g.ps_hist_date = None
    g.ps_series = None          # code -> list(每日PS值，近1256交易日，PS=close÷每股营收TTM)
    g.ps_dates = None           # code -> list(对应日期)
    # 聚宽因子库 jqfactor（官方 TTM 因子，对齐原版 revenue_ps_ttm_yoy / gross_profit_rate_ttm_yoy 等）
    g.jq_factors = ['operating_revenue_growth_rate', 'np_parent_company_owners_growth_rate',
                    'np_parent_company_owners_ttm', 'non_recurring_gain_loss',
                    'DEGM', 'operating_cost_ttm', 'sale_expense_ttm',
                    'total_operating_revenue_per_share_ttm']  # 每股营业总收入TTM，对齐原版 revenue_ps_ttm_yoy
    g.jq_cache = None            # code -> dict(财务因子)，每日更新（当日最新，跟随财报披露）
    g.jq_cache_date = None
    g.jq_hist = None             # code -> dict(1年前/2年前 TTM 值)，季度缓存（历史值固定）
    g.jq_hist_date = None
    g.trade_phase = None

    # 每日更新因子（财务用缓存+增量财报，估值/价格每日刷新，对齐 BigQuant 每日重算）
    run_daily(build_factors, time='09:20')
    # 与其他策略统一：先卖后买，给卖单留出成交和资金释放时间。
    run_daily(execute_sells, time='09:30')
    run_daily(execute_buys, time='09:40')

    # 校验账户初始资金与策略假设一致（仓位正确的前提）
    log.info(f"账户初始资金 = {context.portfolio.portfolio_value:.0f}，策略假设 CAPITAL = {CAPITAL}。"
             f"若不一致（账户<CAPITAL），请修改【回测设置-初始资金】为 {CAPITAL}，否则单票{CAPITAL // g.max_holdings}元会把资金用光、仓位失衡")


# ============================================================
# 工具函数
# ============================================================
def get_allowed_industry_stocks(data_date):
    """获取13个允许行业的成分股，去重并返回行业映射。
    缓存：行业成分分类低频变化，7天内复用（逻辑等价，砍掉每日13次 get_industry_stocks）"""
    if g.industry_map and g.industry_cache_date is not None and \
       (data_date - g.industry_cache_date).days < 7:
        return list(g.industry_map.keys()), g.industry_map
    all_stocks = []
    industry_map = {}
    for ind_code in ALLOWED_INDUSTRY_CODES:
        try:
            stocks = get_industry_stocks(ind_code, date=data_date)
            if stocks:
                all_stocks.extend(stocks)
                for s in stocks:
                    industry_map[s] = ind_code
        except:
            continue
    # set 直接转 list 的顺序不稳定，会使同分候选在不同运行间出现差异。
    all_stocks = sorted(set(all_stocks))
    g.industry_map = industry_map
    g.industry_cache_date = data_date
    return all_stocks, industry_map


def filter_stock_health(context, stock_list, data_date):
    """健康筛选：去ST、停牌、上市天数>756(约3年)、PE>0（对齐 BigQuant SQL 过滤）
    顺序优化：先按上市天数过滤（本地计算免费）缩小集合，再查 ST/停牌，减少 get_price 查询量。逻辑等价。"""
    if not stock_list:
        return []
    # 上市信息缓存（7天；start_date 不变，逻辑等价，避免每日 get_all_securities）
    if g.securities_cache is None or g.securities_cache_date is None or \
       (data_date - g.securities_cache_date).days >= 7:
        g.securities_cache = get_all_securities(['stock'], date=data_date)
        g.securities_cache_date = data_date
    securities = g.securities_cache
    # 上市满 756 天（list_days > 756）—— 本地计算，最先做以缩小后续查询集合
    sub = []
    for s in stock_list:
        if s not in securities.index:
            continue
        start_date = securities.loc[s, 'start_date']
        if isinstance(start_date, pd.Timestamp):
            start_date = start_date.date()
        if (data_date - start_date).days > LIST_DAYS_MIN:
            sub.append(s)
    if not sub:
        return []
    # ST（仅对上市满期的子集）
    st_data = get_extras('is_st', sub, start_date=data_date, end_date=data_date)
    st_row = st_data.iloc[-1] if st_data is not None and not st_data.empty else pd.Series(dtype=bool)
    st_list = [s for s in sub if bool(st_row.get(s, False))]
    # 停牌（批量，仅对上市满期且非ST的子集）
    candidates = [s for s in sub if s not in st_list]
    suspended = []
    batch_size = 800
    for i in range(0, len(candidates), batch_size):
        batch = candidates[i:i + batch_size]
        try:
            df_p = get_price(batch, end_date=data_date, count=1, frequency='daily',
                             fields=['paused'], skip_paused=False, panel=False)
            if df_p is not None and not df_p.empty:
                suspended.extend(df_p[df_p['paused'] == 1]['code'].tolist())
        except:
            continue
    suspended = set(suspended)
    pool = [s for s in candidates if s not in suspended]
    return pool  # PE>0 过滤已移到 build_factors，与估值查询合并（省一次全池查询，提速）


def _normalize_income_rows(df, data_date=None):
    """统一财报日期，并只保留当时已公告的每个报告期最新版本。"""
    if df is None or df.empty:
        return df
    df = df.copy()
    df['pub_date'] = pd.to_datetime(df['pub_date'], errors='coerce')
    df['end_date'] = pd.to_datetime(df['end_date'], errors='coerce')
    df = df.dropna(subset=['code', 'pub_date', 'end_date'])
    if data_date is not None:
        df = df[df['pub_date'].dt.date <= _to_date(data_date)]
    # 同一报告期可能存在更正稿；只能使用截至 data_date 已披露的最新一版。
    df = df.sort_values(['code', 'end_date', 'pub_date'], kind='mergesort')
    return df.drop_duplicates(['code', 'end_date'], keep='last').reset_index(drop=True)


def fetch_income_statement(pool, data_date):
    """分页获取利润表（最近5年，用于 TTM 计算），返回合并后的 DataFrame"""
    all_fin = []
    offset = 0
    # finance.run_query 单次返回有平台上限；用3000分页兼容不同版本的限制。
    page_size = 3000
    while True:
        q = query(
            finance.STK_INCOME_STATEMENT.code,
            finance.STK_INCOME_STATEMENT.total_operating_revenue,
            finance.STK_INCOME_STATEMENT.operating_cost,
            finance.STK_INCOME_STATEMENT.np_parent_company_owners,
            finance.STK_INCOME_STATEMENT.sale_expense,
            finance.STK_INCOME_STATEMENT.administration_expense,
            finance.STK_INCOME_STATEMENT.financial_expense,
            finance.STK_INCOME_STATEMENT.pub_date,
            finance.STK_INCOME_STATEMENT.end_date,
        ).filter(
            finance.STK_INCOME_STATEMENT.code.in_(pool),
            finance.STK_INCOME_STATEMENT.report_type == 0,
            finance.STK_INCOME_STATEMENT.pub_date <= data_date,
            finance.STK_INCOME_STATEMENT.end_date >= (data_date - timedelta(days=4 * 366)),
            finance.STK_INCOME_STATEMENT.end_date <= data_date,
        ).order_by(
            finance.STK_INCOME_STATEMENT.code.asc(),
            finance.STK_INCOME_STATEMENT.end_date.desc(),
            finance.STK_INCOME_STATEMENT.pub_date.desc(),
        ).limit(page_size).offset(offset)
        batch = finance.run_query(q)
        if batch.empty:
            break
        all_fin.append(batch)
        offset += page_size
        if len(batch) < page_size:
            break
    if not all_fin:
        return None
    df = pd.concat(all_fin, ignore_index=True)
    df = df.rename(columns={
        'total_operating_revenue': 'operating_revenue',
        'np_parent_company_owners': 'net_profit',
    })
    return _normalize_income_rows(df, data_date)


def fetch_incremental_income(pool, data_date, last_pub):
    """增量拉取 pub_date > last_pub 的新财报（每日调用，量小）"""
    if last_pub is None:
        return None
    last_pub = _to_date(last_pub)
    all_fin = []
    offset = 0
    page_size = 3000
    while True:
        q = query(
            finance.STK_INCOME_STATEMENT.code,
            finance.STK_INCOME_STATEMENT.total_operating_revenue,
            finance.STK_INCOME_STATEMENT.operating_cost,
            finance.STK_INCOME_STATEMENT.np_parent_company_owners,
            finance.STK_INCOME_STATEMENT.sale_expense,
            finance.STK_INCOME_STATEMENT.administration_expense,
            finance.STK_INCOME_STATEMENT.financial_expense,
            finance.STK_INCOME_STATEMENT.pub_date,
            finance.STK_INCOME_STATEMENT.end_date,
        ).filter(
            finance.STK_INCOME_STATEMENT.code.in_(pool),
            finance.STK_INCOME_STATEMENT.report_type == 0,
            finance.STK_INCOME_STATEMENT.pub_date > last_pub,
            finance.STK_INCOME_STATEMENT.pub_date <= data_date,
            finance.STK_INCOME_STATEMENT.end_date >= (data_date - timedelta(days=4 * 366)),
            finance.STK_INCOME_STATEMENT.end_date <= data_date,
        ).order_by(
            finance.STK_INCOME_STATEMENT.code.asc(),
            finance.STK_INCOME_STATEMENT.end_date.desc(),
            finance.STK_INCOME_STATEMENT.pub_date.desc(),
        ).limit(page_size).offset(offset)
        batch = finance.run_query(q)
        if batch is None or batch.empty:
            break
        all_fin.append(batch)
        offset += page_size
        if len(batch) < page_size:
            break
    if not all_fin:
        return None
    df = pd.concat(all_fin, ignore_index=True)
    df = df.rename(columns={
        'total_operating_revenue': 'operating_revenue',
        'np_parent_company_owners': 'net_profit',
    })
    return _normalize_income_rows(df, data_date)


def compute_ttm_factors(fin_cache, industry_map):
    """从利润表缓存计算 TTM 财务因子（营收/净利/毛利率/费用增速 + 去年增速）"""
    df_fin = _normalize_income_rows(fin_cache)
    # 关键：按 end_date 降序排列，保证 quarter=0 是最新报告期（TTM 计算的基准）
    df_fin = df_fin.sort_values(['code', 'end_date'], ascending=[True, False])
    df_fin = df_fin.groupby('code').head(16).reset_index(drop=True)
    df_fin['quarter'] = df_fin.groupby('code').cumcount()  # 0=最新
    pivot_cols = ['operating_revenue', 'operating_cost', 'net_profit',
                  'sale_expense', 'administration_expense', 'financial_expense']
    df_pivot = df_fin.pivot(index='code', columns='quarter', values=pivot_cols)
    df_pivot.columns = [f'{c[0]}_{c[1]}' for c in df_pivot.columns]
    q0m = df_fin.groupby('code')['end_date'].first().dt.month.rename('q0_month')
    df_all = df_pivot.join(q0m, how='inner')
    df_all['industry'] = df_all.index.map(industry_map)

    # 对齐 BigQuant 原版口径：
    #  - op_yoy/nt_yoy/last_year_op/last_year_nt/gp_yoy 用 TTM 同比
    #    （对应原版 revenue_ps_ttm_yoy / net_profit_deducted_ttm_yoy / gross_profit_rate_ttm_yoy）
    #  - cost_incr/sale_incr 用「最新报告期累计 vs 去年同期累计」同比
    #    （对应原版 *_lf_yoy；聚宽无该因子表，用累计同比近似）
    annual_map = {3: 1, 6: 2, 9: 3, 12: 4}

    def calc_ttm(field):
        f0 = df_all[f'{field}_0']
        f4 = df_all[f'{field}_4'] if f'{field}_4' in df_all else pd.Series(np.nan, index=df_all.index)
        f8 = df_all[f'{field}_8'] if f'{field}_8' in df_all else pd.Series(np.nan, index=df_all.index)
        f12 = df_all[f'{field}_12'] if f'{field}_12' in df_all else pd.Series(np.nan, index=df_all.index)
        now = pd.Series(np.nan, index=df_all.index)
        py = pd.Series(np.nan, index=df_all.index)
        y2 = pd.Series(np.nan, index=df_all.index)
        for qm, ai in annual_map.items():
            mask = (df_all['q0_month'] == qm)
            now[mask] = f0[mask] + df_all[f'{field}_{ai}'][mask] - f4[mask]
            py[mask] = f4[mask] + df_all[f'{field}_{ai+4}'][mask] - f8[mask]
            y2[mask] = f8[mask] + df_all[f'{field}_{ai+8}'][mask] - f12[mask]
        return now, py, y2

    def lf_col(field, idx):
        return df_all[f'{field}_{idx}'] if f'{field}_{idx}' in df_all else pd.Series(np.nan, index=df_all.index)

    def yoy(now, py):
        return (now - py) / py.replace(0, np.nan)

    rev_now, rev_py, rev_2y = calc_ttm('operating_revenue')
    cost_now, cost_py, _ = calc_ttm('operating_cost')
    nt_now, nt_py, nt_2y = calc_ttm('net_profit')

    df_all['op_yoy'] = yoy(rev_now, rev_py)          # 营收 TTM 同比（对齐 revenue_ps_ttm_yoy）
    df_all['last_year_op'] = yoy(rev_py, rev_2y)     # 去年营收 TTM 同比（对齐 lag 252）
    df_all['nt_yoy'] = yoy(nt_now, nt_py)            # 净利 TTM 同比（对齐 net_profit_deducted_ttm_yoy；聚宽无扣非，用 net_profit 近似）
    df_all['last_year_nt'] = yoy(nt_py, nt_2y)       # 去年净利 TTM 同比（对齐 lag 252）
    df_all['cost_incr'] = yoy(lf_col('operating_cost', 0), lf_col('operating_cost', 4))  # 成本最新报告期同比
    df_all['sale_incr'] = yoy(lf_col('sale_expense', 0), lf_col('sale_expense', 4))      # 销售费用最新报告期同比
    # 毛利率 TTM 同比（对齐 gross_profit_rate_ttm_yoy）
    gm_now = (rev_now - cost_now) / rev_now.replace(0, np.nan)
    gm_py = (rev_py - cost_py) / rev_py.replace(0, np.nan)
    df_all['gp_yoy'] = (gm_now - gm_py) / gm_py.replace(0, np.nan)

    df_all['revenue_ttm'] = rev_now   # TTM 营收（供 c6）
    return df_all


def jq_factor_snapshot(pool, factors, target_date):
    """用聚宽因子库 jqfactor 取 target_date 各因子的值，返回 dict: factor -> Series(index=code)。
    批量请求失败时逐因子重试，避免一个因子异常拖垮整批数据。"""
    try:
        from jqfactor import get_factor_values
    except Exception:
        return None
    try:
        data = get_factor_values(pool, factors, end_date=target_date, count=1)
    except Exception as batch_exc:
        data = {}
        log.warning('[因子接口] %s 批量请求失败，改为逐因子重试：%s' % (target_date, batch_exc))
        for factor_name in factors:
            try:
                single = get_factor_values(pool, [factor_name], end_date=target_date, count=1)
                data[factor_name] = single.get(factor_name)
            except Exception as single_exc:
                data[factor_name] = None
                log.warning('[因子接口] %s / %s 不可用：%s' %
                            (target_date, factor_name, single_exc))
    out = {}
    for f in factors:
        df = data.get(f)
        if df is None or df.empty:
            out[f] = pd.Series(np.nan, index=pool)
        else:
            out[f] = df.iloc[-1].reindex(pool)
    return out


def compute_ma(codes, data_date):
    """对指定股票计算 MA60/MA250（收盘价简单均线）"""
    ma60_d, ma250_d = {}, {}
    if not codes:
        return ma60_d, ma250_d
    price_frames = []
    batch_size = 500
    for i in range(0, len(codes), batch_size):
        batch = codes[i:i + batch_size]
        try:
            df_price = get_price(batch, end_date=data_date, count=260, frequency='daily',
                                 fields=['close'], skip_paused=False, panel=False)
            if df_price is not None and not df_price.empty:
                price_frames.append(df_price)
        except:
            continue
    if price_frames:
        price_all = pd.concat(price_frames, ignore_index=True)
        for code, grp in price_all.groupby('code'):
            close = grp.sort_values('time')['close'].reset_index(drop=True)
            if len(close) >= 250:
                ma60_d[code] = close.rolling(60).mean().iloc[-1]
                ma250_d[code] = close.rolling(250).mean().iloc[-1]
            else:
                ma60_d[code] = np.nan
                ma250_d[code] = np.nan
    return ma60_d, ma250_d


def build_factors(context):
    """每日：重算因子。财务用利润表缓存+增量财报；估值/价格每日刷新；PS历史季度缓存"""
    # 当日任一步骤失败时禁止沿用旧因子交易，避免静默使用过期信号。
    g.factor_df = None
    current_date = context.current_dt.date()
    current_date_str = current_date.strftime('%Y-%m-%d')

    # 用缓存交易日列表定位前一交易日（避免每日 get_trade_days）
    idx = bisect.bisect_left(g.trading_days, current_date) - 1
    if idx < 0:
        return
    data_date = g.trading_days[idx]

    # 1. 行业成分 + 健康筛选（每日）
    all_stocks, industry_map = get_allowed_industry_stocks(data_date)
    if not all_stocks:
        return
    pool = filter_stock_health(context, all_stocks, data_date)
    if not pool:
        return
    log.info(f"股票池: {len(pool)}只")

    # 2.0 估值查询（一次取 PE/PS/市值；PE>0 过滤股票池，同时为 ps_3y/score 供数，省一次全池查询）
    q_val = query(valuation.code, valuation.pe_ratio, valuation.ps_ratio, valuation.market_cap).filter(
        valuation.code.in_(pool))
    df_val = get_fundamentals(q_val, date=data_date)
    if df_val is None or df_val.empty:
        return
    df_val.set_index('code', inplace=True)
    if 'pe_ratio' in df_val.columns:
        pool = df_val[df_val['pe_ratio'] > 0].index.tolist()
    if not pool:
        return

    # 2. 财务：每日维护利润表缓存（增量），自算财务因子——
    #    cost_incr/sale_incr 用「最新报告期累计 vs 去年同期累计」同比（对齐原版 *_lf_yoy）；
    #    op/nt/gp 会被下方 jqfactor 每日覆盖（jq 失败时回退自算）；revenue_ttm 供 c6。
    if g.fin_cache is None:
        df_fin = fetch_income_statement(pool, data_date)
        if df_fin is None or df_fin.empty:
            return
        g.fin_cache = df_fin
        g.last_pub_date = df_fin['pub_date'].max() if 'pub_date' in df_fin.columns else data_date
    else:
        df_new_list = []
        df_new = fetch_incremental_income(pool, data_date, g.last_pub_date)
        if df_new is not None and not df_new.empty:
            df_new_list.append(df_new)
        # 补充：池中新增股票的历史财报（增量按公告日会漏掉它们）
        known = set(g.fin_cache['code'].unique())
        missing = [c for c in pool if c not in known]
        if missing:
            df_miss = fetch_income_statement(missing, data_date)
            if df_miss is not None and not df_miss.empty:
                df_new_list.append(df_miss)
        if df_new_list:
            df_new_all = pd.concat(df_new_list, ignore_index=True)
            g.fin_cache = _normalize_income_rows(
                pd.concat([g.fin_cache, df_new_all], ignore_index=True), data_date)
            g.last_pub_date = g.fin_cache['pub_date'].max()
            # 控制缓存规模：每只仅保留最近20期
            g.fin_cache = g.fin_cache.sort_values(['code', 'end_date']).groupby('code').tail(20).reset_index(drop=True)
    df_all = compute_ttm_factors(g.fin_cache, industry_map)
    # 3. join 估值（市值/PS，用 PE>0 过滤后的子集）
    df_all = df_all.join(df_val[['ps_ratio', 'market_cap']], how='inner')
    df_all['ps_ttm'] = df_all['ps_ratio']

    # 2.5 用聚宽因子库 jqfactor 覆盖财务因子（对齐原版 TTM 因子）：
    #     op_yoy/nt_yoy/gp_yoy 用官方因子（每股营收TTM同比、扣非净利TTM同比、DEGM）；
    #     cost_incr/sale_incr 不用 jq（jq是TTM同比，原版是累计同比），保留上面自算的累计同比。
    #     【当日因子每日更新】（get_factor_values 取当日已披露最新财报，对齐原版每日因子表）；
    #     【1年前/2年前历史值季度缓存】（历史值固定）。失败自动回退自算。研发费用已去掉。
    idx_py = max(0, idx - 252)          # 1年前交易日（对应原版 lag 252）
    idx_2y = max(0, idx - 504)          # 2年前交易日
    date_py = g.trading_days[idx_py]
    date_2y = g.trading_days[idx_2y]
    # 沿用原刷新节奏；这里只在缓存缺少新入池股票时额外重建，防止新股票永久缺因子。
    known_hist = set(g.jq_hist.keys()) if g.jq_hist else set()
    need_hist = (g.jq_hist is None
                 or (current_date.month in (3, 6, 9, 12)
                     and current_date != g.jq_hist_date)
                 or any(code not in known_hist for code in pool))
    if need_hist:
        snap_py = jq_factor_snapshot(pool, g.jq_factors, date_py)
        snap_2y = jq_factor_snapshot(pool, g.jq_factors, date_2y)
        if snap_py is not None and snap_2y is not None:
            g.jq_hist = {}
            for code in pool:
                g.jq_hist[code] = {
                    'np_py': snap_py['np_parent_company_owners_ttm'].get(code, np.nan),
                    'nc_py': snap_py['non_recurring_gain_loss'].get(code, np.nan),
                    'np_2y': snap_2y['np_parent_company_owners_ttm'].get(code, np.nan),
                    'nc_2y': snap_2y['non_recurring_gain_loss'].get(code, np.nan),
                    'cost_py': snap_py['operating_cost_ttm'].get(code, np.nan),
                    'sale_py': snap_py['sale_expense_ttm'].get(code, np.nan),
                    'psr_py': snap_py['total_operating_revenue_per_share_ttm'].get(code, np.nan),
                    'psr_2y': snap_2y['total_operating_revenue_per_share_ttm'].get(code, np.nan),
                    'opg_py': snap_py['operating_revenue_growth_rate'].get(code, np.nan),
                    'opg_2y': snap_2y['operating_revenue_growth_rate'].get(code, np.nan),
                }
            g.jq_hist_date = current_date
    snap_now = jq_factor_snapshot(pool, g.jq_factors, data_date)   # 当日快照（每日）
    if snap_now is not None and g.jq_hist:
        cache = {}
        for code in pool:
            h = g.jq_hist.get(code)
            if h is None:
                continue
            # 扣非净利TTM = 归母净利TTM - 非经常性损益（对齐原版 net_profit_deducted_ttm_yoy）
            ded_now = snap_now['np_parent_company_owners_ttm'].get(code, np.nan) - snap_now['non_recurring_gain_loss'].get(code, np.nan)
            ded_py = h['np_py'] - h['nc_py']
            ded_2y = h['np_2y'] - h['nc_2y']
            now_cost = snap_now['operating_cost_ttm'].get(code, np.nan)
            now_sale = snap_now['sale_expense_ttm'].get(code, np.nan)
            cost_incr = (now_cost / h['cost_py'] - 1.0) if (pd.notnull(h['cost_py']) and h['cost_py'] > 0) else np.nan
            sale_incr = (now_sale / h['sale_py'] - 1.0) if (pd.notnull(h['sale_py']) and h['sale_py'] > 0) else np.nan
            nt_yoy = (ded_now / ded_py - 1.0) if (pd.notnull(ded_py) and ded_py > 0) else np.nan
            last_nt = (ded_py / ded_2y - 1.0) if (pd.notnull(ded_2y) and ded_2y > 0) else np.nan
            # 每股营业总收入TTM同比（对齐原版 revenue_ps_ttm_yoy）；缺失时回退总量口径 operating_revenue_growth_rate
            psr_now = snap_now['total_operating_revenue_per_share_ttm'].get(code, np.nan)
            if pd.notnull(psr_now) and pd.notnull(h['psr_py']) and h['psr_py'] > 0:
                op_yoy = psr_now / h['psr_py'] - 1.0
                last_op = (h['psr_py'] / h['psr_2y'] - 1.0) if (pd.notnull(h['psr_2y']) and h['psr_2y'] > 0) else np.nan
            else:
                op_yoy = snap_now['operating_revenue_growth_rate'].get(code, np.nan)
                last_op = h['opg_py']
            cache[code] = {
                'op_yoy': op_yoy,              # 每股营业总收入TTM同比（原版口径）
                'last_year_op': last_op,       # 去年每股营业总收入TTM同比
                'nt_yoy': nt_yoy,              # 扣非净利TTM同比（原版口径）
                'last_year_nt': last_nt,       # 去年扣非净利TTM同比
                'gp_yoy': snap_now['DEGM'].get(code, np.nan),
                'cost_incr': cost_incr,
                'sale_incr': sale_incr,
            }
        g.jq_cache = cache
        g.jq_cache_date = current_date
        if need_hist:
            log.info(f"[{current_date_str}] 聚宽因子库财务因子更新（每日当日快照+季度历史）：{len(cache)}只")
    if g.jq_cache:
        jq_df = pd.DataFrame(g.jq_cache).T   # index=code, columns=因子
        # 只覆盖 op/nt/gp 及去年值；cost_incr/sale_incr 保留自算累计同比（对齐原版 *_lf_yoy）
        for f in ['op_yoy', 'last_year_op', 'nt_yoy', 'last_year_nt', 'gp_yoy']:
            jq_values = jq_df[f].reindex(df_all.index)
            # 单个聚宽因子缺失时保留利润表自算值，防止整列NaN导致候选恒为0。
            df_all[f] = jq_values.combine_first(df_all[f])

    # 4. PS：用「close ÷ 每股营业总收入TTM」构造每日 PS 序列（近1256交易日），
    #    ps_3y = 当日 PS 在历史每日 PS 序列中的分位（对齐原版 m_pct_rank(ps_ttm, 1256)，纯因子不查估值表）
    psr_snapshot = None if snap_now is None else snap_now.get('total_operating_revenue_per_share_ttm')
    has_psr_factor = psr_snapshot is not None and pd.to_numeric(
        psr_snapshot, errors='coerce').gt(0).any()
    if g.ps_series is None and has_psr_factor:
        g.ps_series, g.ps_dates = init_ps_series(pool, data_date)
        log.info(f"PS每日序列初始化：近{PS_HIST_DAYS}个交易日（close÷每股营收TTM）")
    elif g.ps_series is not None and has_psr_factor:
        missing_ps_codes = [code for code in pool if code not in g.ps_series]
        if missing_ps_codes:
            new_series, new_dates = init_ps_series(missing_ps_codes, data_date)
            g.ps_series.update(new_series)
            g.ps_dates.update(new_dates)
            log.info(f"PS每日序列补建：新增{len(missing_ps_codes)}只")
    if g.ps_series is not None and has_psr_factor:
        # 当日 close（全池一次）
        df_c1 = None
        try:
            df_c1 = get_price(pool, end_date=data_date, count=1, frequency='daily',
                              fields=['close'], skip_paused=False, panel=False)
        except Exception:
            pass
        close_now = {}
        if df_c1 is not None and not df_c1.empty:
            close_now = dict(zip(df_c1['code'], df_c1['close']))
        # 每日滚动：追加当日 PS，超窗口则裁剪
        for code in pool:
            dts = g.ps_dates.get(code)
            if dts is None or (dts and dts[-1] == data_date):
                continue
            c = close_now.get(code, np.nan)
            eps = snap_now['total_operating_revenue_per_share_ttm'].get(code, np.nan)
            if pd.notnull(c) and c > 0 and pd.notnull(eps) and eps > 0:
                g.ps_series[code].append(c / eps)
                g.ps_dates[code].append(data_date)
                if len(g.ps_series[code]) > PS_HIST_DAYS:
                    g.ps_series[code] = g.ps_series[code][-PS_HIST_DAYS:]
                    g.ps_dates[code] = g.ps_dates[code][-PS_HIST_DAYS:]
        # ps_3y：当日 PS 在历史每日 PS 中的分位（逐股向量化）
        ps_3y = {}
        for code in pool:
            arr = np.asarray(g.ps_series.get(code, []), dtype=float)
            c = close_now.get(code, np.nan)
            eps = snap_now['total_operating_revenue_per_share_ttm'].get(code, np.nan)
            if len(arr) >= 8 and pd.notnull(c) and c > 0 and pd.notnull(eps) and eps > 0:
                now_ps = c / eps
                ps_3y[code] = float((arr < now_ps).mean())
            else:
                ps_3y[code] = 0.5
        df_all['ps_3y'] = pd.Series(ps_3y).reindex(df_all.index)
    else:
        # 聚宽每股营收TTM因子不可用时，退回官方估值表PS的近60个月分位；
        # 不再写死0.5，否则 c3(ps_3y<10%) 会让策略永远没有候选股。
        if g.ps_hist is None:
            g.ps_hist = fetch_ps_history(pool, data_date)
        else:
            missing_ps_codes = [code for code in pool if code not in g.ps_hist.index]
            if missing_ps_codes:
                new_hist = fetch_ps_history(missing_ps_codes, data_date)
                if new_hist is not None:
                    g.ps_hist = g.ps_hist.combine_first(new_hist)
            if g.ps_hist_date is None or (data_date.year, data_date.month) != \
               (g.ps_hist_date.year, g.ps_hist_date.month):
                g.ps_hist = update_ps_history(g.ps_hist, pool, data_date)
        g.ps_hist_date = data_date
        ps_rank = {}
        if g.ps_hist is not None:
            for code in df_all.index:
                if code not in g.ps_hist.index:
                    ps_rank[code] = np.nan
                    continue
                values = pd.to_numeric(g.ps_hist.loc[code], errors='coerce').dropna().values
                now_ps = df_all.at[code, 'ps_ratio'] if 'ps_ratio' in df_all.columns else np.nan
                ps_rank[code] = float((values < now_ps).mean()) \
                    if len(values) >= 8 and pd.notnull(now_ps) and now_ps > 0 else np.nan
        df_all['ps_3y'] = pd.Series(ps_rank).reindex(df_all.index)
        log.warning(f"[{current_date_str}] 每股营收TTM因子不可用，PS分位已回退为估值表近60个月口径")

    # 5. 候选池 MA（每日只对通过财务条件的股票算，控制开销；持仓 MA 在 execute_trades 每日更新）
    # 注意：cost_incr/sale_incr 允许 NaN（c2为OR逻辑，任一 > op_yoy 即通过；全NaN则不过）
    req = ['op_yoy', 'nt_yoy', 'gp_yoy', 'ps_3y']
    if BUY_CONDITIONS['c1']:
        req += ['last_year_op', 'last_year_nt']
    if BUY_CONDITIONS['c6']:
        req += ['revenue_ttm', 'last_year_op']
    mask = df_all[req].notna().all(axis=1)
    m = mask.copy()
    if BUY_CONDITIONS['c1']:
        m &= (df_all['op_yoy'] > df_all['nt_yoy'] + 0.1) & \
             (df_all['last_year_op'] > df_all['last_year_nt'] + 0.1) & \
             (df_all['op_yoy'] > 0) & (df_all['last_year_op'] > 0)
    if BUY_CONDITIONS['c2']:
        # c2：成本/销售费用增速至少一项超过营收增速（研发费用已去掉）
        m &= ((df_all['cost_incr'] > df_all['op_yoy']) |
              (df_all['sale_incr'] > df_all['op_yoy']))
    if BUY_CONDITIONS['c4']:
        # 原版c4：毛利率 TTM 同比在 ±20% 以内
        m &= (df_all['gp_yoy'] > -0.2) & (df_all['gp_yoy'] < 0.2)
    if BUY_CONDITIONS['c6']:
        m &= (df_all['revenue_ttm'] >= REVENUE_MIN_TTM) & \
             (df_all['op_yoy'] >= REVENUE_GROWTH_MIN) & \
             (df_all['last_year_op'] >= REVENUE_GROWTH_MIN)
    pre = df_all[m].index.tolist()

    # 诊断（仅预筛候选为0时打印，避免每日长日志拖慢回测）
    if len(pre) == 0:
        n_op = int(df_all['op_yoy'].notna().sum())
        n_nt = int(df_all['nt_yoy'].notna().sum())
        n_cost = int(df_all['cost_incr'].notna().sum())
        n_sale = int(df_all['sale_incr'].notna().sum())
        n_pslow = int((df_all['ps_3y'] < 0.1).sum())
        psv = df_all['ps_3y'].replace([np.inf, -np.inf], np.nan).dropna()
        ps_min = psv.min() if len(psv) else float('nan')
        ps_med = psv.median() if len(psv) else float('nan')
        log.info(f"诊断：预筛候选为0！op_yoy非空={n_op}，nt_yoy非空={n_nt}，cost_incr非空={n_cost}，sale_incr非空={n_sale}，ps_3y<0.1={n_pslow}，ps_3y min={ps_min:.3f}，median={ps_med:.3f}")

    ma60_dict, ma250_dict = compute_ma(pre, data_date)
    df_all['ma60'] = df_all.index.map(ma60_dict)
    df_all['ma250'] = df_all.index.map(ma250_dict)

    df_all = df_all.replace([np.inf, -np.inf], np.nan)

    g.factor_df = df_all
    g.industry_map = industry_map
    g.universe_date = current_date
    log.info(f"[{current_date_str}] 因子更新完成：股票池{len(pool)}只，预筛候选{len(pre)}只")


# ============================================================
# 获取 PS 历史序列（每日滚动，对齐 m_pct_rank(ps_ttm,1256)）
# PS = 当日 close ÷ 每股营业总收入TTM（total_operating_revenue_per_share_ttm，纯因子，不查估值表）
# ============================================================
def _quarter_ends(data_date, n=20):
    """近 n 个季度末交易日（升序，用缓存 g.trading_days 本地过滤，无 API 调用）"""
    qends = []
    seen = set()
    for d in reversed(g.trading_days):
        if d > data_date:
            continue
        key = (d.year, (d.month - 1) // 3)
        if key not in seen:
            seen.add(key)
            qends.append(d)
        if len(qends) >= n:
            break
    return sorted(qends)


def init_ps_series(pool, data_date):
    """初始化历史每日 PS 序列（近1256交易日）：PS = 当日 close ÷ 当日所属季度的每股营收TTM。
    返回 (ps_series: code->list[PS], ps_dates: code->list[date])。首次调用较重，之后每日滚动增量。"""
    qends = _quarter_ends(data_date, n=20)
    eps_by_q = {}
    for qd in qends:
        snap = jq_factor_snapshot(pool, ['total_operating_revenue_per_share_ttm'], qd)
        if snap is not None:
            eps_by_q[qd] = snap['total_operating_revenue_per_share_ttm']
    close_all = {}
    batch = 100
    for i in range(0, len(pool), batch):
        sub = pool[i:i + batch]
        try:
            df = get_price(sub, end_date=data_date, count=PS_HIST_DAYS, frequency='daily',
                           fields=['close'], skip_paused=False, panel=False)
        except Exception:
            continue
        if df is None or df.empty:
            continue
        for code, grp in df.groupby('code'):
            dts = grp['time'].dt.date.tolist()
            cls = grp['close'].tolist()
            close_all[code] = list(zip(dts, cls))
    qd_sorted = sorted(eps_by_q.keys())
    ps_series = {}
    ps_dates = {}
    for code in pool:
        rows = close_all.get(code, [])
        vals = []
        dts = []
        qi = 0
        cur_eps = np.nan
        for d, c in rows:
            while qi < len(qd_sorted) and qd_sorted[qi] <= d:
                cur_eps = eps_by_q[qd_sorted[qi]].get(code, np.nan)
                qi += 1
            if pd.notnull(cur_eps) and cur_eps > 0 and pd.notnull(c) and c > 0:
                vals.append(c / cur_eps)
                dts.append(d)
        ps_series[code] = vals
        ps_dates[code] = dts
    return ps_series, ps_dates


def _month_dates(data_date):
    """近60个月窗口内、每月末（该月最后一个交易日）的日期列表（升序）。
    用已缓存的 g.trading_days 本地过滤（无 API 调用），对齐原版 m_pct_rank(ps_ttm, 1256) 的近5年月度采样"""
    window = timedelta(days=PS_HIST_MONTHS * 31)
    month_dates = []
    seen = set()
    for d in reversed(g.trading_days):
        if d > data_date:
            continue
        if data_date - d > window:
            break
        key = (d.year, d.month)
        if key not in seen:
            seen.add(key)
            month_dates.append(d)
    return sorted(month_dates)


def fetch_ps_history(pool, data_date):
    """返回近60个月、每月末的 PS 历史序列 DataFrame（index=code, 列=ps_YYYY-MM-DD）
    仅首次全量调用；后续月份用 update_ps_history 增量追加（对齐原版 ps_3y 的近5年月度采样）"""
    quarter_dates = _month_dates(data_date)
    ps_hist_list = []
    for d in quarter_dates:
        d_str = d.strftime('%Y-%m-%d')
        q_ps = query(valuation.code, valuation.ps_ratio).filter(valuation.code.in_(pool))
        df_ps = get_fundamentals(q_ps, date=d_str)
        if df_ps is not None and not df_ps.empty:
            df_ps.set_index('code', inplace=True)
            ps_hist_list.append(df_ps['ps_ratio'].rename(f'ps_{d_str}'))
    if not ps_hist_list:
        return None
    return pd.concat(ps_hist_list, axis=1)


def update_ps_history(ps_hist, pool, data_date):
    """PS 历史增量更新：每个新月只追加最新月末的 PS 列，并丢弃超出近60个月窗口的最老列。
    与 fetch_ps_history 全量结果完全等价，但把每月 ~60 次全池 get_fundamentals 降到 1 次。"""
    quarter_dates = _month_dates(data_date)
    valid_cols = {f'ps_{d.strftime("%Y-%m-%d")}' for d in quarter_dates}
    ps_hist = ps_hist[[c for c in ps_hist.columns if c in valid_cols]]
    latest = quarter_dates[-1]
    col_latest = f'ps_{latest.strftime("%Y-%m-%d")}'
    if col_latest in ps_hist.columns:
        return ps_hist
    q_ps = query(valuation.code, valuation.ps_ratio).filter(valuation.code.in_(pool))
    df_ps = get_fundamentals(q_ps, date=latest.strftime('%Y-%m-%d'))
    if df_ps is not None and not df_ps.empty:
        df_ps.set_index('code', inplace=True)
        new_col = df_ps['ps_ratio'].rename(col_latest)
        ps_hist = ps_hist.join(new_col, how='left')
    return ps_hist


# ============================================================
# 每日交易（对齐 BigQuant handle_data）
# ============================================================
def execute_sells(context):
    g.trade_phase = 'sell'
    execute_trades(context)


def execute_buys(context):
    g.trade_phase = 'buy'
    execute_trades(context)


def execute_trades(context):
    if g.factor_df is None or g.factor_df.empty:
        return

    trade_phase = getattr(g, 'trade_phase', 'both')
    current_date = context.current_dt.date()
    current_date_str = current_date.strftime('%Y-%m-%d')
    df_all = g.factor_df
    industry_map = g.industry_map

    # 初始化交易日列表
    if not g.trading_days:
        td = get_trade_days(start_date=context.run_params.start_date,
                            end_date=context.run_params.end_date)
        g.trading_days = sorted({_to_date(d) for d in td})

    holding_list = [s for s, p in context.portfolio.positions.items() if p.total_amount > 0]
    g.current_holdings = len(holding_list)

    # 估值/PS分位/财务因子已由每日 build_factors（09:20）更新，此处直接使用

    # ---- 半年基准资金更新（6/15、12/15，非交易日顺延）----
    for (m, d) in HALF_UPDATE_DAYS:
        target = _next_trade_day(date(current_date.year, m, d))
        if target is None or target > g.run_end_date:
            continue
        if current_date == target:
            period_name = f"{current_date.year}-{'H1' if m == 6 else 'H2'}"
            if g.current_half_year == period_name:
                continue
            if g.current_half_year is None:
                g.half_yearly_base_capital = CAPITAL
            else:
                g.half_yearly_base_capital = context.portfolio.portfolio_value
            g.current_half_year = period_name
            log.info(f"[{current_date_str}] 切换至{g.current_half_year}，半年基准资金：{g.half_yearly_base_capital:.2f}")

    # ---- 每日更新持仓的 MA（用于卖出，对齐 BigQuant 每日 sma_60/sma_250）----
    for stock in holding_list:
        if stock not in df_all.index:
            continue
        try:
            df_price = attribute_history(stock, 260, '1d', ['close'], skip_paused=True)
            if len(df_price) >= 60:
                df_all.at[stock, 'ma60'] = df_price['close'].rolling(60).mean().iloc[-1]
            if len(df_price) >= 250:
                df_all.at[stock, 'ma250'] = df_price['close'].rolling(250).mean().iloc[-1]
        except:
            pass

    # 更新行业持仓计数 + 持仓最高价(昨日最高 day_high，移动止损跟踪；不用今日盘中价，避免回撤恒为0)
    g.industry_holdings = {}
    current_data = get_current_data()
    for stock in holding_list:
        ind = industry_map.get(stock, '')
        if ind:
            g.industry_holdings[ind] = g.industry_holdings.get(ind, 0) + 1
        try:
            # 昨日最高价：回测中 attribute_history 截至前一交易日（不含今天），取最后一行 high
            df_hi = attribute_history(stock, 1, '1d', ['high'], skip_paused=True)
            if df_hi is not None and len(df_hi) > 0:
                hi_px = df_hi['high'].iloc[-1]
                if pd.notnull(hi_px):
                    if stock in g.highest_prices:
                        cur = g.highest_prices[stock]
                        # 防 nan 污染：max(nan, hi) 在 Python 里恒为 nan，需显式判断
                        if pd.isnull(cur) or hi_px > cur:
                            g.highest_prices[stock] = hi_px
                    else:
                        g.highest_prices[stock] = hi_px
        except:
            continue

    # ================= 卖出（每日，对齐 BigQuant 六个条件） =================
    for stock in (holding_list[:] if trade_phase != 'buy' else []):
        if stock not in df_all.index:
            continue
        row = df_all.loc[stock]
        snapshot = _current_snapshot(current_data, stock)
        last_px = snapshot.last_price if snapshot is not None else np.nan
        # 今日开盘价（对齐原版 current_open；day_open 可能返回 nan，用 get_price 兜底，确保 sell4 正常触发）
        open_px = np.nan
        try:
            if snapshot is not None:
                _o = snapshot.day_open
                if _o is not None and pd.notnull(_o) and _o > 0:
                    open_px = float(_o)
        except Exception:
            pass
        if pd.isnull(open_px):
            open_px = float(last_px) if _valid_price(last_px) else np.nan
        op_yoy = row['op_yoy']
        nt_yoy = row['nt_yoy']
        ps_3y = row['ps_3y']
        gp_yoy = row['gp_yoy']
        ma60 = row['ma60']
        ma250 = row['ma250']

        # 卖出条件（对齐原版六个平仓条件，用开关控制便于消融），记录触发原因
        is_close = False
        reasons = []
        # 平仓条件2：PS回升至近5年80%分位
        if SELL_CONDITIONS['sell_ps_high'] and pd.notnull(ps_3y) and ps_3y >= 0.8:
            is_close = True
            reasons.append(f"PS回升(分位{ps_3y:.0%}≥80%)")
        # 平仓条件3：PS>50%分位 且 净利TTM增速≥50%
        if SELL_CONDITIONS['sell_ps_nt'] and pd.notnull(ps_3y) and pd.notnull(nt_yoy) and \
           ps_3y > 0.5 and nt_yoy >= 0.5:
            is_close = True
            reasons.append(f"PS>50%且净利增速{nt_yoy:.1%}≥50%")
        # 平仓条件4：移动止损/动态止盈（对齐原版：盈利>=SELL4_MIN_PROFIT 启动，开盘价较持有期最高价回落>=SELL4_DROP 清仓）
        if SELL_CONDITIONS['sell4'] and stock in g.buy_prices and stock in g.highest_prices and pd.notnull(open_px):
            buy_price = g.buy_prices[stock]
            highest = g.highest_prices[stock]
            # 临时监控日志：所有持仓每日打印，便于核对回落/盈利；确认后可删
            drop_now = (highest - open_px) / highest if highest > 0 else float('nan')
            profit_now = (open_px / buy_price - 1.0) if buy_price > 0 else float('nan')
            log.info(f"[{current_date_str}] 移动止损监控{stock}: 买{buy_price:.2f} 最高{highest:.2f} 今开{open_px:.2f} "
                     f"回落{drop_now:.1%} 盈利{profit_now:.1%} (需 回落≥{SELL4_DROP:.0%} 且 盈利≥{SELL4_MIN_PROFIT:.0%})")
            if open_px > buy_price * (1 + SELL4_MIN_PROFIT) and highest > 0:
                if drop_now >= SELL4_DROP:
                    is_close = True
                    reasons.append(f"移动止损(今开{open_px:.2f}较最高{highest:.2f}回落{drop_now:.1%})")
        # 平仓条件5：营收/净利/毛利率TTM同比均腰斩（<-50%）
        if SELL_CONDITIONS['sell5'] and pd.notnull(op_yoy) and pd.notnull(nt_yoy) and pd.notnull(gp_yoy) and \
           op_yoy < -0.5 and nt_yoy < -0.5 and gp_yoy < -0.5:
            is_close = True
            reasons.append(f"基本面恶化(营收{op_yoy:.0%}、净利{nt_yoy:.0%}、毛利率{gp_yoy:.0%}均腰斩)")
        # 平仓条件6：MA60跌破MA250（趋势恶化）
        if SELL_CONDITIONS['sell6'] and pd.notnull(ma60) and pd.notnull(ma250) and ma60 < ma250:
            is_close = True
            reasons.append(f"趋势恶化(ma60 {ma60:.2f}<ma250 {ma250:.2f})")

        if is_close:
            buy_dt = pd.to_datetime(g.last_buy_dates.get(stock)).date() if g.last_buy_dates.get(stock) else current_date
            hold_days = (current_date - buy_dt).days
            order = safe_order_target_value(context, stock, 0, current_data)
            if order is None:
                log.warning(f"[{current_date_str}] {stock}触发卖出但委托未提交，保留持仓跟踪状态")
                continue
            ind = industry_map.get(stock, '')
            if ind in g.industry_holdings:
                g.industry_holdings[ind] = max(0, g.industry_holdings[ind] - 1)
            g.buy_prices.pop(stock, None)
            g.highest_prices.pop(stock, None)
            # 冷却期：把卖出日记为 last_buy_dates，使卖出后 BUY_COOLDOWN_DAYS 天内禁止重新买入，
            # 防止"卖出后立即又买入"（原版按"距上次买入30天"算，持有超30天卖出后会被立刻买回）
            g.last_buy_dates[stock] = current_date_str
            log.info(f"[{current_date_str}] 卖出{stock}（{INDUSTRY_NAME_MAP.get(ind, ind)}）：{'；'.join(reasons) if reasons else '其他'}，持有{hold_days}天")

    holding_list = [s for s, p in context.portfolio.positions.items() if p.total_amount > 0]
    g.current_holdings = len(holding_list)

    if trade_phase == 'sell':
        return

    # ================= 固定日期补仓（6/25、12/25） =================
    for (m, d) in REBALANCE_DAYS:
        target = _next_trade_day(date(current_date.year, m, d))
        if target is None or target > g.run_end_date:
            continue
        if current_date == target:
            # 文档口径：单票目标=半年基准资金/5，同时受账户30%上限约束。
            total_assets = context.portfolio.portfolio_value
            target_value = min(g.half_yearly_base_capital / g.max_holdings,
                               total_assets * MAX_SINGLE_POSITION)
            rebalance_cash = max(0.0, float(context.portfolio.available_cash))
            for stock in holding_list[:]:
                if stock not in df_all.index:
                    continue
                ind = industry_map.get(stock, '')
                cur_count = g.industry_holdings.get(ind, 0)
                pos = context.portfolio.positions[stock]
                snapshot = _current_snapshot(current_data, stock)
                if snapshot is None or not _valid_price(snapshot.last_price):
                    continue
                current_value = pos.total_amount * snapshot.last_price
                if current_value < target_value * 0.95 and cur_count < MAX_PER_INDUSTRY:
                    need_buy = target_value - current_value
                    if need_buy > 0:
                        order, actual_value, rebalance_cash = safe_order_value(
                            context, stock, need_buy, current_data, rebalance_cash)
                        if order is not None:
                            log.info(f"[{current_date_str}] 补仓{stock}：{actual_value:.2f}元，目标{target_value:.2f}元")
            break

    # 持仓已满则跳过买入
    if g.current_holdings >= g.max_holdings:
        return

    # ================= 买入（每日） =================

    # 向量化筛选候选（各条件用开关控制，便于消融实验）
    # 注意：ma60/ma250 不放进基础非空掩码，只在 c5 条件中应用——
    # 这样关闭 c5 时均线完全不限制；诊断时 c1~c4 通过数也不会被 MA 缺失掩盖成 0
    req_cols = ['op_yoy', 'nt_yoy', 'ps_3y', 'gp_yoy']
    if BUY_CONDITIONS['c1']:
        req_cols += ['last_year_op', 'last_year_nt']
    if BUY_CONDITIONS['c6']:
        req_cols += ['revenue_ttm', 'last_year_op']
    mask = df_all[req_cols].notna().all(axis=1) & ~df_all.index.isin(holding_list)
    # 各条件布尔（始终计算，供开关与诊断使用）
    c1b = (df_all['op_yoy'] > df_all['nt_yoy'] + 0.1) & \
          (df_all['last_year_op'] > df_all['last_year_nt'] + 0.1) & \
          (df_all['op_yoy'] > 0) & (df_all['last_year_op'] > 0)
    # c2：成本/销售费用增速至少一项超过营收增速（研发费用已去掉）
    c2b = (df_all['cost_incr'] > df_all['op_yoy']) | \
          (df_all['sale_incr'] > df_all['op_yoy'])
    c3b = df_all['ps_3y'] < 0.1
    # 原版c4：毛利率 TTM 同比在 ±20% 以内
    c4b = (df_all['gp_yoy'] > -0.2) & (df_all['gp_yoy'] < 0.2)
    c5b = df_all['ma60'] > df_all['ma250']   # 需 ma60/ma250 均非空（NaN>NaN=False 天然过滤无均线数据的股票）
    c6b = (df_all['revenue_ttm'] >= REVENUE_MIN_TTM) & \
          (df_all['op_yoy'] >= REVENUE_GROWTH_MIN) & \
          (df_all['last_year_op'] >= REVENUE_GROWTH_MIN)
    m = mask.copy()
    if BUY_CONDITIONS['c1']: m &= c1b
    if BUY_CONDITIONS['c2']: m &= c2b
    if BUY_CONDITIONS['c3']: m &= c3b
    if BUY_CONDITIONS['c4']: m &= c4b
    if BUY_CONDITIONS['c5']: m &= c5b
    if BUY_CONDITIONS['c6']: m &= c6b
    sel = df_all[m]

    # 诊断：按启用条件统计累计通过数（仅当日候选为0时打印）
    if len(sel) == 0:
        cum = mask.copy()
        log_parts = []
        for name, cond in [('c1', c1b), ('c2', c2b), ('c3', c3b), ('c4', c4b), ('c5', c5b), ('c6', c6b)]:
            if BUY_CONDITIONS[name]:
                cum = cum & cond
            log_parts.append(f"{name}={int(cum.sum())}")
        log.info(f"[{current_date_str}] 当日候选为0（诊断）：累计通过 " + "，".join(log_parts))

    # 原版：score 打分（1.5×市值分位 + 营收增速分位 - 0.3×净利增速分位 - ps_3y）+ 行业分组（每行业最多2只）
    available_slots = g.max_holdings - g.current_holdings
    if available_slots <= 0:
        return
    sel_score = sel.copy()
    sel_score['pct_mcap'] = sel_score['market_cap'].rank(pct=True)
    sel_score['pct_op'] = sel_score['op_yoy'].rank(pct=True)
    sel_score['pct_nt'] = sel_score['nt_yoy'].rank(pct=True)
    sel_score['score'] = 1.5 * sel_score['pct_mcap'] + sel_score['pct_op'] - 0.3 * sel_score['pct_nt'] - sel_score['ps_3y']
    sel_score = sel_score.dropna(subset=['score'])
    # 全市场按 score 排序，再依次施加行业上限和冷却期；否则字典遍历顺序
    # 会造成行业先后偏差，冷却股也会白白占用候选名额。
    ranked_stocks = sorted(
        sel_score.index,
        key=lambda code: (-float(sel_score.at[code, 'score']), str(code)))
    final_stocks = []
    pending_by_industry = {}
    for stock in ranked_stocks:
        last_buy = g.last_buy_dates.get(stock)
        if last_buy and (current_date - pd.to_datetime(last_buy).date()).days < g.buy_cooldown_days:
            continue
        ind = sel_score.at[stock, 'industry']
        used = g.industry_holdings.get(ind, 0) + pending_by_industry.get(ind, 0)
        if used >= g.max_per_industry:
            continue
        final_stocks.append(stock)
        pending_by_industry[ind] = pending_by_industry.get(ind, 0) + 1
        if len(final_stocks) >= available_slots:
            break
    stocks_to_buy = final_stocks

    # 文档口径：每只目标为半年基准资金/5；账户变化较大时仍受30%硬上限保护。
    total_assets = context.portfolio.portfolio_value
    target_value = min(g.half_yearly_base_capital / g.max_holdings,
                       total_assets * MAX_SINGLE_POSITION)
    target_pct = target_value / total_assets if total_assets > 0 else 0

    # 现金保护：现金不足时按剩余现金买（避免委托失败）
    cash = context.portfolio.available_cash
    for stock in stocks_to_buy:
        # 今日开盘价：day_open 有时返回 nan，用 get_price 兜底取当日开盘，确保 buy_prices/highest_prices 不为 nan
        open_px = np.nan
        snapshot = _current_snapshot(current_data, stock)
        try:
            if snapshot is not None:
                _o = snapshot.day_open
                if _o is not None and pd.notnull(_o) and _o > 0:
                    open_px = float(_o)
        except Exception:
            pass
        if pd.isnull(open_px):
            open_px = snapshot.last_price if snapshot is not None else np.nan
        pos = context.portfolio.positions.get(stock)
        current_value = pos.total_amount * snapshot.last_price if pos and pos.total_amount > 0 and snapshot is not None else 0
        need_buy = target_value - current_value
        if need_buy > 0:
            order, actual_value, cash = safe_order_value(
                context, stock, need_buy, current_data, cash)
            if order is None:
                continue
            if current_value == 0:
                g.current_holdings += 1
            g.last_buy_dates[stock] = current_date_str
            g.buy_prices[stock] = open_px
            g.highest_prices[stock] = open_px   # 买入当天最高=买入价；之后每日用昨日最高价更新
            ind = industry_map.get(stock, '')
            if ind:
                g.industry_holdings[ind] = g.industry_holdings.get(ind, 0) + 1
            row_b = df_all.loc[stock]
            op_b = row_b.get('op_yoy', np.nan)
            nt_b = row_b.get('nt_yoy', np.nan)
            # 显示该股票真实通过的启用条件（原来罗列启用条件名是误导）
            passed = [k for k, cond in [('c1', c1b), ('c2', c2b), ('c3', c3b), ('c4', c4b), ('c5', c5b), ('c6', c6b)]
                      if BUY_CONDITIONS.get(k) and bool(cond[stock])]
            conds = '+'.join(passed) if passed else '-'
            fmt_op = f"{op_b:.1%}" if pd.notnull(op_b) else "NA"
            fmt_nt = f"{nt_b:.1%}" if pd.notnull(nt_b) else "NA"
            log.info(f"[{current_date_str}] 买入{stock}（{INDUSTRY_NAME_MAP.get(ind, ind)}）：{actual_value:.2f}元 权重{target_pct:.1%} "
                     f"| 通过[{conds}] 营收增速{fmt_op} 净利增速{fmt_nt}")


def before_trading_start(context):
    pass


def after_trading_end(context):
    pass
