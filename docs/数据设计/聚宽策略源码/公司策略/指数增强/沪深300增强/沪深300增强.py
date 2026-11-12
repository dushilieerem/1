import pandas as pd
import numpy as np
import datetime
from jqdata import *
from jqfactor import *

# ===== 打分预处理开关（效果对照用，直接改这里；默认全关 = 最原始版：缩尾+百分位排名+等权）=====
USE_MC_NEUTRAL = False   # 市值中性化：True=开（消除市值暴露，但可能削掉成分内偏小市值收益）
USE_ORTHO      = False   # 因子间正交化：True=开（三因子去相关，但因子变残差、业务含义消失）
USE_ZSCORE     = False   # 合成方式：True=z-score 等权；False=百分位排名等权（原始）

# 初始化函数 
def initialize(context):
    
    # 系统设置
    set_benchmark('000300.XSHG')
    set_option('use_real_price', True)
    set_option("avoid_future_data", True)
    set_slippage(PriceRelatedSlippage(0.00))
    set_order_cost(OrderCost(open_tax=0, close_tax=0.001, open_commission=0.0003, close_commission=0.0003, close_today_commission=0, min_commission=5),type='stock')
    log.set_level('order', 'error')
    log.set_level('history', 'error')
    log.set_level('system', 'error')
    
    # 全局变量
    g.stock_num = 60          # 持仓数量（用户 2026-08-07 调整为 60）
    g.hold_list = []
    g.high_limit_list = []
    g.s_list = []
    g.b_list = []
    g.target_list = []
    g.rebalance_ready = False
    g.target_invest_ratio = 0.995   # 预留约 0.5% 现金覆盖佣金和价格波动
    
    # 交易时间
    run_daily(prepare_stock_list, '09:00')
    run_monthly(get_stock_list, 1, '09:01')
    run_monthly(sell_adjustment, 1, '09:30')
    run_monthly(reduce_adjustment, 1, '09:30')
    run_monthly(buy_adjustment, 1, '09:40')
    run_daily(check_limit_up, '14:55')



# 准备股票池
def prepare_stock_list(context):
    
    #获取昨日涨停列表
    g.high_limit_list = []
    g.hold_list = list(context.portfolio.positions)
    if len(g.hold_list) != 0:
        df = get_price(g.hold_list, end_date=context.previous_date, frequency='daily', fields=['close','high_limit'], count=1, panel=False, fill_paused=False, skip_paused=False).dropna()
        df = df[df['close'] == df['high_limit']]
        g.high_limit_list = list(df.code)



# TTM 现金流工具：聚宽季度财务数据是单季度口径，直接汇总观察日前已披露的最近四个季度
def get_ttm_cashflow(stocks, asof):
    """返回按股票代码索引的 TTM 经营现金流和资本开支。

    watch_date 只读取观察日当时已经披露的数据；每只股票必须有四个不同报告期且字段完整，
    否则不参与本月打分，避免把缺报误当成 0。聚宽单次最多返回 5000 行，
    沪深300成分股 × 4 个季度约 1200 行，处于接口限制内。
    """
    if not stocks:
        return pd.Series(dtype=float), pd.Series(dtype=float)

    try:
        df = get_history_fundamentals(
            security=stocks,
            fields=[cash_flow.net_operate_cash_flow,
                    cash_flow.fix_intan_other_asset_acqui_cash],
            watch_date=asof,
            count=4,
            interval='1q',
            stat_by_year=False,
        )
    except Exception as exc:
        log.error('读取历史现金流失败：%s' % exc)
        return pd.Series(dtype=float), pd.Series(dtype=float)

    if df is None or df.empty:
        log.warning('历史现金流接口返回空表')
        return pd.Series(dtype=float), pd.Series(dtype=float)

    # 不同聚宽运行环境可能返回 statDate、day 或把 code 放在索引中。
    # TTM 求和只依赖每只股票最近四期，不应因报告期列名差异把整张表判为空。
    df = df.copy()
    df.columns = [str(c).split('.')[-1] for c in df.columns]
    if 'code' not in df.columns:
        df = df.reset_index()
        df.columns = [str(c).split('.')[-1] for c in df.columns]

    value_columns = ['net_operate_cash_flow',
                     'fix_intan_other_asset_acqui_cash']
    required = ['code'] + value_columns
    missing = [c for c in required if c not in df.columns]
    if missing:
        log.warning('历史现金流缺少字段 %s；实际字段 %s'
                    % (missing, list(df.columns)))
        return pd.Series(dtype=float), pd.Series(dtype=float)

    report_column = next((c for c in ['statDate', 'stat_date', 'day']
                          if c in df.columns), None)
    if report_column is not None:
        df = df.drop_duplicates(subset=['code', report_column], keep='last')

    ocf, capx = {}, {}
    for code, group in df.groupby('code'):
        if report_column is not None:
            group = group.sort_values(report_column)
        group = group.tail(4)
        if len(group) < 4:
            continue
        values = group[value_columns].apply(pd.to_numeric, errors='coerce')
        if values.isnull().any().any():
            continue
        ocf[code] = values['net_operate_cash_flow'].sum()
        capx[code] = values['fix_intan_other_asset_acqui_cash'].sum()

    log.info('TTM现金流：接口返回 %d 行，有效股票 %d/%d'
             % (len(df), len(ocf), len(stocks)))
    return pd.Series(ocf), pd.Series(capx)


