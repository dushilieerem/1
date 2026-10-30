# -*- coding: utf-8 -*-
"""自由现金流轮动策略 v3：风控修正版，聚宽Python3，股票/分钟回测。
月初09:30完整轮动，每日14:50补仓；1月、4月空仓。
保留v2的FCF代理公式与20只目标；不是持续按市值等权再平衡。
个股成本止损12%，默认关闭翻倍止盈；市场信号沿用上一交易日
399101成分股close/open等权均值<=0.94，不冒充当日实时指数跌幅。
市场触发当天禁买，数据失败禁新增；个股止损独立于市场数据。
未成交卖出任务跨日保留，按closeable_amount处理T+1，直至退出。
所有买卖状态按实际成交同步；买单09:31/14:51撤余单。
财务及因子取previous_date，市值使用valuation.market_cap乘1e8。
回测开始/结束日期、初始资金在聚宽页面设置，代码不伪造回测结果。
"""
from jqdata import *
from jqfactor import get_factor_values
import builtins as bi
import datetime
import numpy as np
import pandas as pd
from pandas import Timedelta


def refined_earnings_filter(df, top_percent=0.8, limits=[0.02, 0.98]):
    """
    对盈利质量列进行清洗、缩尾，并保留前 top_percent 的股票。
    参数：
        df: 必须包含 'earnings_quality' 列的 DataFrame
        top_percent: 保留的百分比（0.8 表示前80%）
        limits: 缩尾分位数 [下界, 上界]（例如 0.02, 0.98）
    返回：
        筛选后的 DataFrame（包含原始列，无新增列）
    """
    if df.empty or 'earnings_quality' not in df.columns:
        return df

    # 1. 去除无穷大和空值
    df_clean = df.replace([np.inf, -np.inf], np.nan).dropna(subset=['earnings_quality']).copy()
    if df_clean.empty:
        return df_clean

    # 2. 缩尾处理 (Winsorize)：上下界分位不同，避免缩尾塌缩为常量
    low_perc, high_perc = df_clean['earnings_quality'].quantile(limits)
    df_clean['eq_winsorized'] = df_clean['earnings_quality'].clip(lower=low_perc, upper=high_perc)

    # 3. 排名与筛选（earnings_quality 越大=盈利质量越高，故 ascending=False 取大值在前）
    df_clean['eq_rank_pct'] = df_clean['eq_winsorized'].rank(ascending=False, pct=True, method='first')
    result = df_clean[df_clean['eq_rank_pct'] <= top_percent].copy()

    # 删除中间列，只保留原始列
    result = result.drop(columns=['eq_winsorized', 'eq_rank_pct'], errors='ignore')
    return result


