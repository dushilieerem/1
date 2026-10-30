# -*- coding: utf-8 -*-
"""聚宽回测策略 A3 季度版：四因子选 2 个行业，每行业用 Alpha#040 选 15 只。

调仓时点：每季度第 6 个北向（沪股通/深股通）交易日开盘。
北向持股数量自 2024-08-19 起改为“每季度第 5 个沪深股通交易日盘后公布上季度末数据”，
所以第 6 个北向交易日开盘是该期数据最早公开、也最早能据此交易的时点。
北向分项只使用这一期已经公布的持股，不引用调仓时点尚未披露的数据。
"""

from jqdata import *
from jqfactor import get_factor_values
import datetime as dt
import numpy as np
import pandas as pd


# 沿用参考策略的 27 个申万一级行业代码。
INDUSTRY_CODES = [
    '801010', '801030', '801040', '801050', '801080', '801110',
    '801120', '801130', '801140', '801150', '801160', '801170',
    '801180', '801200', '801210', '801230', '801710', '801720',
    '801730', '801740', '801750', '801760', '801770', '801780',
    '801790', '801880', '801890',
]

# 每年 1、4、7、10 月调仓一次，具体落在该季度第几个北向交易日见下方常量。
QUARTER_START_MONTHS = (1, 4, 7, 10)

# 北向持股披露安排：每季度第 5 个沪股通/深股通交易日盘后公布上季度末的单只证券持股。
# 因此调仓放在第 6 个北向交易日：第 5 个北向交易日收盘后数据才公开，第 6 个交易日开盘才可用。
NORTHBOUND_DISCLOSURE_DAY = 5
REBALANCE_NORTHBOUND_DAY = NORTHBOUND_DISCLOSURE_DAY + 1

# 北向持股均值窗口（自然日），沿用参考代码口径：
# 日频年代约合 20 个交易日；改为季度披露后，窗口内只剩当季那一期数据。
NORTHBOUND_WINDOW_DAYS = 25
# 数据商还没更新到本期基准日时的回看上限（自然日），足够覆盖再上一期。
NORTHBOUND_FALLBACK_LOOKBACK = 200

# 北向交易日 = 内地与香港同时开市。港股是否开市用港股行情序列识别。
HK_CALENDAR_SECURITIES = ('00700.XHKG', '00001.XHKG')
# 取不到港股行情时的保守缓冲：多等这些 A股交易日，保证不早于第 6 个北向交易日。
HK_CALENDAR_FALLBACK_EXTRA_A_DAYS = 2
# 手工兜底：内地开市但北向休市的日期，正常情况留空。
MANUAL_NON_NORTHBOUND_DAYS = ()


def initialize(context):
    set_benchmark('000905.XSHG')
    set_option('use_real_price', True)
    set_option('avoid_future_data', True)
    # 与参考代码保持相同的回测成本；实际交易时需另测更高冲击成本。
    set_order_cost(OrderCost(close_tax=0.0005, open_commission=0.0001,
                             close_commission=0.0001, min_commission=1), type='stock')
    set_slippage(FixedSlippage(0.02))
    g.min_average_money = 20000000  # 过去 10 日平均每日成交额至少 2000 万元
    g.industry_count = 2
    g.stocks_per_industry = 15
    g.rebalanced_quarter = None      # 记录本季度是否已经调过仓
    g.hk_calendar_code = None        # 识别港股开市日所用的行情代码
    g.northbound_calendar_note = None
    # 每个交易日开盘检查一次，只有季度首月里北向交易日计数到位的那天才真正调仓。
    run_daily(market_open, time='open')


def eligible_stocks(context):
    """只使用前一交易日已经上市、今日开盘可交易的主板股票。"""
    asof = context.previous_date
    securities = get_all_securities(['stock'], date=asof)
    cutoff = pd.Timestamp(asof) - pd.Timedelta(days=50)
    current = get_current_data()
    result = []
    for stock, row in securities.iterrows():
        # 与参考策略一致排除创业板、科创板；补充排除北交所 9 开头代码。
        if stock[0] in ('4', '8', '9') or stock[:2] in ('30', '68'):
            continue
        if pd.Timestamp(row['start_date']) >= cutoff:
            continue
        if current[stock].is_st or current[stock].paused:
            continue
        result.append(stock)
    return result


def industry_members(stocks, asof):
    pool = set(stocks)
    return {
        code: sorted(pool.intersection(get_industry_stocks(code, date=asof)))
        for code in INDUSTRY_CODES
    }