# 选股
def get_stock_list(context):
    # 只有本次选股完整成功，后续三个调仓阶段才允许执行。
    g.rebalance_ready = False
    g.s_list = []
    g.b_list = []

    #基础信息
    yesterday = context.previous_date
    # 股票池改为沪深300成分股（原：get_all_securities 全市场）
    initial_list = get_index_stocks('000300.XSHG', date=context.previous_date)
    initial_list = filter_new_stock(context, initial_list)
    initial_list = filter_st_stock(initial_list)
    initial_list = filter_paused_stock(initial_list)
    if not initial_list:
        log.warning('沪深300可选股票池为空，跳过本次调仓并保留持仓')
        return
    
    # ===== 三因子对齐 BigQuant 的 TTM 口径 =====
    # 用户给的 BigQuant 定义：
    #   cash_to_assets_ttm = 全部资产现金回收率(滚动十二期) = TTM经营现金流净额 / 总资产
    #   cash_to_invest_ttm = 现金满足投资比率(滚动十二期) = TTM经营现金流净额 / TTM购建固定资产等支付的现金
    #   fcff_rate          = fcff_ttm / 企业价值近似值
    # 聚宽季度接口返回单季度数据，因此 TTM 应汇总最近四个已披露季度，不能用本期减去年同期。
    ttm_ocf, ttm_capx = get_ttm_cashflow(initial_list, context.previous_date)
    if ttm_ocf.empty or ttm_capx.empty:
        log.warning('TTM 现金流数据缺失，跳过本次调仓并保留持仓')
        return

    # 资产负债表面值 + 总市值（市值用于打分前中性化）
    try:
        q = get_fundamentals(query(
            valuation.code,
            valuation.market_cap,                  # 总市值（亿元）
            balance.total_assets,
            balance.total_liability,
            balance.cash_equivalents,
        ).filter(valuation.code.in_(initial_list)), date=yesterday)
    except Exception as exc:
        log.error('读取资产负债表失败：%s' % exc)
        return
    if q is None or q.empty:
        log.warning('资产负债表数据缺失，跳过本次调仓并保留持仓')
        return
    q = q.set_index('code')

    # 1) cash_to_assets_ttm = TTM经营现金流 / 总资产（期末）
    cash_to_assets = (ttm_ocf / q['total_assets']).reindex(initial_list)

    # 2) cash_to_invest_ttm = TTM经营现金流 / TTM购建固定资产等支付的现金(capx)；capx<=0 置 NaN
    cash_to_invest = (ttm_ocf / ttm_capx.mask(ttm_capx <= 0)).reindex(initial_list)

    # 3) fcff_rate = fcff_ttm / 企业价值近似值
    #    EV ≈ 总市值 + 负债合计 − 现金及等价物。market_cap 单位为亿元，先换算为元。
    #    原代码使用“负债 + 账面权益 − 现金”，实质接近总资产减现金，并非市场口径企业价值。
    #    fcff_ttm ≈ TTM(经营现金流) − TTM(购建固定资产等支付的现金)，即企业自由现金流 TTM
    fcff = ttm_ocf - ttm_capx
    ev = q['market_cap'] * 1e8 + q['total_liability'] - q['cash_equivalents']
    ev = ev.mask(ev <= 0)
    fcff_rate = (fcff / ev).reindex(initial_list)

    # 构建因子矩阵并对齐索引
    df = pd.DataFrame(index=initial_list)
    df['cash_to_assets'] = cash_to_assets
    df['cash_to_invest'] = cash_to_invest
    df['fcff_rate'] = fcff_rate
    df['market_cap'] = q['market_cap'].reindex(initial_list)

    # 质量底线：剔除三因子任一为 NaN 的票（无法打分）
    df = df.dropna(subset=['cash_to_assets', 'cash_to_invest', 'fcff_rate'])
    if df.empty:
        log.warning('三因子有效股票为空，跳过本次调仓并保留持仓')
        return

    # ---- 打分预处理（开关见文件顶部 USE_* 配置，用于快速效果对照）----
    # 1) 缩尾(winsorize)：截掉 1%~99% 之外的极端值（对 rank 无意义，但 z-score 前必须）
    def winsorize(s, lo=0.01, hi=0.99):
        ql, qh = s.quantile(lo), s.quantile(hi)
        return s.clip(ql, qh)
    for _c in ['cash_to_assets', 'cash_to_invest', 'fcff_rate']:
        df[_c] = winsorize(df[_c])

    # 诊断：打印三因子原始相关性（三者分子均为 TTM经营现金流，天然高相关）
    _corr = df[['cash_to_assets', 'cash_to_invest', 'fcff_rate']].corr()
    print('三因子相关性矩阵:\n', _corr.round(2))

    # 2) 市值中性化（开关 USE_MC_NEUTRAL）：
    #    沪深300成分内"偏小市值+质量"常是增强策略主要超额来源，中性化可能削掉这部分收益
    #    → 效果不好时先关掉这个对比（当前默认关）
    if USE_MC_NEUTRAL:
        df['ln_mc'] = np.log(df['market_cap'].mask(df['market_cap'] <= 0))
        df = df.dropna(subset=['ln_mc'])            # 市值缺失/非正的票不参与打分
        for _c in ['cash_to_assets', 'cash_to_invest', 'fcff_rate']:
            X = np.column_stack([np.ones(len(df)), df['ln_mc']])
            beta, *_ = np.linalg.lstsq(X, df[_c], rcond=None)
            df[_c] = df[_c] - X @ beta              # 残差 = 剔除市值后的纯因子

    # 2.5) 因子间正交化（开关 USE_ORTHO）：cash_to_invest/fcff_rate 对 cash_to_assets 回归取残差
    #      （默认关：正交化后因子变残差、业务含义消失，若增量信息本身弱反而损失区分度）
    if USE_ORTHO:
        _base = df['cash_to_assets'].copy()
        for _c in ['cash_to_invest', 'fcff_rate']:
            Xo = np.column_stack([np.ones(len(df)), _base])
            beta_o, *_ = np.linalg.lstsq(Xo, df[_c], rcond=None)
            df[_c] = df[_c] - Xo @ beta_o

    # 3) 合成（开关 USE_ZSCORE：True=z-score 等权；False=百分位排名等权，即最原始方式）
    w_assets, w_invest, w_fcff = 1/3, 1/3, 1/3
    if USE_ZSCORE:
        def zscore(s):
            m, sd = s.mean(), s.std()
            if sd == 0 or pd.isna(sd):
                return s * 0.0
            return (s - m) / sd
        for _c in ['cash_to_assets', 'cash_to_invest', 'fcff_rate']:
            df[_c] = zscore(df[_c])
        df['composite'] = (w_assets * df['cash_to_assets']
                           + w_invest * df['cash_to_invest']
                           + w_fcff * df['fcff_rate'])
    else:
        for _c in ['cash_to_assets', 'cash_to_invest', 'fcff_rate']:
            df[_c + '_r'] = df[_c].rank(pct=True)
        df['composite'] = (w_assets * df['cash_to_assets_r']
                           + w_invest * df['cash_to_invest_r']
                           + w_fcff * df['fcff_rate_r'])

    # 按综合评分降序，取前 200 再截最大持仓数
    df = df.sort_values('composite', ascending=False).head(200)
    stock_list = list(df.index)

    # 截取不超过最大持仓数的股票量
    target_list = stock_list[:min(g.stock_num, len(stock_list))]
    
    # 本次选股已完整成功：退出指数、ST、因子落选或不再进入前60名的持仓都应退出。
    # 昨日涨停股暂缓卖出，由尾盘涨停检查处理。
    g.target_list = target_list
    g.s_list = [s for s in g.hold_list
                if s not in target_list and s not in g.high_limit_list]
    g.b_list = [s for s in target_list if s not in g.hold_list]
    g.rebalance_ready = True
    print('卖出', g.s_list)
    print('———————————————————————————————————')
    print('买入', g.b_list)
    print('———————————————————————————————————')