class FCFStrategy:
    def __init__(self):
        self.stock_num = 20
        self.exclude_finance_real = True
        self.limit_days = 20
        self.exclude_kcbj = True
        self.enable_empty_months = True
        self.empty_months = [1, 4]
        self.run_stoploss = True
        self.stoploss_strategy = 3  # 1个股；2市场；3联合
        self.stoploss_limit = 0.88
        self.stoploss_market = 0.94
        self.enable_takeprofit = False  # 显式参数，默认与v2模式3一致
        self.HV_control = True
        self.HV_duration = 120
        self.HV_ratio = 0.9
        self.day = None
        self.hold_list = []
        self.yesterday_HL_list = []
        self.target_list = []
        self.target_day = None
        self.not_buy_again = set()  # 当日实际买入（含部分成交）
        self.sold_today = set()     # 当日实际卖出（含部分成交）
        self.exit_requested_today = set()  # 风控意图，不能冒充已成交
        self.pending_exits = {}     # 跨日持久保存，直到实际持仓归零
        self.tracked_orders = {}
        self.buy_blocked = False
        self.market_data_ok = False
        self.orders_ok = False
        self.hold_data_ok = False

    def initialize(self, context):
        set_benchmark('000300.XSHG')
        set_option('use_real_price', True)
        set_option('avoid_future_data', True)
        set_order_cost(OrderCost(open_tax=0, close_tax=0.001,
            open_commission=0.0003, close_commission=0.0003,
            close_today_commission=0, min_commission=5), type='stock')
        set_slippage(PriceRelatedSlippage(0.002))
        log.info('FCF v3：月初09:30调仓/14:50补仓，1、4月空仓，止损12%，市场风险当天禁买')

    def ensure_day(self, context):
        day = str(context.current_dt.date())
        if self.day == day:
            return
        self.day = day
        self.not_buy_again = set()
        self.sold_today = set()
        self.exit_requested_today = set()
        self.tracked_orders = {}
        self.buy_blocked = False
        self.market_data_ok = False
        self.orders_ok = False
        self.hold_data_ok = False
        self.target_list = []
        self.target_day = None
        # pending_exits不能按日清空：T+1、停牌、跌停未成交需要继续退出。

    def positions(self, context):
        return {s: p for s, p in context.portfolio.positions.items()
                if p.total_amount > 0}

    def sync_orders(self, context):
        self.ensure_day(context)
        try:
            all_orders = get_orders()
            opens = get_open_orders()
            if all_orders is None or opens is None:
                raise ValueError('委托查询返回None')
            for oid, meta in self.tracked_orders.items():
                o = all_orders.get(oid)
                if o is not None:
                    self.apply_fill(o, meta['code'], meta['buy'])
            held = self.positions(context)
            open_codes = {o.security for o in opens.values()}
            for code in list(self.pending_exits):
                if code not in held and code not in open_codes:
                    del self.pending_exits[code]
            self.orders_ok = True
            return opens
        except Exception as e:
            self.orders_ok = False
            log.error('委托状态查询失败，暂停新增委托：%s', e)
            return None

    def apply_fill(self, o, code, is_buy):
        if o is not None and o.filled > 0:
            if is_buy:
                self.not_buy_again.add(code)
            else:
                self.sold_today.add(code)

    def track_order(self, o, code, is_buy):
        if o is None:
            log.warn('委托未受理：%s %s', code, '买入' if is_buy else '卖出')
            return
        self.tracked_orders[o.order_id] = {'code': code, 'buy': is_buy}
        self.apply_fill(o, code, is_buy)
        log.info('委托受理 %s %s，数量=%s，已成交=%s；受理不代表全部成交',
                 code, '买入' if is_buy else '卖出', o.amount, o.filled)

    def cancel_buys(self, context, code=None):
        opens = self.sync_orders(context)
        if opens is None:
            return
        for o in list(opens.values()):
            if o.is_buy and (code is None or o.security == code):
                try:
                    cancel_order(o)
                except Exception as e:
                    self.buy_blocked = True
                    log.error('撤销买单失败 %s：%s', o.security, e)
        self.sync_orders(context)

    def queue_exit(self, context, code, reason):
        self.pending_exits[code] = reason
        self.exit_requested_today.add(code)
        self.cancel_buys(context, code)

    def process_exits(self, context):
        opens = self.sync_orders(context)
        if opens is None:
            return
        open_codes = {o.security for o in opens.values()}
        current = get_current_data()
        for code, reason in list(self.pending_exits.items()):
            p = self.positions(context).get(code)
            if p is None or code in open_codes:
                continue
            d = current[code]
            if d.paused or p.closeable_amount <= 0:
                log.info('待退出 %s（%s）：停牌或T+1无可卖数量，任务保留', code, reason)
                continue
            if not np.isfinite(d.last_price) or d.last_price <= 0:
                continue
            if d.last_price <= d.low_limit:
                log.info('待退出 %s（%s）：跌停，保留任务等待后续检查', code, reason)
                continue
            try:
                # 按真实可卖数量下单；剩余当日买入股份留待下一交易日。
                o = order(code, -bi.int(p.closeable_amount))
                self.track_order(o, code, False)
            except Exception as e:
                log.error('卖出失败 %s（%s）：%s；保留退出任务', code, reason, e)
        self.sync_orders(context)

    def check_empty_month(self, context):
        return self.enable_empty_months and context.current_dt.month in self.empty_months

    def market_check(self, context):
        if not self.run_stoploss or self.stoploss_strategy not in (2, 3):
            self.market_data_ok = True
            return
        try:
            stocks = get_index_stocks('399101.XSHE', date=context.previous_date)
            if not stocks:
                raise ValueError('市场监控成分股为空')
            df = get_price(stocks, end_date=context.previous_date, count=1,
                frequency='daily', fields=['open', 'close', 'paused'],
                panel=False, skip_paused=False, fq=None)
            if df is None or df.empty:
                raise ValueError('市场监控行情为空')
            good = df.replace([np.inf, -np.inf], np.nan).dropna(subset=['open', 'close'])
            good = good[(good['open'] > 0) & (good['close'] > 0) & (good['paused'] == 0)]
            required = bi.max(1, bi.int(bi.len(stocks) * 0.8))
            if len(good) < required:
                raise ValueError('有效市场样本不足80%')
            ratio = float((good['close'] / good['open']).mean())
            self.market_data_ok = np.isfinite(ratio)
            if not self.market_data_ok:
                raise ValueError('市场监控结果非有限值')
            if ratio <= self.stoploss_market:
                self.buy_blocked = True
                self.cancel_buys(context)
                for code in self.positions(context):
                    self.queue_exit(context, code, '市场止损')
                log.warn('市场止损：上一交易日成分股close/open均值=%.4f，今日禁买', ratio)
        except Exception as e:
            self.market_data_ok = False
            log.error('市场数据异常，暂停新增仓位，个股止损继续：%s', e)

    def risk_check(self, context):
        self.ensure_day(context)
        self.sync_orders(context)
        if self.check_empty_month(context):
            self.buy_blocked = True
            self.cancel_buys(context)
            for code in self.positions(context):
                self.queue_exit(context, code, '空仓月份')
        else:
            self.market_check(context)
            # 个股检查独立执行，不嵌入市场行情成功返回的分支。
            if self.run_stoploss and self.stoploss_strategy in (1, 3):
                current = get_current_data()
                for code, p in self.positions(context).items():
                    price = current[code].last_price
                    if not np.isfinite(price) or price <= 0 or p.avg_cost <= 0:
                        continue
                    if price < p.avg_cost * self.stoploss_limit:
                        self.queue_exit(context, code, '个股12%止损')
                    elif self.enable_takeprofit and price >= p.avg_cost * 2:
                        self.queue_exit(context, code, '个股翻倍止盈')
        self.process_exits(context)

    def refresh_holdings(self, context):
        self.hold_list = list(self.positions(context))
        self.yesterday_HL_list = []
        self.hold_data_ok = False
        if not self.hold_list:
            self.hold_data_ok = True
            return
        try:
            df = get_price(self.hold_list, end_date=context.previous_date, count=1,
                frequency='daily', fields=['close', 'high_limit'], panel=False,
                skip_paused=False, fq=None)
            if df is None or df.empty or df['code'].nunique() < len(self.hold_list):
                raise ValueError('昨日持仓行情缺失')
            self.yesterday_HL_list = df.loc[df['close'] == df['high_limit'], 'code'].tolist()
            self.hold_data_ok = True
        except Exception as e:
            # 不把未知状态冒充涨停，也不因行情故障误卖全部原持仓。
            log.error('昨日持仓行情失败，跳过月度调仓：%s', e)

    def premarket_selection(self, context):
        self.ensure_day(context)
        self.refresh_holdings(context)
        self.sync_orders(context)
        self.market_check(context)
        if self.check_empty_month(context):
            self.buy_blocked = True
            return
        try:
            self.target_list = self.select_stocks(context)
            self.target_day = self.day
            log.info('每日候选（用于月度调仓及14:50补仓）：%s', self.target_list)
        except Exception as e:
            self.target_list = []
            self.target_day = None
            log.error('选股异常，保留原持仓、暂停新增：%s', e)

    def prepare_stock_list(self, context):
        self.ensure_day(context)
        self.refresh_holdings(context)
        self.sync_orders(context)

    def monthly_rebalance(self, context):
        self.risk_check(context)  # 先风控后交易，市场触发时不先买后卖。
        if (self.check_empty_month(context) or self.buy_blocked
                or not self.market_data_ok or not self.hold_data_ok):
            return
        if self.target_day != self.day or not self.target_list:
            log.warn('无当日有效候选，跳过月度调仓，避免数据故障导致全平')
            return
        target = self.target_list[:self.stock_num]
        for code in self.positions(context):
            if code not in target and code not in self.yesterday_HL_list:
                self.queue_exit(context, code, '月度换仓')
        self.process_exits(context)
        self.buy_securities(context, target)

    def can_buy(self, context):
        self.ensure_day(context)
        opens = self.sync_orders(context)
        return (opens is not None and not self.check_empty_month(context)
            and not self.buy_blocked and self.market_data_ok
            and not self.pending_exits and self.target_day == self.day)

    def buy_securities(self, context, target_list):
        if not self.can_buy(context):
            return
        current = get_current_data()
        held = self.positions(context)
        opens = get_open_orders()
        open_codes = {o.security for o in opens.values()}
        reserved = {o.security for o in opens.values() if o.is_buy and o.security not in held}
        slots = self.stock_num - len(held) - len(reserved)
        candidates = []
        for code in target_list:
            if code in held or code in open_codes or code in self.not_buy_again:
                continue
            if code in self.sold_today or code in self.exit_requested_today:
                continue
            d = current[code]
            if d.paused or d.is_st or not np.isfinite(d.last_price) or d.last_price <= 0:
                continue
            if d.last_price >= d.high_limit or d.last_price <= d.low_limit:
                continue
            if len(candidates) < slots:
                candidates.append(code)
        if not candidates:
            return
        # 留出佣金、滑点及价格波动余量；只对新增仓位均分现金。
        budget = float(context.portfolio.available_cash) * 0.99 / len(candidates)
        for code in candidates:
            if not self.can_buy(context):
                break
            current_opens = get_open_orders()
            now_held = self.positions(context)
            now_reserved = {o.security for o in current_opens.values()
                if o.is_buy and o.security not in now_held}
            if len(now_held) + len(now_reserved) >= self.stock_num:
                break
            cash = bi.min(budget, float(context.portfolio.available_cash) * 0.99)
            price = current[code].last_price
            if cash < price * 100 * 1.003 + 5:
                continue
            try:
                self.track_order(order_target_value(code, cash), code, True)
            except Exception as e:
                log.error('买入失败 %s：%s', code, e)

    def replenish_positions(self, context):
        self.risk_check(context)
        self.buy_securities(context, self.target_list)

    def check_limit_up(self, context):
        if self.check_empty_month(context):
            return
        current = get_current_data()
        for code in self.yesterday_HL_list:
            if code not in self.positions(context):
                continue
            d = current[code]
            if not d.paused and np.isfinite(d.last_price) and 0 < d.last_price < d.high_limit:
                self.queue_exit(context, code, '昨日涨停今日破板')

    def check_high_volume(self, context):
        if not self.HV_control or self.check_empty_month(context):
            return
        current = get_current_data()
        for code in self.positions(context):
            d = current[code]
            if d.paused or d.last_price >= d.high_limit:
                continue
            try:
                past = get_price(code, end_date=context.previous_date, count=self.HV_duration,
                    frequency='daily', fields=['volume'], skip_paused=False, fq=None)
                intraday = get_price(code,
                    start_date=context.current_dt.replace(hour=9, minute=30, second=0, microsecond=0),
                    end_date=context.current_dt, frequency='1m', fields=['volume'],
                    skip_paused=False, fq=None)
                if past is None or intraday is None or len(past) < self.HV_duration or intraday.empty:
                    continue
                highest = float(past['volume'].max())
                today = float(intraday['volume'].sum())
                if highest > 0 and np.isfinite(today) and today > self.HV_ratio * highest:
                    self.queue_exit(context, code, '14:30累计量超过前120完整交易日最高量的90%')
            except Exception as e:
                log.warn('成交量监控失败 %s：%s', code, e)

    def select_stocks(self, context):
        """
        执行自由现金流选股，返回目标股票列表（长度=stock_num，除非全市场不足）
        """
        current_date = str(context.previous_date)
        log.info('开始选股，日期：%s', current_date)

        # 获取全市场A股，剔除ST、停牌、次新股
        stock_list = get_all_securities(['stock'], date=context.previous_date).index.tolist()
        stock_list = self.filter_st_stock(stock_list)
        stock_list = self.filter_paused_stock(stock_list)
        stock_list = self.filter_new_stock(stock_list, context.previous_date, 60)

        # 剔除科创板及北交所股票
        if self.exclude_kcbj:
            stock_list = self.filter_kcbj_stock(stock_list)

        if not stock_list:
            log.warn('无可交易股票')
            return []

        # 获取因子数据
        factor_names = [
            'net_operate_cash_flow_ttm',
            'net_invest_cash_flow_ttm',
            'operating_profit_ttm'
        ]
        try:
            factor_data = get_factor_values(securities=stock_list,
                                            factors=factor_names,
                                            end_date=current_date,
                                            count=1)
        except Exception as e:
            log.error('获取因子数据失败：%s', str(e))
            return []

        df_factor = pd.DataFrame()
        for factor in factor_names:
            series = factor_data[factor].iloc[-1]
            df_factor[factor] = series
        df_factor = df_factor.reset_index().rename(columns={'index': 'code'})

        # 获取资产负债表数据
        df_bal = self.get_balance_sheet_batch(stock_list, current_date)
        if df_bal.empty:
            log.warn('获取资产负债表数据失败')
            return []

        df = pd.merge(df_factor, df_bal, on='code', how='inner')
        if df.empty:
            log.warn('无有效数据')
            return []

        df = df.replace([np.inf, -np.inf], np.nan)
        df = df.dropna(subset=['net_operate_cash_flow_ttm', 'net_invest_cash_flow_ttm',
                               'operating_profit_ttm', 'market_cap', 'total_liability',
                               'cash_equivalents', 'total_assets'])

        df = df[df['total_assets'] > 0].copy()
        # 市值表单位亿元，转换成元，与财务报表统一。
        df['market_cap'] = df['market_cap'] * 100000000.0

        # 计算指标
        df['capex'] = -df['net_invest_cash_flow_ttm']
        df['fcf'] = df['net_operate_cash_flow_ttm'] - df['capex']
        df['ev'] = df['market_cap'] + df['total_liability'] - df['cash_equivalents']
        df['earnings_quality'] = (df['net_operate_cash_flow_ttm'] - df['operating_profit_ttm']) / df['total_assets']

        # 筛选 FCF>0 且 EV>0
        df = df[(df['fcf'] > 0) & (df['ev'] > 0)]

        # 剔除金融地产
        if self.exclude_finance_real and len(df) > 0:
            df = self.exclude_finance_real_estate(df, current_date)

        # ----- 盈利质量筛选（优化版，v2 修复方向） -----
        # earnings_quality = (经营现金流_ttm - 营业利润_ttm) / 总资产
        #   Sloan 应计异象反向：该值越大 → 经营现金流越真实、盈利质量越高
        #   因此直接保留 earnings_quality 最大的前 80%（refined_earnings_filter 默认 ascending=False 即取大值在前）
        if len(df) > 0:
            df_filtered = refined_earnings_filter(df, top_percent=0.8, limits=[0.02, 0.98])
            if df_filtered.empty:
                log.warn('盈利质量筛选后无股票')
                return []
            df = df_filtered
            log.info('盈利质量前80%%（高质量）后股票数：%d', len(df))
        else:
            log.warn('无股票通过前两步筛选')
            return []

        # 计算自由现金流率并排序（从大到小）
        if len(df) > 0:
            df['fcf_yield'] = df['fcf'] / df['ev']
            df = df.sort_values('fcf_yield', ascending=False)
            raw_sorted = df['code'].tolist()          # 原始排名列表
        else:
            raw_sorted = []

        # 获取最近涨停股黑名单（不在持仓中的）
        blacklist = self.get_blacklist_recent_limit_up(context)
        if blacklist is None:
            return []

        # 从原始排名中依次取股，跳过黑名单，直到取满 stock_num 只
        selected = []
        for code in raw_sorted:
            if code not in blacklist:
                selected.append(code)
                if len(selected) >= self.stock_num:
                    break

        log.info(f"最终选出 {len(selected)} 只股票")
        return selected


    def get_blacklist_recent_limit_up(self, context):
        """获取最近 limit_days 天内涨停过且不在当前持仓中的股票黑名单"""
        if self.limit_days <= 0:
            return []
        yesterday = context.previous_date
        try:
            all_stocks = get_all_securities(['stock'], date=yesterday).index.tolist()
            h = get_price(all_stocks, end_date=yesterday, frequency='daily',
                          fields=['close', 'high_limit', 'paused'],
                          count=self.limit_days, panel=False)
            if h is None or h.empty:
                log.warn('涨停黑名单数据为空，暂停本次选股')
                return None
            limit_up_stocks = h.query('close==high_limit and paused==0').groupby('code').size()
            recent_limit_up_list = limit_up_stocks.index.tolist()
            blacklist = list(set(recent_limit_up_list) - set(self.hold_list))
            if blacklist:
                log.info(f"最近{self.limit_days}天内涨停且不在持仓中的股票数量：{len(blacklist)}")
            return blacklist
        except Exception as e:
            log.error(f"获取最近涨停股黑名单时出错: {e}")
            return None


    def filter_st_stock(self, stock_list):
        current_data = get_current_data()
        return [s for s in stock_list if not current_data[s].is_st]


    def filter_paused_stock(self, stock_list):
        current_data = get_current_data()
        return [s for s in stock_list if not current_data[s].paused]


    def filter_new_stock(self, stock_list, date, days=60):
        if isinstance(date, datetime.datetime):
            date = date.date()
        stocks_info = get_all_securities(['stock'], date)
        delta = Timedelta(days=days)
        return [s for s in stock_list if s in stocks_info.index and (pd.Timestamp(date) - pd.Timestamp(stocks_info.loc[s, 'start_date'])) >= delta]


    def filter_kcbj_stock(self, stock_list):
        return [s for s in stock_list if not s.startswith(('4', '8', '68', '92'))]

    def get_balance_sheet_batch(self, stock_list, date):
        batch_size = 3000
        dfs = []
        for i in range(0, len(stock_list), batch_size):
            batch = stock_list[i:i+batch_size]
            q = query(
                balance.code,
                valuation.market_cap,
                balance.total_liability,
                balance.cash_equivalents,
                balance.total_assets
            ).filter(balance.code.in_(batch), valuation.code == balance.code)
            df = get_fundamentals(q, date=date)
            if df is not None and not df.empty:
                df = df.reset_index()
                dfs.append(df[['code', 'market_cap', 'total_liability', 'cash_equivalents', 'total_assets']])
        return pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()


    def exclude_finance_real_estate(self, df, date):
        codes = df['code'].tolist()
        res = get_industry(codes, date=date)
        exc_codes = ['801780', '801790', '801180']
        keep = []
        for code in codes:
            if code not in res:
                keep.append(code)
            else:
                ind = res[code].get('sw_l1')
                if not ind:
                    keep.append(code)
                elif ind['industry_code'] not in exc_codes:
                    keep.append(code)
        return df[df['code'].isin(keep)]




