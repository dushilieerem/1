# 导入函数库
# ====================== 小市值策略 (国证2000掘金策略) ======================
# 文件名: small_cap_strategy.py

import math
import datetime
import numpy as np
import pandas as pd
from jqdata import *
from jqfactor import *
from datetime import time, date, timedelta

def initialize(context):
    """初始化函数"""
    set_option('use_real_price', True)
    set_option('avoid_future_data', True)
    log.set_level('system', 'error')
    set_benchmark('399303.XSHE')
    
    set_slippage(FixedSlippage(0.015))
    set_order_cost(OrderCost(open_tax=0,
                            close_tax=0.0005,
                            open_commission=0.0001,
                            close_commission=0.0001,
                            close_today_commission=0,
                            min_commission=1), type='stock')
    
    # 策略参数
    g.stock_num = 8
    g.dieting_stocks = []
    g.today_target_list = []
    # 放量阈值：昨日成交量 > vol_spike_ratio × 近5日均量 视为「涨停次日放量/派发」，买入筛选剔除
    g.vol_spike_ratio = 2.0
    
    # 调度函数
    run_daily(prepare_buy_list, '09:30')
    run_daily(sell_strategy, '09:30')
    run_daily(buy_strategy, '09:40')
    run_daily(sell_strategy, '11:30')
    run_daily(sell_strategy, '14:55')
    run_daily(dieting_strategy, time="every_bar")
    run_daily(print_date_separator, time="15:05")

def prepare_buy_list(context):
    """9:30根据集合竞价和前一交易日数据生成当日候选池，不在此处下单。"""
    # 跌停监控状态只在当日有效，避免前一交易日的状态污染当天判断
    g.dieting_stocks = []

    # 仅允许在财报窗口开新仓；窗口外继续由卖出逻辑管理已有持仓
    if not is_trade_period(context):
        g.today_target_list = []
        log.info("当前不在开仓窗口，今日不执行买入筛选")
        return
    
    codes = get_index_non_stocks(context)
    if codes:
        codes = filter_by_fundamentals(codes)
    if codes:
        codes = filter_by_limit_up(codes, context)
    if codes:
        codes = filter_by_technical(codes, context)
    if codes:
        codes = filter_by_call_auction(codes, context)
    if codes:
        codes = rank_by_factor(codes, context)
    
    g.today_target_list = codes if codes else []
    hold_list = list(context.portfolio.positions.keys())
    remaining_positions = g.stock_num - len(hold_list)
    log.info(f"今日候选股票数量：{len(g.today_target_list)}只，可买仓位：{remaining_positions}个")
    
    if g.today_target_list:
        try:
            display_stocks = g.today_target_list[:10]
            stock_names = [get_security_info(code).display_name + f"({code})" for code in display_stocks]
            log.info(f"最终候选股票：{', '.join(stock_names)}")
        except:
            display_stocks = g.today_target_list[:10]
            log.info(f"最终候选股票：{', '.join(display_stocks)}")
    else:
        log.info("今日无符合条件的候选股票")
    

def buy_strategy(context):
    """9:40使用9:30生成的候选池执行买入。"""
    if not is_trade_period(context):
        return
    if not g.today_target_list:
        log.info("今日无符合条件的候选股票，不执行买入")
        return
    place_buy_orders(g.today_target_list, context)

