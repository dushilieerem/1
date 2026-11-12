# -*- coding: utf-8 -*-
# 高斯趋势-拉普拉斯防追高：09:30执行修正版，2026-10-16。
# 按原策略保留因子、12日动量、阈值及固定退出时间；修复取数和订单/风控状态。
# 新买单仅09:30提交，09:31请求撤销余单；下单时间不等于保证成交时间。
# 每分钟只同步成交、观察持仓现价高点、撤销逾时买单，不增加分钟止损信号。
# 回测请选择聚宽Python3环境、分钟频率。日期和初始资金仍需在网页设置。
# 风控20%为阶段回撤触发线；实际清仓后重置阶段高点，次交易日恢复筛选。
# 不保证成交价、单笔损失、全历史回撤或收益；本地验证不等于聚宽实际撮合。

from jqdata import *
import pandas as pd
import numpy as np
import math
from datetime import timedelta
import builtins as _bi


def initialize(context):
    set_benchmark('000300.XSHG')
    set_option('use_real_price', True)
    set_option('avoid_future_data', True)

    set_order_cost(
        OrderCost(
            close_tax=0.0005,
            open_commission=0.00015,
            close_commission=0.00015,
            min_commission=5
        ),
        type='stock'
    )
    set_slippage(FixedSlippage(0.001))

    # 高斯趋势参数
    g.gaussian_fast_window = 10
    g.gaussian_mid_window = 20
    g.gaussian_slow_window = 30
    g.gaussian_fast_sigma = 3.0
    g.gaussian_mid_sigma = 6.0
    g.gaussian_slow_sigma = 9.0
    g.gaussian_slope_days = 3
    g.gaussian_slope_min = 0.002

    # 拉普拉斯曲率与防追高
    g.laplacian_min = -0.20
    g.laplacian_max = 0.30
    g.max_gaussian_extension_atr = 4.00
    g.max_recent_5d_range = 0.12
    g.max_open_gap = 0.05
    g.max_momentum = 0.25
    g.volume_ratio = 1.2

    # RSI与动量
    g.rsi_period = 14
    g.rsi_oversold = 30
    g.rsi_overbought = 70
    g.rsi_buy_min = 25
    g.rsi_buy_max = 75
    g.momentum_period = 12
    g.momentum_threshold = 0.02

    # 波动率
    g.atr_period = 14
    g.max_volatility = 0.45
    g.min_volatility = 0.10
    g.require_all_ma_up = True

    # 硬止损
    g.stop_loss = 0.04

    # 分级锁盈
    g.lock_activate_1 = 0.015
    g.lock_floor_1 = 0.005
    g.lock_activate_2 = 0.030
    g.lock_floor_2 = 0.010
    g.lock_giveback_2 = 0.020
    g.lock_activate_3 = 0.060
    g.lock_floor_3 = 0.030
    g.lock_giveback_3 = 0.025
    g.lock_activate_4 = 0.100
    g.lock_floor_4 = 0.060
    g.lock_giveback_4 = 0.035
    g.bad_market_tighten = 0.005

    # 盈利停滞
    g.peak_stall_days = 3
    g.peak_stall_keep_ratio = 0.65

    # 高斯趋势退出
    g.exit_price_below_fast_atr = 0.80
    g.exit_slope_soft = 0.0
    g.exit_slope_hard = -0.003
    g.exit_laplacian_soft = -0.15
    g.exit_laplacian_hard = -0.35
    g.exit_confirm_days = 2

    # 持股效率
    g.review_day_1 = 4
    g.review_day_2 = 7
    g.review_day_3 = 12
    g.day_2_min_profit = 0.008
    g.day_3_min_profit = 0.020
    g.final_review_days = 20
    g.final_min_profit = 0.050
    g.max_peak_stale_days = 4

    # 仓位管理
    g.max_holdings = 2
    g.max_daily_buy = 2
    g.single_position_pct = 0.5
    g.max_daily_loss = 0.03
    g.max_drawdown_stop = 0.20

    # 市场环境
    g.market_ma = 20
    g.require_market_uptrend = False
    g.market_strength_threshold = 0.01

    # 行业分散
    g.max_same_industry = 100

    # 持仓记录
    g.buy_price = {}
    g.highest_price = {}
    g.buy_date = {}
    g.buy_volume = {}
    g.buy_industry = {}
    g.buy_signal_score = {}
    g.weak_trend_days = {}
    g.last_peak_date = {}

    # 冷静期
    g.rebuy_cooldown_days = 10
    g.last_sell_date = {}

    # 状态
    g.last_log_date = None
    g.market_trend = 1
    g.market_strength = 0
    g.pause_trading = False
    g.daily_start_value = 0
    g.portfolio_high = float(context.portfolio.total_value)  # 阶段风控高点
    g.historical_high = g.portfolio_high                    # 全历史统计，不重置
    g.max_historical_drawdown = 0.0
    g.portfolio_liquidating = False
    g.daily_risk_halted = False
    g.risk_trigger_date = None
    g.tracked_orders = {}
    g.exit_requests = {}
    g.exit_last_fill_date = {}
    g.bought_today = set()
    g.execution_ready = True
    g.execution_error_logged = None
    g.exit_block_log = {}
    g.sell_last_attempt = {}
    g.daily_buy_count = 0
    g.observer_calls = 0
    g.observer_last_dt = None
    g.minute_frequency_warning_logged = False

    g.prepared_date = None
    g.buy_scan_date = None
    g.weak_check_date = {}
    # 每分钟仅观察/同步；固定退出时间沿用用户原始策略。
    run_daily(before_trading_start, time='09:00')
    run_daily(observe_execution, time='every_bar')
    run_daily(check_signals, time='09:30')
    run_daily(close_buy_window, time='09:31')
    run_daily(check_exit_open, time='10:05')
    run_daily(check_exit_open, time='11:20')
    run_daily(check_exit_open, time='13:30')
    run_daily(check_exit_open, time='14:20')
    run_daily(check_stop_loss, time='14:50')
    run_daily(check_portfolio_risk, time='14:55')


