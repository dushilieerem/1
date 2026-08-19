# Verification：经典策略迁移

## 已验证

- RSI 策略作为事件策略资产登记，使用 Wilder RSI、MA200 与持仓均价风控。
- 事件引擎测试覆盖均价写入、读取和清除。
- 策略库测试覆盖 RSI 指标范围和标准日频 OHLC 回测。
- CANSLIM Lite 策略作为事件策略资产登记，只用价格和沪深 300 日线；测试覆盖简化基底突破和日频回测。
- KD 随机指标策略作为事件策略资产登记；测试覆盖慢速 K/D 数值范围和标准日频 OHLC 回测。
- 一目均衡表策略作为事件策略资产登记；测试覆盖当前云层采用 26 日前数据计算和标准日频 OHLC 回测。
- 均线多头排列策略作为事件策略资产登记；测试覆盖 MA5/10/20/60 的排列与斜率、止盈条件和标准日频 OHLC 回测。
- 配对交易作为向量化研究策略资产登记；测试覆盖偏离时的等名义多空权重、净敞口为零和 NativeEngine 回测。
- 德邦特—塞勒长期反转与豪根—海因斯低波动异象策略作为事件策略资产登记；测试覆盖目录登记、长期反转的跳月形成期与恢复确认字段，以及两者在所需点时面板上的日频回测。
- Piotroski F-Score 与股息增长策略作为事件策略资产登记；测试覆盖目录登记、F-Score 九项满分情形、连续五年分红与最近一年不降条件，以及两者在所需点时面板上的日频回测。真实策略结果仍依赖 FEAT-010 发布公告日财务 TTM 和分红事件面板。
- Aroon 趋势策略作为事件策略资产登记；测试覆盖 26 个观测窗口的最近极值计算和标准日频 OHLC 回测。
- KST 多周期动量策略作为事件策略资产登记；测试覆盖 ROC 平滑加权公式、9 日信号线和标准日频 OHLC 回测。
- 聂夫低市盈率与戴维斯双击策略作为事件策略资产登记；测试覆盖基本面字段契约、低 PE/历史 PE 分位筛选、月度调仓及标准日频面板回测。
- 12-1 动量、小盘价值、红利低波狗股和三重滤网均作为事件策略资产登记；新增回归测试覆盖目录契约、行业/基本面字段面板回测、狗股仅在一月调仓和三重滤网日频运行。
- 抛物线 SAR 与 Fama-French/Carhart 多因子均作为事件策略资产登记；新增回归测试覆盖 SAR 反转、目录契约及具备点时市值/PB 面板的日频回测。
- 凯特纳通道与 Williams %R 均作为事件策略资产登记；新增回归测试覆盖通道、%R 公式、目录契约及日频 OHLC 回测。
- OBV、蔡金和净营运资产异象策略作为事件策略资产登记；Dual Thrust 作为向量化研究策略资产登记。新增回归测试覆盖四项目录契约、OBV/蔡金核心指标、NOA 公式、Dual Thrust Range 和 NativeEngine 运行。
- CCI、MFI、TRIX 和 ROC 作为事件策略资产登记；新增回归测试覆盖四项目录契约、CCI/MFI/TRIX/ROC 核心公式、MFI 缺少成交量时的拒绝行为以及 OHLC/OHLCV 日频事件回测。
- Ultimate Oscillator、Vortex Indicator、Relative Vigor Index 和 Elder Force Index 作为事件策略资产登记；新增回归测试覆盖四项目录契约、核心公式、Elder Force Index 缺少成交量时的拒绝行为以及 OHLC/OHLCV 日频事件回测。
- CMO、Fisher Transform、Ease of Movement 和 Volume Price Trend 作为事件策略资产登记；新增回归测试覆盖四项目录契约、核心公式、EOM/VPT 缺少成交量时的拒绝行为以及 OHLC/OHLCV 日频事件回测。
- Awesome Oscillator、Balance of Power、Choppiness Index 突破和 Coppock Curve 作为事件策略资产登记；新增回归测试覆盖四项目录契约、核心公式、未来观测不改变历史指标、OHLC 字段拒绝、持仓/权重约束和标准日频事件回测。
- DPO、TSI、StochRSI 与 RVI 作为事件策略资产登记；新增回归测试覆盖四项目录契约、与 `Factor/libraries/technical_lib.py` 对齐的核心公式、未来观测不改变历史指标、`close` 字段拒绝、持仓/权重约束和标准日频事件回测。
- Connors RSI(2)、Supertrend、Hull Moving Average 与 Williams Alligator 作为事件策略资产登记；新增回归测试覆盖目录契约、RSI/ATR/WMA/SMMA 核心公式、未来观测不改变历史指标、真实字段缺失拒绝、持仓/权重约束和标准日频事件回测。

## 本次验证记录（2026-08-14）

- `conda run --no-capture-output -n svquant python -m pytest ResearchEngine/tests/test_strategy_migration_ao_bop_choppiness_coppock.py -q`：13 passed。
- `conda run --no-capture-output -n svquant python -m pytest ResearchEngine/tests/test_strategy_library.py ResearchEngine/tests/test_classic_technical_factors.py -q`：12 passed。
- `StrategyCatalog` 共解析 58 个资产；本次四个 `strategy_id/file/entrypoint/execution_mode` 四元组均为有效 `event/v1` 条目。
- `git diff --check`：通过；仅输出工作区既有文件的 LF/CRLF 转换提示，无空白错误。

## 本次增量验证记录（2026-08-17）