def sell_strategy(context):
    """卖出逻辑"""
    positions = context.portfolio.positions
    hold_list = list(positions)
    if not hold_list:
        return
    
    current_data = get_current_data()
    yesterday = context.previous_date

    hist_data = get_price(
        hold_list, end_date=yesterday, frequency='daily',
        fields=['close'], count=8, panel=False
    )
    if hist_data is None or hist_data.empty:
        return
    
    ma7_data = hist_data.groupby('code')['close'].apply(
        lambda x: x.rolling(7).mean().iloc[-1]
    ).to_dict()
    
    df_history = get_price(
        hold_list, end_date=yesterday, frequency='daily',
        fields=['close', 'high_limit'], count=1, panel=False
    )
    if df_history is None or df_history.empty:
        return
    
    # 使用股票代码映射数据，避免依赖 get_price 返回行顺序与持仓顺序一致
    df_history = df_history.copy().rename(columns={'high_limit': 'yesterday_high_limit'})
    avg_cost_map = {s: positions[s].avg_cost for s in hold_list}
    position_price_map = {s: positions[s].price for s in hold_list}
    today_high_limit_map = {s: current_data[s].high_limit for s in hold_list}
    today_low_limit_map = {s: current_data[s].low_limit for s in hold_list}
    last_price_map = {s: current_data[s].last_price for s in hold_list}
    closeable_amount_map = {s: positions[s].closeable_amount for s in hold_list}

    df_history['avg_cost'] = df_history['code'].map(avg_cost_map)
    df_history['price'] = df_history['code'].map(position_price_map)
    df_history['today_high_limit'] = df_history['code'].map(today_high_limit_map)
    df_history['today_low_limit'] = df_history['code'].map(today_low_limit_map)
    df_history['last_price'] = df_history['code'].map(last_price_map)
    df_history['ma7'] = df_history['code'].map(ma7_data).fillna(0)
    df_history['closeable_amount'] = df_history['code'].map(closeable_amount_map)
    
    cond_not_limit_up = (df_history['last_price'] != df_history['today_high_limit'])
    cond_break_ma7 = df_history['last_price'] < df_history['ma7']
    cond_profit = (df_history['price'] / df_history['avg_cost'] - 1) * 100 > 0
    cond_yesterday_limit_up = (df_history['close'] == df_history['yesterday_high_limit'])
    
    sell_condition = cond_not_limit_up & (cond_break_ma7 | cond_profit | cond_yesterday_limit_up)
    
    sell_list = df_history[
        sell_condition &
        (df_history['last_price'] > df_history['today_low_limit']) &
        (df_history['closeable_amount'] > 0)
    ].code.tolist()
    
    for stock in sell_list:
        try:
            position = positions[stock]
            cost_price = position.avg_cost
            current_price = current_data[stock].last_price
            stock_name = get_security_info(stock).display_name
            reason = "其他"
            if cost_price > 0:
                profit_rate = (current_price / cost_price - 1) * 100
                if current_price < df_history[df_history['code'] == stock]['ma7'].iloc[0]:
                    reason = "跌破均线"
                elif profit_rate > 0:
                    reason = "盈利"
            sell_amount = position.closeable_amount * current_price
            log_message = f'🏃 {reason}卖出：{stock_name}({stock}) | 价：{current_price:.2f} | 数量：{position.closeable_amount} | 金额：{sell_amount:.0f}'
        except:
            position = positions[stock]
            current_price = current_data[stock].last_price
            sell_amount = position.closeable_amount * current_price
            log_message = f'🏃 卖出：{stock} | 价：{current_price:.2f} | 数量：{position.closeable_amount} | 金额：{sell_amount:.0f}'
        order_obj = order_target_value(stock, 0)
        if order_obj is not None:
            log.info(log_message)
        else:
            log.warning(f'卖出委托失败：{stock}')

def dieting_strategy(context):
    """跌停打开止损"""
    positions = context.portfolio.positions
    if not positions:
        return
    
    current_data = get_current_data()
    
    for s in list(positions.keys()):
        if s not in g.dieting_stocks:
            dtj = current_data[s].low_limit
            zxj = current_data[s].last_price
            if zxj == dtj and (positions[s].closeable_amount != 0):
                g.dieting_stocks.append(s)
    
    g.dieting_stocks = list(set(g.dieting_stocks))
    
    if len(g.dieting_stocks) > 0:
        for s in g.dieting_stocks[:]:
            dtj = current_data[s].low_limit
            zxj = current_data[s].last_price
            if zxj > dtj and s in positions:
                try:
                    stock_name = get_security_info(s).display_name
                    pos = positions[s]
                    cost_price = pos.avg_cost
                    current_price = zxj
                    profit_rate = 0.0
                    if cost_price > 0:
                        profit_rate = (current_price / cost_price - 1) * 100
                    sell_amount = pos.closeable_amount * current_price
                    log_message = f"🏃 跌停打开止损卖出：{stock_name}({s}) | 价：{current_price:.2f} | 数量：{pos.closeable_amount} | 金额：{sell_amount:.0f} | 盈亏：{profit_rate:+.2f}%"
                except:
                    pos = positions[s]
                    current_price = current_data[s].last_price
                    sell_amount = pos.closeable_amount * current_price
                    log_message = f"🏃 跌停打开止损卖出：{s} | 价：{current_price:.2f} | 金额：{sell_amount:.0f}"
                order_obj = order_target_value(s, 0)
                if order_obj is not None:
                    log.info(log_message)
                    g.dieting_stocks.remove(s)
                else:
                    log.warning(f"跌停打开卖出委托失败：{s}")

def print_date_separator(context):
    log.info("=" * 60)

def get_index_non_stocks(context):
    """获取非ST股票"""
    stocks = get_index_stocks('399303.XSHE', date=context.previous_date)
    if not stocks:
        return []
    st_flags = get_extras('is_st', stocks, count=1, end_date=context.previous_date).T
    st_flags.columns = ['is_st']
    return st_flags[st_flags['is_st'] == False].index.tolist()

