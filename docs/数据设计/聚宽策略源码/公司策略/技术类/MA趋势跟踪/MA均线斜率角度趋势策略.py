# -*- coding: utf-8 -*-
"""MA均线斜率角度趋势策略：09:30聚宽执行修正版，2026-10-16。

使用聚宽Python3、分钟回测；页面设置2016-09-30～2026-09-30及初始资金。
只在09:30提交新买单；09:31撤销余单，实际成交时间由平台撮合决定。
保留MA10>MA20、RSI35～65、12日动量等原有因子和阈值。
原require_all_ma_up虽为True但未执行；本版False保持双均线，可显式改True实验三均线。
个股新退出信号仍在14:50检查；未完成退出在09:30/09:31/14:50/14:55重试。
移动止损达到6%后持续激活；盘中采样及完整分钟high补查共同跟踪持仓高点。
日亏损3%禁买当日及下一交易日；阶段回撤20%确认清仓后次交易日才恢复。
20%是阶段清仓触发线，不保证全历史回撤上限；不使用永久停机或长期空仓解锁。
时间退出保留20自然日且当前收益<+3%；不改成20交易日或-3%。
仅经本地模拟检查，未宣称已在聚宽服务器回测通过。
"""
from jqdata import *
import numpy as np
import math
import builtins as _bi
from datetime import timedelta


def initialize(context):
    set_benchmark('000300.XSHG')
    set_option('use_real_price', True)
    set_option('avoid_future_data', True)
    set_order_cost(OrderCost(close_tax=0.001, open_commission=0.0003,
                            close_commission=0.0003, min_commission=5), type='stock')
    set_slippage(FixedSlippage(0.001))  # 金额价差0.001元，不是0.1%。
    g.ma_short, g.ma_mid, g.ma_long = 10, 20, 30
    g.angle_threshold, g.volume_ratio = 0.5, 1.2
    g.rsi_period, g.rsi_buy_min, g.rsi_buy_max = 14, 35, 65
    g.momentum_period, g.momentum_threshold = 12, 0.02
    g.atr_period, g.min_volatility, g.max_volatility = 14, 0.10, 0.45
    g.require_all_ma_up = False  # 默认保留原源码实际执行的MA10>MA20。
    g.stop_loss, g.take_profit = 0.05, 0.12
    g.trailing_stop, g.trailing_activate = 0.04, 0.06
    g.max_hold_days, g.time_stop_loss = 20, 0.03
    g.max_holdings, g.max_daily_buy, g.single_position_pct = 2, 2, 0.5
    g.max_daily_loss, g.max_drawdown_stop = 0.03, 0.20
    g.market_ma, g.market_strength_threshold = 20, 0.01
    g.require_market_uptrend, g.max_same_industry = False, 100
    g.limit_buffer = 0.01  # 委托保护带1%，不是滑点；涨跌停价另行约束。
    for name in ('buy_price', 'highest_price', 'buy_date', 'buy_volume',
                 'buy_industry', 'buy_signal_score', 'trailing_activated',
                 'tracked_orders', 'exit_requests', 'exit_block_log', 'sell_last_attempt'):
        setattr(g, name, {})
    g.prepared_date = g.buy_scan_date = g.observer_last_dt = None
    g.bought_today = set()
    g.daily_buy_count = g.observer_calls = 0
    g.daily_start_value = g.portfolio_high = float(context.portfolio.total_value)
    g.historical_high = g.portfolio_high
    g.max_historical_drawdown = 0.0
    g.portfolio_liquidating = g.daily_risk_halted = g.pause_trading = False
    g.daily_cooldown_pending = g.daily_cooldown_active = False
    g.risk_trigger_date = g.execution_error_logged = None
    g.execution_ready = True
    g.market_trend, g.market_strength, g.market_ready = 0, 0.0, False
    frequency = getattr(getattr(context, 'run_params', None), 'frequency', None)
    if frequency is not None and frequency != 'minute':
        raise ValueError('请在聚宽回测界面选择“分钟”频率，才能执行09:30买入。')
    run_daily(before_trading_start, time='09:00')
    run_daily(observe_execution, time='every_bar')
    run_daily(check_signals, time='09:30')
    run_daily(close_buy_window, time='09:31')
    run_daily(check_stop_loss, time='14:50')
    run_daily(check_portfolio_risk, time='14:55')
    log.info('MA0930修正版：分钟回测；09:30买入、09:31撤余单、14:50个股退出、14:55账户风控')


