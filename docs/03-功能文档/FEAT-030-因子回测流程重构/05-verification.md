# FEAT-030：因子回测流程重构 — Verification

- 状态：验收中（主链已实施，专项矩阵尚未全部关闭）
- 日期：2026-08-28
- 关联：[需求验收标准](02-product-requirements.md)、[实施关卡](04-project-plan.md)

## 1. 重构前基线（历史记录）

2026-08-28 的规划阶段，在当前工作区使用 svquant 环境执行以下七组已有测试：

```powershell
$svquantPython = "D:/Devtools/anaconda3/envs/svquant/python.exe"
& $svquantPython -m pytest -q ResearchEngine/tests/quantcore/test_data.py ResearchEngine/tests/quantcore/test_factor.py ResearchEngine/tests/quantcore/test_metric.py ResearchEngine/tests/quantcore/test_factor_tools.py ResearchEngine/tests/quantcore/test_adapter.py ResearchEngine/tests/test_layered.py ResearchEngine/tests/services/test_factor_backtest_architecture.py
```

实际结果：**82 passed in 3.97s**。对应旧 Executor/NativeEngine 链路，仅证明上述用例在该
工作区通过；不是完整旧版验收，更不是 FEAT-030 新实现通过。工作区存在未提交变更，
不能把该结果归属于一个干净提交。M1 必须重新记录实施时源码、环境和基准数据。

## 1.1 实施阶段验证记录

2026-08-28 用户明确批准代码重构后，完成了 DataEngine、FactorEngine、PortfolioEngine、
MetricEngine、BacktestEngine 及因子入口/批量配置迁移。以下是当前已执行的自动化验证：

```powershell
& "D:/Devtools/anaconda3/envs/svquant/python.exe" -m pytest -q ResearchEngine/tests
```

结果：**521 passed, 1 warning in 676.75s**。该结果覆盖当时工作区的完整 ResearchEngine
测试集；警告来自 `starlette.testclient` 对 `httpx` 的弃用提示，不是回测失败。

随后针对最后补充的过滤状态覆盖和“完整 close 索引先计算远期收益”边界，执行：

```powershell
& "D:/Devtools/anaconda3/envs/svquant/python.exe" -m pytest -q ResearchEngine/tests/quantcore/test_factor_backtest_engines.py
```

结果：**5 passed in 1.11s**。随后补充交易评价摘要、完整 close 传递和兼容错误信息，
并将两处旧测试断言更新为已批准的“有效池先于预处理”顺序；没有修改数值期望。

最终候选代码再次执行同一完整测试集：

```powershell
& "D:/Devtools/anaconda3/envs/svquant/python.exe" -m pytest -q ResearchEngine/tests
```

结果：**523 passed, 1 warning in 679.51s**。唯一警告来自 `starlette.testclient` 对
`httpx` 的弃用提示，不是回测失败。该结果作为 M5 的最终全量自动化证据；下表列出的
数据版本对照、缓存恢复、跨入口显式等价及资源基准仍需专项收口。

## 1.2 services/models 目录修订验证（ADR-029）

本轮在 `researchengine` 分支、HEAD `e812c48` 的既有未提交工作区上执行；
结果不对应一个干净提交，不覆盖或清理此前改动。解释器始终为
`D:/Devtools/anaconda3/envs/svquant/python.exe`。

| 检查 | 实际结果 |
|---|---|
| 本轮迁移前全量基线 | 523 passed, 1 warning in 739.56s |
| 迁移后数据/因子/指标/策略底层及研究门面检查 | 99 passed in 7.56s |
| 最终全量 `python -m pytest -q ResearchEngine/tests` | **528 passed, 1 warning in 728.85s** |
| OpenAPI 排序 JSON 的 SHA-256 | 迁移前后均为 `9b884a7deaf7588e685f5463ca090541cfdff7cc1322d5e14bf4a2172281b381` |
| CLI 导入及帮助 | `python -m app.cli.factor_backtest_batch --help` 正常退出 |
| 包发现 | setuptools 发现 32 个包，无 app.quantcore/core/repositories |
| 文档链接 | 最终检查的 28 份文档、66 处本地链接目标均存在 |
| Git 边界与空白检查 | `git -c core.safecrlf=false diff --check` 通过；WebApp 无 Git 差异或新增文件 |

唯一全量测试警告是原有 Starlette/httpx 弃用提示。新增 5 个架构测试覆盖：
models/database 不在运行时反向导入服务或 HTTP、独立导入 models 不加载服务/FastAPI、
旧包源码不再出现、Engine/模型归属、资源默认路径不因文件移动漂移。
现有 CSV 往返用例增加 ResultData 与 ResultManager.load() 的边界验证。

中途定向测试曾出现 1 failed, 24 passed：因内置因子源码导入路径变化使索引 updated 日期过期；
核对生成差异后仅更新日期到 2026-08-28，没有改因子数目、参数、公式或数值期望。
此问题已由最终 528 项全量回归覆盖。

