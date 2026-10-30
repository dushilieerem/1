# 聚宽版本 - 40交易日回购 + 小市值 + 全年基本面筛选 + 保守模式（1/4/12月半仓+严格筛选）

import pandas as pd
import warnings
warnings.filterwarnings('ignore')

from jqdata import *
from jqdata import finance

def initialize(context):
    set_option('use_real_price', True)
    set_option("avoid_future_data", True)
    set_benchmark('000852.XSHG')
    
    set_order_cost(OrderCost(
        open_tax=0, 
        close_tax=0.001, 
        open_commission=0.0003, 
        close_commission=0.0003, 
        close_today_commission=0, 
        min_commission=5
    ), type='stock')
    set_slippage(FixedSlippage(0.002))
    
    # 每月第一个交易日：先生成目标池，9:30卖出/减仓，9:40买入/补仓
    run_monthly(rebalance, 1, time='09:01')
    run_monthly(sell_rebalance, 1, time='09:30')
    run_monthly(buy_rebalance, 1, time='09:40')

    g.max_positions = 5                # 固定持有5只
    g.max_position_percent = 0.20      # 默认单只上限20%
    g.review_days = 40
    g.max_market_cap = 500             # valuation.market_cap 单位为亿元，默认上限500亿
    g.target_codes = []
    g.rebalance_ready = False

def rebalance(context):
    # 只有本月目标池完整生成后，后续卖出和买入阶段才允许执行。
    g.target_codes = []
    g.rebalance_ready = False
    current_date = context.current_dt.date()
    current_date_str = current_date.strftime('%Y-%m-%d')
    
    log.info(f"\n{'='*60}")
    log.info(f"{current_date_str}: 月度调仓开始")
    log.info(f"{'='*60}")
    
    # ========== 根据月份决定保守/正常模式 ==========
    current_month = current_date.month
    if current_month in [1, 4, 12]:
        log.info(f"当前月份为 {current_month} 月，启用【保守模式】（半仓 + 严格筛选）")
        # 保守参数
        g.max_position_percent = 0.10          # 单只最大10%，总仓位≤50%
        pe_limit = 30
        pb_limit = 3
    else:
        log.info(f"当前月份为 {current_month} 月，启用【正常模式】")
        g.max_position_percent = 0.20
        g.max_market_cap = 500
        pe_limit = 40
        pb_limit = 4
    
    # ========== 第一步：获取过去40个交易日有回购的股票 ==========
    buyback_stocks = get_buyback_stocks(context)
    if buyback_stocks is None:
        log.error("回购公告查询失败，本月保持现有持仓，不执行调仓")
        return
    if len(buyback_stocks) == 0:
        log.info("过去40个交易日无回购公告，本月目标为空")
        g.rebalance_ready = True
        return
    log.info(f"有回购的股票: {len(buyback_stocks)}只")
    
    # ========== 第二步：获取前一个交易日数据 ==========
    prev_date = context.previous_date
    prev_date_str = prev_date.strftime('%Y-%m-%d')
    log.info(f"使用数据日期: {prev_date_str}")
    
    # ========== 第三步：获取股票数据并筛选 ==========
    candidate_stocks = []
    filter_stats = {
        'total': len(buyback_stocks),
        '不可交易或ST': 0,
        '无数据': 0,
        '市值过大': 0,
        'PE无效或超标': 0,
        'PB无效或超标': 0,
        '通过': 0
    }

    current_data = get_current_data()
    tradable_stocks = []
    for stock in buyback_stocks:
        try:
            data = current_data[stock]
            if data.paused or data.is_st or data.last_price <= 0:
                filter_stats['不可交易或ST'] += 1
                continue
            tradable_stocks.append(stock)
        except Exception:
            filter_stats['不可交易或ST'] += 1

    if tradable_stocks:
        q = query(
            valuation.code,
            valuation.market_cap,
            valuation.pe_ratio,
            valuation.pb_ratio
        ).filter(valuation.code.in_(tradable_stocks))
        try:
            val_df = get_fundamentals(q, date=prev_date_str)
        except Exception as e:
            log.error(f"基本面批量查询失败，本月保持现有持仓: {e}")
            return
    else:
        val_df = pd.DataFrame()

    returned_codes = set(val_df['code'].tolist()) if not val_df.empty else set()
    filter_stats['无数据'] = len(tradable_stocks) - len(returned_codes)

    for row in val_df.itertuples(index=False):
        try:
            stock = row.code
            market_cap = row.market_cap
            if pd.isna(market_cap) or market_cap <= 0:
                filter_stats['无数据'] += 1
                continue
            
            # 市值筛选（使用动态上限）
            if market_cap > g.max_market_cap:
                filter_stats['市值过大'] += 1
                continue
            
            pe = row.pe_ratio
            pb = row.pb_ratio
            
            # 使用动态 PE/PB 上限
            if pd.isna(pe) or pe <= 0 or pe > pe_limit:
                filter_stats['PE无效或超标'] += 1
                continue
            
            if pd.isna(pb) or pb <= 0 or pb > pb_limit:
                filter_stats['PB无效或超标'] += 1
                continue
            
            filter_stats['通过'] += 1
            candidate_stocks.append({
                'code': stock,
                'market_cap': market_cap,
                'pe': pe,
                'pb': pb
            })
            
        except Exception:
            filter_stats['无数据'] += 1
            continue
    
    # 打印筛选统计（动态显示阈值）
    log.info(f"\n{'='*60}")
    log.info("基本面筛选统计:")
    log.info(f"  总回购股票: {filter_stats['total']}")
    log.info(f"  不可交易或ST: {filter_stats['不可交易或ST']}")
    log.info(f"  无数据: {filter_stats['无数据']}")
    log.info(f"  市值过大(>{g.max_market_cap:.0f}亿): {filter_stats['市值过大']}")
    log.info(f"  PE无效或超标(PE≤0或PE>{pe_limit}): {filter_stats['PE无效或超标']}")
    log.info(f"  PB无效或超标(PB≤0或PB>{pb_limit}): {filter_stats['PB无效或超标']}")
    log.info(f"  最终通过: {filter_stats['通过']}")
    log.info(f"{'='*60}")
    
    if len(candidate_stocks) == 0:
        log.info("无符合条件的候选股票，本月目标为空")
        g.rebalance_ready = True
        return
    
    # ========== 第五步：按市值排序，选最小的 g.max_positions 只 ==========
    candidate_stocks.sort(key=lambda x: x['market_cap'])
    target_stocks = candidate_stocks[:g.max_positions]
    
    log.info(f"\n选中 {len(target_stocks)} 只目标股票（市值最小）:")
    for i, s in enumerate(target_stocks, 1):
        log.info(f"{i}. {s['code']}: 市值{s['market_cap']:.2f}亿, PE={s['pe']:.2f}, PB={s['pb']:.2f}")
    
    # ========== 第六步：保存目标池，等待9:30和9:40分阶段调仓 ==========
    g.target_codes = [s['code'] for s in target_stocks]
    g.rebalance_ready = True

