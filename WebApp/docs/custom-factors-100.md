# 自定义因子 100 条（可复制试算）

> 在「因子库 → 新增自定义因子 → 自由表达式」粘贴：**因子代码**=函数名，**简介**=中文，**完整函数**=代码块。
> 无统一前缀；名称已与本机公开库 / 聚宽兼容 / 自定义演示名做不区分大小写去重。
> 只用 close/open/high/low/volume/amount。生成日：2026-07-23

## 1. phantom_gap

简介：隔夜幽灵跳空

```python
def phantom_gap(self):
    """隔夜幽灵跳空"""
    return self.open / self.close.shift(1) - 1
```

## 2. intraday_pulse

简介：日内开收脉搏

```python
def intraday_pulse(self):
    """日内开收脉搏"""
    return self.close / self.open - 1
```

## 3. dawn_dusk_spread

简介：隔夜减日内差

```python
def dawn_dusk_spread(self):
    """隔夜减日内差"""
    ovn = self.open / self.close.shift(1) - 1
    intra = self.close / self.open - 1
    return ovn - intra
```

## 4. candle_body_share

简介：实体占振幅比

```python
def candle_body_share(self):
    """实体占振幅比"""
    body = (self.close - self.open).abs()
    rng = (self.high - self.low).replace(0, float("nan"))
    return body / rng
```

## 5. wick_overhead

简介：上影相对振幅

```python
def wick_overhead(self):
    """上影相对振幅"""
    top = self.close.where(self.close > self.open, self.open)
    rng = (self.high - self.low).replace(0, float("nan"))
    return (self.high - top) / rng
```

## 6. wick_underfoot

简介：下影相对振幅

```python
def wick_underfoot(self):
    """下影相对振幅"""
    bot = self.close.where(self.close < self.open, self.open)
    rng = (self.high - self.low).replace(0, float("nan"))
    return (bot - self.low) / rng
```

## 7. close_seat

简介：收盘区间座位

```python
def close_seat(self):
    """收盘区间座位"""
    rng = (self.high - self.low).replace(0, float("nan"))
    return (self.close - self.low) / rng
```

## 8. open_seat

简介：开盘区间座位

```python
def open_seat(self):
    """开盘区间座位"""
    rng = (self.high - self.low).replace(0, float("nan"))
    return (self.open - self.low) / rng
```

## 9. seat_drift_20

简介：20日座位漂移

```python
def seat_drift_20(self):
    """20日座位漂移"""
    rng = (self.high - self.low).replace(0, float("nan"))
    seat = (self.close - self.low) / rng
    return seat.rolling(20).mean()
```

## 10. range_coil

简介：振幅盘绕收缩

```python
def range_coil(self):
    """振幅盘绕收缩"""
    rng = self.high - self.low
    return rng.rolling(5).mean() / rng.rolling(20).mean()
```

## 11. range_spring

简介：振幅弹簧加速

```python
def range_spring(self):
    """振幅弹簧加速"""
    rng = (self.high - self.low) / self.close
    r5 = rng.rolling(5).mean()
    return r5 / r5.shift(5) - 1
```

## 12. true_span_pct

简介：真实波幅占比

```python
def true_span_pct(self):
    """真实波幅占比"""
    prev = self.close.shift(1)
    a = self.high - self.low
    b = (self.high - prev).abs()
    c = (self.low - prev).abs()
    tr = a.where(a > b, b)
    tr = tr.where(tr > c, c)
    return tr / self.close
```

## 13. span_ratio_fast_slow

简介：短长真实波幅比

```python
def span_ratio_fast_slow(self):
    """短长真实波幅比"""
    prev = self.close.shift(1)
    a = self.high - self.low
    b = (self.high - prev).abs()
    c = (self.low - prev).abs()
    tr = a.where(a > b, b)
    tr = tr.where(tr > c, c)
    return tr.rolling(14).mean() / tr.rolling(60).mean()
```

## 14. path_efficiency_10

简介：10日路径效率

