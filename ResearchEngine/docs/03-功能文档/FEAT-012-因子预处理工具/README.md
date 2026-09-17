# FEAT-012：通用因子预处理工具

> [FEAT-030 当前实现](../../../../docs/03-功能文档/FEAT-030-因子回测流程重构/README.md) 已把回测中的预处理调用归入 FactorEngine：
> 完整历史计算 → 有效池 → 可选去极值 → 可选标准化，默认不处理。
> 已有中性化工具继续保留，但本期不增加中性化的回测配置入口；工具已交付，回测接线专项验收中。

状态：已完成 MVP

本功能将横截面去极值、标准化、排名、归一化和中性化收敛至
`quantcore.factor.tool`。

因子函数可直接使用：

```python
from app.quantcore.factor.tool import winsorize, zscore

def value_score(self):
    return zscore(winsorize(1 / self.pb))
```

行业/市值中性化需要显式传入对应的历史暴露面板：

```python
from app.quantcore.factor.tool import neutralize

def neutral_value(self):
    return neutralize(
        1 / self.pb,
        industry=self["industry"],
        market_cap=self.total_mv,
    )
```

## 1. 价值与范围

### 功能名称

因子横截面预处理工具。

### 背景

不同因子库和组合策略已经各自实现了去极值、标准化等逻辑，口径容易分叉。因子中性化还需要行业、市值等外部暴露数据，不应由具体因子库各自实现或隐式读取。

### 用户价值

研究员可以在因子函数中复用同一套、可测试的横截面处理方法，组合不同来源的因子时得到一致结果。

### 商业价值

统一基础研究能力，降低自定义因子编写门槛及回测结果因处理口径不同而不可解释的风险。

### MVP 范围

- 必须做：分位数去极值、MAD 去极值、Z-score、百分位排名、绝对值和归一化、传入行业/市值暴露后的横截面中性化。
- 可以以后做：行业、市值暴露数据的存储与自动装载；分组标准化；暴露回归诊断。
- 明确不做：在工具函数中自动请求或推断行业、财务数据。

## 2. 业务规则与场景

### 用户故事

作为研究员，我希望用公共函数处理日期×标的因子宽表，以便在任意因子库中复用相同的横截面口径。

### 需求与验收标准

1. 所有函数接收、返回 `pandas.DataFrame`（行=日期、列=标的），并保持索引、列和原始缺失值。
2. `winsorize` 支持按日分位数截断；非法分位数抛出 `ValueError`。
3. `mad_winsorize` 以每日中位数和 MAD 进行截断；MAD 为零的有效值保持不变。
4. `zscore` 按日标准化，常数横截面有效值为 0。
5. `rank` 返回按日百分位排名；`normalize` 按日将绝对值和归一化为 1。
6. `neutralize` 支持行业虚拟变量、对数市值或两者；未提供任何暴露时抛出 `ValueError`，样本不足的日期返回缺失值而不伪造结果。
7. 因子库可通过 `from app.quantcore.factor.tool import ...` 使用工具；现有组合策略复用同一实现。

## 3. 方案设计

> 2026-08-28 架构修订：用户已确认 ADR-029 的常规 FastAPI 分层。
> 原 QuantCore 运行时边界取消；五个 Engine 的业务逻辑进入 `app.services`，
> Panel、MetricContext、回测规格/结果和实验上下文进入 `app.models`，数据访问进入 `app.database`。
> 配置为 `app.config`，通用工具为 `app.utils`；不增加 domain/application/infrastructure。
> 下文中的旧目录和旧分层仅作历史设计追溯，不再作为新代码约束；既有业务规则和历史验证记录保留。
> 详见根目录 FEAT-030/06-app-layout.md 与 ADR-029。FEAT-029 因子来源加载目标保持不变。


> [FEAT-030 当前实现](../../../../docs/03-功能文档/FEAT-030-因子回测流程重构/README.md)：factor.tool 保持无状态函数；FactorEngine
> 负责在 DataEngine 掩码之后调用去极值和标准化，不再由应用入口拼装预处理。
> 两项默认 0，中性化回测入口后续另做；既有工具及策略兼容方法保留。代码已切换，专项验收中。

### 模块边界

新增 `QuantCore/quantcore/factor/tool.py`，只包含无状态、数据源无关的 DataFrame 函数。它不依赖 `Panel`，也不访问 MarketData。

`neutralize` 对每一个交易日以截距、行业哑变量和可选的 `log(market_cap)` 做最小二乘回归，返回残差。行业暴露可为日期×标的 DataFrame，或静态的标的 Series；市值必须与因子对齐。

### 兼容性

保留 `FactorPortfolioStrategy` 的静态方法签名，内部委托新工具函数，因此现有策略代码无需改动。

### 测试策略

覆盖去极值边界、缺失值、常数横截面、归一化、行业和市值中性化、非法输入，以及组合策略的兼容行为。

## 4. 计划与里程碑

| 任务 | 复杂度 | 风险 | 状态 |
|---|---:|---|---|
| 定义无状态预处理函数 | 2 | 低 | 已完成 |
| 组合策略迁移至公共实现 | 1 | 低 | 已完成 |
| 单元测试与兼容验证 | 2 | 中 | 已完成 |

里程碑：M1 为工具函数与单元测试通过；M2 为组合策略复用并完成回归测试。