def alpha040_scores(stocks, asof, min_average_money):
    """严格按 -RANK(STD(HIGH,10))*CORR(HIGH,VOLUME,10) 计算。

    RANK 在全部合格股票上只做一次，再按行业取股票；A、B、C 因此可直接比较。
    """
    rows = []
    for start in range(0, len(stocks), 300):
        batch = stocks[start:start + 300]
        bars = get_price(batch, end_date=asof, count=10, frequency='daily',
                         fields=['high', 'volume', 'money'], skip_paused=False,
                         fq='pre', panel=False)
        if bars is None or bars.empty:
            continue
        if 'time' not in bars.columns:
            bars = bars.reset_index()
        if 'time' not in bars.columns and 'date' in bars.columns:
            bars = bars.rename(columns={'date': 'time'})
        if 'time' not in bars.columns or 'code' not in bars.columns:
            raise ValueError('get_price(panel=False) 未返回 time/date 与 code 列')
        bars = bars.drop_duplicates(['time', 'code'], keep='last')
        for stock, one in bars.groupby('code'):
            one = one.sort_values('time')
            if len(one) != 10:
                continue
            high = pd.to_numeric(one['high'], errors='coerce').values.astype(float)
            volume = pd.to_numeric(one['volume'], errors='coerce').values.astype(float)
            money = pd.to_numeric(one['money'], errors='coerce').values.astype(float)
            if (not np.isfinite(high).all() or not np.isfinite(volume).all()
                    or not np.isfinite(money).all() or (volume <= 0).any()
                    or money.mean() < min_average_money):
                continue
            if np.std(high) == 0 or np.std(volume) == 0:
                continue
            rows.append((stock, np.std(high, ddof=1), np.corrcoef(high, volume)[0, 1]))
    if not rows:
        return pd.Series(dtype=float)
    data = pd.DataFrame(rows, columns=['code', 'high_std', 'high_volume_corr']).set_index('code')
    data = data.replace([np.inf, -np.inf], np.nan).dropna()
    # pct=True 与因子文档中的横截面百分比排名一致；分数越大越优先。
    return -data['high_std'].rank(pct=True) * data['high_volume_corr']


def to_ts(value):
    """统一成当天零点的 Timestamp，方便比较。"""
    return pd.Timestamp(value).normalize()


def a_trade_days(start_date, end_date):
    """A股交易日列表（get_trade_days 是交易日历函数，回测中也是完整日历）。"""
    return [to_ts(d) for d in get_trade_days(start_date=start_date, end_date=end_date)]


def hk_trade_days(start_date, end_date):
    """用港股行情序列识别港股开市日，返回 (交易日集合, 使用的代码)；取不到返回 (None, None)。"""
    for code in HK_CALENDAR_SECURITIES:
        try:
            bars = get_price(code, start_date=start_date, end_date=end_date,
                             frequency='daily', fields=['close'], skip_paused=False,
                             fq=None, panel=False)
        except Exception as err:
            if getattr(g, 'northbound_calendar_note', None) != 'fallback':
                log.info('A3季度：北向日历取 %s 行情失败（%s）' % (code, err))
            continue
        if bars is None:
            continue
        if 'time' in getattr(bars, 'columns', []):
            raw = bars['time']
        elif 'date' in getattr(bars, 'columns', []):
            raw = bars['date']
        else:
            raw = bars.index
        days = sorted(set(to_ts(x) for x in raw))
        if days:
            return set(days), code
    return None, None


def northbound_trade_days(start_date, end_date):
    """北向交易日 = A股交易日 ∩ 港股交易日；取不到港股行情时返回 None。"""
    if to_ts(start_date) > to_ts(end_date):
        return []
    hk_days, code = hk_trade_days(start_date, end_date)
    if hk_days is None:
        return None
    if getattr(g, 'hk_calendar_code', None) != code:
        g.hk_calendar_code = code
        log.info('A3季度：北向交易日历用 %s 的行情识别港股开市日' % code)
    manual = set(to_ts(d) for d in MANUAL_NON_NORTHBOUND_DAYS)
    return [d for d in a_trade_days(start_date, end_date)
            if d in hk_days and d not in manual]