def before_trading_start(context):
    """盘前和09:00显式调度兼容；同日只重置一次，盘前不发交易委托。"""
    if g.prepared_date == context.current_dt.date():
        return
    g.prepared_date = context.current_dt.date()
    g.bought_today = set()
    g.daily_buy_count = g.observer_calls = 0
    g.observer_last_dt = None
    g.daily_start_value = float(context.portfolio.total_value)
    g.daily_risk_halted = False
    g.daily_cooldown_active = g.daily_cooldown_pending
    g.daily_cooldown_pending = False
    sync_execution_state(context)
    finish_portfolio_liquidation(context)
    update_daily_risk(context)
    check_market_environment(context)
    log.info('【盘前状态】持仓%s只，待卖%s，日亏损冷静期=%s，阶段清仓=%s'
             % (len(live_positions(context)), sorted(g.exit_requests),
                g.daily_cooldown_active, g.portfolio_liquidating))


def calculate_ma_angle(ma_values):
    """计算均线的斜率角度"""
    if len(ma_values) < 2:
        return 0
    
    y1 = ma_values[-2]
    y2 = ma_values[-1]
    delta_y = y2 - y1
    
    if delta_y == 0 or y1 == 0:
        return 0
    
    relative_change = delta_y / y1
    angle_rad = math.atan(_bi.abs(relative_change))
    angle_deg = math.degrees(angle_rad)
    
    return angle_deg if delta_y > 0 else -angle_deg


def calculate_rsi(close_prices, period=14):
    """计算RSI指标"""
    if len(close_prices) < period + 1:
        return 50
    
    deltas = np.diff(close_prices[-period-1:])
    gains = deltas[deltas > 0].sum() / period
    losses = -deltas[deltas < 0].sum() / period
    
    if losses == 0:
        return 100
    
    rs = gains / losses
    rsi = 100 - (100 / (1 + rs))
    return rsi


def calculate_atr(high, low, close, period=14):
    """计算ATR和波动率"""
    if len(close) < period + 1:
        return 0, 0
    
    tr_list = []
    for i in range(1, len(close)):
        tr = _bi.max(high[i] - low[i], 
                _bi.abs(high[i] - close[i-1]), 
                _bi.abs(low[i] - close[i-1]))
        tr_list.append(tr)
    
    if len(tr_list) < period:
        return 0, 0
    
    atr = np.mean(tr_list[-period:])
    
    # 计算波动率（20日收益率标准差）
    if len(close) >= 21:
        returns = np.diff(close[-21:]) / close[-21:-1]
        volatility = np.std(returns) * np.sqrt(252)
    else:
        volatility = 0
    
    return atr, volatility


def calculate_momentum(close_prices, period=10):
    """计算动量"""
    if len(close_prices) < period + 1:
        return 0
    
    return (close_prices[-1] - close_prices[-period-1]) / close_prices[-period-1]


def positive_number(value):
    try:
        value = float(value)
        return value if np.isfinite(value) and value > 0 else 0.0
    except (ValueError, TypeError, OverflowError):
        return 0.0


def get_realtime_price(stock, current_data=None, fallback_price=None, prefer_open=False):
    """无有效当前行情就跳过；买入只参考当日开盘价，不回退昨日价格。"""
    try:
        if current_data is None:
            current_data = get_current_data()
        item = current_data[stock]
        return positive_number(item.day_open if prefer_open else item.last_price)
    except Exception:
        return 0.0


def get_stock_industry_name(stock, date=None):
    try:
        info = get_industry(stock, date=date).get(stock, {})
        return (info.get('sw_l1') or {}).get('industry_name', '未知')
    except Exception as exc:
        log.warning('【行业查询失败】%s：%s' % (stock, exc))
        return '未知'


def check_market_environment(context):
    g.market_ready = False
    try:
        df = get_price('000300.XSHG', end_date=context.previous_date,
                       count=g.market_ma + 20, frequency='daily', fields=['close'],
                       skip_paused=True, fq='pre')
        if df is None or len(df) < _bi.max(20, g.market_ma):
            raise ValueError('指数历史不足')
        close = np.asarray(df['close'].values, dtype=float)
        if not np.all(np.isfinite(close)) or np.any(close <= 0):
            raise ValueError('指数历史价格无效')
        g.market_trend = int(close[-1] > np.mean(close[-g.market_ma:]))
        g.market_strength = close[-1] / close[-20] - 1.0  # 保留原首尾口径，19个间隔。
        g.market_ready = True
    except Exception as exc:
        g.market_strength = float('nan')
        log.error('【市场取数失败】禁买，不沿用旧信号：%s' % exc)