```python
def path_efficiency_10(self):
    """10日路径效率"""
    net = (self.close - self.close.shift(10)).abs()
    path = self.close.diff().abs().rolling(10).sum()
    return net / path.replace(0, float("nan"))
```

## 15. path_efficiency_20

简介：20日路径效率

```python
def path_efficiency_20(self):
    """20日路径效率"""
    net = (self.close - self.close.shift(20)).abs()
    path = self.close.diff().abs().rolling(20).sum()
    return net / path.replace(0, float("nan"))
```

## 16. path_static

简介：20日路径噪声

```python
def path_static(self):
    """20日路径噪声"""
    net = (self.close - self.close.shift(20)).abs()
    path = self.close.diff().abs().rolling(20).sum()
    return 1 - net / path.replace(0, float("nan"))
```

## 17. price_z_fast

简介：收盘短窗标准化

```python
def price_z_fast(self):
    """收盘短窗标准化"""
    mu = self.close.rolling(20).mean()
    sd = self.close.rolling(20).std().replace(0, float("nan"))
    return (self.close - mu) / sd
```

## 18. price_z_slow

简介：收盘长窗标准化

```python
def price_z_slow(self):
    """收盘长窗标准化"""
    mu = self.close.rolling(60).mean()
    sd = self.close.rolling(60).std().replace(0, float("nan"))
    return (self.close - mu) / sd
```

## 19. z_twist

简介：短长标准化扭转

```python
def z_twist(self):
    """短长标准化扭转"""
    z20 = (self.close - self.close.rolling(20).mean()) / self.close.rolling(20).std()
    z60 = (self.close - self.close.rolling(60).mean()) / self.close.rolling(60).std()
    return z20 - z60
```

## 20. return_skew_20

简介：20日收益偏度

```python
def return_skew_20(self):
    """20日收益偏度"""
    return self.close.pct_change().rolling(20).skew()
```

## 21. return_kurt_20

简介：20日收益峰度

```python
def return_kurt_20(self):
    """20日收益峰度"""
    return self.close.pct_change().rolling(20).kurt()
```

## 22. green_day_share

简介：20日阳线占比

```python
def green_day_share(self):
    """20日阳线占比"""
    up = (self.close > self.close.shift(1)).astype(float)
    return up.rolling(20).mean()
```

## 23. bleed_intensity

简介：下跌出血强度

```python
def bleed_intensity(self):
    """下跌出血强度"""
    r = self.close.pct_change()
    return r.where(r < 0, 0).rolling(20).mean()
```

## 24. thrust_intensity

简介：上涨冲刺强度

```python
def thrust_intensity(self):
    """上涨冲刺强度"""
    r = self.close.pct_change()
    return r.where(r > 0, 0).rolling(20).mean()
```

## 25. payoff_asymmetry

简介：盈亏幅度不对称

```python
def payoff_asymmetry(self):
    """盈亏幅度不对称"""
    r = self.close.pct_change()
    gain = r.where(r > 0, 0).rolling(20).mean()
    loss = (-r.where(r < 0, 0)).rolling(20).mean().replace(0, float("nan"))
    return gain / loss
```

## 26. signed_flow_vol

简介：带符号量能流

```python
def signed_flow_vol(self):
    """带符号量能流"""
    sign = (self.close > self.close.shift(1)).astype(float) * 2 - 1
    return (sign * self.volume).rolling(20).sum() / self.volume.rolling(20).sum()
```

## 27. signed_flow_amt

简介：带符号额能流

```python
def signed_flow_amt(self):
    """带符号额能流"""
    sign = (self.close > self.open).astype(float) * 2 - 1
    return (sign * self.amount).rolling(20).sum() / self.amount.rolling(20).sum()
```

## 28. echo_vol_price

简介：量价回声相关

```python
def echo_vol_price(self):
    """量价回声相关"""
    return self.close.pct_change().rolling(20).corr(self.volume.pct_change())
```

## 29. echo_amt_price

简介：额价回声相关

