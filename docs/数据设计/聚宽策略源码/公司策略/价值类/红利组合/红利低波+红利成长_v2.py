# -*- coding: utf-8 -*-
"""红利双策略v2.1，聚宽Python3，股票/分钟回测，兼容旧版pandas。
建议页面区间2017-01-01~2026-07-21（结束日沿用原报告）；日期不能由策略脚本修改。
统一自然月首个交易日判断：09:01选股，09:30换仓/买入，09:31撤买单余单。
每日09:30处理待卖与超限；10:00昨日涨停开板检查；14:50仅重试待卖。
A/B各5名额，每名额10%资金，重叠相加；实际乘0.99留费，缺额不转移预算。
组合最多10股、每行业最多5股、单股20%检查线；定时纠正，不保证瞬时市值上限。
A：流动性/三年年末可见ROE快照/三完整自然年派息/过去一年股息率/周低波。
B：原PE、扣非ROE及增长条件+过去一年股息率；不擅加没有定义的低PB阈值。
两池统一流通市值>=50亿元；过去数据均截止previous_date；异常不放行原池。
无ETF、无额外成本止损/账户回撤止损；旧版回测收益不代表此版本表现。
"""
from jqdata import *
import builtins as bi
import datetime as dt
import traceback
import numpy as np
import pandas as pd

BACKTEST_START = '2017-01-01'
BACKTEST_END = '2026-07-21'
BENCHMARK = '000015.XSHG'


def ranked(series, ascending=False):
    s = pd.to_numeric(series, errors='coerce').replace([np.inf, -np.inf], np.nan).dropna()
    return s.sort_index().sort_values(ascending=ascending, kind='mergesort')


def allocate_pools(a_rank, b_rank, industry, per_pool=5, industry_limit=5, invest_ratio=0.99):
    """轮流从A、B候选递补；行业按合并后的唯一股票计数；缺额留现金。"""
    candidates = [list(dict.fromkeys(a_rank)), list(dict.fromkeys(b_rank))]
    chosen = [[], []]
    pointers = [0, 0]
    selected = set()
    industry_counts = {}
    while True:
        progressed = False
        for k in (0, 1):
            if len(chosen[k]) >= per_pool:
                continue
            while pointers[k] < len(candidates[k]):
                code = candidates[k][pointers[k]]
                pointers[k] += 1
                progressed = True
                sector = industry.get(code)
                if not sector:
                    continue
                if code not in selected and industry_counts.get(sector, 0) >= industry_limit:
                    continue
                chosen[k].append(code)
                if code not in selected:
                    selected.add(code)
                    industry_counts[sector] = industry_counts.get(sector, 0) + 1
                break
        if not progressed:
            break
    weights = {}
    slot = invest_ratio * 0.5 / per_pool
    for pool in chosen:
        for code in pool:
            weights[code] = weights.get(code, 0.0) + slot
    return weights, chosen


def trailing_yield(records, caps, asof):
    if records.empty:
        return pd.Series(dtype=float)
    d = records.copy()
    dates = pd.to_datetime(d['a_registration_date'], errors='coerce')
    cash = pd.to_numeric(d['bonus_amount_rmb'], errors='coerce')
    age = (pd.Timestamp(asof) - dates).dt.days
    good = (age >= 0) & (age < 365) & (cash > 0)
    sums = cash[good].groupby(d.loc[good, 'code']).sum()
    cap = pd.to_numeric(caps.reindex(sums.index), errors='coerce')
    # 派息金额万元，估值表市值亿元，沿用原数据字段的换算口径。
    return ranked((sums / 10000.0) / cap.where(cap > 0))


def continuous_dividend_codes(records, codes, years):
    if records.empty:
        return []
    d = records.copy()
    d['year'] = pd.to_datetime(d['a_registration_date'], errors='coerce').dt.year
    d['cash'] = pd.to_numeric(d['bonus_amount_rmb'], errors='coerce')
    groups = d.loc[d['cash'] > 0].groupby('code')['year'].apply(set)
    required = set(years)
    return [c for c in codes if c in groups.index and required.issubset(groups.loc[c])]