def check_signals(context):
    """每日只允许09:30扫描/开仓；无信号时给出过滤统计。"""
    if context.current_dt.strftime('%H:%M') != '09:30':
        return
    before_trading_start(context)
    if g.buy_scan_date == context.current_dt.date():
        return
    g.buy_scan_date = context.current_dt.date()
    check_market_environment(context)
    check_portfolio_risk(context)
    if not g.execution_ready or g.pause_trading:
        log.info('【今日禁买】日内风控=%s，下一交易日冷静期=%s，阶段清仓=%s，清仓确认日期=%s'
                 % (g.daily_risk_halted, g.daily_cooldown_active,
                    g.portfolio_liquidating, g.risk_trigger_date))
        return
    if not g.market_ready or g.market_strength < g.market_strength_threshold:
        log.info('【今日无开仓】市场强度=%s，需>=1%%' % g.market_strength)
        return
    if g.require_market_uptrend and g.market_trend != 1:
        log.info('【今日无开仓】指数未在MA20之上')
        return
    opens = read_open_orders(context)
    if opens is None:
        return
    occupied = set(live_positions(context)) | {o.security for o in opens.values() if o.is_buy}
    if len(occupied) >= g.max_holdings:
        log.info('【今日无开仓】实际持仓与待成交买单已占满%s个名额' % g.max_holdings)
        return
    try:
        pool = get_index_stocks('000300.XSHG', date=context.previous_date)
        current = get_current_data()
    except Exception as exc:
        log.error('【股票池/行情失败】取消今日买入：%s' % exc)
        return
    signals, counts, industry_count = [], {}, {}
    for stock in live_positions(context):
        industry = g.buy_industry.get(stock, '未知')
        industry_count[industry] = industry_count.get(industry, 0) + 1
    def rejected(reason):
        counts[reason] = counts.get(reason, 0) + 1
    for stock in pool:
        try:
            if stock in occupied or stock in g.exit_requests:
                rejected('已持仓或待处理'); continue
            item = current[stock]  # 直接触发按需加载，不能先用字典成员判断。
            if item.paused or item.is_st or _bi.any(x in item.name for x in ('ST', '*', '退')):
                rejected('ST停牌退市风险'); continue
            df = get_price(stock, end_date=context.previous_date, count=g.ma_long + 51,
                           frequency='daily', fields=['close','high','low','volume'],
                           skip_paused=True, fq='pre')
            if df is None or len(df) < g.ma_long + 50:
                rejected('历史不足'); continue
            close, high, low, volume = [np.asarray(df[f].values, dtype=float)
                                        for f in ('close','high','low','volume')]
            if (_bi.any(not np.all(np.isfinite(x)) for x in (close,high,low,volume))
                    or np.any(close<=0) or np.any(high<=0) or np.any(low<=0) or np.any(volume<0)):
                rejected('历史无效'); continue
            ma10, ma20, ma30 = [np.mean(close[-w:]) for w in (g.ma_short,g.ma_mid,g.ma_long)]
            if not (ma10>ma20) or (g.require_all_ma_up and not (ma20>ma30)):
                rejected('均线排列'); continue
            previous_ma = np.mean(close[-g.ma_short-1:-1])
            angle = calculate_ma_angle([previous_ma,ma10])
            if angle < g.angle_threshold:
                rejected('角度'); continue
            rsi = calculate_rsi(close,g.rsi_period)
            if not (g.rsi_buy_min<=rsi<=g.rsi_buy_max):
                rejected('RSI'); continue
            momentum = calculate_momentum(close,g.momentum_period)
            if not np.isfinite(momentum) or momentum < g.momentum_threshold:
                rejected('动量'); continue
            atr, volatility = calculate_atr(high,low,close,g.atr_period)
            if not np.isfinite(volatility) or not (g.min_volatility<=volatility<=g.max_volatility):
                rejected('波动率'); continue
            if volume[-1] < np.mean(volume[-10:-1])*g.volume_ratio:
                rejected('成交量'); continue
            price = get_realtime_price(stock,current,prefer_open=True)
            if price<=0 or price>=item.high_limit or price<=item.low_limit:
                rejected('开盘行情涨跌停'); continue
            if price/ma10-1 > 0.10:
                rejected('高于MA10超过10%'); continue
            industry = get_stock_industry_name(stock,context.previous_date)
            if industry_count.get(industry,0)>=g.max_same_industry:
                rejected('行业上限'); continue
            score = angle*2+(rsi-50)*0.5+momentum*100
            signals.append((stock,float(score),industry))
        except Exception as exc:
            rejected('异常')
            log.warning('【个股跳过】%s：%s' % (stock,exc))
    log.info('【09:30扫描】股票池%s，候选%s，过滤统计%s'
             % (len(pool),len(signals),sorted(counts.items())))
    execute_trades(context,signals,industry_count)


