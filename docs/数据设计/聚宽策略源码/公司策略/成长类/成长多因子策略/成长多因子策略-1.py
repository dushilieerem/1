# 导入函数库
from jqdata import *
from jqfactor import *
import pandas as pd
import datetime

#初始化函数 
def initialize(context):
    #设定股票池
    set_benchmark('000905.XSHG')
    # 用真实价格交易
    set_option('use_real_price', True)
    # 打开防未来函数
    set_option("avoid_future_data", True)
    # 将滑点设置为0
    set_slippage(FixedSlippage(0))
    # 设置交易成本万分之三
    set_order_cost(OrderCost(open_tax=0, close_tax=0.001, open_commission=0.0003, close_commission=0.0003, close_today_commission=0, min_commission=5),type='stock')
    # 过滤order中低于error级别的日志
    log.set_level('order', 'error')
    #选股参数
    g.stock_num = 5 #持仓数
    
    g.no_trading_today_signal = False
    g.hold_list = [] #当前持仓的全部股票  
    g.candidate_list = []
    g.target_list = []
    g.rebalance_ready = False
    g.target_invest_ratio = 0.995
    
    # 设置交易时间，每天运行
    run_weekly(prepare_rebalance, weekday=1, time='09:01', reference_security='000300.XSHG')
    run_weekly(sell_adjustment, weekday=1, time='09:30', reference_security='000300.XSHG')
    run_weekly(buy_adjustment, weekday=1, time='09:40', reference_security='000300.XSHG')
    run_daily(close_account, '09:30')
    run_daily(print_position_info, time='15:10', reference_security='000300.XSHG')



#1-1 选股模块
#先根据资产负债排除一些股票，再选出roe改善最多的列表，最后在这个列表中根据pb轮动
def get_stock_list(context):
    yesterday = context.previous_date
    # 必须指定历史日期，否则会把回测日之后上市的股票带入初始股票池。
    initial_list = get_all_securities(['stock'], date=yesterday).index.tolist()
    initial_list = filter_new_stock(context,initial_list)
    initial_list = filter_kcb_stock(context, initial_list)
    initial_list = filter_st_stock(initial_list)
    
    factor_values = get_factor_values(initial_list, ['operating_revenue_growth_rate', #营业收入增长率
    'total_profit_growth_rate', #利润总额增长率
    'earnings_growth', #5年盈利增长率
    ], end_date=yesterday, count=1)
    
    df = pd.DataFrame(index=initial_list)
    for factor_name in ['operating_revenue_growth_rate',
                        'total_profit_growth_rate', 'earnings_growth']:
        factor_df = factor_values.get(factor_name)
        if factor_df is None or factor_df.empty:
            log.warning('成长因子缺失：%s' % factor_name)
            return []
        df[factor_name] = factor_df.iloc[-1].reindex(initial_list)
    # 聚宽环境的 pandas 版本不固定，使用普通 NaN，避免旧版本没有 pd.NA。
    df = df.replace([float('inf'), float('-inf')], float('nan')).dropna()
    if df.empty:
        return []
    df['total_score'] = 0.2*df['operating_revenue_growth_rate'] + 0.4*df['total_profit_growth_rate'] +  0.4*df['earnings_growth'] 
    df = df.sort_values(by=['total_score'], ascending=False, kind='mergesort')
    top_count = max(1, int(0.1 * len(df)))
    complex_growth_list = list(df.index)[:top_count]
    
    q = query(valuation.code,valuation.circulating_market_cap,indicator.eps).filter(valuation.code.in_(complex_growth_list)).order_by(valuation.circulating_market_cap.asc())
    df = get_fundamentals(q, date=yesterday)
    if df is None or df.empty:
        return []
    df = df[df['eps']>0]
    final_list = list(df.code)
    
    return final_list