def before_trading_start(context):
    """开盘前重置每日状态；兼容平台自动回调和显式09:00调度。"""
    if g.prepared_date == context.current_dt.date():
        return
    g.prepared_date = context.current_dt.date()
    g.daily_buy_count = 0
    g.observer_calls = 0
    g.observer_last_dt = None
    g.daily_start_value = context.portfolio.total_value
    g.bought_today = set()
    g.daily_risk_halted = False
    sync_execution_state(context)  # 盘前只查询，不提交订单
    finish_portfolio_liquidation(context)
    g.pause_trading = g.portfolio_liquidating
    try:
        check_market_environment(context)
    except Exception as exc:
        g.market_strength = float("nan")
        log.error("【市场取数失败】本次禁买：%s" % exc)

    log.info('=' * 60)
    log.info('高斯趋势 + 拉普拉斯防追高策略（研究版）')
    log.info(
        '高斯窗口：%s/%s/%s，斜率>%.2f%%，拉普拉斯区间[%.2f, %.2f] ATR'
        % (
            g.gaussian_fast_window,
            g.gaussian_mid_window,
            g.gaussian_slow_window,
            g.gaussian_slope_min * 100,
            g.laplacian_min,
            g.laplacian_max
        )
    )
    log.info(
        '仓位：最大持仓%s只，每日最多买入%s只，单只上限%.0f%%'
        % (
            g.max_holdings,
            g.max_daily_buy,
            g.single_position_pct * 100
        )
    )
    log.info('=' * 60)


def causal_gaussian_filter(values, window, sigma):
    """单边高斯滤波：只覆盖当前及过去数据。"""
    values = np.asarray(values, dtype=float)
    if len(values) < window or window < 3 or sigma <= 0:
        return np.array([])

    distance = np.arange(window - 1, -1, -1, dtype=float)
    weights = np.exp(-0.5 * (distance / sigma) ** 2)
    weights /= weights.sum()

    result = []
    for end in range(window, len(values) + 1):
        result.append(np.dot(values[end - window:end], weights))
    return np.asarray(result)


def gaussian_trend_metrics(close_prices, atr):
    """返回快/中/慢高斯线、快线斜率与ATR归一化曲率。"""
    fast = causal_gaussian_filter(
        close_prices,
        g.gaussian_fast_window,
        g.gaussian_fast_sigma
    )
    mid = causal_gaussian_filter(
        close_prices,
        g.gaussian_mid_window,
        g.gaussian_mid_sigma
    )
    slow = causal_gaussian_filter(
        close_prices,
        g.gaussian_slow_window,
        g.gaussian_slow_sigma
    )

    if (
        len(fast) < g.gaussian_slope_days + 1
        or len(mid) < 1
        or len(slow) < 1
    ):
        return None

    base = fast[-1 - g.gaussian_slope_days]
    slope = fast[-1] / base - 1 if base > 0 else 0
    laplacian = fast[-1] - 2 * fast[-2] + fast[-3]
    laplacian_atr = laplacian / atr if atr > 0 else 0
    return fast[-1], mid[-1], slow[-1], slope, laplacian_atr


def calculate_rsi(close_prices, period=14):
    """计算RSI。"""
    if len(close_prices) < period + 1:
        return 50

    deltas = np.diff(close_prices[-period - 1:])
    gains = deltas[deltas > 0].sum() / period
    losses = -deltas[deltas < 0].sum() / period

    if losses == 0:
        return 100

    rs = gains / losses
    return 100 - 100 / (1 + rs)


def calculate_atr(high, low, close, period=14):
    """计算ATR与20日年化波动率。"""
    if len(close) < period + 1:
        return 0, 0

    tr_list = []
    for i in range(1, len(close)):
        tr = _bi.max(
            high[i] - low[i],
            _bi.abs(high[i] - close[i - 1]),
            _bi.abs(low[i] - close[i - 1])
        )
        tr_list.append(tr)

    if len(tr_list) < period:
        return 0, 0

    atr = np.mean(tr_list[-period:])

    if len(close) >= 21:
        returns = np.diff(close[-21:]) / close[-21:-1]
        volatility = np.std(returns) * np.sqrt(252)
    else:
        volatility = 0

    return atr, volatility


def calculate_momentum(close_prices, period=10):
    """计算区间价格动量。"""
    if len(close_prices) < period + 1:
        return 0
    return (
        close_prices[-1] - close_prices[-period - 1]
    ) / close_prices[-period - 1]


def get_realtime_price(stock, current_data=None, fallback_price=None):
    """取得当前可见最新价；无有效行情时返回0，不用昨日收盘代替。"""
    try:
        if current_data is None:
            current_data = get_current_data()
        price = float(current_data[stock].last_price)
        if np.isfinite(price) and price > 0:
            return price
    except Exception:
        pass

    return 0.0


def get_intraday_high(stock, current_dt, fallback_price, entry_dt=None):
    """取得当日截至当前时点的分钟最高价。"""
    try:
        start_dt = current_dt.replace(
            hour=9,
            minute=30,
            second=0,
            microsecond=0
        )
        if entry_dt is not None and entry_dt.date() == current_dt.date():
            start_dt = _bi.max(start_dt, entry_dt)
        if current_dt <= start_dt:
            return float(fallback_price)

        minute_df = get_price(
            stock,
            start_date=start_dt,
            end_date=current_dt,
            frequency='1m',
            fields=['high'],
            skip_paused=True,
            fq='pre'
        )

        if minute_df is not None and len(minute_df) > 0:
            day_high = float(minute_df['high'].max())
            if np.isfinite(day_high) and day_high > 0:
                return _bi.max(day_high, float(fallback_price))
    except Exception:
        pass

    return float(fallback_price)


def get_stock_industry_name(stock, date=None):
    """获取申万一级行业名称。

    注意：自定义函数不能命名为get_industry，否则会遮蔽聚宽原生接口。
    """
    try:
        industry_info = get_industry(stock, date=date)
        stock_info = industry_info.get(stock, {})

        if 'sw_l1' in stock_info and stock_info['sw_l1'] is not None:
            return stock_info['sw_l1'].get('industry_name', '未知')

        # 兼容部分聚宽环境中的对象式返回
        if hasattr(stock_info, 'sw1') and stock_info.sw1 is not None:
            return stock_info.sw1.get('industry_name', '未知')
    except Exception:
        pass

    return '未知'


def check_market_environment(context):
    """判断沪深300市场趋势与20日强度。"""
    current_date = context.current_dt.strftime('%Y-%m-%d')

    df = get_price(
        '000300.XSHG',
        end_date=context.previous_date,
        count=g.market_ma + 20,
        frequency='daily',
        fields=['close'],
        skip_paused=True,
        fq='pre'
    )

    if df is None or len(df) < g.market_ma:
        g.market_trend = 1
        g.market_strength = 0
        return

    close_prices = df['close'].values.astype(float)
    market_ma = np.mean(close_prices[-g.market_ma:])
    current_price = close_prices[-1]

    g.market_trend = 1 if current_price > market_ma else 0

    if len(close_prices) >= 20:
        g.market_strength = (
            close_prices[-1] - close_prices[-20]
        ) / close_prices[-20]
    else:
        g.market_strength = 0

    if g.last_log_date != current_date:
        trend_str = '上升趋势' if g.market_trend == 1 else '下降趋势'
        log.info(
            '【市场环境】%s, 近20个收盘价区间涨幅:%.2f%%'
            % (trend_str, g.market_strength * 100)
        )