def make_order_style(stock, item, price, is_buy):
    """统一限价保护，兼容科创板，限价不保证成交。"""
    hi, lo = positive_number(item.high_limit), positive_number(item.low_limit)
    if not hi or not lo or lo>hi or not positive_number(price):
        raise ValueError('无效行情或涨跌停价')
    raw = price*(1+g.limit_buffer if is_buy else 1-g.limit_buffer)
    limit = (math.ceil(raw*100-1e-8) if is_buy else math.floor(raw*100+1e-8))/100.
    limit = _bi.max(lo,_bi.min(hi,limit))
    return LimitOrderStyle(limit), limit


def execute_trades(context, signals, industry_count=None):
    if context.current_dt.strftime('%H:%M') != '09:30':
        return
    service_pending_execution(context)
    if g.pause_trading or not g.execution_ready:
        return
    opens = read_open_orders(context)
    if opens is None:
        return
    occupied = set(live_positions(context)) | {o.security for o in opens.values() if o.is_buy}
    pending = {o.security for o in opens.values() if o.is_buy}
    slots = _bi.min(g.max_holdings-len(occupied),g.max_daily_buy-len(g.bought_today|pending))
    if slots<=0 or not signals:
        return
    # 待卖或卖单未完成时先完成退出；不使用预计卖出资金开新仓。
    if g.exit_requests or _bi.any(not o.is_buy for o in opens.values()):
        log.info('【买入暂缓】仍有待卖或未完成卖单'); return
    industry_count = dict(industry_count or {})
    choices = sorted((x for x in signals if x[0] not in occupied),key=lambda x:x[1],reverse=True)
    if not choices:
        return
    budget_each = _bi.min(float(context.portfolio.available_cash)/_bi.min(slots,len(choices)),
                          float(context.portfolio.total_value)*g.single_position_pct)
    remaining = float(context.portfolio.available_cash)
    current = get_current_data()
    for stock, score, industry in choices:
        if slots<=0 or not g.execution_ready or g.pause_trading:
            break
        try:
            if stock in occupied or industry_count.get(industry,0)>=g.max_same_industry:
                continue
            item = current[stock]
            price = get_realtime_price(stock,current,prefer_open=True)
            if item.paused or item.is_st or price<=item.low_limit or price>=item.high_limit or price<=0:
                continue
            style,budget_price = make_order_style(stock,item,price,True)
            budget = _bi.min(budget_each,remaining,float(context.portfolio.available_cash))
            net = _bi.max(0.,budget-_bi.max(5.,budget*0.0003))
            shares = int(net/budget_price)//100*100
            if shares < (200 if is_star_stock(stock) else 100):
                continue
            obj = order(stock,shares,style=style)
            if not remember_order(context,obj,stock,'buy',industry=industry,score=score):
                continue
            filled = int(getattr(obj,'filled',0) or 0)
            if order_is_terminal(obj) and filled<=0:
                continue
            occupied.add(stock);slots-=1
            industry_count[industry] = industry_count.get(industry,0)+1
            remaining -= shares*budget_price+_bi.max(5.,shares*budget_price*0.0003)
        except Exception as exc:
            log.warning('【买入异常】%s：%s' % (stock,exc))


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
        g.trailing_activated[stock] = False
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
            # 仅在实际持仓归零且无活动委托后确认清仓；本策略不新增卖后冷静期。
            log.info('【清仓确认】%s，持仓归零，原因：%s'
                     % (stock, g.exit_requests[stock]['reason']))
            del g.exit_requests[stock]
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
    for obj in list(open_orders.values()):
        if getattr(obj, 'is_buy', False) and obj.security in g.exit_requests:
            try:
                cancel_order(obj)
            except Exception as exc:
                log_exit_block(context, obj.security, '止损撤买单失败：%s' % exc)
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
            if price <= 0:
                log_exit_block(context, stock, '无有效行情')
                continue
            quantity = _bi.min(closeable, int(position.total_amount))
            if quantity < int(position.total_amount):
                if is_star_stock(stock) and quantity < 200:
                    log_exit_block(context, stock, '科创板非全清仓不足200股，继续等待可卖数量')
                    continue
                if not is_star_stock(stock):
                    quantity = quantity // 100 * 100
                    if quantity <= 0:
                        log_exit_block(context, stock, '非全清仓可卖数量不足一手')
                        continue
            last_attempt = g.sell_last_attempt.get(stock)
            if last_attempt == context.current_dt:
                continue
            g.sell_last_attempt[stock] = context.current_dt
            try:
                style, _ = make_order_style(stock, item, price, False)
                # 仅出售可卖数量；T+1锁定的余量留在队列，次日继续清仓。
                obj = order(stock, -quantity, style=style)
            except Exception as exc:
                log_exit_block(context, stock, '下单异常：%s' % exc)
                continue
            remember_order(context, obj, stock, 'sell',
                           reason=g.exit_requests[stock]['reason'])
        except Exception as exc:
            log_exit_block(context, stock, '行情或委托状态异常：%s' % exc)


