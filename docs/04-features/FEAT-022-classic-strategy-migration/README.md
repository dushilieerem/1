# FEAT-022：经典策略迁移

- 状态：开发中（已新增聂夫低市盈率、戴维斯双击、12-1 动量、小盘价值、红利低波狗股、三重滤网、抛物线 SAR、Fama-French 多因子、凯特纳通道、Williams %R、德邦特—塞勒长期反转、豪根—海因斯低波动异象、Piotroski F-Score、股息增长、OBV、蔡金、Dual Thrust、净营运资产异象、CCI、MFI、TRIX、ROC、Ultimate Oscillator、Vortex Indicator、Relative Vigor Index、Elder Force Index、CMO、Fisher Transform、EOM、VPT、AO、BOP、Choppiness、Coppock、DPO、TSI、StochRSI、RVI、Connors RSI(2)、Supertrend、Hull Moving Average、Williams Alligator、KAMA、McGinley Dynamic、Heikin-Ashi、Pivot Point、BBI、Mass Index、VHF、WVAD 策略）
- 所属 Initiative：INIT-001 投研核心
- 所属能力：策略研究 / 策略回测
- 优先级：P1
- 宏观影响：L1（扩充既有策略研究资产，不改变产品边界）

## 目标

将用户提供的策略迁移为可版本化的 SVQuant 策略资产：交付可验证的 Wilder RSI、CANSLIM Lite、KD 随机指标、一目均衡表、均线多头排列、Aroon、KST、聂夫低市盈率、戴维斯双击、12-1 动量、小盘价值、红利低波狗股、三重滤网、抛物线 SAR、Fama-French 多因子、凯特纳通道、Williams %R、德邦特—塞勒长期反转、豪根—海因斯低波动异象、Piotroski F-Score、股息增长、OBV、蔡金、净营运资产异象、CCI、MFI、TRIX、ROC、Ultimate Oscillator、Vortex Indicator、Relative Vigor Index、Elder Force Index、CMO、Fisher Transform、EOM、VPT、AO、BOP、Choppiness、Coppock、DPO、TSI、StochRSI、RVI、Connors RSI(2)、Supertrend、Hull Moving Average、Williams Alligator、KAMA、McGinley Dynamic、Heikin-Ashi 与 Pivot Point 日频/月频事件策略，以及 Dual Thrust 和配对交易向量化研究策略。

## 本次增量（2026-08-18）

新增四个日频事件研究策略：Connors RSI(2) 短期反转、Supertrend 趋势跟随、Hull Moving Average 低滞后趋势和 Williams Alligator 多均线趋势。四者仅新增 `ResearchEngine/app/assets/strategies/libraries/` 版本化源码与索引条目，不改变 app.quantcore、EventEngine 或 ResearchEngine 的共享接口；策略均遵守前收盘可见、下一开盘成交、现金多头和研究版边界。

- `01-feature-proposal.md`
- `02-product-requirements.md`
- `03-technical-design.md`
- `04-project-plan.md`
- `05-verification.md`

## 本次增量（2026-08-19）

新增四个日频事件研究策略：Kaufman 自适应移动平均线（KAMA）、McGinley Dynamic、Heikin-Ashi 趋势和 Pivot Point 支撑阻力突破。四者新增独立版本化源码、索引条目与验收测试，不修改 app.quantcore、EventEngine 或 ResearchEngine 共享接口；均遵守前收盘可见、下一开盘成交、现金多头、最多十只和单只默认 9% 目标权重的研究边界。

- KAMA 与 McGinley Dynamic 只声明 `close`；Heikin-Ashi 声明完整 OHLC，Pivot Point 声明前一交易日所需的 `high/low/close`。
- 四个策略均在缺少声明字段时明确拒绝运行，并对历史不足、无候选和无有效价格保持不下单。
- 回滚方式为从 `ResearchEngine/app/assets/strategies/libraries/index.yaml` 移除四个条目，保留 v1 源码以支持历史版本追溯。

## 本次增量（2026-08-20）

新增四个日频事件研究策略：BBI 多空指数趋势、Mass Index 梅斯线波动反转、VHF 纵横指标趋势强度和 WVAD 威廉变异离散量价趋势。四者新增独立版本化源码、索引条目与验收测试，不修改 app.quantcore、EventEngine 或 ResearchEngine 共享接口；均遵守前收盘可见、下一开盘成交、现金多头、最多十只和单只默认 9% 目标权重的研究边界。

- BBI 与 VHF 只声明 `close`；Mass Index 声明 `high/low/close`；WVAD 声明 `open/high/low/close/volume`。
- 四个策略均在缺少声明字段时明确拒绝运行，对历史不足、无候选和无有效价格保持不下单；WVAD 对零振幅日采用零资金流处理。
- 回滚方式为从 `ResearchEngine/app/assets/strategies/index.yaml` 移除四个条目，保留 v1 源码以支持历史版本追溯。

## 本次增量（2026-08-21）

新增四个日频事件研究策略：TEMA 三重指数移动平均线、SMI 随机动量指标、Ulcer Index 低回撤和 Schaff Trend Cycle 趋势动量。四者新增独立版本化源码、索引条目与验收测试，不修改 `app.quantcore`、EventEngine 或 ResearchEngine 共享接口；均遵守前收盘可见、下一开盘成交、现金多头、最多十只和单只默认 9% 目标权重的研究边界。

- TEMA 与 Ulcer Index 只声明 `close`；SMI 声明 `high/low/close`；STC 只声明 `close`。
- 四个策略均在缺少声明字段时明确拒绝运行，对历史不足、无候选和无有效价格保持不下单；调仓只统计正数量持仓，避免事件账本中的零数量历史键影响持仓上限。
- 回滚方式为从 `ResearchEngine/app/assets/strategies/index.yaml` 移除四个条目，保留 v1 源码以支持历史版本追溯。