```python
def echo_amt_price(self):
    """额价回声相关"""
    return self.close.pct_change().rolling(20).corr(self.amount.pct_change())
```

## 30. volume_burst

简介：量能突发冲击

```python
def volume_burst(self):
    """量能突发冲击"""
    return self.volume / self.volume.rolling(20).mean() - 1
```

## 31. amount_burst

简介：额能突发冲击

```python
def amount_burst(self):
    """额能突发冲击"""
    return self.amount / self.amount.rolling(20).mean() - 1
```

## 32. volume_drought

简介：量能旱情

```python
def volume_drought(self):
    """量能旱情"""
    return self.volume.rolling(5).mean() / self.volume.rolling(60).mean()
```

## 33. ticket_proxy

简介：单位成交均价

```python
def ticket_proxy(self):
    """单位成交均价"""
    return self.amount / self.volume.replace(0, float("nan"))
```

## 34. fair_price_drift

简介：额量均价偏离

```python
def fair_price_drift(self):
    """额量均价偏离"""
    vwap = self.amount / self.volume.replace(0, float("nan"))
    return self.close / vwap - 1
```

## 35. fair_drift_smooth

简介：均价偏离平滑

```python
def fair_drift_smooth(self):
    """均价偏离平滑"""
    vwap = self.amount / self.volume.replace(0, float("nan"))
    return (self.close / vwap - 1).rolling(20).mean()
```

## 36. ceiling_distance

简介：距20日天花板

```python
def ceiling_distance(self):
    """距20日天花板"""
    return self.close / self.high.rolling(20).max() - 1
```

## 37. floor_distance

简介：距20日地板

```python
def floor_distance(self):
    """距20日地板"""
    return self.close / self.low.rolling(20).min() - 1
```

## 38. corridor_seat_60

简介：60日走廊座位

```python
def corridor_seat_60(self):
    """60日走廊座位"""
    hi = self.high.rolling(60).max()
    lo = self.low.rolling(60).min()
    return (self.close - lo) / (hi - lo).replace(0, float("nan"))
```

## 39. corridor_width_60

简介：60日走廊宽度

```python
def corridor_width_60(self):
    """60日走廊宽度"""
    hi = self.high.rolling(60).max()
    lo = self.low.rolling(60).min()
    return (hi - lo) / self.close
```

## 40. ceiling_pullback

简介：天花板回撤压

```python
def ceiling_pullback(self):
    """天花板回撤压"""
    hi = self.high.rolling(20).max()
    return (hi - self.close) / hi
```

## 41. meanline_tilt

简介：均线倾斜度

```python
def meanline_tilt(self):
    """均线倾斜度"""
    ma = self.close.rolling(20).mean()
    return ma / ma.shift(5) - 1
```

## 42. meanline_fanout

简介：均线扇形张开

```python
def meanline_fanout(self):
    """均线扇形张开"""
    m5 = self.close.rolling(5).mean()
    m20 = self.close.rolling(20).mean()
    m60 = self.close.rolling(60).mean()
    return ((m5 - m20).abs() + (m20 - m60).abs()) / self.close
```

## 43. stack_bull_score

简介：多头堆叠得分

```python
def stack_bull_score(self):
    """多头堆叠得分"""
    m5 = self.close.rolling(5).mean()
    m20 = self.close.rolling(20).mean()
    m60 = self.close.rolling(60).mean()
    return (m5 > m20).astype(float) + (m20 > m60).astype(float) + (self.close > m5).astype(float)
```

## 44. above_mean_habit

简介：站上均线习惯

```python
def above_mean_habit(self):
    """站上均线习惯"""
    ma = self.close.rolling(20).mean()
    return (self.close > ma).astype(float).rolling(20).mean()
```

## 45. ema_ribbon_gap

简介：EMA彩带间距

```python
def ema_ribbon_gap(self):
    """EMA彩带间距"""
    e12 = self.close.ewm(span=12).mean()
    e26 = self.close.ewm(span=26).mean()
    return (e12 - e26) / self.close
```