def is_trade_period(context):
    """判断是否可交易月份"""
    today = context.current_dt.strftime('%m-%d')
    return (
        '01-15' <= today <= '01-31' or
        '04-15' <= today <= '04-30' or
        '12-15' <= today <= '12-31'
    )

def filter_by_fundamentals(stocks):
    """基本面过滤"""
    if not stocks:
        return []
    q = query(
        valuation.code,
        income.np_parent_company_owners,
        income.net_profit,
        income.operating_revenue,
        indicator.roe,
        indicator.roa
    ).filter(
        valuation.code.in_(stocks),
        income.np_parent_company_owners > 0,
        income.net_profit > 0,
        income.operating_revenue > 1e8,
        indicator.roe > 0,
        indicator.roa > 0
    )
    df = get_fundamentals(q, date=None)
    return list(df.code) if (df is not None and not df.empty) else []

def filter_by_limit_up(stocks, context):
    """过滤涨停 + 仅排除「前天涨停、昨天放量且滞涨」的派发形态

    保留形态：前天(T-2)涨停、昨天(T-1)未涨停。
    剔除形态：前天涨停后，昨天既放巨量(> vol_spike_ratio × 近5日均量) 又滞涨
              (昨天收盘 < 前天涨停收盘，即涨停日涨幅被吐回) —— 典型拉高出货/派发。
    关键改进：昨天「放量但继续上涨」(收盘 ≥ 前天涨停收盘) 视为健康动量延续，保留，
              避免在强势行情(如2025)中误杀主升浪。较初版「放量即剔」明显放宽。
    """
    if not stocks:
        return []
    # 取近 7 日：rank6=昨天(T-1), rank5=前天(T-2), rank0..4=近5日均量基准(不含涨停日与昨天)
    prices = get_price(
        stocks, end_date=context.previous_date, frequency='daily',
        fields=['close', 'high_limit', 'open', 'volume'], count=7, panel=False
    )
    if prices is None or prices.empty:
        return []
    prices = prices.reset_index()
    prices['day_rank'] = prices.groupby('code').cumcount()  # 0..6, 6=昨天

    p2 = prices[prices['day_rank'] == 5].set_index('code')   # 前天 T-2
    p1 = prices[prices['day_rank'] == 6].set_index('code')   # 昨天 T-1
    base = prices[prices['day_rank'] <= 4].groupby('code')['volume'].mean()  # 前5日均量

    df = pd.concat([
        p2['close'].rename('close_day_before'),
        p2['high_limit'].rename('hl_day_before'),
        p1['close'].rename('close_yesterday'),
        p1['high_limit'].rename('hl_yesterday'),
        p1['open'].rename('open_yesterday'),
        p1['volume'].rename('vol_yesterday'),
        base.rename('vol_ma5'),
    ], axis=1).dropna()

    cond_limit = (
        (df['close_day_before'] == df['hl_day_before']) &     # 前天涨停
        (df['close_yesterday'] < df['hl_yesterday'])          # 昨天未涨停(未连板)
    )
    cond_distribute = (
        (df['vol_yesterday'] > g.vol_spike_ratio * df['vol_ma5']) &   # 昨天放量
        (df['close_yesterday'] < df['close_day_before'])             # 且滞涨(吐回涨停日涨幅)
    )
    cond = cond_limit & (~cond_distribute)                    # 保留，仅剔派发
    return df[cond].index.tolist()

def filter_by_technical(stocks, context):
    """技术面过滤"""
    if not stocks:
        return []
    hist = get_price(
        stocks, end_date=context.previous_date,
        fields=['close', 'low', 'volume'], count=11, panel=False
    )
    if hist is None or hist.empty:
        return []
    hist = hist.reset_index()
    hist['ma10'] = hist.groupby('code')['close'].transform(lambda x: x.rolling(10).mean())
    hist['prev_low'] = hist.groupby('code')['low'].shift(1)
    hist['prev_volume'] = hist.groupby('code')['volume'].shift(1)
    last_data = hist.groupby('code').tail(1)
    cond = (
        (last_data['close'] > last_data['prev_low']) &
        (last_data['close'] > last_data['ma10']) &
        (last_data['volume'] > last_data['prev_volume']) &
        (last_data['volume'] < 10 * last_data['prev_volume']) &
        (last_data['close'] > 1)
    )
    return last_data.loc[cond, 'code'].tolist()

