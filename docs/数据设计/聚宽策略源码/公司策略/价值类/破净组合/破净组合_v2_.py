# -*- coding: utf-8 -*-
"""破净组合 v2，聚宽Python3，股票/分钟回测。
月初09:05选股，09:30调仓；每日14:00、14:50昨日涨停开板检查。
09:30/14:00/14:50同时检查仓位上限、重试未完成卖出，不增加下午股票买入。
五维：ROA最高、正EBIT最高、毛利率最高、自定义8项FF最高、股息率最高。
红利分支：最近五个互不重叠365天窗口均有正派息，最近窗口股息率>=5%。
最多新建至5只股票（ETF另计）；单股目标19.8%，20%检查线，受交易约束。
保留月度换出时的昨日涨停保护，但受总持仓数及仓位约束。
未完成卖出跨日保留；委托与实际成交分别记录；买单09:31撤余单。
511880为货币ETF：月末14:55释放，非释放日14:56归集闲置现金。
所有历史因子/财务/股票池使用previous_date，无选股结果或数据异常保留原持仓。
未添加原策略没有的普通个股止损、指数择时或账户回撤止损。
日期、初始资金在平台设置；旧版收益不能代表此版本结果。
"""
from jqdata import *
from jqfactor import get_factor_values, Factor, calc_factors
import builtins as bi
import datetime as dt
import numpy as np
import pandas as pd


def clean_rank(series, codes, positive=False):
    """按代码对齐、数值清洗，降序；同分以代码升序稳定打破平局。"""
    s = pd.to_numeric(series.reindex(codes), errors='coerce')
    s = s.replace([np.inf, -np.inf], np.nan).dropna()
    if positive:
        s = s[s > 0]
    return s.sort_index().sort_values(ascending=False, kind='mergesort')


def ff8_components(data):
    """保留原8项结构，修正负基数改善方向与两期流动资产平均。
    此处ROA2为利润加财务费用/平均流动资产的自定义指标，不冒充标准ROA。
    """
    def last(name):
        return pd.to_numeric(data[name].iloc[-1], errors='coerce')
    def ratio(a, b):
        return a / b.where(b > 0)
    avg_assets = (last('total_current_assets') + last('total_current_assets_1')) / 2.0
    avg_assets_old = (last('total_current_assets_4') + last('total_current_assets_5')) / 2.0
    r2 = ratio(last('total_profit') + last('financial_expense'), avg_assets)
    r2_old = ratio(last('total_profit_4') + last('financial_expense_4'), avg_assets_old)
    lever = ratio(last('total_non_current_liability'), last('total_non_current_assets'))
    lever_old = ratio(last('total_non_current_liability_4'), last('total_non_current_assets_4'))
    liquid = ratio(last('total_current_assets'), last('total_current_liability'))
    liquid_old = ratio(last('total_current_assets_4'), last('total_current_liability_4'))
    turnover = ratio(last('operating_revenue'), avg_assets)
    turnover_old = ratio(last('operating_revenue_4'), avg_assets_old)
    return pd.DataFrame({
        'DELTA_ROE': last('roe') - last('roe_4'),
        'DELTA_ROA1': last('roa') - last('roa_4'),
        'ROA2': r2,
        'DELTA_ROA2': r2 - r2_old,
        'DELTA_LEVER': lever_old - lever,
        'DELTA_LIQUID': liquid - liquid_old,
        'DELTA_MARGIN': last('gross_profit_margin') - last('gross_profit_margin_4'),
        'DELTA_CATURN': turnover - turnover_old,
    }).replace([np.inf, -np.inf], np.nan)


class FF8Score(Factor):
    name = 'PojingFF8'
    max_window = 1
    dependencies = [
        'roe', 'roe_4', 'roa', 'roa_4',
        'total_profit', 'total_profit_4', 'financial_expense', 'financial_expense_4',
        'total_current_assets', 'total_current_assets_1',
        'total_current_assets_4', 'total_current_assets_5',
        'total_non_current_liability', 'total_non_current_liability_4',
        'total_non_current_assets', 'total_non_current_assets_4',
        'total_current_liability', 'total_current_liability_4',
        'gross_profit_margin', 'gross_profit_margin_4',
        'operating_revenue', 'operating_revenue_4',
    ]

    def calc(self, data):
        metrics = ff8_components(data)
        # 缺失数据不能被当作真实0分参与选股。
        score = metrics.gt(0).sum(axis=1).astype(float)
        return score.where(metrics.notna().all(axis=1))