## 46. hist_norm_pulse

简介：标准化柱脉冲

```python
def hist_norm_pulse(self):
    """标准化柱脉冲"""
    e12 = self.close.ewm(span=12).mean()
    e26 = self.close.ewm(span=26).mean()
    dif = e12 - e26
    dea = dif.ewm(span=9).mean()
    return (dif - dea) / self.close
```

## 47. hist_tilt

简介：柱线倾斜

```python
def hist_tilt(self):
    """柱线倾斜"""
    e12 = self.close.ewm(span=12).mean()
    e26 = self.close.ewm(span=26).mean()
    dif = e12 - e26
    dea = dif.ewm(span=9).mean()
    hist = dif - dea
    return hist - hist.shift(3)
```

## 48. rsi_midline_bias

简介：RSI中轴偏离

```python
def rsi_midline_bias(self):
    """RSI中轴偏离"""
    d = self.close.diff()
    up = d.clip(lower=0).rolling(14).mean()
    down = (-d.clip(upper=0)).rolling(14).mean().replace(0, float("nan"))
    rsi = 100 - 100 / (1 + up / down)
    return rsi - 50
```

## 49. rsi_turn_speed

简介：RSI转向速度

```python
def rsi_turn_speed(self):
    """RSI转向速度"""
    d = self.close.diff()
    up = d.clip(lower=0).rolling(14).mean()
    down = (-d.clip(upper=0)).rolling(14).mean().replace(0, float("nan"))
    rsi = 100 - 100 / (1 + up / down)
    return rsi - rsi.shift(5)
```

## 50. stochastic_heat

简介：随机指标热度

```python
def stochastic_heat(self):
    """随机指标热度"""
    lo = self.low.rolling(14).min()
    hi = self.high.rolling(14).max()
    return 100 * (self.close - lo) / (hi - lo).replace(0, float("nan"))
```

## 51. stochastic_cool

简介：随机指标冷却线

```python
def stochastic_cool(self):
    """随机指标冷却线"""
    lo = self.low.rolling(14).min()
    hi = self.high.rolling(14).max()
    k = 100 * (self.close - lo) / (hi - lo).replace(0, float("nan"))
    return k.rolling(3).mean()
```

## 52. heat_cool_gap

简介：热度冷却差

```python
def heat_cool_gap(self):
    """热度冷却差"""
    lo = self.low.rolling(14).min()
    hi = self.high.rolling(14).max()
    k = 100 * (self.close - lo) / (hi - lo).replace(0, float("nan"))
    d = k.rolling(3).mean()
    return k - d
```

## 53. band_location

简介：布林带内位置

```python
def band_location(self):
    """布林带内位置"""
    mid = self.close.rolling(20).mean()
    sd = self.close.rolling(20).std()
    up = mid + 2 * sd
    dn = mid - 2 * sd
    return (self.close - dn) / (up - dn).replace(0, float("nan"))
```

## 54. band_squeeze_ratio

简介：带宽挤压比

```python
def band_squeeze_ratio(self):
    """带宽挤压比"""
    mid = self.close.rolling(20).mean()
    sd = self.close.rolling(20).std()
    width = (4 * sd) / mid
    return width / width.rolling(60).mean()
```

## 55. band_walk_up

简介：沿上轨行走

```python
def band_walk_up(self):
    """沿上轨行走"""
    mid = self.close.rolling(20).mean()
    up = mid + 2 * self.close.rolling(20).std()
    return (self.close > up.shift(1)).astype(float).rolling(10).mean()
```

## 56. gap_magnet

简介：跳空磁吸压

```python
def gap_magnet(self):
    """跳空磁吸压"""
    return (self.open - self.close.shift(1)) / self.close.shift(1)
```

## 57. inside_nest_rate

简介：内包线筑巢率

```python
def inside_nest_rate(self):
    """内包线筑巢率"""
    inside = (self.high < self.high.shift(1)) & (self.low > self.low.shift(1))
    return inside.astype(float).rolling(10).mean()
```