def get_rebuy_cooldown_remaining(stock, current_dt):
    """返回卖出冷静期剩余自然日数。"""
    last_sell_date = g.last_sell_date.get(stock)
    if last_sell_date is None:
        return 0

    try:
        elapsed_days = (current_dt.date() - last_sell_date).days
    except Exception:
        return 0

    return _bi.max(g.rebuy_cooldown_days - elapsed_days, 0)


def check_signals(context):
    """只在交易日09:30扫描并提交新买单；同日仅运行一次。"""
    if context.current_dt.strftime('%H:%M') != '09:30':
        return
    before_trading_start(context)
    if g.buy_scan_date == context.current_dt.date():
        return
    g.buy_scan_date = context.current_dt.date()
    try:
        check_market_environment(context)
    except Exception as exc:
        g.market_strength = float('nan')
        log.error('【市场取数失败】取消今日买入：%s' % exc)
        return
    check_portfolio_risk(context)
    # [FIX-4] 开仓前确认订单状态及当日日亏损，避免只在14:55判断禁买。
    service_pending_execution(context)
    if not g.execution_ready:
        return
    current_date = context.current_dt.strftime('%Y-%m-%d')
    current_data = get_current_data()

    if g.daily_buy_count >= g.max_daily_buy:
        return

    if g.pause_trading:
        return

    # 当前代码实际要求指数20日收益至少1%
    if not np.isfinite(g.market_strength) or g.market_strength < g.market_strength_threshold:
        return

    if g.require_market_uptrend and g.market_trend != 1:
        return
    current_holdings = list(live_positions(context))
    long_signals = []

    if g.last_log_date != current_date:
        log.info('=' * 60)
        log.info('信号扫描 - %s' % current_date)
        log.info(
            '市场:%s, 强度:%.2f%%'
            % (
                '上升' if g.market_trend == 1 else '下降',
                g.market_strength * 100
            )
        )
        log.info(
            '持仓:%s/%s, 今日已买:%s/%s'
            % (
                len(current_holdings),
                g.max_holdings,
                g.daily_buy_count,
                g.max_daily_buy
            )
        )
        log.info('=' * 60)
        g.last_log_date = current_date

    industry_count = {}
    for stock in current_holdings:
        if stock in g.buy_industry:
            industry = g.buy_industry[stock]
            industry_count[industry] = industry_count.get(industry, 0) + 1

    try:
        stock_pool = get_index_stocks('000300.XSHG', date=context.previous_date)
    except Exception as exc:
        log.error('【股票池取数失败】取消今日买入：%s' % exc)
        return
    total_checked = 0
    passed_filters = 0
    cooldown_skipped = 0

    for stock in stock_pool:
        try:
            if g.daily_buy_count >= g.max_daily_buy:
                break
    
            if stock in current_holdings:
                continue
    
            cooldown_remaining = get_rebuy_cooldown_remaining(
                stock,
                context.current_dt
            )
            if cooldown_remaining > 0:
                cooldown_skipped += 1
                continue
    
            if is_st_stock(stock) or is_suspended(stock):
                continue
    
            total_checked += 1
            count = g.gaussian_slow_window + 50
    
            df = get_price(
                stock,
                end_date=context.previous_date,
                count=count + 1,
                frequency='daily',
                fields=['close', 'high', 'low', 'volume'],
                skip_paused=True,
                fq='pre'
            )
    
            if df is None or len(df) < count + 1:
                continue
    
            try:
                if df.index[-1].strftime('%Y-%m-%d') == current_date:
                    df_history = df.iloc[:-1]
                else:
                    df_history = df
            except Exception:
                df_history = df
    
            if len(df_history) < count:
                continue
    
            close_prices = df_history['close'].values.astype(float)
            high_prices = df_history['high'].values.astype(float)
            low_prices = df_history['low'].values.astype(float)
            volume_prices = df_history['volume'].values.astype(float)
            if (not np.all(np.isfinite(close_prices)) or np.any(close_prices <= 0)
                    or not np.all(np.isfinite(high_prices)) or np.any(high_prices <= 0)
                    or not np.all(np.isfinite(low_prices)) or np.any(low_prices <= 0)
                    or not np.all(np.isfinite(volume_prices)) or np.any(volume_prices < 0)):
                continue
    
            atr, volatility = calculate_atr(
                high_prices,
                low_prices,
                close_prices,
                g.atr_period
            )
            if atr <= 0:
                continue
    
            metrics = gaussian_trend_metrics(close_prices, atr)
            if metrics is None:
                continue
    
            (
                gaussian_fast,
                gaussian_mid,
                gaussian_slow,
                gaussian_slope,
                laplacian_atr
            ) = metrics
    
            if not (gaussian_fast > gaussian_mid > gaussian_slow):
                continue
            if gaussian_slope < g.gaussian_slope_min:
                continue
            if (
                laplacian_atr < g.laplacian_min
                or laplacian_atr > g.laplacian_max
            ):
                continue
    
            rsi = calculate_rsi(close_prices, g.rsi_period)
            if rsi < g.rsi_buy_min or rsi > g.rsi_buy_max:
                continue
    
            momentum = calculate_momentum(
                close_prices,
                g.momentum_period
            )
            if (
                momentum < g.momentum_threshold
                or momentum > g.max_momentum
            ):
                continue
    
            if (
                volatility < g.min_volatility
                or volatility > g.max_volatility
            ):
                continue
    
            if len(volume_prices) >= 10:
                avg_volume = np.mean(volume_prices[-10:-1])
                current_volume = volume_prices[-1]
                if current_volume < avg_volume * g.volume_ratio:
                    continue
    
            current_price = get_realtime_price(
                stock,
                current_data=current_data,
                fallback_price=close_prices[-1]
            )
            if current_price <= 0:
                continue
    
            current_item = current_data[stock]
            if current_item.paused:
                continue
            if current_price >= current_item.high_limit:
                continue
    
            extension_atr = (
                (current_price - gaussian_fast) / atr
                if atr > 0
                else 999
            )
            recent_5d_range = (
                np.max(high_prices[-5:]) / np.min(low_prices[-5:]) - 1
            )
            day_open = float(current_item.day_open)
            if not np.isfinite(day_open) or day_open <= 0:
                continue
            open_gap = day_open / close_prices[-1] - 1
    
            if extension_atr > g.max_gaussian_extension_atr:
                continue
            if recent_5d_range > g.max_recent_5d_range:
                continue
            if open_gap > g.max_open_gap:
                continue
    
            industry = get_stock_industry_name(stock, context.previous_date)
            if industry_count.get(industry, 0) >= g.max_same_industry:
                continue
    
            passed_filters += 1
    
            score = 0
            score += gaussian_slope * 1000
            score += (rsi - 50) * 0.3
            score += momentum * 60
            score -= _bi.max(extension_atr, 0) * 2
            score -= _bi.abs(laplacian_atr) * 3
    
            long_signals.append(
                (
                    stock,
                    score,
                    gaussian_slope * 100,
                    current_price,
                    gaussian_fast,
                    rsi,
                    momentum,
                    industry
                )
            )
    
            if len(long_signals) <= 20:
                log.info(
                    '【候选】%s(%s) 得分:%.1f, 斜率:%.2f%%, '
                    '曲率:%.3fATR, 延伸:%.2fATR, RSI:%.1f, 动量:%.1f%%'
                    % (
                        stock,
                        industry,
                        score,
                        gaussian_slope * 100,
                        laplacian_atr,
                        extension_atr,
                        rsi,
                        momentum * 100
                    )
                )
        except Exception as exc:
            log.warning('【候选跳过】%s，数据或行情异常：%s' % (stock, exc))
            continue

    log.info(
        '【扫描统计】检查:%s只, 通过:%s只, 候选:%s只, 冷静期跳过:%s只'
        % (
            total_checked,
            passed_filters,
            len(long_signals),
            cooldown_skipped
        )
    )

    if len(long_signals) > 0:
        execute_trades(
            context,
            long_signals,
            current_date,
            industry_count
        )