#1-2 开盘前打印自选股
def print_stock_list_before_open(context):
    stock_list = get_stock_list(context)
    stock_list = filter_paused_stock(stock_list)
    stock_list = stock_list[:g.stock_num]
    print('今日自选股:{}'.format(stock_list))



#2-1 周一盘前生成目标池
def prepare_rebalance(context):
    g.no_trading_today_signal = today_is_between(context, '04-05', '04-30')
    g.hold_list = list(context.portfolio.positions.keys())
    g.candidate_list = []
    g.target_list = []
    g.rebalance_ready = False
    if g.no_trading_today_signal:
        return

    try:
        target_list = get_stock_list(context)
    except Exception as exc:
        log.error('成长多因子选股失败，保留现有持仓：%s' % exc)
        return
    if not target_list:
        log.warning('成长多因子选股结果为空，本周不调仓并保留现有持仓')
        return
    # 暂存完整排序，09:30 再按实时可交易状态递补出前5只。
    g.candidate_list = target_list
    g.rebalance_ready = True


def _valid_last_price(data):
    return data.last_price is not None and not pd.isna(data.last_price) and data.last_price > 0


def _select_tradable_targets(context, current_data):
    targets = []
    held = set(context.portfolio.positions.keys())
    for stock in g.candidate_list:
        data = current_data[stock]
        # 已持仓股票即便临时停牌或涨跌停也保留为目标，避免被动错误换出。
        if stock not in held and (data.paused or data.is_st
                or not _valid_last_price(data)
                or data.last_price >= data.high_limit
                or data.last_price <= data.low_limit):
            continue
        targets.append(stock)
        if len(targets) >= g.stock_num:
            break
    return targets


#2-2 09:30卖出目标池外股票，并降低目标池内超配仓位
def sell_adjustment(context):
    if g.no_trading_today_signal or not g.rebalance_ready:
        return
    current_data = get_current_data()
    g.target_list = _select_tradable_targets(context, current_data)
    if not g.target_list:
        log.warning('当前候选均不可交易，本周保留现有持仓')
        g.rebalance_ready = False
        return
    target_value = (context.portfolio.total_value * g.target_invest_ratio
                    / len(g.target_list))
    for stock, position in list(context.portfolio.positions.items()):
        desired_value = target_value if stock in g.target_list else 0
        if position.value <= desired_value:
            continue
        data = current_data[stock]
        if data.paused or not _valid_last_price(data) or data.last_price <= data.low_limit:
            log.info('%s 停牌、价格无效或跌停，暂缓卖出' % stock)
            continue
        if desired_value > 0 and position.value - desired_value < data.last_price * 100:
            continue
        order_obj = order_target_value(stock, desired_value)
        if order_obj is None:
            log.warning('%s 卖出/减仓委托创建失败' % stock)


#2-3 09:40买入或补足目标股票
def buy_adjustment(context):
    if g.no_trading_today_signal or not g.rebalance_ready:
        return
    current_data = get_current_data()
    target_value = (context.portfolio.total_value * g.target_invest_ratio
                    / len(g.target_list))
    for stock in g.target_list:
        data = current_data[stock]
        if (data.paused or data.is_st or not _valid_last_price(data)
                or data.last_price >= data.high_limit
                or data.last_price <= data.low_limit):
            continue
        position = context.portfolio.positions.get(stock)
        current_value = position.value if position is not None else 0
        if target_value - current_value < data.last_price * 100:
            continue
        order_obj = order_target_value(stock, target_value)
        if order_obj is None:
            log.warning('%s 买入/补仓委托创建失败' % stock)

    

#3-1 交易函数
def order_target_value_(security, value):
    if value == 0:
        log.debug("Selling out %s" % (security))
    else:
        log.debug("Order %s to value %f" % (security, value))
    return order_target_value(security, value)

def open_position(security, value):
    order = order_target_value_(security, value)
    if order != None and order.filled > 0:
        return True
    return False