## 58. outside_burst_rate

简介：外包线爆发率

```python
def outside_burst_rate(self):
    """外包线爆发率"""
    outside = (self.high > self.high.shift(1)) & (self.low < self.low.shift(1))
    return outside.astype(float).rolling(10).mean()
```

## 59. fresh_high_rate

简介：刷新高点频率

```python
def fresh_high_rate(self):
    """刷新高点频率"""
    return (self.high > self.high.shift(1)).astype(float).rolling(20).mean()
```

## 60. fresh_low_rate

简介：刷新低点频率

```python
def fresh_low_rate(self):
    """刷新低点频率"""
    return (self.low < self.low.shift(1)).astype(float).rolling(20).mean()
```

## 61. trend_clarity

简介：趋势清晰度

```python
def trend_clarity(self):
    """趋势清晰度"""
    r = self.close.pct_change(20)
    vol = self.close.pct_change().rolling(20).std().replace(0, float("nan"))
    return r / vol
```

## 62. thrust_per_range

简介：单位振幅动量

```python
def thrust_per_range(self):
    """单位振幅动量"""
    mom = self.close.pct_change(20)
    v = (self.high - self.low).rolling(20).mean() / self.close
    return mom / v.replace(0, float("nan"))
```

## 63. momentum_jerk

简介：动量加加速度

```python
def momentum_jerk(self):
    """动量加加速度"""
    return self.close.pct_change(5) - self.close.pct_change(20) / 4
```

## 64. return_memory

简介：收益记忆相关

```python
def return_memory(self):
    """收益记忆相关"""
    r = self.close.pct_change()
    return r.rolling(10).corr(r.shift(1))
```

## 65. absret_volume_tie

简介：绝对收益绑量

```python
def absret_volume_tie(self):
    """绝对收益绑量"""
    return self.close.pct_change().abs().rolling(20).corr(self.volume)
```

## 66. span_volume_tie

简介：振幅绑量相关

```python
def span_volume_tie(self):
    """振幅绑量相关"""
    amp = (self.high - self.low) / self.close
    return amp.rolling(20).corr(self.volume)
```

## 67. session_impulse

简介：日内额加权冲量

```python
def session_impulse(self):
    """日内额加权冲量"""
    impulse = (self.close / self.open - 1) * self.amount
    return impulse.rolling(10).sum() / self.amount.rolling(10).sum()
```

## 68. overnight_impulse

简介：隔夜额加权冲量

```python
def overnight_impulse(self):
    """隔夜额加权冲量"""
    impulse = (self.open / self.close.shift(1) - 1) * self.amount
    return impulse.rolling(10).sum() / self.amount.rolling(10).sum()
```

## 69. bid_pressure_proxy

简介：买压近似

```python
def bid_pressure_proxy(self):
    """买压近似"""
    rng = (self.high - self.low).replace(0, float("nan"))
    return ((self.close - self.low) / rng * self.volume).rolling(10).sum() / self.volume.rolling(10).sum()
```

## 70. ask_pressure_proxy

简介：卖压近似

```python
def ask_pressure_proxy(self):
    """卖压近似"""
    rng = (self.high - self.low).replace(0, float("nan"))
    return ((self.high - self.close) / rng * self.volume).rolling(10).sum() / self.volume.rolling(10).sum()
```

## 71. pressure_skew

简介：买卖压倾斜

```python
def pressure_skew(self):
    """买卖压倾斜"""
    rng = (self.high - self.low).replace(0, float("nan"))
    buy = (self.close - self.low) / rng * self.volume
    sell = (self.high - self.close) / rng * self.volume
    return (buy - sell).rolling(10).sum() / self.volume.rolling(10).sum()
```

## 72. volume_timed_edge

简介：量时钟收益边

```python
def volume_timed_edge(self):
    """量时钟收益边"""
    w = self.volume / self.volume.rolling(20).mean()
    return (self.close.pct_change() * w).rolling(10).mean()
```

## 73. dollar_timed_edge