GitNexus 增量刷新遇到 FTS 索引不一致，随后 `analyze --force` 完整重建成功：
16,979 nodes、31,766 edges、300 flows。MCP 会话仍显示旧统计；其 detect_changes(scope=all)
报告 130 文件、286 符号、13 条受影响流程和 HIGH 风险，涉及策略及批量入口。
该报告包含工作区原有改动，并把未修改的同名 WebApp README 列入结果，不能作为精准变更清单；
实际边界以 Git 差异、源码导入检查和测试为准。没有提交代码，也未忽略高风险提示。

旧 quantcore/core/repositories 的 Python 源码已迁移，无转发包；残留仅有忽略的
`__pycache__`。目录清理被运行环境拒绝，本轮未绕过限制；这些目录不被 setuptools 收录。
历史 `tests/quantcore` 名称保留，测试导入已切换，不代表仍存在 QuantCore 运行时。

本节证明本轮目录与模型归属迁移的自动化验证完成，不替代下表尚未完成的原 M5 专项验收。

## 1.3 FactorEngine 因子解析职责收口验证（2026-08-28）

本轮将 `_resolve_factor(spec)` 收归 `FactorEngine`，移除 runner 中的重复来源
解析和 `factor_resolver` 接线，并将文件/源码加载实现集中到
`app.services.factor.loader`。定向执行：

```powershell
& "D:/Devtools/anaconda3/envs/svquant/python.exe" -m pytest -q `
  ResearchEngine/tests/quantcore/test_factor_backtest_engines.py `
  ResearchEngine/tests/quantcore/test_factor.py `
  ResearchEngine/tests/services/test_factor_backtest_architecture.py `
  ResearchEngine/tests/test_api.py `
  ResearchEngine/tests/test_factor_batch.py `
  ResearchEngine/tests/test_worldquant_alpha101.py `
  ResearchEngine/tests/services/test_factor_backtest_batch_queue.py