def is_star_stock(stock):
    return stock.startswith(('688', '689')) and stock.endswith('.XSHG')

def live_positions(context):
    return {s: p for s, p in context.portfolio.positions.items()
            if p.total_amount > 0}

def order_key(order_obj):
    value = getattr(order_obj, 'order_id', None)
    return str(value) if value is not None else None

def order_is_terminal(order_obj):
    # 聚宽 filled 表示部分成交；held 才是全部成交。
    status = getattr(order_obj, 'status', None)
    name = str(getattr(status, 'name', status)).split('.')[-1].lower()
    value = getattr(status, 'value', status)
    return name in ('held', 'canceled', 'rejected') or value in (2, 3, 4)

def read_open_orders(context):
    try:
        return get_open_orders()
    except Exception as exc:
        g.execution_ready = False
        if g.execution_error_logged != context.current_dt.date():
            log.error('【订单查询失败】暂停新委托，保留持仓和卖出意图：%s' % exc)
            g.execution_error_logged = context.current_dt.date()
        return None

def initialize_filled_position(context, stock, position, meta, order_obj):
    """仅在确认实际成交后创建记录；成本优先使用持仓实际成本。"""
    cost = getattr(position, 'avg_cost', None) if position is not None else None
    if cost is None or not np.isfinite(cost) or cost <= 0:
        cost = float(getattr(order_obj, 'price', 0) or 0)
    if cost <= 0 or not np.isfinite(cost):
        log.error('【成交成本异常】%s，等待持仓成本同步' % stock)
        return
    if stock not in g.buy_date:
        g.buy_date[stock] = context.current_dt
        g.highest_price[stock] = cost
        g.last_peak_date[stock] = context.current_dt
        g.weak_trend_days[stock] = 0
    g.buy_price[stock] = cost
    g.buy_volume[stock] = (position.total_amount if position is not None
                           else int(getattr(order_obj, 'filled', 0) or 0))
    g.buy_industry[stock] = meta.get('industry', '未知')
    g.buy_signal_score[stock] = meta.get('score', 0)

def sync_execution_state(context):
    """按委托实际成交量及实际持仓同步；委托成功不等于成交。"""
    try:
        today_orders = get_orders()
        open_orders = get_open_orders()
    except Exception as exc:
        g.execution_ready = False
        if g.execution_error_logged != context.current_dt.date():
            log.error('【订单同步失败】禁止新委托，状态原样保留：%s' % exc)
            g.execution_error_logged = context.current_dt.date()
        return
    g.execution_ready = True
    orders = {str(k): v for k, v in today_orders.items()}
    orders.update({str(k): v for k, v in open_orders.items()})
    positions = live_positions(context)
    new_fills = set()
    for oid, meta in list(g.tracked_orders.items()):
        obj = orders.get(oid)
        if obj is None:
            if meta['submit_date'] < context.current_dt.date():
                # get_orders仅覆盖当日；已不在未完成列表的隔日订单结束跟踪。
                # 这不代表卖出完成：是否清仓仍以实际持仓为准。
                stock = meta['stock']
                position = positions.get(stock)
                if meta['side'] == 'buy' and position is not None and stock not in g.buy_date:
                    initialize_filled_position(context, stock, position, meta, meta['snapshot'])
                    g.buy_date[stock] = meta['submit_dt']
                    g.last_peak_date[stock] = meta['submit_dt']
                del g.tracked_orders[oid]
                continue
            obj = meta['snapshot']
        filled = int(getattr(obj, 'filled', 0) or 0)
        delta = _bi.max(filled - meta['filled_seen'], 0)
        stock = meta['stock']
        if delta > 0:
            if meta['side'] == 'buy':
                initialize_filled_position(context, stock, positions.get(stock), meta, obj)
                new_fills.add(stock)
                g.bought_today.add(stock)
                g.daily_buy_count = len(g.bought_today)
            else:
                g.exit_last_fill_date[stock] = context.current_dt.date()
            log.info('【成交确认】%s %s 新增%s股，累计%s/%s股，成交均价%.3f'
                     % (stock, meta['side'], delta, filled,
                        getattr(obj, 'amount', 0), float(getattr(obj, 'price', 0) or 0)))
            meta['filled_seen'] = filled
        meta['snapshot'] = obj
        if order_is_terminal(obj):
            log.info('【委托结束】%s %s，状态%s，实际成交%s股'
                     % (stock, meta['side'], getattr(obj, 'status', None), filled))
            del g.tracked_orders[oid]

    open_stocks = {o.security for o in open_orders.values()}
    for stock in set(g.buy_date) | set(g.exit_requests):
        if stock in positions or stock in open_stocks or stock in new_fills:
            continue
        if stock in g.exit_requests:
            # 只有实际持仓归零，且未完成委托消失，才确认平仓并启动冷静期。
            filled_date = g.exit_last_fill_date.get(stock)
            if filled_date is not None:
                g.last_sell_date[stock] = filled_date
            log.info('【清仓确认】%s，持仓归零，原因：%s'
                     % (stock, g.exit_requests[stock]['reason']))
            del g.exit_requests[stock]
            g.exit_last_fill_date.pop(stock, None)
            g.sell_last_attempt.pop(stock, None)
            g.exit_block_log.pop(stock, None)
        clean_position_records(stock)
    for stock, position in positions.items():
        if stock in g.buy_price and position.avg_cost > 0:
            align_position_cost(stock, position)
            g.buy_volume[stock] = position.total_amount