# 聚宽g保存状态；不在模块导入时创建可变交易实例。
def initialize(context):
    g.fcf = FCFStrategy()
    g.fcf.initialize(context)
    run_daily(premarket_selection, time='07:02')
    run_daily(prepare_stock_list, time='09:05')
    run_monthly(monthly_rebalance, 1, time='09:30')
    run_daily(cancel_buy_remainders, time='09:31')
    run_daily(sell_stocks, time='10:00')
    run_daily(trade_afternoon, time='14:30')
    run_daily(replenish_at_1450, time='14:50')
    run_daily(cancel_buy_remainders, time='14:51')
    run_daily(close_account, time='14:55')
    run_daily(end_of_day, time='15:10')

def premarket_selection(context):
    g.fcf.premarket_selection(context)

def prepare_stock_list(context):
    g.fcf.prepare_stock_list(context)

def monthly_rebalance(context):
    g.fcf.monthly_rebalance(context)

def cancel_buy_remainders(context):
    g.fcf.ensure_day(context)
    g.fcf.cancel_buys(context)

def sell_stocks(context):
    g.fcf.risk_check(context)

def trade_afternoon(context):
    g.fcf.risk_check(context)
    g.fcf.check_limit_up(context)
    g.fcf.check_high_volume(context)
    g.fcf.process_exits(context)

def replenish_at_1450(context):
    g.fcf.replenish_positions(context)

def close_account(context):
    g.fcf.risk_check(context)

def end_of_day(context):
    g.fcf.cancel_buys(context)
    g.fcf.sync_orders(context)
    log.info('收盘：持仓=%d，实际买入=%s，实际卖出=%s，待退出=%s，今日禁买=%s',
        len(g.fcf.positions(context)), sorted(g.fcf.not_buy_again),
        sorted(g.fcf.sold_today), g.fcf.pending_exits, g.fcf.buy_blocked)