- `conda run --no-capture-output -n svquant python -m pytest ResearchEngine/tests/test_strategy_migration_dpo_tsi_stochrsi_rvi.py ResearchEngine/tests/test_strategy_library.py -q`：19 passed。
- 本批四个 `strategy_id/file/entrypoint/execution_mode` 四元组均可由 `StrategyCatalog` 加载，执行模式均为 `event`，策略字段契约均为 `close`。
- `git diff --check`：通过；仅输出工作区已有文件的 LF/CRLF 转换提示，无空白错误。

## 本次增量验证记录（2026-08-18）

- `conda run --no-capture-output -n svquant python -m pytest ResearchEngine/tests/test_strategy_migration_rsi2_supertrend_hma_alligator.py -q`：12 passed。
- `conda run --no-capture-output -n svquant python -m pytest ResearchEngine/tests/test_strategy_library.py ResearchEngine/tests/test_classic_technical_factors.py -q`：12 passed。
- `conda run --no-capture-output -n svquant python -m pytest ResearchEngine/tests -k strategy_migration -q`：67 passed，244 deselected；仅有既有 FastAPI/Starlette 弃用警告。
- `conda run --no-capture-output -n svquant python -m pytest -q`：376 passed；仅有既有 FastAPI/Starlette 弃用警告。
- `StrategyCatalog` 共解析 62 个资产；本批四个 `strategy_id/file/entrypoint/execution_mode` 四元组均可加载，执行模式均为 `event/v1`。
- `git diff --check`：通过；Git 仅提示工作区部分文件的 LF/CRLF 转换，不存在空白错误。

## 限制与遗留项

- 日频风控以已知的前一收盘触发、下一开盘成交；不宣称模拟盘中止损。
- RSI 股票池、历史 ST/停牌/上市过滤待数据面板提供。
- CANSLIM Lite 不含原始策略的 C/A/I/S 与历史证券状态过滤，且月线条件只是简化基底突破；结果仅用于研究验证。
- KD 与一目均衡表未模拟历史宽基成分、ST/停牌/上市日期、涨跌停与 T+1 可成交性；这些需由数据准备和事件引擎后续能力共同覆盖。
- 配对交易未模拟融券可得性、借券费、保证金、分红与分钟级成交；其结果仅用于研究验证，实盘或模拟盘迁移需依赖 `cn_multi_asset_intraday_v1` 能力画像。
- Aroon 与 KST 未模拟历史宽基成分、ST、停牌、上市日期和涨跌停/T+1 的原聚宽侧过滤；日频下由事件引擎的可用市场状态模拟，仍仅用于研究验证。
- 12-1 动量和小盘价值依赖日期×证券的行业、成交额与点时基本面面板；红利低波狗股依赖点时 PE 与股息率。当前策略库不会补齐缺失字段或以当前截面回填历史；在数据底座发布前仅用于具备相应研究面板的本地验证。
- Fama-French/Carhart 多因子依赖点时总市值和 PB；当前不会将流通市值、最新估值或缺失值替代为历史输入。SAR 的日频止损以截至前一收盘计算、下一开盘成交，不模拟 14:50 的盘中成交。
- 凯特纳通道与 Williams %R 不模拟盘中突破、部分成交或成交量约束；回测结果仅作为日频研究验证，不能视为实盘执行承诺。
- OBV 与蔡金只在月度调仓时检查量价/行业/估值条件，未把原脚本的 ST、退市和盘中状态检查移入事件策略；这些条件仍由点时数据面板和事件引擎能力承载。
- 净营运资产异象依赖点时资产负债表字段；`long_borr`、`bond_payable` 或其他核心字段缺失时不生成候选，不以零值补齐。
- Dual Thrust 的原始 09:45 盘中触发、当日开盘后成交、涨跌停和 T+1 均未由 v1 模拟；v1 仅表示日线收盘触发后下一交易日收益的研究结果。
- CCI、MFI、TRIX 和 ROC 仅提供日频研究版；不模拟盘中触发、动态历史成分股、ST/停牌/涨跌停之外的策略专属过滤，也不构成实盘执行承诺。
- Ultimate Oscillator、Vortex Indicator、Relative Vigor Index 和 Elder Force Index 仅提供日频研究版；不模拟盘中触发、动态历史成分股、ST/停牌/涨跌停之外的策略专属过滤，也不构成实盘执行承诺。
- CMO、Fisher Transform、Ease of Movement 和 Volume Price Trend 仅提供日频研究版；不模拟盘中触发、动态历史成分股、ST/停牌/涨跌停之外的策略专属过滤，也不构成实盘执行承诺。
- AO、BOP、Choppiness 与 Coppock 仅提供日频研究版；Coppock 的 11/14/10 日参数是与因子库一致的日频适配，不代表原始月线指标复刻。BOP 的 14 日平滑和 Choppiness 的 38.2/61.8 阈值是可测试研究规则，不代表已完成参数有效性验证。
- DPO、TSI、StochRSI 与 RVI 仅提供日频研究版；四者只使用前收盘 `close` 计算，不模拟盘中触发、动态历史成分股、ST/停牌/涨跌停之外的策略专属过滤，也不构成实盘执行承诺。TSI、StochRSI 与 RVI 的参数为研究默认值，尚未完成跨市场状态的参数稳健性验证。
- Connors RSI(2)、Supertrend、Hull Moving Average 与 Williams Alligator 仅提供日频研究版；不模拟盘中触发、动态历史成分股、ST/停牌/涨跌停之外的策略专属过滤，也不构成实盘执行承诺。Supertrend 的 ATR 递推和 Alligator 的 SMMA 参数为研究默认值，尚未完成跨市场状态的参数稳健性验证。