def update_daily_risk(context):
    """3%日亏损一旦触发，禁买当日及下一交易日，不因反弹解除。"""
    total_value = float(context.portfolio.total_value)
    invalid_value = not np.isfinite(total_value) or total_value <= 0
    if np.isfinite(g.daily_start_value) and g.daily_start_value > 0 and not invalid_value:
        loss = 1.0 - total_value / g.daily_start_value
        if loss + 1e-12 >= g.max_daily_loss and not g.daily_risk_halted:
            g.daily_risk_halted = True
            g.daily_cooldown_pending = True
            log.warning('【当日禁买】日亏损%.2f%%，当日及下一交易日禁买' % (loss * 100))
    g.pause_trading = (invalid_value or g.daily_risk_halted or g.daily_cooldown_active or g.portfolio_liquidating
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
    # 确认清仓当日禁买；次交易日仍须满足独立的日亏损冷静期及市场过滤。
    g.risk_trigger_date = context.current_dt.date()
    log.info('【账户清仓确认】阶段高点重置为%.2f；全历史高点%.2f保持，下一交易日起按市场条件及日亏损冷静期筛选'
             % (g.portfolio_high, g.historical_high))


def service_pending_execution(context):
    """在09:30/09:31/14:50/14:55同步和重试已存在的退出，不补买。"""
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

        end_dt = _bi.min(current_dt - timedelta(minutes=1),
                         current_dt.replace(hour=15, minute=0, second=0, microsecond=0))
        if end_dt < start_dt:
            return float(fallback_price)
        minute_df = get_price(
            stock,
            start_date=start_dt,
            end_date=end_dt,
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


def align_position_cost(stock, position):
    cost = positive_number(getattr(position,'avg_cost',0))
    if not cost:
        return False
    g.buy_price[stock] = cost
    g.buy_volume[stock] = int(position.total_amount)
    return True


def observe_peaks(context, full_minutes=False):
    """T+1同样跟踪；固定检查/收盘补齐已完成分钟high，避免只记录收盘采样价。"""
    current = get_current_data()
    for stock,position in live_positions(context).items():
        try:
            if not align_position_cost(stock,position):
                log_exit_block(context,stock,'实际成本尚未同步'); continue
            price = get_realtime_price(stock,current)
            if price<=0:
                continue
            high = (get_intraday_high(stock,context.current_dt,price,g.buy_date.get(stock))
                    if full_minutes else price)
            g.highest_price[stock] = _bi.max(g.highest_price.get(stock,g.buy_price[stock]),high)
            if g.highest_price[stock]/g.buy_price[stock]-1+1e-12 >= g.trailing_activate:
                g.trailing_activated[stock] = True
        except Exception as exc:
            log_exit_block(context,stock,'高点观察异常：%s' % exc)


def observe_execution(context):
    if g.observer_last_dt == context.current_dt:
        return
    g.observer_last_dt = context.current_dt
    g.observer_calls += 1
    sync_execution_state(context)
    if context.current_dt.strftime('%H:%M')>'09:30':
        opens = read_open_orders(context)
        if opens is not None and _bi.any(o.is_buy for o in opens.values()):
            cancel_unfinished_buys(context)
    observe_peaks(context)
    finish_portfolio_liquidation(context)


def close_buy_window(context):
    sync_execution_state(context)
    cancel_unfinished_buys(context)
    service_pending_execution(context)


def check_stop_loss(context):
    """14:50生成个股退出意图；即使T+1或委托失败，意图也会跨日保留。"""
    check_portfolio_risk(context)
    observe_peaks(context,full_minutes=True)
    current = get_current_data()
    for stock,position in list(live_positions(context).items()):
        if stock in g.exit_requests:
            continue
        try:
            price = get_realtime_price(stock,current)
            if current[stock].paused or price<=0 or not align_position_cost(stock,position):
                continue
            cost = g.buy_price[stock]
            profit = price/cost-1
            high = g.highest_price.get(stock,cost)
            drawdown = 1-price/high
            entry = g.buy_date.get(stock)
            held = (context.current_dt.date()-entry.date()).days if entry is not None else None
            reason = None
            if profit <= -g.stop_loss+1e-12:
                reason = '固定止损，收益%.2f%%' % (profit*100)
            elif g.trailing_activated.get(stock,False) and drawdown+1e-12>=g.trailing_stop:
                reason = '已激活移动止损，高点回撤%.2f%%，当前收益%.2f%%' % (drawdown*100,profit*100)
            elif profit+1e-12 >= g.take_profit:
                reason = '固定止盈，收益%.2f%%' % (profit*100)
            elif held is not None and held>=g.max_hold_days and profit<g.time_stop_loss:
                reason = '时间退出，持有%s自然日，收益%.2f%%' % (held,profit*100)
            if reason:
                request_exit(context,stock,reason)
                log.info('【退出信号】%s：%s，等待实际成交' % (stock,reason))
        except Exception as exc:
            log_exit_block(context,stock,'退出检查异常：%s' % exc)
    service_pending_execution(context)


def check_portfolio_risk(context):
    service_pending_execution(context)
    total = positive_number(context.portfolio.total_value)
    if not total:
        g.pause_trading = True
        log.error('【净值异常】停止新买入'); return
    g.historical_high = _bi.max(g.historical_high,total)
    g.max_historical_drawdown = _bi.max(g.max_historical_drawdown,1-total/g.historical_high)
    if not g.portfolio_liquidating:
        g.portfolio_high = _bi.max(g.portfolio_high,total)
        dd = 1-total/g.portfolio_high
        if dd+1e-12 >= g.max_drawdown_stop:
            g.portfolio_liquidating = True
            g.risk_trigger_date = context.current_dt.date()
            log.warning('【阶段回撤清仓】%.2f%%，未确认实际清仓前不重置高点' % (dd*100))
    if g.portfolio_liquidating:
        for stock in live_positions(context):
            request_exit(context,stock,'账户阶段回撤清仓',force=True)
        cancel_unfinished_buys(context)
    service_pending_execution(context)


def clean_position_records(stock):
    for name in ('buy_price','highest_price','buy_date','buy_volume',
                 'buy_industry','buy_signal_score','trailing_activated'):
        getattr(g,name).pop(stock,None)


def after_trading_end(context):
    """只核对成交、补齐当日高点及记录统计，不发买卖单。"""
    sync_execution_state(context)
    observe_peaks(context,full_minutes=True)
    finish_portfolio_liquidation(context)
    total = positive_number(context.portfolio.total_value)
    if total:
        g.historical_high = _bi.max(g.historical_high,total)
        g.max_historical_drawdown = _bi.max(g.max_historical_drawdown,1-total/g.historical_high)
    if g.observer_calls<2:
        log.error('【频率异常】请使用分钟回测，当前观察回调不足2次')
    log.info('【收盘】持仓=%s，今日实际买入=%s，待卖=%s，阶段清仓=%s，全历史观测最大回撤=%.2f%%'
             % (sorted(live_positions(context)),sorted(g.bought_today),
                sorted(g.exit_requests),g.portfolio_liquidating,g.max_historical_drawdown*100))