```

结果：**125 passed, 1 failed**；失败为批量两槽 FIFO 用例的 3 秒启动时序断言。该用例
随后单独重跑 3 次均通过；核心因子解析/入口/架构相关定向用例另行执行为 **29 passed,
1 warning**。因此本节证明 FactorEngine 解析职责和相关入口回归通过，但全量验收仍保持
“验收中”，并发窗口测试的稳定性不将一次重跑结果直接标记为最终通过。

## 1.4 Spec 与运行状态收敛验证（2026-08-30）

本轮删除因子主链中的 `effective_spec`、Spec → ConfigManager 转换和旧 Context 访问，
保留调用方原始 `FactorBacktestSpec`，运行时数据终点单独记录为 `actual_end`。缓存标准报告
升级为 v2，执行身份升级为 `factor-execution-v4`；缓存恢复后仍保留原始 Spec。

```powershell
& "D:/Devtools/anaconda3/envs/svquant/python.exe" -m pytest -q ResearchEngine/tests
```

结果：**533 passed, 1 warning in 744.15s**。唯一警告仍为 Starlette TestClient/httpx
弃用提示。全量过程中同时修正三项测试/架构残留：测试替换全局 DataEngine 后未恢复、
API fixture 未模拟 lifespan 数据初始化、策略与批量预检仍按旧 Context 访问 `.data_engine`。
修正后因子、策略、批量及研究资产 API 均直接使用应用级 DataEngine。

## 2. 重构验收矩阵

以下逐项标注实际状态，不用文档审查或一次全量回归替代专项运行时验证。

| 编号 | 关联需求 | 场景与判定 | 状态 |
|---|---|---|---|
| V-01 | AC-01 | API、批量、Python 均调用同一 BacktestEngine；因子主链无旧 Executor/adapter 委托 | 部分验证：架构测试通过，跨入口专项待补 |
| V-02 | AC-01、AC-13 | 按 ADR-029 取消 QuantCore；models/database 无运行时上层依赖；MetricEngine 公共旧入口兼容 | 架构与旧指标入口自动化测试通过，见 §1.2 |
| V-03 | AC-02 | 四项默认关闭；过滤独立开启；预处理 0–3；批量/API/CLI/Python 配置一致 | 部分验证：默认值和批量配置测试通过 |
| V-04 | AC-03 | 筛选不删除请求范围内日期，输入面板哈希/内容不变；系统不读取 start 前预热历史 | 待执行 |
| V-05 | AC-03 | 修改 end 之后数据不改变结果；省略 end 固定有效截止日 | 待执行 |
| V-06 | AC-04 | 关闭过滤不要求状态；缺字段跳过告警；部分状态缺失放行并标记覆盖不足 | 已验证：专项测试通过 |
| V-07 | AC-04、09 | 缓存命中保留告警；当次批量摘要/日志可见；不伪造历史诊断 | 待执行 |
| V-08 | AC-05 | 有效池先于去极值/标准化，常数、缺失、重复值结果确定 | 已验证：有效池顺序专项测试通过；其余边界待补 |
| V-09 | AC-06 | Q1 最高组、退化 qcut、空组、不同组数及多空权重符合基准 | 部分验证：已有分组/适配层回归通过 |
| V-10 | AC-06 | 非调仓日持仓延续；过滤变化不自动清仓；调仓意图不标为成交 | 待执行 |
| V-11 | AC-06 | h=1/多期标签按完整索引计算，停牌间隙不压缩，尾部缺失不反向改变组合 | 待执行 |
| V-12 | AC-06 | 100→110→121→133.1 价格例得到收益 0.1/0.1/0.1、展示净值 1/1.1/1.21 | 已验证：专项测试通过 |
| V-13 | AC-06 | 非零费用、首期成本、交易评价摘要、基准和既有缺失值规则与冻结样例一致 | 部分验证：交易成本摘要专项通过，冻结样例待执行 |
| V-14 | AC-06 | IC/RankIC 使用因子数值而非组号，有效样本数与时点正确 | 待执行 |
| V-15 | AC-07 | 同显式 Spec、源码及 release 跨入口对比截面、组合、净值、指标 | 待执行 |
| V-16 | AC-08 | 混合开关并发不串状态，共享 DataEngine 不被替换/修改 | 待执行 |
| V-17 | AC-08 | FIFO、两槽批量、取消、重试、错误分类、断点续跑保持 | 待执行 |
| V-18 | AC-08 | 向量化和事件策略及既有策略资产相关测试无新增失败 | 自动化覆盖：全量测试通过 |
| V-19 | AC-09 | execution=v4/cache=v10，显式相同参数不串用旧缓存/批次；历史表结构和记录保留 | 部分验证：版本测试通过，最终缓存/历史证据待补 |
| V-20 | AC-10 | core/full、年度/回撤/行业/FF3、保存和图表结果保持，呈现层无重复公式 | 待执行 |
| V-21 | AC-11 | 所有数值差异落入已确认差异或单独获得审核；不能只更新期望值 | 待执行 |
| V-22 | AC-12 | 文档/代码开工关卡、WebApp 边界及本次修改范围检查 | 已验证：用户已批准开工，本次未修改 WebApp |
| V-23 | 非功能 | 固定环境对比耗时、读次数、内存；不新增无必要整面板复制或逐股票重复读取 | 待执行 |
| V-24 | AC-13 | Engine 业务在 services，数据结构在 models，存储在 database；动态导入、资源路径、HTTP 契约和包发现正确 | 本轮自动化验证通过，见 §1.2；不包含既有 AI/HTTP 投影全部拆分 |

测试策略：优先扩展已有测试及 fixture；仅当 PortfolioEngine 等新职责没有自然归属时新增
测试文件。架构约束测试需要随目标更新，但数值基准不能被架构改名覆盖。

## 3. 允许差异与审核记录

| 差异 | 已确认处理 |
|---|---|
| 未传过滤参数 | 新版默认全部关闭，区别于旧版默认开启 |
| 同时使用过滤与预处理 | 有效池先于去极值/标准化，可能改变处理数值 |
| 缺失过滤状态 | 新增显式告警；原有数据可用时不改变筛选定义 |
| 其他收益、成本、分组或缺失值变化 | 不在授权差异内；说明原因并返审 |

后续每条差异记录输入、旧结果、新结果、原因、审核结论。已有自动化结果见 §1，
完整固定数据版本的新旧数值对照尚未交付；目录迁移没有更新数值期望来掩盖差异。

## 4. 文档交付检查与代码验收分离

M0 只检查文档包完整性、链接、状态、范围及跨文档一致性；检查结果在文档交付时单独报告。
代码获准实施后，V-01–V-23 按实际命令和固定样例填写证据；本文件仍保留未完成项目。

### M0 文档校验记录（2026-08-28）

- 六份 Feature 文档及 ADR-028 已写入，关联文档已增加职责、调用链和状态说明。
- 58 处新增本地链接的目标文件检查通过；新增文档标题、代码围栏及尾部空格检查通过。
- `git diff --check` 通过；本次代码修改未触及 WebApp，策略旧 Native/Event 链路仍保留。
- Feature 已进入实施/验收中，ADR-028 已采纳但尚未宣告最终交付；12 项需求和 23 项运行时验证仍需逐项收口。

### 原四引擎实施阶段的变更影响检查（历史记录，2026-08-28）

GitNexus `detect_changes(scope=all)` 报告工作区共有 39 个变更文件、151 个变更符号，
其中 4 条已索引执行流程受到影响，整体风险为 **medium**。该结果包含工作区在本次任务
之前已经存在的文档和代码改动；本次相关影响集中在批量入口、MetricEngine、因子实验门面
及兼容辅助函数，未发现 HIGH/CRITICAL 风险。WebApp 未被本次重构修改。

以上是原阶段的文档交付检查与代码证据，不等同于 M5 全部验收完成；
不能将当时的 medium 风险套用到本轮目录迁移，本轮 HIGH 风险及工具限制见 §1.2。

M5 全量验证已使用 svquant 环境执行，最终命令为：

```powershell
& "D:/Devtools/anaconda3/envs/svquant/python.exe" -m pytest -q ResearchEngine/tests
```

最终验收记录仍需补充：工作区/代码版本、固定数据/源码哈希、版本元信息、差异清单及
专项跨入口/缓存/并发证据。未执行项目保持“待执行”，不能凭全量测试推断通过。