# 判断行情字段是否可用于下单
def valid_last_price(data):
    return data.last_price is not None and not pd.isna(data.last_price) and data.last_price > 0


# 调仓第一阶段：先卖出目标池外股票，给后续再平衡释放现金
def sell_adjustment(context):
    if not g.rebalance_ready:
        log.warning('本月选股未成功，取消调仓并保留现有持仓')
        return

    current_data = get_current_data()
    for s in g.s_list:
        data = current_data[s]
        if data.paused or not valid_last_price(data):
            log.info('%s 停牌或价格无效，暂缓卖出' % s)
            continue
        if data.last_price <= data.low_limit:
            log.info('%s 跌停，无法卖出' % s)
            continue
        order = order_target_value(s, 0)
        if order is None:
            log.warning('%s 清仓委托创建失败' % s)


# 调仓第二阶段：先降低目标池内超配仓位
def reduce_adjustment(context):
    if not g.rebalance_ready or not g.target_list:
        return

    current_data = get_current_data()
    target_value = (context.portfolio.total_value * g.target_invest_ratio
                    / len(g.target_list))
    for s in g.target_list:
        position = context.portfolio.positions.get(s)
        if position is None or position.value <= target_value:
            continue
        data = current_data[s]
        if data.paused or not valid_last_price(data) or data.last_price <= data.low_limit:
            continue
        if position.value - target_value < data.last_price * 100:
            continue
        order = order_target_value(s, target_value)
        if order is None:
            log.warning('%s 降仓委托创建失败' % s)