def weekly_volatilities(frame, asof, min_weeks=50):
    if frame.empty:
        return pd.Series(dtype=float)
    result = {}
    for code, data in frame.groupby('code'):
        values = pd.to_numeric(data['close'], errors='coerce')
        times = pd.to_datetime(data['time'], errors='coerce')
        # 聚宽旧版pandas没有Series.to_numpy；values在旧内核可用。
        close_values = np.asarray(values.values, dtype=float)
        time_index = pd.DatetimeIndex(times.values)
        s = pd.Series(close_values, index=time_index).dropna().sort_index()
        s = s[(s > 0) & (s.index.normalize() <= pd.Timestamp(asof).normalize())]
        s = s[~s.index.duplicated(keep='last')]
        weekly = s.resample('W-FRI').last().dropna()
        # 不把本周尚未到周五的部分周当作完整周。
        weekly = weekly[weekly.index <= pd.Timestamp(asof)]
        if len(weekly) < min_weeks:
            continue
        ret = np.log(weekly / weekly.shift(1)).replace([np.inf,-np.inf], np.nan).dropna()
        value = float(ret.std(ddof=1))
        if np.isfinite(value) and value > 0:
            result[code] = value
    return ranked(pd.Series(result, dtype=float), ascending=True)


class DividendStrategy:
    def __init__(self):
        self.per_pool = 5
        self.max_positions = 10
        self.max_industry = 5
        self.max_weight = 0.20
        self.safe_max_weight = 0.198
        self.invest_ratio = 0.99
        self.cash_reserve = 0.01
        self.min_cap = 50.0  # 流通市值亿元，统一作用于两池
        self.listed_days = 365
        self.yield_min = 0.03
        self.vol_days = 780
        self.min_weeks = 50  # 请求最多780日，但不声称每股必须有780日历史
        self.roe_years = 3
        self.day = None
        self.first_day = False
        self.calendar_ok = False
        self.hold_data_ok = False
        self.industry_ok = False
        self.selection_day = None
        self.weights = {}
        self.industry = {}
        self.yesterday_hl = set()
        self.pending = {}  # 待卖任务跨日保存：weight、reason、protect_limit_up
        self.tracked = {}
        self.bought = set()
        self.sold = set()
        self.exit_intent = set()
        self.orders_ok = False
        self.buy_blocked = False

    def setup(self, context):
        set_option('avoid_future_data', True)
        set_option('use_real_price', True)
        set_benchmark(BENCHMARK)
        set_slippage(PriceRelatedSlippage(0.002), type='stock')
        set_order_cost(OrderCost(open_tax=0, close_tax=0.0005,
            open_commission=0.0001, close_commission=0.0001,
            close_today_commission=0, min_commission=5), type='stock')
        log.info('红利v2.1（旧版pandas兼容）；页面建议区间%s~%s，脚本不能替代网页日期设置', BACKTEST_START, BACKTEST_END)

    def holdings(self, context):
        return {c:p for c,p in context.portfolio.positions.items() if p.total_amount > 0}

    def ensure_day(self, context):
        day = str(context.current_dt.date())
        if self.day == day:
            return
        self.day = day
        self.selection_day = None
        self.weights = {}
        self.tracked = {}
        self.bought = set()
        self.sold = set()
        self.exit_intent = set()
        self.yesterday_hl = set()
        self.hold_data_ok = False
        self.industry_ok = False
        self.industry = {}
        self.buy_blocked = False
        self.orders_ok = False
        self.first_day = False
        self.calendar_ok = False
        try:
            today = context.current_dt.date()
            days = get_trade_days(start_date=today.replace(day=1), end_date=today)
            if days is None or len(days) == 0:
                raise ValueError('交易日历为空')
            self.first_day = pd.Timestamp(days[0]).date() == today
            self.calendar_ok = True
        except Exception as e:
            log.error('交易日历异常，今日不新增：%s', e)
        # pending不能按日清空，否则T+1、停牌和跌停退出任务会丢失。

    def quote(self, code):
        # 直接按代码加载；不用code in current_data作为有效性判断。
        try:
            d = get_current_data()[code]
            if not np.isfinite(d.last_price) or d.last_price <= 0:
                return None
            return d
        except Exception as e:
            log.warn('行情不可用 %s：%s', code, e)
            return None

    def sync(self, context):
        self.ensure_day(context)
        try:
            orders = get_orders()
            opens = get_open_orders()
            if orders is None or opens is None:
                raise ValueError('委托查询返回None')
            for oid, meta in self.tracked.items():
                o = orders.get(oid)
                if o is not None and o.filled > 0:
                    (self.bought if meta['buy'] else self.sold).add(meta['code'])
            held = self.holdings(context)
            open_codes = {o.security for o in opens.values()}
            for code, task in list(self.pending.items()):
                if code in open_codes:
                    continue
                p = held.get(code)
                if p is None:
                    del self.pending[code]
                elif task['weight'] > 0:
                    d = self.quote(code)
                    if d is not None and p.total_amount*d.last_price <= context.portfolio.total_value*task['weight']:
                        del self.pending[code]
            self.orders_ok = True
            return opens
        except Exception as e:
            self.orders_ok = False
            log.error('委托状态异常，暂停新委托：%s', e)
            return None

    def track(self, order_obj, code, buy):
        if order_obj is None:
            log.warn('未受理 %s %s', code, '买入' if buy else '卖出')
            return
        self.tracked[order_obj.order_id] = {'code':code,'buy':buy}
        if order_obj.filled > 0:
            (self.bought if buy else self.sold).add(code)
        log.info('委托 %s %s 数量=%s 已成交=%s；受理不等于完成',
            code, '买入' if buy else '卖出', order_obj.amount, order_obj.filled)

    def cancel_buys(self, context, code=None):
        opens = self.sync(context)
        if opens is None:
            self.buy_blocked = True
            return
        for o in list(opens.values()):
            if o.is_buy and (code is None or o.security == code):
                try:
                    cancel_order(o)
                except Exception as e:
                    self.buy_blocked = True
                    log.error('撤买单失败 %s：%s', o.security, e)
        self.sync(context)

    def queue_sell(self, context, code, weight, reason, protect=False):
        old = self.pending.get(code)
        if old is None:
            self.pending[code] = {'weight':float(weight),'reason':reason,'protect':protect}
        else:
            if weight < old['weight']:
                old['weight'] = float(weight)
                old['reason'] = reason
            old['protect'] = old['protect'] and protect
        self.exit_intent.add(code)
        self.cancel_buys(context, code)

    def process_sells(self, context):
        opens = self.sync(context)
        if opens is None:
            return
        open_codes = {o.security for o in opens.values()}
        for code, task in list(self.pending.items()):
            p = self.holdings(context).get(code)
            if p is None or code in open_codes:
                continue
            d = self.quote(code)
            if d is None or d.paused or p.closeable_amount <= 0:
                log.info('待卖 %s：无行情/停牌/T+1，任务保留', code)
                continue
            if d.last_price <= d.low_limit or (task['protect'] and d.last_price >= d.high_limit):
                log.info('待卖 %s：跌停或保留封板，任务保留', code)
                continue
            desired = 0
            if task['weight'] > 0:
                desired = bi.int(context.portfolio.total_value*task['weight']/d.last_price/100)*100
            amount = bi.min(bi.int(p.closeable_amount), bi.max(0,bi.int(p.total_amount)-desired))
            if amount <= 0:
                continue
            try:
                self.track(order(code, -amount), code, False)
            except Exception as e:
                log.error('卖出异常 %s：%s；保留任务', code, e)
        self.sync(context)

    def fetch_industry(self, codes, asof):
        if not codes:
            return {}
        data = get_industry(security=list(codes), date=asof)
        if data is None:
            raise ValueError('行业数据返回None')
        return {c:data.get(c,{}).get('sw_l1',{}).get('industry_code') for c in codes}

    def before_open(self, context):
        self.ensure_day(context)
        self.sync(context)
        codes = list(self.holdings(context))
        if not codes:
            self.hold_data_ok = True
            self.industry_ok = True
            return
        try:
            frame = get_price(codes, end_date=context.previous_date, count=1,
                frequency='daily', fields=['close','high_limit'], panel=False,
                skip_paused=False, fq=None)
            if frame is None or frame.empty or frame['code'].nunique() < len(codes):
                raise ValueError('昨日持仓行情缺失')
            self.yesterday_hl = set(frame.loc[frame['close']==frame['high_limit'],'code'])
            self.hold_data_ok = True
        except Exception as e:
            self.hold_data_ok = False
            log.error('昨日持仓行情异常，今日不换仓新增：%s', e)
        try:
            self.industry.update(self.fetch_industry(codes,context.previous_date))
            self.industry_ok = bi.all(self.industry.get(c) for c in codes)
        except Exception as e:
            self.industry_ok = False
            log.error('持仓行业不可核对，今日不新增：%s', e)

    def base_data(self, codes, asof):
        pieces = []
        for start in bi.range(0,len(codes),800):
            q = query(valuation.code, valuation.market_cap, valuation.circulating_market_cap,
                valuation.pe_ratio, indicator.inc_return,
                indicator.inc_total_revenue_year_on_year, indicator.inc_net_profit_year_on_year
            ).filter(valuation.code.in_(codes[start:start+800]))
            frame = get_fundamentals(q,date=asof)
            if frame is None:
                raise ValueError('基本面数据返回None')
            if not frame.empty:
                pieces.append(frame)
        if not pieces:
            return pd.DataFrame()
        frame = pd.concat(pieces,ignore_index=True).drop_duplicates('code').set_index('code')
        frame = frame.replace([np.inf,-np.inf],np.nan)
        return frame[frame['circulating_market_cap']>=self.min_cap]

    def price_batches(self, codes, asof, count, fields, fq=None):
        pieces = []
        for start in bi.range(0,len(codes),200):
            frame = get_price(codes[start:start+200],end_date=asof,count=count,
                frequency='daily',fields=fields,panel=False,skip_paused=False,fq=fq)
            if frame is None:
                raise ValueError('历史行情返回None')
            if not frame.empty:
                pieces.append(frame)
        return pd.concat(pieces,ignore_index=True) if pieces else pd.DataFrame()

    def roe_quality(self, codes, asof, years):
        snapshots = {}
        for year in years:
            snapshot_date = bi.min(dt.date(year,12,31),asof)
            pieces = []
            for start in bi.range(0,len(codes),800):
                q = query(indicator.code,indicator.inc_return).filter(
                    indicator.code.in_(codes[start:start+800]))
                frame = get_fundamentals(q,date=snapshot_date)
                if frame is None:
                    raise ValueError('ROE快照返回None')
                if not frame.empty:
                    pieces.append(frame)
            if pieces:
                frame = pd.concat(pieces,ignore_index=True).drop_duplicates('code').set_index('code')
                snapshots[year] = pd.to_numeric(frame['inc_return'],errors='coerce')
            else:
                snapshots[year] = pd.Series(dtype=float)
        values = pd.DataFrame(snapshots).reindex(index=codes,columns=years)
        values = values.replace([np.inf,-np.inf],np.nan).dropna()
        if values.empty:
            return []
        quality = ranked(values.mean(axis=1)-values.std(axis=1,ddof=1))
        keep=bi.max(1,bi.int(np.ceil(len(quality)*.70)))
        return quality.head(keep).index.tolist()

    def dividend_query(self, codes, start, end):
        q = query(finance.STK_XR_XD.code,finance.STK_XR_XD.a_registration_date,
            finance.STK_XR_XD.bonus_amount_rmb).filter(
            finance.STK_XR_XD.code.in_(codes),
            finance.STK_XR_XD.a_registration_date>start,
            finance.STK_XR_XD.a_registration_date<=end).limit(4000)
        frame = finance.run_query(q)
        if frame is None:
            raise ValueError('分红记录返回None')
        if len(frame)<4000:
            return frame
        days=(end-start).days
        if days>1:
            mid=start+dt.timedelta(days=days//2)
            return pd.concat([self.dividend_query(codes,start,mid),
                self.dividend_query(codes,mid,end)],ignore_index=True)
        if len(codes)>1:
            half=len(codes)//2
            return pd.concat([self.dividend_query(codes[:half],start,end),
                self.dividend_query(codes[half:],start,end)],ignore_index=True)
        raise ValueError('单股单日分红触达行数上限，拒绝截断数据')

    def dividends(self, codes, asof, years):
        start=dt.date(years[0],1,1)-dt.timedelta(days=1)
        pieces=[]
        for i in bi.range(0,len(codes),200):
            frame=self.dividend_query(codes[i:i+200],start,asof)
            if not frame.empty:
                pieces.append(frame)
        return pd.concat(pieces,ignore_index=True) if pieces else pd.DataFrame()

    def pool_a(self, codes, base, records, yields, asof, years):
        frame=self.price_batches(codes,asof,5,['money'])
        if frame.empty:
            return []
        frame=frame.copy()
        frame['money']=pd.to_numeric(frame['money'],errors='coerce')
        frame=frame.replace([np.inf,-np.inf],np.nan).dropna(subset=['money'])
        sums=frame.groupby('code')['money'].agg(['mean','count'])
        sums=sums[(sums['count']>=5)&(sums['mean']>0)]
        if sums.empty:
            return []
        money=ranked(sums['mean'])
        keep=bi.max(1,bi.int(np.ceil(len(money)*.80)))
        codes=money.head(keep).index.tolist()
        if not codes:
            return []
        codes=self.roe_quality(codes,asof,years)
        codes=continuous_dividend_codes(records,codes,years)
        eligible=yields.reindex(codes).dropna()
        eligible=eligible[eligible>self.yield_min]
        if len(eligible)>10:
            eligible=ranked(eligible).head(bi.max(1,bi.int(np.ceil(len(eligible)*.40))))
        if eligible.empty:
            return []
        history=self.price_batches(eligible.index.tolist(),asof,self.vol_days,['close'],fq='pre')
        if history.empty:
            return []
        return weekly_volatilities(history,asof,self.min_weeks).index[:self.per_pool*3].tolist()

    def pool_b(self, codes, base, yields):
        # 保留原PE/盈利成长定义，不凭报告的“低PB”字样臆造阈值。
        ok=(base['pe_ratio'].between(5,50)&base['inc_return'].between(5,100)
            &base['inc_total_revenue_year_on_year'].between(5,100)
            &base['inc_net_profit_year_on_year'].between(10,100))
        candidates=base.index[ok]
        score=ranked(yields.reindex(candidates))
        return score[score>self.yield_min].index[:self.per_pool*3].tolist()

    def select(self, context):
        self.ensure_day(context)
        if not self.calendar_ok or not self.first_day:
            return
        self.selection_day=None
        self.weights={}
        stage='股票池与基础过滤'
        try:
            asof=context.previous_date
            info=get_all_securities(types=['stock'],date=asof)
            if info is None or info.empty:
                raise ValueError('股票池为空')
            codes=[]
            for code,row in info.iterrows():
                if code.startswith(('68','4','8','92')) or pd.isna(row['start_date']):
                    continue
                if (pd.Timestamp(asof)-pd.Timestamp(row['start_date'])).days<self.listed_days:
                    continue
                d=self.quote(code)
                if d is not None and not d.paused and not d.is_st and not bi.any(x in d.name for x in ('ST','*','退')):
                    codes.append(code)
            stage='基础财务与市值'
            base=self.base_data(codes,asof)
            if base.empty:
                log.warn('基础数据无合格股，本月保留持仓')
                return
            codes=base.index.tolist()
            # 用当前评估年的前三个完整自然年，年初取数仍不得晚于asof。
            years=list(bi.range(context.current_dt.year-self.roe_years,context.current_dt.year))
            stage='历史分红'
            records=self.dividends(codes,asof,years)
            stage='过去一年股息率'
            yields=trailing_yield(records,base['market_cap'],asof)
            stage='A池流动性、ROE、连续分红及周波动率'
            a=self.pool_a(codes,base,records,yields,asof,years)
            stage='B池红利价值'
            b=self.pool_b(codes,base,yields)
            stage='合并行业与权重'
            industries=self.fetch_industry(list(dict.fromkeys(a+b)),asof)
            weights,chosen=allocate_pools(a,b,industries,self.per_pool,self.max_industry,self.invest_ratio)
            if not weights:
                log.warn('两池无合格目标，保留原持仓；不把空选视为清仓信号')
                return
            self.industry.update(industries)
            self.weights=weights
            self.selection_day=self.day
            log.info('A=%s B=%s 权重=%s 总目标仓位=%.2f%%，缺额留现金',
                chosen[0],chosen[1],weights,bi.sum(weights.values())*100)
        except Exception as e:
            self.weights={}
            self.selection_day=None
            log.error('选股失败，阶段=%s；保留持仓且不使用上月权重：%s\n%s',
                stage,e,traceback.format_exc())

    def enforce_limits(self, context):
        held=self.holdings(context)
        nav=context.portfolio.total_value
        priority=lambda c:(c in self.weights,c)
        if len(held)>self.max_positions:
            for code in sorted(held,key=priority)[:len(held)-self.max_positions]:
                self.queue_sell(context,code,0,'持仓数量超限')
        sectors={}
        for code,p in held.items():
            sector=self.industry.get(code)
            if sector:
                sectors.setdefault(sector,[]).append(code)
            d=self.quote(code)
            if d is not None and p.total_amount*d.last_price>nav*self.max_weight:
                self.queue_sell(context,code,self.safe_max_weight,'单股权重超过20%')
        for sector,codes in sectors.items():
            if len(codes)>self.max_industry:
                for code in sorted(codes,key=priority)[:len(codes)-self.max_industry]:
                    self.queue_sell(context,code,0,'行业股票数量超限')

    def trade(self, context):
        self.ensure_day(context)
        self.enforce_limits(context)
        self.process_sells(context)
        if (not self.first_day or self.selection_day!=self.day or not self.weights
                or not self.hold_data_ok or not self.industry_ok):
            return
        can_add=[]
        for code in self.weights:
            d=self.quote(code)
            if d is not None and not d.paused and not d.is_st and d.low_limit<d.last_price<d.high_limit:
                can_add.append(code)
        if not can_add:
            log.warn('目标均不可买，本次不执行月度换仓')
            return
        for code,p in self.holdings(context).items():
            if code not in self.weights:
                # 可保留封板，但退出意图跨日跟踪，不无条件等到下月。
                self.queue_sell(context,code,0,'月度换出',protect=True)
            else:
                d=self.quote(code)
                if d is not None and p.total_amount*d.last_price>context.portfolio.total_value*self.weights[code]:
                    self.queue_sell(context,code,self.weights[code],'月度目标减仓',protect=True)
        self.process_sells(context)
        self.buy_targets(context)

    def buy_targets(self, context):
        if (context.current_dt.strftime('%H:%M')!='09:30' or not self.first_day
                or self.selection_day!=self.day or not self.weights or self.buy_blocked
                or not self.hold_data_ok or not self.industry_ok):
            return
        for code,weight in self.weights.items():
            opens=self.sync(context)
            if opens is None:
                return
            if self.pending or bi.any(not o.is_buy for o in opens.values()):
                log.info('待卖未完成，暂停新增；不在其他时间补买股票')
                return
            if code in self.bought or code in self.sold or code in self.exit_intent:
                continue
            if bi.any(o.security==code for o in opens.values()):
                continue
            d=self.quote(code)
            if d is None or d.paused or d.is_st or bi.any(x in d.name for x in ('ST','*','退')):
                continue
            if not (d.low_limit<d.last_price<d.high_limit):
                continue
            held=self.holdings(context)
            reserved={o.security for o in opens.values() if o.is_buy}
            occupied=set(held)|reserved
            if code not in occupied and len(occupied)>=self.max_positions:
                continue
            sector=self.industry.get(code)
            if not sector or bi.any(not self.industry.get(c) for c in occupied):
                continue
            if code not in occupied and bi.sum(self.industry.get(c)==sector for c in occupied)>=self.max_industry:
                continue
            nav=float(context.portfolio.total_value)
            existing=held[code].total_amount*d.last_price if code in held else 0.0
            desired=nav*bi.min(weight,self.safe_max_weight)
            free=bi.max(0.0,context.portfolio.available_cash-nav*self.cash_reserve)
            budget=bi.min(bi.max(0.0,desired-existing),free*0.99)
            # PriceRelatedSlippage(0.002)按完整0.2%留余量，另检查最低佣金。
            buy_price=d.last_price*1.002
            shares=bi.int(budget/buy_price/100)*100
            if shares<=0 or budget<shares*buy_price+5:
                continue
            try:
                self.track(order(code,shares),code,True)
            except Exception as e:
                log.error('买入异常 %s：%s',code,e)

    def limit_open_check(self, context):
        self.ensure_day(context)
        self.cancel_buys(context)
        for code in self.yesterday_hl:
            if code not in self.holdings(context):
                continue
            d=self.quote(code)
            if d is not None and not d.paused and d.last_price<d.high_limit:
                self.queue_sell(context,code,0,'10:00昨日涨停开板')
        self.enforce_limits(context)
        self.process_sells(context)


def initialize(context):
    g.dividend=DividendStrategy()
    g.dividend.setup(context)
    run_daily(prepare_stock_list,time='09:00')
    run_daily(get_stock_list,time='09:01')  # 与trade使用同一自然月交易日判断
    run_daily(trade,time='09:30')
    run_daily(cancel_buy_remainders,time='09:31')
    run_daily(check_limit_up,time='10:00')
    run_daily(retry_sells,time='14:50')
    run_daily(end_of_day,time='15:10')

def prepare_stock_list(context):
    g.dividend.before_open(context)

def get_stock_list(context):
    g.dividend.select(context)

def trade(context):
    g.dividend.trade(context)

def cancel_buy_remainders(context):
    g.dividend.cancel_buys(context)

def check_limit_up(context):
    g.dividend.limit_open_check(context)

def retry_sells(context):
    g.dividend.ensure_day(context)
    g.dividend.cancel_buys(context)
    g.dividend.enforce_limits(context)
    g.dividend.process_sells(context)

def end_of_day(context):
    g.dividend.cancel_buys(context)
    g.dividend.sync(context)
    log.info('收盘：持仓数=%d 实际买入=%s 实际卖出=%s 待卖=%s 选股日=%s',
        len(g.dividend.holdings(context)),sorted(g.dividend.bought),sorted(g.dividend.sold),
        g.dividend.pending,g.dividend.selection_day)