def remember_order(context, obj, stock, side, **extra):
    if obj is None:
        log.warning('【委托未创建】%s %s，等待后续检查' % (stock, side))
        return False
    oid = order_key(obj)
    if oid is None:
        g.execution_ready = False
        log.error('【订单ID异常】%s %s；禁止继续开仓' % (stock, side))
        return False
    meta = {'stock': stock, 'side': side, 'submit_dt': context.current_dt,
            'submit_date': context.current_dt.date(), 'filled_seen': 0,
            'snapshot': obj}
    meta.update(extra)
    g.tracked_orders[oid] = meta
    log.info('【委托提交】%s %s，订单%s，尚待成交确认' % (stock, side, oid))
    sync_execution_state(context)
    return True

def cancel_unfinished_buys(context):
    open_orders = read_open_orders(context)
    if open_orders is None:
        return
    for obj in list(open_orders.values()):
        # 优先识别本策略元数据；is_buy覆盖订单刚创建/重启等情况。
        meta = g.tracked_orders.get(order_key(obj), {})
        if meta.get('side') == 'buy' or getattr(obj, 'is_buy', False):
            try:
                cancel_order(obj)
            except Exception as exc:
                log.warning('【风控撤买单失败】%s：%s' % (obj.security, exc))

def request_exit(context, stock, reason, force=False):
    if stock not in g.exit_requests or force:
        g.exit_requests[stock] = {'reason': reason, 'created_dt': context.current_dt}

def log_exit_block(context, stock, reason):
    marker = (context.current_dt.date(), reason)
    if g.exit_block_log.get(stock) != marker:
        log.warning('【卖出待重试】%s：%s，持仓记录保留' % (stock, reason))
        g.exit_block_log[stock] = marker

def retry_pending_exits(context):
    if not g.exit_requests:
        return
    open_orders = read_open_orders(context)
    if open_orders is None:
        return
    # 限价卖单挂单超过5分钟时，在固定退出检查点请求撤单并重新报价。
    # 必须等未完成订单查询确认旧单消失后才能重新委托。
    for obj in list(open_orders.values()):
        meta = g.tracked_orders.get(order_key(obj), {})
        if meta.get('side') != 'sell' or obj.security not in g.exit_requests:
            continue
        if (context.current_dt - meta['submit_dt']).total_seconds() >= 300:
            try:
                cancel_order(obj)
            except Exception as exc:
                log_exit_block(context, obj.security, '过时卖单撤销失败：%s' % exc)
    open_orders = read_open_orders(context)
    if open_orders is None:
        return
    open_stocks = {o.security for o in open_orders.values()}
    current_data = get_current_data()
    for stock in list(g.exit_requests):
        try:
            position = live_positions(context).get(stock)
            if position is None:
                continue  # 由sync_execution_state确认并清理
            if stock in open_stocks:
                log_exit_block(context, stock, '存在未完成委托，等待成交或撤单确认')
                continue
            closeable = int(getattr(position, 'closeable_amount', 0) or 0)
            if closeable <= 0:
                log_exit_block(context, stock, 'T+1或可卖数量为零')
                continue
            item = current_data[stock]
            price = get_realtime_price(stock, current_data)
            if item.paused:
                log_exit_block(context, stock, '停牌')
                continue
            if price <= 0 or price <= item.low_limit:
                log_exit_block(context, stock, '无有效行情或跌停')
                continue
            last_attempt = g.sell_last_attempt.get(stock)
            if last_attempt == context.current_dt:
                continue
            g.sell_last_attempt[stock] = context.current_dt
            try:
                style, _ = make_order_style(stock, item, price, False)
                # 仅出售可卖数量；T+1锁定的余量留在队列，次日继续清仓。
                obj = order(stock, -_bi.min(closeable, int(position.total_amount)), style=style)
            except Exception as exc:
                log_exit_block(context, stock, '下单异常：%s' % exc)
                continue
            remember_order(context, obj, stock, 'sell',
                           reason=g.exit_requests[stock]['reason'])
        except Exception as exc:
            log_exit_block(context, stock, '行情或委托状态异常：%s' % exc)



def make_order_style(stock, item, price, is_buy):
    """[FIX-2] 仅科创板补限价；价格由原滑点和最小报价单位确定。"""
    if not is_star_stock(stock):
        return None, price + 0.001 if is_buy else price
    if is_buy:
        limit = _bi.min(math.ceil((price + 0.001) * 100 - 1e-8) / 100.0,
                    float(item.high_limit))
    else:
        limit = _bi.max(math.floor((price - 0.001) * 100 + 1e-8) / 100.0,
                    float(item.low_limit))
    if not np.isfinite(limit) or limit <= 0:
        raise ValueError('无有效科创板限价')
    return LimitOrderStyle(limit), limit


def update_daily_risk(context):
    """[FIX-4] 3%日亏损一旦触发，当天不因反弹解除。"""
    total_value = float(context.portfolio.total_value)
    invalid_value = not np.isfinite(total_value) or total_value <= 0
    if np.isfinite(g.daily_start_value) and g.daily_start_value > 0 and not invalid_value:
        loss = 1.0 - total_value / g.daily_start_value
        if loss + 1e-12 >= g.max_daily_loss and not g.daily_risk_halted:
            g.daily_risk_halted = True
            log.warning('【当日禁买】日亏损%.2f%%，锁定到下一交易日' % (loss * 100))
    g.pause_trading = (invalid_value or g.daily_risk_halted or g.portfolio_liquidating
                       or g.risk_trigger_date == context.current_dt.date())


def finish_portfolio_liquidation(context):
    """[FIX-4] 实际清仓确认后才沿用原策略重置阶段高点。"""
    if not g.portfolio_liquidating or not g.execution_ready:
        return
    open_orders = read_open_orders(context)
    if open_orders is None:
        return
    if live_positions(context) or open_orders or g.tracked_orders or g.exit_requests:
        return
    g.portfolio_liquidating = False
    g.portfolio_high = float(context.portfolio.total_value)
    # 清仓当日禁买，下一交易日按原规则继续；没有新增多日冷静期。
    g.risk_trigger_date = context.current_dt.date()
    log.info('【账户清仓确认】阶段高点重置为%.2f；全历史高点%.2f保持，下一交易日正常筛选'
             % (g.portfolio_high, g.historical_high))