def filter_by_call_auction(stocks, context):
    """集合竞价过滤"""
    if not stocks:
        return []
    date_now = context.current_dt.strftime("%Y-%m-%d")
    start, end = date_now + ' 09:15:00', date_now + ' 09:26:00'
    auction = get_call_auction(
        stocks, start_date=start, end_date=end,
        fields=['time','a1_p','a1_v','a2_p','a2_v','a3_p','a3_v','a4_p','a4_v','a5_p','a5_v',
                'b1_p','b1_v','b2_p','b2_v','b3_p','b3_v','b4_p','b4_v','b5_p','b5_v','current']
    )
    if auction is None or auction.empty:
        return []
    auction = auction.reset_index()
    pre_close = get_price(
        stocks, end_date=context.previous_date, fields=['close'], count=1, panel=False
    )
    if pre_close is None or pre_close.empty:
        return []
    pre_close = pre_close.reset_index()
    auction = auction.merge(pre_close[['code', 'close']], on='code', how='left').rename(columns={'close': 'pre_close'})
    
    auction = auction.assign(
        sellmoney=lambda df: df['a1_p'] * df['a1_v'] + df['a2_p'] * df['a2_v'] + df['a3_p'] * df['a3_v'] +
                            df['a4_p'] * df['a4_v'] + df['a5_p'] * df['a5_v'],
        buymoney=lambda df: df['b1_p'] * df['b1_v'] + df['b2_p'] * df['b2_v'] + df['b3_p'] * df['b3_v'] +
                            df['b4_p'] * df['b4_v'] + df['b5_p'] * df['b5_v']
    )
    auction['sellmoney'] = auction['sellmoney'].clip(lower=1.0)
    auction['b_s'] = (auction['buymoney'] - auction['sellmoney']) / auction['sellmoney']
    return auction.query('b_s > 0 and current > 0.95*pre_close and current < 1.01*pre_close')['code'].tolist()

def rank_by_factor(stocks, context):
    """因子排名"""
    if not stocks:
        return []
    val = get_valuation(stocks, end_date=context.previous_date, fields=['turnover_ratio'], count=1)
    if val is None or val.empty:
        return []
    val = val.reset_index()
    date_now = context.current_dt.strftime("%Y-%m-%d")
    start, end = date_now + ' 09:15:00', date_now + ' 09:26:00'
    auction = get_call_auction(stocks, start_date=start, end_date=end, fields=['time', 'current'])
    if auction is None or auction.empty:
        return []
    auction = auction.reset_index().sort_values(['code', 'time']).groupby('code').tail(1).rename(columns={'current': 'open'})
    pre_close = get_price(stocks, end_date=context.previous_date, fields=['close'], count=1, panel=False)
    if pre_close is None or pre_close.empty:
        return []
    pre_close = pre_close.reset_index().rename(columns={'close': 'pre_close'})
    df = pd.merge(val[['code', 'turnover_ratio']], auction[['code', 'open']], on='code', how='inner')
    df = pd.merge(df, pre_close[['code', 'pre_close']], on='code', how='inner')
    q99 = df['turnover_ratio'].quantile(0.99)
    df['turnover_ratio'] = df['turnover_ratio'].clip(upper=q99)
    df['factor'] = df['turnover_ratio'] * (df['open'] / df['pre_close'])
    return df.sort_values(by='factor', ascending=False)['code'].tolist()

def place_buy_orders(stocks, context):
    """执行买入"""
    hold_list = list(context.portfolio.positions.keys())
    num = g.stock_num - len(hold_list)
    if num <= 0:
        return
    cd = get_current_data()
    stocks = [
        s for s in stocks
        if s not in hold_list
        and not cd[s].paused
        and cd[s].last_price > cd[s].low_limit
        and cd[s].last_price < cd[s].high_limit
    ][:num]
    if not stocks:
        return
    cash_per_stock = context.portfolio.available_cash / len(stocks)
    for stock in stocks:
        try:
            stock_name = get_security_info(stock).display_name
        except:
            stock_name = stock
        price = cd[stock].last_price
        amount = int(cash_per_stock / price / 100) * 100
        min_cost = price * 100
        if cash_per_stock < min_cost or amount <= 0:
            log.info(f'跳过买入：{stock_name}({stock}) | 资金不足，最低需{min_cost:.2f}')
            continue
        order_obj = order(stock, amount)
        if order_obj is not None:
            log.info(f'👉️ 提交买入委托：{stock_name}({stock}) | 价：{price:.2f} | 数量：{amount} | 金额：{amount*price:.0f}')
        else:
            log.warning(f'买入委托失败：{stock_name}({stock})')