简介：额时钟收益边

```python
def dollar_timed_edge(self):
    """额时钟收益边"""
    w = self.amount / self.amount.rolling(20).mean()
    return (self.close.pct_change() * w).rolling(10).mean()
```

## 74. spike_hangover

简介：放量后遗症

```python
def spike_hangover(self):
    """放量后遗症"""
    spike = self.volume > self.volume.rolling(20).mean() * 1.5
    ret = self.close.pct_change()
    return (-ret.shift(1)).where(spike.shift(1), 0).rolling(20).mean()
```

## 75. dryup_follow_through

简介：缩量后跟进

```python
def dryup_follow_through(self):
    """缩量后跟进"""
    dry = self.volume < self.volume.rolling(20).mean() * 0.7
    ret = self.close.pct_change(5)
    return ret.where(dry.shift(5), 0).rolling(20).mean()
```

## 76. wing_asymmetry

简介：高低翼不对称

```python
def wing_asymmetry(self):
    """高低翼不对称"""
    up = (self.high / self.close - 1).rolling(20).mean()
    dn = (1 - self.low / self.close).rolling(20).mean()
    return up - dn
```

## 77. open_drive_force

简介：开盘驱动力度

```python
def open_drive_force(self):
    """开盘驱动力度"""
    gap = self.open / self.close.shift(1) - 1
    amp = ((self.high - self.low) / self.close).replace(0, float("nan"))
    return gap / amp
```

## 78. close_drive_force

简介：尾盘驱动力度

```python
def close_drive_force(self):
    """尾盘驱动力度"""
    body = self.close / self.open - 1
    amp = ((self.high - self.low) / self.close).replace(0, float("nan"))
    return body / amp
```

## 79. quiet_money

简介：静默资金代理

```python
def quiet_money(self):
    """静默资金代理"""
    amp = ((self.high - self.low) / self.close).replace(0, float("nan"))
    return (self.amount / amp).rolling(10).mean() / self.amount.rolling(10).mean()
```

## 80. noisy_crowd

简介：嘈杂资金代理

```python
def noisy_crowd(self):
    """嘈杂资金代理"""
    amp = (self.high - self.low) / self.close
    vol_z = self.volume / self.volume.rolling(20).mean()
    return (amp * vol_z).rolling(10).mean()
```

## 81. liquidity_strain

简介：流动性紧绷

```python
def liquidity_strain(self):
    """流动性紧绷"""
    amp = (self.high - self.low) / self.close
    return amp / (self.amount / self.amount.rolling(20).mean())
```

## 82. impact_friction

简介：冲击摩擦成本

```python
def impact_friction(self):
    """冲击摩擦成本"""
    ret_abs = self.close.pct_change().abs()
    liq = (self.amount / self.amount.rolling(20).mean()).replace(0, float("nan"))
    return ret_abs / liq
```

## 83. smooth_edge

简介：平滑优势分

```python
def smooth_edge(self):
    """平滑优势分"""
    net = (self.close - self.close.shift(20)).abs()
    path = self.close.diff().abs().rolling(20).sum()
    eff = net / path.replace(0, float("nan"))
    vol = self.close.pct_change().rolling(20).std().replace(0, float("nan"))
    return eff / vol
```

## 84. choppiness_lite

简介：轻量震荡指数

```python
def choppiness_lite(self):
    """轻量震荡指数"""
    prev = self.close.shift(1)
    a = self.high - self.low
    b = (self.high - prev).abs()
    c = (self.low - prev).abs()
    tr = a.where(a > b, b)
    tr = tr.where(tr > c, c)
    atr_sum = tr.rolling(14).sum()
    hi = self.high.rolling(14).max()
    lo = self.low.rolling(14).min()
    return atr_sum / (hi - lo).replace(0, float("nan"))
```

## 85. meander_ratio

简介：蜿蜒路径比

```python
def meander_ratio(self):
    """蜿蜒路径比"""
    path = self.close.diff().abs().rolling(20).sum()
    net = (self.close - self.close.shift(20)).abs().replace(0, float("nan"))
    return path / net
```