def dividend_ratios(records, caps, asof, codes):
    """纯计算：bonus_amount_rmb万元，market_cap亿元；窗口左开右闭。"""
    if records.empty:
        return pd.Series(dtype=float)
    d = records.copy()
    d['a_registration_date'] = pd.to_datetime(d['a_registration_date'], errors='coerce')
    d['bonus_amount_rmb'] = pd.to_numeric(d['bonus_amount_rmb'], errors='coerce')
    age = (pd.Timestamp(asof) - d['a_registration_date']).dt.days
    d = d.loc[(age >= 0) & (age < 365 * 5) & (d['bonus_amount_rmb'] > 0)].copy()
    if d.empty:
        return pd.Series(dtype=float)
    d['window'] = ((pd.Timestamp(asof) - d['a_registration_date']).dt.days // 365).astype(int)
    by_window = d.groupby(['code', 'window'])['bonus_amount_rmb'].sum().unstack(fill_value=0)
    by_window = by_window.reindex(columns=bi.range(5), fill_value=0)
    stable = by_window.index[(by_window > 0).all(axis=1)]
    recent = by_window.loc[stable, 0]
    cap = pd.to_numeric(caps.reindex(stable), errors='coerce')
    result = (recent / 10000.0) / cap.where(cap > 0)
    return clean_rank(result, codes, positive=True)


class PojingStrategy:
    def __init__(self):
        self.top_n = 1
        self.max_positions = 5  # 股票上限，511880另计；扩大TopN还需明确调整此参数。
        self.max_weight = 0.20
        self.target_weight = 0.198  # 相对20%留出价格/费用余量。
        self.cash_reserve = 0.01
        self.min_listed_days = 200  # 自然日
        self.etf = '511880.XSHG'
        self.day = None
        self.candidates = []
        self.selection_day = None
        self.selection_failed_day = None
        self.yesterday_hl = set()
        self.hold_data_ok = False
        self.pending_sells = {}  # code -> {'weight':0或目标权重,'reason':...}；跨日保留
        self.tracked_orders = {}
        self.bought_today = set()
        self.sold_today = set()
        self.exit_intent_today = set()
        self.orders_ok = False
        self.cash_release_day = None
        self.cash_blocked_today = False

    def setup(self, context):
        set_benchmark('000300.XSHG')
        set_option('use_real_price', True)
        set_option('avoid_future_data', True)
        set_order_cost(OrderCost(open_tax=0, close_tax=0.001,
            open_commission=0.00012, close_commission=0.00012, min_commission=5), type='stock')
        # 货币ETF单独设置费用，不把股票印花税用于基金。
        set_order_cost(OrderCost(open_tax=0, close_tax=0,
            open_commission=0.00012, close_commission=0.00012, min_commission=5), type='fund', ref=self.etf)
        set_slippage(FixedSlippage(0.001))
        log.info('破净组合v2：月初09:30调仓，正EBIT/股息率降序，最多5只股票，ETF现金管理开启')

    def ensure_day(self, context):
        day = str(context.current_dt.date())
        if self.day == day:
            return
        self.day = day
        self.tracked_orders = {}
        self.bought_today = set()
        self.sold_today = set()
        self.exit_intent_today = set()
        self.orders_ok = False
        self.hold_data_ok = False
        self.yesterday_hl = set()
        self.cash_blocked_today = False
        # 当月候选可保存，但只有selection_day==今日才允许股票买入。

    def holdings(self, context, stocks_only=False):
        return {c:p for c,p in context.portfolio.positions.items()
            if p.total_amount > 0 and (not stocks_only or c != self.etf)}

    def sync_orders(self, context):
        self.ensure_day(context)
        try:
            orders = get_orders()
            opens = get_open_orders()
            if orders is None or opens is None:
                raise ValueError('委托查询返回None')
            for oid, meta in self.tracked_orders.items():
                o = orders.get(oid)
                if o is not None and o.filled > 0:
                    if meta['buy']:
                        self.bought_today.add(meta['code'])
                    else:
                        self.sold_today.add(meta['code'])
            positions = self.holdings(context)
            open_codes = {o.security for o in opens.values()}
            for code, task in list(self.pending_sells.items()):
                if code in open_codes:
                    continue
                p = positions.get(code)
                if p is None:
                    del self.pending_sells[code]
                elif task['weight'] > 0:
                    price = get_current_data()[code].last_price
                    if np.isfinite(price) and price > 0:
                        if p.total_amount * price <= context.portfolio.portfolio_value * task['weight']:
                            del self.pending_sells[code]
            self.orders_ok = True
            return opens
        except Exception as e:
            self.orders_ok = False
            log.error('委托状态异常，暂停新增委托：%s', e)
            return None

    def track(self, o, code, buy):
        if o is None:
            log.warn('委托未受理 %s %s', code, '买' if buy else '卖')
            return
        self.tracked_orders[o.order_id] = {'code':code, 'buy':buy}
        if o.filled > 0:
            (self.bought_today if buy else self.sold_today).add(code)
        log.info('委托 %s %s 数量=%s 已成交=%s，未成交部分不视为完成',
            code, '买' if buy else '卖', o.amount, o.filled)

    def cancel_buys(self, context, code=None):
        opens = self.sync_orders(context)
        if opens is None:
            self.cash_blocked_today = True
            return
        for o in list(opens.values()):
            if o.is_buy and (code is None or o.security == code):
                try:
                    cancel_order(o)
                except Exception as e:
                    self.cash_blocked_today = True
                    log.error('撤买单失败 %s：%s', o.security, e)
        self.sync_orders(context)

    def queue_sell(self, context, code, weight, reason):
        previous = self.pending_sells.get(code)
        if previous is None or weight < previous['weight']:
            self.pending_sells[code] = {'weight':float(weight), 'reason':reason}
        self.exit_intent_today.add(code)
        self.cancel_buys(context, code)

    def process_sells(self, context, only_code=None):
        opens = self.sync_orders(context)
        if opens is None:
            return
        open_codes = {o.security for o in opens.values()}
        current = get_current_data()
        for code, task in list(self.pending_sells.items()):
            if only_code is not None and code != only_code:
                continue
            p = self.holdings(context).get(code)
            if p is None or code in open_codes:
                continue
            d = current[code]
            if d.paused or p.closeable_amount <= 0:
                log.info('待卖 %s（%s）：停牌/T+1无可卖数量，跨日保留', code, task['reason'])
                continue
            if not np.isfinite(d.last_price) or d.last_price <= 0:
                continue
            if d.last_price <= d.low_limit:
                log.info('待卖 %s：跌停，等待后续检查', code)
                continue
            desired = 0
            if task['weight'] > 0:
                desired = bi.int(context.portfolio.portfolio_value * task['weight'] / d.last_price / 100) * 100
            amount = bi.min(bi.int(p.closeable_amount), bi.max(0, bi.int(p.total_amount) - desired))
            if amount <= 0:
                continue
            try:
                self.track(order(code, -amount), code, False)
            except Exception as e:
                log.error('卖单异常 %s：%s；保留任务', code, e)
        self.sync_orders(context)

    def before_open(self, context):
        self.ensure_day(context)
        self.sync_orders(context)
        codes = list(self.holdings(context, True))
        if not codes:
            self.hold_data_ok = True
            return
        try:
            df = get_price(codes, end_date=context.previous_date, count=1,
                frequency='daily', fields=['close','high_limit'],
                panel=False, skip_paused=False, fq=None)
            if df is None or df.empty or df['code'].nunique() < len(codes):
                raise ValueError('昨日持仓行情缺失')
            self.yesterday_hl = set(df.loc[df['close'] == df['high_limit'], 'code'])
            self.hold_data_ok = True
        except Exception as e:
            self.hold_data_ok = False
            log.error('昨日涨停状态未知，暂停月度换仓：%s', e)

    def tradable(self, code, buy=False):
        d = get_current_data()[code]
        if d.paused or not np.isfinite(d.last_price) or d.last_price <= 0:
            return False
        if buy and (d.is_st or '退' in d.name or d.last_price >= d.high_limit):
            return False
        return d.last_price > d.low_limit

    def fundamentals(self, codes, asof):
        chunks = []
        for start in bi.range(0, len(codes), 1000):
            batch = codes[start:start+1000]
            q = query(valuation.code, valuation.pb_ratio, valuation.market_cap,
                indicator.adjusted_profit_to_profit, indicator.inc_net_profit_year_on_year,
                indicator.roa, indicator.gross_profit_margin).filter(
                valuation.code.in_(batch), valuation.pb_ratio > 0, valuation.pb_ratio < 1,
                indicator.adjusted_profit_to_profit > 80,
                indicator.inc_net_profit_year_on_year > 0)
            df = get_fundamentals(q, date=asof)
            if df is None:
                raise ValueError('基本面查询失败')
            if not df.empty:
                chunks.append(df)
        if not chunks:
            return pd.DataFrame()
        df = pd.concat(chunks, ignore_index=True).drop_duplicates('code').set_index('code')
        return df.replace([np.inf,-np.inf], np.nan)

    def query_dividends(self, codes, start, end):
        """finance返回达到4000行时递归拆日期，避免静默截断。"""
        q = query(finance.STK_XR_XD.code, finance.STK_XR_XD.a_registration_date,
            finance.STK_XR_XD.bonus_amount_rmb).filter(
            finance.STK_XR_XD.code.in_(codes),
            finance.STK_XR_XD.a_registration_date > start,
            finance.STK_XR_XD.a_registration_date <= end).limit(4000)
        frame = finance.run_query(q)
        if frame is None:
            raise ValueError('分红查询失败')
        if len(frame) < 4000:
            return frame
        days = (end - start).days
        if days > 1:
            mid = start + dt.timedelta(days=days // 2)
            return pd.concat([self.query_dividends(codes,start,mid),
                self.query_dividends(codes,mid,end)], ignore_index=True)
        if len(codes) > 1:
            half = len(codes)//2
            return pd.concat([self.query_dividends(codes[:half],start,end),
                self.query_dividends(codes[half:],start,end)], ignore_index=True)
        raise ValueError('单股单日分红记录触达查询上限，拒绝使用不完整结果')

    def dividend_branch(self, codes, base, asof):
        pieces = []
        oldest = asof - dt.timedelta(days=365*5)
        for start in bi.range(0, len(codes), 200):
            frame = self.query_dividends(codes[start:start+200], oldest, asof)
            if not frame.empty:
                pieces.append(frame)
        if not pieces:
            return []
        records = pd.concat(pieces, ignore_index=True)
        ranked = dividend_ratios(records, base['market_cap'], asof, codes)
        ranked = ranked[ranked >= 0.05]
        if ranked.empty:
            return []
        industry = get_industry(security=ranked.index.tolist(), date=asof)
        table = pd.DataFrame({'dividend_ratio':ranked})
        table['industry'] = [industry.get(c,{}).get('sw_l1',{}).get('industry_code')
            for c in table.index]
        table = table.dropna(subset=['industry'])
        # 仅红利候选每行业最多2只，并非整个组合行业中性。
        table = table.sort_index().sort_values('dividend_ratio', ascending=False, kind='mergesort')
        table = table.groupby('industry', sort=False).head(2)
        return table.index[:self.top_n].tolist()

    def select(self, context):
        self.ensure_day(context)
        self.selection_day = None
        self.candidates = []  # 选股失败不能继续沿用上月名单交易。
        try:
            asof = context.previous_date
            info = get_all_securities(types=['stock'], date=asof)
            if info is None or info.empty:
                raise ValueError('股票池为空')
            current = get_current_data()
            codes = []
            for code, row in info.iterrows():
                if code.startswith(('68','4','8','92')):
                    continue
                if (pd.Timestamp(asof)-pd.Timestamp(row['start_date'])).days < self.min_listed_days:
                    continue
                d = current[code]
                if not d.paused and not d.is_st and '退' not in d.name:
                    codes.append(code)
            base = self.fundamentals(codes, asof)
            if base.empty:
                log.warn('破净池为空，本月保留原持仓，不视为清仓信号')
                self.selection_failed_day = self.day
                return
            codes = base.index.tolist()
            roa = clean_rank(base['roa'], codes).head(self.top_n).index.tolist()
            gross = clean_rank(base['gross_profit_margin'], codes).head(self.top_n).index.tolist()
            raw = get_factor_values(securities=codes, factors=['EBIT'], end_date=asof, count=1)
            if raw is None or 'EBIT' not in raw or raw['EBIT'].empty:
                raise ValueError('EBIT行情缺失')
            if clean_rank(raw['EBIT'].iloc[-1], codes).empty:
                raise ValueError('EBIT全部缺失或无穷值')
            ebit = clean_rank(raw['EBIT'].iloc[-1], codes, positive=True).head(self.top_n).index.tolist()
            ff = calc_factors(codes, [FF8Score()], start_date=asof, end_date=asof)
            if ff is None or 'PojingFF8' not in ff or ff['PojingFF8'].empty:
                raise ValueError('FF评分缺失')
            ff_rank = clean_rank(ff['PojingFF8'].iloc[-1], codes).head(self.top_n).index.tolist()
            if not roa or not gross or not ff_rank:
                raise ValueError('质量因子全部缺失，暂停本月选股')
            dividend = self.dividend_branch(codes, base, asof)
            selected = list(dict.fromkeys(roa + ebit + gross + ff_rank + dividend))
            self.candidates = selected[:self.max_positions]
            self.selection_day = self.day
            self.selection_failed_day = None
            log.info('五分支 ROA=%s EBIT=%s 毛利率=%s FF=%s 红利=%s；合并目标=%s',
                roa, ebit, gross, ff_rank, dividend, self.candidates)
        except Exception as e:
            self.candidates = []
            self.selection_day = None
            self.selection_failed_day = self.day
            log.error('月度选股失败，保留持仓、不沿用旧名单：%s', e)

    def enforce_limits(self, context):
        """限制新增数量，并在定时检查时尝试纠正既有超限，不能保证瞬时市值上限。"""
        held = self.holdings(context, True)
        nav = context.portfolio.portfolio_value
        current = get_current_data()
        if len(held) > self.max_positions:
            # 优先退出非目标，若原账户已超限则不再承诺昨日涨停豁免。
            ordered = sorted(held, key=lambda c:(c in self.candidates,c))
            for code in ordered[:len(held)-self.max_positions]:
                self.queue_sell(context, code, 0, '纠正既有股票数量超限')
        for code, p in held.items():
            price = current[code].last_price
            if np.isfinite(price) and price > 0 and nav > 0:
                if price * p.total_amount > nav * self.max_weight:
                    self.queue_sell(context, code, self.target_weight, '单股超过20%，减至19.8%附近')

    def trade_at_0930(self, context):
        self.ensure_day(context)
        # 日常只减仓/退出；只有当月选股成功当日才允许股票买入。
        self.enforce_limits(context)
        self.process_sells(context)
        if self.selection_day != self.day or not self.candidates or not self.hold_data_ok:
            return
        target = [c for c in self.candidates if self.tradable(c, True)]
        if not target:
            log.warn('当月目标均不可买，保留原持仓，不误清仓')
            return
        # 原始目标中的涨停/跌停旧股保留；只有真正掉出选股池的旧股才月度换出。
        for code in self.holdings(context, True):
            if code not in self.candidates and code not in self.yesterday_hl:
                self.queue_sell(context, code, 0, '月度换出')
        # 月末ETF释放若未完成，在09:30再尝试；不增加其他时刻股票买入。
        if self.etf in self.holdings(context):
            self.queue_sell(context, self.etf, 0, '月度释放ETF资金')
        self.process_sells(context)
        self.buy_stocks(context, target)

    def buy_stocks(self, context, target):
        if (context.current_dt.strftime('%H:%M') != '09:30'
                or self.selection_day != self.day or not self.hold_data_ok
                or self.cash_blocked_today):
            return
        for code in target:
            opens = self.sync_orders(context)
            if opens is None:
                return
            held = self.holdings(context, True)
            # 月度换出、ETF释放尚未完成时不依赖未到帐现金买股。
            if self.pending_sells or bi.any(not o.is_buy for o in opens.values()):
                log.info('仍有待卖/卖单未完成，09:30不新增股票，下一次月度再评估')
                return
            if code in self.bought_today or code in self.sold_today or code in self.exit_intent_today:
                continue
            if bi.any(o.security == code for o in opens.values()):
                continue
            reserved = {o.security for o in opens.values()
                if o.is_buy and o.security != self.etf and o.security not in held}
            if code not in held and len(held) + len(reserved) >= self.max_positions:
                continue
            if not self.tradable(code, True):
                continue
            d = get_current_data()[code]
            nav = float(context.portfolio.portfolio_value)
            old_value = held[code].total_amount * d.last_price if code in held else 0.0
            desired = nav * bi.min(self.target_weight, 0.99 / len(target))
            headroom = bi.max(0.0, desired - old_value)
            available = bi.max(0.0, context.portfolio.available_cash - nav * self.cash_reserve)
            addition = bi.min(headroom, available * 0.99)
            if addition < d.last_price * 100 * 1.002 + 5:
                continue
            # 显式按100股取整，含滑点余量，避免order_target_value临界多买一手。
            shares = bi.int(addition / (d.last_price + 0.001) / 100) * 100
            if shares <= 0:
                continue
            try:
                self.track(order(code, shares), code, True)
            except Exception as e:
                log.error('买入失败 %s：%s', code, e)

    def afternoon(self, context):
        self.ensure_day(context)
        self.cancel_buys(context)
        self.enforce_limits(context)
        for code in list(self.yesterday_hl):
            if code not in self.holdings(context, True):
                continue
            if not self.tradable(code, False):
                continue
            d = get_current_data()[code]
            if d.last_price < d.high_limit:
                self.queue_sell(context, code, 0, '昨日涨停今日检查时开板')
        self.process_sells(context)

    def release_cash(self, context):
        self.ensure_day(context)
        self.cash_release_day = self.day
        self.cancel_buys(context)
        if self.etf in self.holdings(context):
            self.queue_sell(context, self.etf, 0, '月末提前释放下月股票资金')
        self.process_sells(context, only_code=self.etf)

    def manage_cash(self, context):
        self.ensure_day(context)
        if (self.cash_release_day == self.day or self.selection_failed_day == self.day
                or self.cash_blocked_today):
            return
        opens = self.sync_orders(context)
        if opens is None or opens or self.pending_sells:
            return
        if not self.tradable(self.etf, True):
            return
        # 避免同日ETF卖出后又立即回买；股票买卖不受ETF计数污染。
        if self.etf in self.sold_today or self.etf in self.bought_today:
            return
        nav = context.portfolio.portfolio_value
        budget = bi.max(0.0, context.portfolio.available_cash - nav * self.cash_reserve) * 0.99
        price = get_current_data()[self.etf].last_price
        shares = bi.int(budget / (price + 0.001) / 100) * 100
        if shares <= 0 or budget < shares * (price + 0.001) + 5:
            return
        try:
            self.track(order(self.etf, shares), self.etf, True)
        except Exception as e:
            log.error('ETF现金归集失败：%s', e)


def initialize(context):
    g.pojing = PojingStrategy()
    g.pojing.setup(context)
    run_daily(before_market_open, time='09:00')
    run_monthly(check_stocks, 1, time='09:05')
    run_daily(my_trade, time='09:30')  # 仅月度有效选股日买股，其余日只执行限额/待卖。
    run_daily(cancel_buy_remainders, time='09:31')
    run_daily(check_limit_up, time='14:00')
    run_daily(check_limit_up, time='14:50')
    run_monthly(release_etf_cash, -1, time='14:55')
    run_daily(manage_cash, time='14:56')
    run_daily(cancel_buy_remainders, time='14:57')
    run_daily(end_of_day, time='15:10')

def before_market_open(context):
    g.pojing.before_open(context)

def check_stocks(context):
    g.pojing.select(context)

def my_trade(context):
    g.pojing.trade_at_0930(context)

def cancel_buy_remainders(context):
    g.pojing.cancel_buys(context)

def check_limit_up(context):
    g.pojing.afternoon(context)

def release_etf_cash(context):
    g.pojing.release_cash(context)

def manage_cash(context):
    g.pojing.manage_cash(context)

def end_of_day(context):
    g.pojing.cancel_buys(context)
    g.pojing.sync_orders(context)
    log.info('收盘：股票数=%d 已买=%s 已卖=%s 待卖=%s 选股日=%s',
        len(g.pojing.holdings(context, True)), sorted(g.pojing.bought_today),
        sorted(g.pojing.sold_today), g.pojing.pending_sells, g.pojing.selection_day)