def service_pending_execution(context):
    """只在原有开仓/退出/风控回调中同步成交、重试清仓，无新检查时点。"""
    sync_execution_state(context)
    if g.portfolio_liquidating:
        for stock in live_positions(context):
            request_exit(context, stock, '账户回撤紧急清仓', force=True)
    finish_portfolio_liquidation(context)
    update_daily_risk(context)
    if g.pause_trading:
        cancel_unfinished_buys(context)
    retry_pending_exits(context)
    sync_execution_state(context)
    finish_portfolio_liquidation(context)
    update_daily_risk(context)


def after_trading_end(context):
    """收盘只同步成交和记录，不提交订单。"""
    if g.observer_calls < 2 and not g.minute_frequency_warning_logged:
        log.warning('【回测频率提示】观察回调今日不足2次；请将回测频率设置为“分钟”以执行09:30定时买入')
        g.minute_frequency_warning_logged = True
    sync_execution_state(context)
    finish_portfolio_liquidation(context)
    total = float(context.portfolio.total_value)
    g.historical_high = _bi.max(g.historical_high, total)
    if g.historical_high > 0:
        g.max_historical_drawdown = _bi.max(g.max_historical_drawdown,
                                        1.0 - total / g.historical_high)
    if g.exit_requests:
        log.warning('【隔日待清仓】%s' % ','.join(sorted(g.exit_requests)))


def execute_trades(context, long_signals, current_date, industry_count):
    """保留原排序及候选范围；仅修复资金、数量、委托与成交记录。"""
    if context.current_dt.strftime('%H:%M') != '09:30':
        return
    service_pending_execution(context)
    if g.pause_trading or not g.execution_ready:
        return
    open_orders = read_open_orders(context)
    if open_orders is None:
        return
    holdings = set(live_positions(context))
    pending_buys = {o.security for o in open_orders.values()
                    if getattr(o, 'is_buy', False)
                    or g.tracked_orders.get(order_key(o), {}).get('side') == 'buy'}
    occupied = holdings | pending_buys
    daily_committed = g.bought_today | pending_buys
    available_slots = _bi.min(g.max_holdings - len(occupied),
                          g.max_daily_buy - len(daily_committed))
    if available_slots <= 0:
        return
    long_signals.sort(key=lambda item: item[1], reverse=True)
    buy_stocks = long_signals[:_bi.min(len(long_signals), available_slots)]
    if not buy_stocks:
        return
    current_data = get_current_data()
    remaining_budget = float(context.portfolio.available_cash)
    cash_per_stock = _bi.min(remaining_budget / len(buy_stocks),
                          context.portfolio.total_value * g.single_position_pct)
    for stock, score, angle, price, fast, rsi, momentum, industry in buy_stocks:
        if g.pause_trading or not g.execution_ready:
            break
        if stock in occupied or stock in g.exit_requests:
            continue
        item = current_data[stock]
        current_price = get_realtime_price(stock, current_data)
        if current_price <= 0 or item.paused or current_price >= item.high_limit:
            continue
        try:
            style, budget_price = make_order_style(stock, item, current_price, True)
            budget = _bi.min(cash_per_stock, remaining_budget,
                          float(context.portfolio.available_cash))
            # [FIX-2] 沿用佣金万分之1.5/最低5元；只预留实际费用，非减仓优化。
            net_budget = _bi.max(budget - _bi.max(5.0, budget * 0.00015), 0.0)
            shares = int(net_budget / budget_price) // 100 * 100
            minimum = 200 if is_star_stock(stock) else 100
            if shares < minimum:
                continue
            obj = order(stock, shares, style=style)
        except Exception as exc:
            log.warning('【买入委托异常】%s：%s' % (stock, exc))
            continue
        if remember_order(context, obj, stock, 'buy', industry=industry, score=score):
            filled = int(getattr(obj, 'filled', 0) or 0)
            if not order_is_terminal(obj) or filled > 0:
                occupied.add(stock)
                remaining_budget -= shares * budget_price

def get_holding_trade_days(buy_date, current_dt):
    """按交易日计算持仓天数。"""
    try:
        trade_days = get_trade_days(
            start_date=buy_date.date(),
            end_date=current_dt.date()
        )
        return _bi.max(len(trade_days) - 1, 0)
    except Exception as exc:
        log.warning('【交易日历异常】跳过依赖持仓天数的退出，不用自然日替代：%s' % exc)
        return None


def get_exit_trend_state(stock, previous_date, current_price):
    """使用已完成日线与当前可见价格判断退出趋势状态。"""
    count = (
        g.gaussian_slow_window
        + g.gaussian_slope_days
        + 15
    )

    try:
        df = get_price(
            stock,
            end_date=previous_date,
            count=count + 1,
            frequency='daily',
            fields=['close', 'high', 'low'],
            skip_paused=True,
            fq='pre'
        )
    except Exception as exc:
        log.error('【退出取数失败】%s，截止%s，%s: %s' % (
            stock, previous_date, type(exc).__name__, exc
        ))
        raise

    if (
        df is None
        or len(df) < (
            g.gaussian_slow_window
            + g.gaussian_slope_days
            + 2
        )
    ):
        return None

    # 请求已明确截至上一交易日，保留最后一根已完成日线。
    history = df

    if len(history) < (
        g.gaussian_slow_window
        + g.gaussian_slope_days
        + 1
    ):
        return None

    close_prices = history['close'].values.astype(float)
    high_prices = history['high'].values.astype(float)
    low_prices = history['low'].values.astype(float)
    if (not np.all(np.isfinite(close_prices)) or np.any(close_prices <= 0)
            or not np.all(np.isfinite(high_prices)) or not np.all(np.isfinite(low_prices))):
        return None

    atr, _ = calculate_atr(
        high_prices,
        low_prices,
        close_prices,
        g.atr_period
    )
    if atr <= 0:
        return None

    live_close = np.append(close_prices, float(current_price))
    metrics = gaussian_trend_metrics(live_close, atr)
    if metrics is None:
        return None

    fast, mid, slow, slope, laplacian_atr = metrics
    price_vs_fast_atr = (current_price - fast) / atr

    weak_items = [
        current_price < fast,
        slope <= g.exit_slope_soft,
        laplacian_atr <= g.exit_laplacian_soft,
        fast <= mid
    ]
    weak_count = _bi.sum(1 for item in weak_items if item)

    severe_break = (
        price_vs_fast_atr <= -g.exit_price_below_fast_atr
        or (fast < mid and current_price < fast)
        or (
            slope <= g.exit_slope_hard
            and laplacian_atr <= g.exit_laplacian_hard
        )
    )

    strong_trend = (
        fast > mid > slow
        and slope > 0
        and current_price >= fast
        and laplacian_atr > g.exit_laplacian_soft
    )

    return {
        'fast': fast,
        'mid': mid,
        'slow': slow,
        'slope': slope,
        'laplacian_atr': laplacian_atr,
        'price_vs_fast_atr': price_vs_fast_atr,
        'weak_count': weak_count,
        'severe_break': severe_break,
        'strong_trend': strong_trend
    }