def get_buyback_stocks(context):
    """获取截至前一交易日、过去 review_days 个交易日内有股份回购的股票"""
    end_date = context.previous_date
    trade_days = get_trade_days(end_date=end_date, count=g.review_days)
    if len(trade_days) == 0:
        log.error("无法取得回购检查窗口的交易日")
        return None
    start_date = trade_days[0]
    
    try:
        q = query(
            finance.STK_CAPITAL_CHANGE.code
        ).filter(
            finance.STK_CAPITAL_CHANGE.pub_date >= start_date.strftime('%Y-%m-%d'),
            finance.STK_CAPITAL_CHANGE.pub_date <= end_date.strftime('%Y-%m-%d'),
            finance.STK_CAPITAL_CHANGE.change_reason == '股份回购'
        ).distinct()
        
        df = finance.run_query(q)
        return df['code'].unique().tolist() if len(df) > 0 else []
        
    except Exception as e:
        log.error(f"查询回购股票出错: {e}")
        return None

def sell_rebalance(context):
    """9:30卖出目标池外持仓，并降低目标池内的超配仓位。"""
    if not g.rebalance_ready:
        log.warning("本月目标池生成失败，保留现有持仓，不执行卖出")
        return

    target_codes = g.target_codes
    current_data = get_current_data()
    weight = (min(1.0 / len(target_codes), g.max_position_percent)
              if target_codes else 0)
    target_value = context.portfolio.total_value * weight

    for stock, position in list(context.portfolio.positions.items()):
        desired_value = target_value if stock in target_codes else 0
        if position.value <= desired_value:
            continue

        data = current_data[stock]
        if (data.paused or data.last_price is None or pd.isna(data.last_price)
                or data.last_price <= data.low_limit):
            log.warning(f"暂无法卖出或减仓: {stock}（停牌、价格无效或跌停）")
            continue
        if desired_value > 0 and position.value - desired_value < data.last_price * 100:
            continue

        order_obj = order_target_value(stock, desired_value)
        if order_obj is not None:
            action = "清仓" if desired_value == 0 else "减仓"
            log.info(f"提交{action}委托: {stock}")
        else:
            log.warning(f"卖出或减仓委托失败: {stock}")


def buy_rebalance(context):
    """9:40使用卖出后释放的资金买入或补足目标股票。"""
    if not g.rebalance_ready:
        log.warning("本月目标池生成失败，不执行买入")
        return

    target_codes = g.target_codes
    current_data = get_current_data()
    if target_codes:
        weight = min(1.0 / len(target_codes), g.max_position_percent)
        target_value = context.portfolio.total_value * weight

        for stock in target_codes:
            data = current_data[stock]
            if (data.paused or data.is_st or data.last_price is None
                    or pd.isna(data.last_price)
                    or data.last_price <= data.low_limit
                    or data.last_price >= data.high_limit):
                log.warning(f"跳过买入: {stock}（停牌、ST、价格无效或处于涨跌停）")
                continue

            position = context.portfolio.positions.get(stock)
            current_value = position.value if position is not None else 0
            if current_value >= target_value:
                continue
            if target_value - current_value < data.last_price * 100:
                continue

            order_obj = order_target_value(stock, target_value)
            if order_obj is not None:
                log.info(f"提交买入/补仓委托: {stock}, 目标权重: {weight:.2%}")
            else:
                log.warning(f"买入/补仓委托失败: {stock}")
    
    # 打印调仓后持仓
    log.info(f"\n{'='*60}")
    log.info("09:40委托提交后当前持仓快照:")
    log.info(f"{'='*60}")
    total_pos_value = 0
    for stock, pos in context.portfolio.positions.items():
        if pos.closeable_amount > 0:
            if pos.price > 0:
                pos_value = pos.value
                total_pos_value += pos_value
                pct = pos_value / context.portfolio.total_value
                log.info(f"  {stock}: {pos.total_amount}股, 市值:{pos_value:.2f}, 占比:{pct:.2%}")
    
    cash_pct = (context.portfolio.total_value - total_pos_value) / context.portfolio.total_value
    log.info(f"现金占比: {cash_pct:.2%}")
    log.info(f"{'='*60}\n")

def before_trading_start(context):
    pass

def after_trading_end(context):
    pass