def close_position(position):
    security = position.security
    order = order_target_value_(security, 0)  # 可能会因停牌失败
    if order != None:
        if order.status == OrderStatus.held and order.filled == order.amount:
            return True
    return False
    
def close_account(context):
    # 每日重新判断，避免只在周一刷新信号造成4月清仓延迟或跨月继续空仓。
    g.no_trading_today_signal = today_is_between(context, '04-05', '04-30')
    if not g.no_trading_today_signal:
        return
    current_data = get_current_data()
    for stock in list(context.portfolio.positions.keys()):
        data = current_data[stock]
        if data.paused or not _valid_last_price(data) or data.last_price <= data.low_limit:
            log.info("暂无法卖出[%s]（停牌、价格无效或跌停）" % stock)
            continue
        order_obj = order_target_value(stock, 0)
        if order_obj is not None:
            log.info("卖出[%s]" % stock)
        else:
            log.warning("卖出委托创建失败[%s]" % stock)

def adjust_position(context, buy_stocks):
    for stock in context.portfolio.positions:
        if stock not in buy_stocks:
            log.info("[%s]不在应买入列表中" % (stock))
            position = context.portfolio.positions[stock]
            close_position(position)
        else:
            log.info("[%s]已经持有无需重复买入" % (stock))
    position_count = len(context.portfolio.positions)
    if g.stock_num > position_count:
        value = context.portfolio.cash / (g.stock_num - position_count)
        for stock in buy_stocks:
            if context.portfolio.positions[stock].total_amount == 0:
                if open_position(stock, value):
                    if len(context.portfolio.positions) == g.stock_num:
                        break



#4-1 过滤函数
def filter_paused_stock(stock_list):
    current_data = get_current_data()
    return [stock for stock in stock_list if not current_data[stock].paused]

def filter_st_stock(stock_list):
    current_data = get_current_data()
    return [stock for stock in stock_list
            if not current_data[stock].is_st
            and 'ST' not in current_data[stock].name
            and '*' not in current_data[stock].name
            and '退' not in current_data[stock].name]

def filter_limitup_stock(context, stock_list):
    last_prices = history(1, unit='1m', field='close', security_list=stock_list)
    current_data = get_current_data()
    return [stock for stock in stock_list if stock in context.portfolio.positions.keys()
            or last_prices[stock][-1] < current_data[stock].high_limit]

def filter_limitdown_stock(context, stock_list):
    last_prices = history(1, unit='1m', field='close', security_list=stock_list)
    current_data = get_current_data()
    return [stock for stock in stock_list if stock in context.portfolio.positions.keys()
            or last_prices[stock][-1] > current_data[stock].low_limit]

def filter_kcb_stock(context, stock_list):
    return [stock for stock in stock_list  if stock[0:3] != '688']

def filter_new_stock(context,stock_list):
    yesterday = context.previous_date
    return [stock for stock in stock_list if not yesterday - get_security_info(stock).start_date < datetime.timedelta(days=250)]
#4-1 判断今天是否为账户资金再平衡的日期
def today_is_between(context, start_date, end_date):
    today = context.current_dt.strftime('%m-%d')
    return start_date <= today <= end_date


#5-1 打印每日持仓信息
def print_position_info(context):
    #打印当天成交记录
    trades = get_trades()
    for _trade in trades.values():
        print('成交记录：'+str(_trade))
    #打印账户信息
    for position in list(context.portfolio.positions.values()):
        securities=position.security
        cost=position.avg_cost
        price=position.price
        ret=100*(price/cost-1)
        value=position.value
        amount=position.total_amount    
        print('代码:{}'.format(securities))
        print('成本价:{}'.format(format(cost,'.2f')))
        print('现价:{}'.format(price))
        print('收益率:{}%'.format(format(ret,'.2f')))
        print('持仓(股):{}'.format(amount))
        print('市值:{}'.format(format(value,'.2f')))
        print('———————————————————————————————————')
    print('———————————————————————————————————————分割线————————————————————————————————————————')