def quarter_range(day):
    """day 所在季度的自然日起止。"""
    first_month = ((day.month - 1) // 3) * 3 + 1
    start = dt.date(day.year, first_month, 1)
    if first_month == 10:
        end = dt.date(day.year, 12, 31)
    else:
        end = dt.date(day.year, first_month + 3, 1) - dt.timedelta(days=1)
    return start, end


def previous_quarter_range(day):
    """上一个季度的自然日起止。"""
    prev_start, _ = quarter_range(day)
    return quarter_range(prev_start - dt.timedelta(days=1))


def northbound_vintage_day(context):
    """北向持股季报的基准日：上一季度最后一个交易日（调仓时该期已经公开）。

    持股数量在非北向交易日不会变化，所以用上一季度最后一个A股交易日作查询上界，
    取到的就是季度末那一期，无论数据商把记录标在季末交易日还是最后一个北向交易日。
    """
    prev_start, prev_end = previous_quarter_range(context.current_dt.date())
    days = a_trade_days(prev_start, prev_end)
    return days[-1] if days else None


def northbound_data_ready(context, q_start):
    """本季度第 5 个北向交易日是否已经走完（即上季度末持股是否已经公布）。

    只用已经发生的历史数据判断，不请求未来行情：
    - 能取到港股行情：数出 [季度首日, 上一交易日] 里的北向交易日个数；
    - 取不到港股行情：退化成 A股交易日数 + 缓冲，宁可晚几天也不提前。

    边界说明：若第 5 个北向交易日的下一个 A股交易日恰逢港股休市，程序会在那天
    调仓（数据前一晚已经公开），真正的第 6 个北向交易日更晚；这是保守方向的偏差。
    """
    if to_ts(q_start) > to_ts(context.previous_date):
        return False
    days = northbound_trade_days(q_start, context.previous_date)
    if days is not None:
        if len(days) < NORTHBOUND_DISCLOSURE_DAY:
            log.info('A3季度：%s 至 %s 已走完北向交易日 %d 个，不足 %d 个，暂不调仓'
                     % (q_start, context.previous_date, len(days), NORTHBOUND_DISCLOSURE_DAY))
            return False
        return True
    if getattr(g, 'northbound_calendar_note', None) != 'fallback':
        g.northbound_calendar_note = 'fallback'
        log.warning('A3季度：取不到港股行情，退化用A股交易日+%d天缓冲，保证不早于第 %d 个北向交易日'
                    % (HK_CALENDAR_FALLBACK_EXTRA_A_DAYS, REBALANCE_NORTHBOUND_DAY))
    a_days = a_trade_days(q_start, context.previous_date)
    need = NORTHBOUND_DISCLOSURE_DAY + HK_CALENDAR_FALLBACK_EXTRA_A_DAYS
    if len(a_days) < need:
        log.info('A3季度：%s 至 %s 已走完A股交易日 %d 个，退化口径需要 %d 个，暂不调仓'
                 % (q_start, context.previous_date, len(a_days), need))
        return False
    return True


def northbound_records(stocks, start, end):
    """取 [start, end] 内两条互联互通线路的持股比例记录。"""
    table = finance.STK_HK_HOLD_INFO
    pieces = []
    for link_id in (310001, 310002):
        data = finance.run_query(
            query(table.code, table.day, table.share_ratio).filter(
                table.day >= start, table.day <= end,
                table.link_id == link_id, table.code.in_(stocks)
            )
        )
        if data is not None and not data.empty:
            pieces.append(data)
    if not pieces:
        return None
    data = pd.concat(pieces, ignore_index=True)
    data['share_ratio'] = pd.to_numeric(data['share_ratio'], errors='coerce')
    data['day'] = pd.to_datetime(data['day'])
    data = data.dropna(subset=['share_ratio'])
    return data if not data.empty else None


def northbound_holding_mean(stocks, north_asof):
    """只用已经公布的一期北向持股：north_asof 之前约 25 个自然日的持股比例均值。

    north_asof 取上一季度最后一个交易日，正是“第 5 个北向交易日盘后公布”的那一期；
    调仓安排在第 6 个北向交易日，所以该期数据在调仓时已经公开，不存在前视。
    这是持仓比例的水平，不是北向净流入。若数据商还没更新到 north_asof，
    就退回最近一期已公布数据，并在日志中说明。
    """
    if north_asof is None:
        return np.nan
    window = dt.timedelta(days=NORTHBOUND_WINDOW_DAYS)
    end = to_ts(north_asof).date()
    data = northbound_records(stocks, end - window, end)
    if data is None:
        lookback = dt.timedelta(days=NORTHBOUND_FALLBACK_LOOKBACK)
        data = northbound_records(stocks, end - lookback, end)
        if data is None:
            log.info('A3季度：北向持股在 %s 之前没有可取数据' % end)
            return np.nan
        latest = data['day'].max()
        data = data[data['day'] > latest - window]
        log.info('A3季度：%s 这一期北向持股尚未更新，改用最近一期 %s'
                 % (end, latest.strftime('%Y-%m-%d')))
    # 先每只代表股取均值，再对代表股等权平均，与参考代码一致。
    return float(data.groupby('code')['share_ratio'].mean().reindex(stocks).mean())


def representative_stocks(stocks, limit, asof):
    """按流通市值选 EPS>0 的前 N 只代表股，显式指定历史查询日期。"""
    if not stocks:
        return []
    q = (query(valuation.code, valuation.circulating_market_cap)
         .filter(valuation.code.in_(stocks), indicator.eps > 0)
         .order_by(valuation.circulating_market_cap.desc())
         .limit(limit))
    frame = get_fundamentals(q, date=asof)
    return frame['code'].tolist() if frame is not None and not frame.empty else []


def select_industries(members, scores, stock_count, asof, north_asof):
    """参考代码的行业分数，取总分最低的两个行业。

    原代码是 -夏普 + DAVOL20 -0.5*预期增长 -北向持仓的 Z 分数之和。
    因此升序实际上偏好高夏普、低 DAVOL20、高预期增长、高北向持仓。
    asof 是日频与基本面因子的查询日（调仓日前一交易日）；
    north_asof 是北向持股基准日，只用已经公布的那一期（上一季度末）。
    """
    n_representatives = max(1, int(round(stock_count / 130.0)))
    fields = ('sharpe_ratio_60', 'DAVOL20', 'long_term_predicted_earnings_growth')
    rows = []
    for code in INDUSTRY_CODES:
        if len(set(members[code]).intersection(scores.index)) < g.stocks_per_industry:
            continue
        reps = representative_stocks(members[code], n_representatives, asof)
        if not reps:
            continue
        factor_data = get_factor_values(reps, list(fields), end_date=asof, count=1)
        values = []
        for field in fields:
            series = pd.to_numeric(factor_data[field].iloc[0], errors='coerce')
            values.append(float(series.mean()))
        north = northbound_holding_mean(reps, north_asof)
        if np.isfinite(values).all() and np.isfinite(north):
            rows.append((code, values[0], values[1], values[2], north))
    if len(rows) < g.industry_count:
        return []
    frame = pd.DataFrame(rows, columns=['code', 'sharpe', 'davol', 'growth', 'north']).set_index('code')
    std = frame.std(ddof=1)
    if (std <= 0).any():
        return []
    z = (frame - frame.mean()) / std
    score = -z['sharpe'] + z['davol'] - 0.5 * z['growth'] - z['north']
    return score.sort_values(ascending=True).head(g.industry_count).index.tolist()


def rebalance_to(context, target):
    for stock in list(context.portfolio.positions.keys()):
        if stock not in target:
            order_target_value(stock, 0)
    value = context.portfolio.total_value / len(target)
    for stock in target:
        order_target_value(stock, value)


def market_open(context):
    if context.current_dt.month not in QUARTER_START_MONTHS:
        return
    today = to_ts(context.current_dt.date())
    q_start, _ = quarter_range(today)
    if g.rebalanced_quarter == str(q_start):
        return
    if not northbound_data_ready(context, q_start):
        return
    g.rebalanced_quarter = str(q_start)
    asof = context.previous_date          # 日频与基本面因子：调仓日前一交易日
    north_asof = northbound_vintage_day(context)
    log.info('A3季度：%s 开始季度调仓（本季度第 %d 个北向交易日，北向基准日 %s）'
             % (today.strftime('%Y-%m-%d'), REBALANCE_NORTHBOUND_DAY, north_asof))
    stocks = eligible_stocks(context)
    if not stocks:
        log.info('A3季度：股票池为空，本季度不调仓')
        return
    members = industry_members(stocks, asof)
    scores = alpha040_scores(stocks, asof, g.min_average_money)
    if scores.empty:
        log.info('A3季度：Alpha#040 无有效值，本季度不调仓')
        return
    sectors = select_industries(members, scores, len(stocks), asof, north_asof)
    log.info('A3季度：选出行业数 %d，行业 %s' % (len(sectors), sectors))
    target = []
    for code in sectors:
        candidates = scores.reindex(members[code]).dropna().sort_values(ascending=False)
        selected = candidates.head(g.stocks_per_industry).index.tolist()
        log.info('A3季度：行业 %s，原始候选 %d 只，Alpha#040 有效候选 %d 只，入选 %d 只' %
                 (code, len(members[code]), len(candidates), len(selected)))
        target.extend(selected)
    if len(target) != g.industry_count * g.stocks_per_industry:
        log.info('A3季度：行业数据不足或选不满 30 只，本季度不调仓；当前目标 %d 只' % len(target))
        return
    log.info('A3季度：行业 %s，目标持股数 %d' % (sectors, len(target)))
    rebalance_to(context, target)
