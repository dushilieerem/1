# -*- coding: utf-8 -*-
"""
小市值“三正”策略

核心逻辑：
1. 股票池：399317.XSHE（国证A指）
2. 剔除 ST
3. 按总市值从小到大排序
4. 取市值最小的 10%
5. 三正筛选：
   - PB > 0
   - inc_return > 0
   - ocf_to_revenue > 0
6. 最终选择 30 只
7. 每日 9:30 卖出、9:40 买入
"""

import pandas as pd


def initialize(context):
    # 系统设置
    log.set_level('order', 'error')
    set_option('use_real_price', True)
    set_option('avoid_future_data', True)

    # 每日运行
    run_daily(before_market_open, 'before_open')
    run_daily(sell_adjustment, '09:30')
    run_daily(buy_adjustment, '09:40')
    run_daily(report, 'after_close')

    # 参数
    g.nchoice = 30          # 最终选择30只股票
    g.days = 0


def before_market_open(context):
    """
    开盘前更新股票池。
    """
    g.days += 1

    # 选股
    g.stocks = choice_small_stocks(context, g.nchoice)

    # 采用30只股票近似等权
    if len(g.stocks) > 0:
        g.position_size = (
            context.portfolio.total_value / len(g.stocks)
        )
    else:
        g.position_size = 0


def sell_adjustment(context):
    """9:30卖出不在目标股票池中的持仓。"""
    stocks = g.stocks

    # 数据异常或无候选时保持现有持仓，避免意外清仓
    if not stocks:
        log.warning('今日选股结果为空，保持现有持仓，不执行卖出')
        return

    cdata = get_current_data()

    for stock in list(context.portfolio.positions.keys()):

        if cdata[stock].paused:
            continue

        if stock not in stocks:
            if cdata[stock].last_price <= cdata[stock].low_limit:
                log.warning('skip sell at low limit', stock, cdata[stock].name)
                continue
            sell_limit_price = max(
                0.99 * cdata[stock].last_price,
                cdata[stock].low_limit
            )
            order_obj = order_target(
                stock,
                0,
                LimitOrderStyle(
                    sell_limit_price
                )
            )
            if order_obj is not None:
                log.info('submit sell', stock, cdata[stock].name)
            else:
                log.warning('sell order failed', stock, cdata[stock].name)


def buy_adjustment(context):
    """9:40使用卖出后释放的资金买入新进入目标池的股票。"""
    stocks = g.stocks
    position_size = g.position_size

    if not stocks:
        log.warning('今日选股结果为空，不执行买入')
        return

    cdata = get_current_data()
    new_stocks = []
    for stock in stocks:
        if stock in context.portfolio.positions:
            continue
        if cdata[stock].paused:
            continue
        if (cdata[stock].last_price <= cdata[stock].low_limit or
                cdata[stock].last_price >= cdata[stock].high_limit):
            continue
        new_stocks.append(stock)

    for index, stock in enumerate(new_stocks):
        remaining = len(new_stocks) - index
        available_cash = context.portfolio.available_cash
        cash_budget = available_cash / remaining
        min_cost = 100 * cdata[stock].last_price

        if cash_budget < min_cost:
            log.warning('skip buy for insufficient cash', stock, cdata[stock].name)
            continue

        value = min(position_size, cash_budget)
        buy_limit_price = min(
            1.01 * cdata[stock].last_price,
            cdata[stock].high_limit
        )

        order_obj = order_value(
            stock,
            value,
            LimitOrderStyle(
                buy_limit_price
            )
        )
        if order_obj is not None:
            log.info('submit buy', stock, cdata[stock].name)
        else:
            log.warning('buy order failed', stock, cdata[stock].name)


def choice_small_stocks(context, nchoice):
    """
    小市值“三正”选股。

    选股步骤：

    国证A指
        ↓
    剔除ST
        ↓
    市值最小10%
        ↓
    PB > 0
    inc_return > 0
    ocf_to_revenue > 0
        ↓
    选择30只
    """

    # =========================
    # 1. 基础股票池
    # =========================

    index = '399317.XSHE'

    dt_now = context.current_dt.date()

    stocks = get_index_stocks(
        index,
        dt_now
    )

    # =========================
    # 2. 剔除 ST
    # =========================

    cdata = get_current_data()

    stocks = [
        stock
        for stock in stocks
        if not cdata[stock].is_st
    ]

    if len(stocks) == 0:
        return []

    # =========================
    # 3. 取市值最小10%
    # =========================

    m = int(
        0.1 * len(stocks)
    )

    if m <= 0:
        return []

    df = get_fundamentals(
        query(
            valuation.code,
            valuation.market_cap,
            valuation.pb_ratio,
            indicator.inc_return,
            indicator.ocf_to_revenue,
        ).filter(

            valuation.code.in_(stocks)

        ).order_by(

            valuation.market_cap.asc()

        ).limit(m)

    ).dropna().set_index('code')

    # =========================
    # 4. 三正筛选
    # =========================

    df = df[
        (df.pb_ratio > 0) &
        (df.inc_return > 0) &
        (df.ocf_to_revenue > 0)
    ]

    # =========================
    # 5. 预留20%候选缓冲
    # =========================

    n_buffer = int(
        1.2 * nchoice
    )

    candidates = (
        df.head(n_buffer)
        .index
        .tolist()
    )

    # =========================
    # 6. 优先保留已有持仓
    # =========================

    old_stocks = [
        stock
        for stock in candidates
        if stock in context.portfolio.positions
    ]

    new_stocks = [
        stock
        for stock in candidates
        if stock not in context.portfolio.positions
    ]

    choice = (
        old_stocks + new_stocks
    )[:nchoice]

    # =========================
    # 7. 输出选股结果
    # =========================

    if len(choice) > 0:

        report_df = (
            df[['market_cap']]
            .loc[choice]
            .copy()
        )

        report_df['name'] = [
            cdata[stock].name
            for stock in report_df.index
        ]

        log.info(
            'small-quality stocks',
            len(choice),
            '\n',
            report_df
        )

    return choice


def report(context):
    """
    收盘后输出持仓。
    """

    cdata = get_current_data()

    total_value = (
        context.portfolio.total_value
    )

    table = pd.DataFrame(
        columns=[
            'amount',
            'value',
            'weight',
            'name'
        ]
    )

    for stock in context.portfolio.positions:

        position = (
            context.portfolio.positions[stock]
        )

        table.loc[stock] = [
            position.total_amount,
            int(position.value),
            100 * position.value / total_value,
            cdata[stock].name
        ]

    table = table.sort_values(
        by='weight',
        ascending=False
    )

    pd.set_option(
        'display.max_rows',
        None
    )

    log.info(
        'positions',
        len(table),
        '\n',
        table
    )

    log.info(
        'total return %.2f%%',
        100 * context.portfolio.returns
    )

    log.info(
        'total value %.2f 万, cash %.2f 万',
        context.portfolio.total_value / 10000,
        context.portfolio.available_cash / 10000
    )

    log.info(
        'running days',
        g.days
    )