## 86. seat_velocity

简介：走廊座位速度

```python
def seat_velocity(self):
    """走廊座位速度"""
    hi = self.high.rolling(20).max()
    lo = self.low.rolling(20).min()
    pos = (self.close - lo) / (hi - lo).replace(0, float("nan"))
    return pos - pos.shift(5)
```

## 87. vol_regime_flip

简介：波动体制翻转

```python
def vol_regime_flip(self):
    """波动体制翻转"""
    v = self.close.pct_change().rolling(10).std()
    return v / v.rolling(60).mean() - 1
```

## 88. return_dispersion

简介：收益离散跨度

```python
def return_dispersion(self):
    """收益离散跨度"""
    r = self.close.pct_change()
    return r.rolling(20).max() - r.rolling(20).min()
```

## 89. upside_semi_vol

简介：上行半波动

```python
def upside_semi_vol(self):
    """上行半波动"""
    r = self.close.pct_change()
    return r.where(r > 0, 0).rolling(20).std()
```

## 90. downside_semi_vol

简介：下行半波动

```python
def downside_semi_vol(self):
    """下行半波动"""
    r = self.close.pct_change()
    return r.where(r < 0, 0).rolling(20).std()
```

## 91. semi_vol_tilt

简介：半波动倾斜

```python
def semi_vol_tilt(self):
    """半波动倾斜"""
    r = self.close.pct_change()
    up = r.where(r > 0, 0).rolling(20).std()
    dn = r.where(r < 0, 0).rolling(20).std().replace(0, float("nan"))
    return up / dn
```

## 92. left_tail_depth

简介：左尾深度

```python
def left_tail_depth(self):
    """左尾深度"""
    return self.close.pct_change().rolling(60).quantile(0.05)
```

## 93. right_tail_reach

简介：右尾伸展

```python
def right_tail_reach(self):
    """右尾伸展"""
    return self.close.pct_change().rolling(60).quantile(0.95)
```

## 94. tail_wingspan

简介：尾部翼展

```python
def tail_wingspan(self):
    """尾部翼展"""
    r = self.close.pct_change()
    return r.rolling(60).quantile(0.95) - r.rolling(60).quantile(0.05)
```

## 95. price_volume_trail

简介：价量踪迹

```python
def price_volume_trail(self):
    """价量踪迹"""
    pvt = self.close.pct_change() * self.volume
    return pvt.rolling(20).sum() / self.volume.rolling(20).sum()
```

## 96. flow_slope

简介：资金流斜率代理

```python
def flow_slope(self):
    """资金流斜率代理"""
    sign = (self.close > self.close.shift(1)).astype(float) * 2 - 1
    obv = (sign * self.volume).rolling(20).sum()
    return obv / self.volume.rolling(20).sum()
```

## 97. typical_bias

简介：典型价偏向

```python
def typical_bias(self):
    """典型价偏向"""
    typical = (self.high + self.low + self.close) / 3
    return self.close / typical - 1
```

## 98. typical_thrust_10

简介：典型价推力

```python
def typical_thrust_10(self):
    """典型价推力"""
    typical = (self.high + self.low + self.close) / 3
    return typical.pct_change(10)
```

## 99. midrange_pull

简介：中轴牵引

```python
def midrange_pull(self):
    """中轴牵引"""
    mid = (self.high + self.low) / 2
    return (self.close / mid - 1).rolling(10).mean()
```

## 100. composite_edge

简介：复合边际优势

```python
def composite_edge(self):
    """复合边际优势"""
    net = (self.close - self.close.shift(20)).abs()
    path = self.close.diff().abs().rolling(20).sum()
    eff = net / path.replace(0, float("nan"))
    rng = (self.high - self.low).replace(0, float("nan"))
    buy = ((self.close - self.low) / rng).rolling(10).mean()
    noise = self.close.pct_change().rolling(20).std().replace(0, float("nan"))
    return eff * buy / noise
```