# 调仓第三阶段：用卖出释放的现金补齐全部目标股，而不只买入新股票
def buy_adjustment(context):
    if not g.rebalance_ready or not g.target_list:
        return

    current_data = get_current_data()
    target_value = (context.portfolio.total_value * g.target_invest_ratio
                    / len(g.target_list))
    for s in g.target_list:
        data = current_data[s]
        if (data.paused or data.is_st or not valid_last_price(data)
                or data.last_price >= data.high_limit
                or data.last_price <= data.low_limit):
            continue
        position = context.portfolio.positions.get(s)
        current_value = position.value if position is not None else 0
        if target_value - current_value < data.last_price * 100:
            continue
        order = order_target_value(s, target_value)
        if order is None:
            log.warning('%s 买入/补仓委托创建失败' % s)



# 调整昨日涨停股票
def check_limit_up(context):
    current_data = get_current_data()
    
    # 昨日涨停且已不在目标池的股票，尾盘开板时卖出；仍在目标池的股票继续持有。
    if g.high_limit_list != []:
        for s in g.high_limit_list:
            if s in g.target_list or s not in context.portfolio.positions:
                continue
            data = current_data[s]
            if data.paused or not valid_last_price(data) or data.last_price <= data.low_limit:
                continue
            if data.last_price < data.high_limit:
                order = order_target_value(s, 0)
                if order is None:
                    log.warning('%s 涨停打开，但卖出委托创建失败' % s)
                    continue
                print(s, '涨停打开，卖出')
                print('———————————————————————————————————')
            else:
                print(s, '涨停，继续持有')
                print('———————————————————————————————————')



# 过滤函数
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

def filter_new_stock(context, stock_list):
    yesterday = context.previous_date
    result = []
    for stock in stock_list:
        info = get_security_info(stock)
        if info is not None and yesterday - info.start_date >= datetime.timedelta(days=250):
            result.append(stock)
    return result