def get_profit_lock_floor(peak_profit_rate):
    """根据最高浮盈计算最低允许保留收益。"""
    if peak_profit_rate >= g.lock_activate_4:
        floor = _bi.max(
            g.lock_floor_4,
            peak_profit_rate - g.lock_giveback_4
        )
    elif peak_profit_rate >= g.lock_activate_3:
        floor = _bi.max(
            g.lock_floor_3,
            peak_profit_rate - g.lock_giveback_3
        )
    elif peak_profit_rate >= g.lock_activate_2:
        floor = _bi.max(
            g.lock_floor_2,
            peak_profit_rate - g.lock_giveback_2
        )
    elif peak_profit_rate >= g.lock_activate_1:
        floor = g.lock_floor_1
    else:
        return None

    if g.market_trend == 0 or g.market_strength < 0:
        floor = _bi.min(
            peak_profit_rate - 0.002,
            floor + g.bad_market_tighten
        )

    return _bi.max(floor, 0.0)


def get_days_since_peak(stock, current_dt):
    """计算距离最近一次刷新最高价的交易日数。"""
    peak_date = g.last_peak_date.get(stock)
    if peak_date is None:
        return 0
    return get_holding_trade_days(peak_date, current_dt)


def close_buy_window(context):
    """09:31撤销未成交买单；撤单请求不等于立即撤单成功。"""
    sync_execution_state(context)
    cancel_unfinished_buys(context)
    sync_execution_state(context)


def observe_execution(context):
    """仅同步、现价高点观察及过时买单撤销；不产生盘中额外买卖信号。"""
    if g.observer_last_dt == context.current_dt:
        return
    g.observer_last_dt = context.current_dt
    g.observer_calls += 1
    sync_execution_state(context)
    if context.current_dt.strftime('%H:%M') > '09:30':
        orders = read_open_orders(context)
        if orders is not None and _bi.any(getattr(o, 'is_buy', False) for o in orders.values()):
            cancel_unfinished_buys(context)
    current_data = get_current_data()
    for stock, position in live_positions(context).items():
        try:
            align_position_cost(stock, position)
            price = get_realtime_price(stock, current_data)
            if price > 0 and stock in g.buy_price:
                record_peak(context, stock, price)
        except Exception as exc:
            log_exit_block(context, stock, '持仓观察异常：%s' % exc)
    finish_portfolio_liquidation(context)


def align_position_cost(stock, position):
    """只同步持仓实际成本，不用现价伪造成交价。"""
    cost = float(getattr(position, 'avg_cost', 0) or 0)
    if not np.isfinite(cost) or cost <= 0:
        return False
    g.buy_price[stock] = cost
    return True


def record_peak(context, stock, observed_price):
    old = g.highest_price.get(stock, g.buy_price[stock])
    if observed_price > old:
        g.highest_price[stock] = observed_price
        # 日期用于交易日停滞判断，微小新高同样属于新高。
        g.last_peak_date[stock] = context.current_dt


def check_exit_open(context):
    """盘中检查硬止损和已激活锁盈。"""
    check_exit_core(context, full_check=False)


def check_stop_loss(context):
    """尾盘执行完整退出检查。"""
    check_exit_core(context, full_check=True)


def check_exit_core(context, full_check=True):
    """统一退出引擎；[FIX-3] 卖出信号与成交确认分开。"""
    service_pending_execution(context)
    current_data = get_current_data()
    current_date = context.current_dt.strftime('%Y-%m-%d')

    for stock in list(context.portfolio.positions.keys()):
        if stock not in context.portfolio.positions:
            continue

        position = context.portfolio.positions[stock]
        if position.total_amount == 0:
            clean_position_records(stock)
            continue

        current_price = get_realtime_price(
            stock,
            current_data=current_data,
            fallback_price=position.price
        )
        if current_price <= 0:
            continue

        item = current_data[stock]
        if item.paused:
            continue

        if not align_position_cost(stock, position):
            log_exit_block(context, stock, '实际成本无效，保留持仓记录')
            continue
        buy_price = g.buy_price[stock]
        profit_rate = (current_price - buy_price) / buy_price
        observed_high = get_intraday_high(
            stock, context.current_dt, current_price, g.buy_date.get(stock)
        )
        record_peak(context, stock, observed_high)
        if stock in g.exit_requests:
            continue  # 退出意图由固定时间回调重试；T+1同样保留意图和最高价。

        highest_price = g.highest_price[stock]
        peak_profit_rate = (highest_price - buy_price) / buy_price

        buy_date = g.buy_date.get(stock, context.current_dt)
        hold_trade_days = get_holding_trade_days(
            buy_date,
            context.current_dt
        )
        days_since_peak = get_days_since_peak(
            stock,
            context.current_dt
        )

        sell_signal = False
        reason = ''

        # 1. 硬止损
        if profit_rate <= -g.stop_loss:
            sell_signal = True
            reason = '硬止损(%.2f%%)' % (profit_rate * 100)

        # 2. 盈利锁定
        if not sell_signal:
            lock_floor = get_profit_lock_floor(peak_profit_rate)
            if lock_floor is not None and profit_rate <= lock_floor:
                sell_signal = True
                reason = (
                    '盈利锁定(最高%.2f%%, 当前%.2f%%<=锁盈线%.2f%%)'
                    % (
                        peak_profit_rate * 100,
                        profit_rate * 100,
                        lock_floor * 100
                    )
                )

        trend_state = None
        if full_check and not sell_signal:
            try:
                trend_state = get_exit_trend_state(
                    stock, context.previous_date, current_price
                )
            except Exception as exc:
                log.warning('【趋势数据缺失】%s，保留硬止损和锁盈检查：%s' % (stock, exc))
            if trend_state is None:
                g.weak_trend_days[stock] = 0
                g.weak_check_date[stock] = context.current_dt.date()

        # 3. 趋势严重破坏
        if (
            full_check
            and not sell_signal
            and trend_state is not None
            and trend_state['severe_break']
        ):
            sell_signal = True
            reason = (
                '高斯趋势严重破坏(斜率%.2f%%, 曲率%.2fATR, '
                '价格距快线%.2fATR)'
                % (
                    trend_state['slope'] * 100,
                    trend_state['laplacian_atr'],
                    trend_state['price_vs_fast_atr']
                )
            )

        # 4. 连续趋势弱化
        if (
            full_check
            and not sell_signal
            and trend_state is not None
        ):
            if g.weak_check_date.get(stock) != context.current_dt.date():
                if trend_state['weak_count'] >= 2:
                    g.weak_trend_days[stock] = g.weak_trend_days.get(stock, 0) + 1
                else:
                    g.weak_trend_days[stock] = 0
                g.weak_check_date[stock] = context.current_dt.date()

            if g.weak_trend_days[stock] >= g.exit_confirm_days:
                sell_signal = True
                reason = (
                    '趋势连续弱化%s日(弱化项%s/4, 斜率%.2f%%)'
                    % (
                        g.weak_trend_days[stock],
                        trend_state['weak_count'],
                        trend_state['slope'] * 100
                    )
                )

        # 5. 盈利停滞
        if (
            full_check
            and not sell_signal
            and peak_profit_rate >= g.lock_activate_1
        ):
            trend_weak = (
                trend_state is not None
                and (
                    trend_state['weak_count'] >= 1
                    or not trend_state['strong_trend']
                )
            )
            retained_ratio = (
                profit_rate / peak_profit_rate
                if peak_profit_rate > 0
                else 1.0
            )

            if (
                days_since_peak is not None
                and days_since_peak >= g.peak_stall_days
                and retained_ratio <= g.peak_stall_keep_ratio
                and trend_weak
            ):
                sell_signal = True
                reason = (
                    '盈利停滞退出(距高点%s日, 最高%.2f%%, 当前保留%.0f%%)'
                    % (
                        days_since_peak,
                        peak_profit_rate * 100,
                        retained_ratio * 100
                    )
                )

        # 6. 持股效率复核
        if full_check and not sell_signal and trend_state is not None and hold_trade_days is not None:
            strong_trend = (
                trend_state is not None
                and trend_state['strong_trend']
            )
            weak_count = (
                trend_state['weak_count']
                if trend_state is not None
                else 0
            )

            if g.review_day_1 <= hold_trade_days < g.review_day_2:
                if (
                    peak_profit_rate < g.lock_activate_1
                    and weak_count >= 2
                ):
                    sell_signal = True
                    reason = (
                        '第4日无进展(%s日, 最高收益%.2f%%, 弱化项%s/4)'
                        % (
                            hold_trade_days,
                            peak_profit_rate * 100,
                            weak_count
                        )
                    )

            elif g.review_day_2 <= hold_trade_days < g.review_day_3:
                if (
                    profit_rate < g.day_2_min_profit
                    and not strong_trend
                ):
                    sell_signal = True
                    reason = (
                        '第7日效率不足(%s日, 收益%.2f%%<%.2f%%)'
                        % (
                            hold_trade_days,
                            profit_rate * 100,
                            g.day_2_min_profit * 100
                        )
                    )

            elif (
                g.review_day_3
                <= hold_trade_days
                < g.final_review_days
            ):
                if (
                    profit_rate < g.day_3_min_profit
                    or not strong_trend
                    or (days_since_peak is not None and days_since_peak > g.max_peak_stale_days)
                ):
                    sell_signal = True
                    reason = (
                        '第12日机会成本退出(%s日, 收益%.2f%%, '
                        '趋势强=%s, 距高点%s日)'
                        % (
                            hold_trade_days,
                            profit_rate * 100,
                            strong_trend,
                            days_since_peak
                        )
                    )

            elif hold_trade_days >= g.final_review_days:
                if (
                    profit_rate < g.final_min_profit
                    or not strong_trend
                    or (days_since_peak is not None and days_since_peak > g.max_peak_stale_days)
                ):
                    sell_signal = True
                    reason = (
                        '20日最终复核退出(%s日, 收益%.2f%%, '
                        '趋势强=%s, 距高点%s日)'
                        % (
                            hold_trade_days,
                            profit_rate * 100,
                            strong_trend,
                            days_since_peak
                        )
                    )

        if sell_signal:
            # [FIX-3] 包括跌停无法成交，也保留退出意图，后续原时点继续重试。
            log.info('【卖出信号】%s - %s；等待实际成交确认' % (stock, reason))
            request_exit(context, stock, reason)
            retry_pending_exits(context)


def check_portfolio_risk(context):
    """[FIX-4] 保留14:55及20%阈值；未清仓不重置高点。"""
    service_pending_execution(context)
    total_value = float(context.portfolio.total_value)
    if not np.isfinite(total_value) or total_value <= 0:
        g.pause_trading = True
        log.error('【账户净值异常】禁止开仓，等待检查')
        return
    g.historical_high = _bi.max(g.historical_high, total_value)
    g.max_historical_drawdown = _bi.max(g.max_historical_drawdown,
                                    1.0 - total_value / g.historical_high)
    if not g.portfolio_liquidating:
        g.portfolio_high = _bi.max(g.portfolio_high, total_value)
        portfolio_drawdown = 1.0 - total_value / g.portfolio_high
        if portfolio_drawdown + 1e-12 >= g.max_drawdown_stop:
            g.portfolio_liquidating = True
            g.risk_trigger_date = context.current_dt.date()
            log.warning('【紧急风控】阶段回撤%.2f%%，保留高点直至实际清仓确认'
                        % (portfolio_drawdown * 100))
    if g.portfolio_liquidating:
        for stock in live_positions(context):
            request_exit(context, stock, '账户回撤紧急清仓', force=True)
        g.pause_trading = True
        cancel_unfinished_buys(context)
        retry_pending_exits(context)
        sync_execution_state(context)
        finish_portfolio_liquidation(context)
    update_daily_risk(context)


def clean_position_records(stock):
    """清理单只股票的持仓跟踪记录。"""
    for attr in [
        'buy_price',
        'highest_price',
        'buy_date',
        'buy_volume',
        'buy_industry',
        'buy_signal_score',
        'weak_trend_days',
        'last_peak_date',
        'weak_check_date'
    ]:
        if hasattr(g, attr) and stock in getattr(g, attr):
            del getattr(g, attr)[stock]


def is_st_stock(stock_code):
    """判断是否为ST、*ST或退市风险股票。"""
    try:
        current_data = get_current_data()
        item = current_data[stock_code]
        stock_name = item.name

        if item.is_st:
            return True
        if stock_name and (
            'ST' in stock_name
            or '*' in stock_name
            or '退' in stock_name
        ):
            return True
    except Exception:
        return True

    return False


def is_suspended(stock_code):
    """判断股票是否停牌。"""
    try:
        return bool(get_current_data()[stock_code].paused)
    except Exception:
        return True
