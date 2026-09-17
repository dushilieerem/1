# FEAT-026：国泰君安 Alpha191 因子库迁移

- 状态：已完成
- 所属 Initiative：INIT-001 投研核心
- 所属能力：因子研究
- 优先级：P0
- 代码位置：`Factor/libraries/gtja_alpha191.py`

## 文档索引

- `02-product-requirements.md`：用户故事、边界与验收标准。
- `03-technical-design.md`：算子、字段契约、兼容与回滚设计。

其余原分册（`01-feature-proposal.md`、`04-project-plan.md`、`05-verification.md`）内容已收编至本 README。

## 1. 价值与范围

### 1. 功能名称

国泰君安 Alpha191 公式因子库（SVQuant 原生实现）。

### 2. 背景

国泰君安 Alpha191 是 A 股研究中常用的公开量价因子集合。现有 SVQuant 已支持
WorldQuant Alpha101，但尚未提供 Alpha191 的统一命名、宽表计算和 API 目录，研究员
迁移旧研究时需要自行维护公式和数据回退口径。

### 3. 用户价值

- 研究员可以按 `alpha191_001`–`alpha191_191` 枚举和复算经典公式。
- 因子库索引清楚展示必需字段、VWAP/成交额回退和基准依赖。
- 公式结果可以直接进入现有因子分析、分层回测和结果缓存链路。

### 4. 商业价值

- 降低 A 股量化团队迁移至 SVQuant 的初始成本。
- 补齐与竞品常见 Alpha101/Alpha191 基线，提升投研闭环的专业完整度。
- 形成可审计的公开公式样例，为后续 AI 因子生成和因子组合分析提供基础资产。

### 5. 竞品与差异化

聚宽等平台提供 Alpha191 目录和取值 API，但绑定其数据、账号和运行时。SVQuant 采用
公开公式 + 本地授权数据 + 原生向量化实现，显式披露字段回退与基准代理，不承诺在
缺少同源数据时逐值一致。

### 6. MVP 范围

#### 必须做

- 提供独立库 `gtja_alpha191`，公开方法 `alpha191_001`–`alpha191_191`。
- 支持 OHLCV 面板；amount、VWAP 和基准依赖使用明确回退规则。
- 更新 `index.yaml`、因子总览和批次说明，保留来源与验证状态。
- 补充库加载、代表性公式、全量形状、缺字段回退和无未来数据测试。

#### 可以以后做

- 与合法同源供应商参考值的逐值容差回归。
- 行业/市值中性化的历史版本字段和前端筛选。
- 对需要 Fama-French 或指数数据的公式接入更多基准。

#### 明确不做

- 不接入聚宽 SDK/API，不保存或分发第三方因子值。
- 不把缺失的 Fama-French/基准数据静默伪装成同源结果。
- 不修改既有 Alpha101 或其他因子库的公开名称和计算行为。

### 7. 优先级评估

商业价值 4、用户价值 5、战略价值 4、开发成本 4，评分 20，纳入 P0；先交付可在
OHLCV 面板运行的公式库，再按授权数据补齐同源回归。

## 2. 验收与证据

### 自动化验证

状态：已完成（2026-08-14）。

- `FactorLoader.load("gtja_alpha191")` 发现 191 个方法，首尾名称正确。
- Alpha001、Alpha002、Alpha041 通过确定性公式对照。
- 全部 191 个方法在含 OHLCV、amount 的标准面板上返回日期×标的宽表。
- 缺少 amount/VWAP 时，VWAP 相关公式使用约定回退。
- 修改最后一行行情不影响此前日期的代表性因子值。
- `factor_catalog check` 验证源码、索引和数量一致。

### 执行命令

```powershell
conda run --no-capture-output -n svquant python -m pytest ResearchEngine/tests/test_gtja_alpha191.py -q
conda run --no-capture-output -n svquant python -m researchengine.factor_catalog check
```

### 未覆盖项

尚未取得与本项目数据源完全同源的 Alpha191 因子值，因此只声明公式复算与工程契约
验证，不声明第三方平台逐值一致或任何收益有效性。Alpha030 的 Fama-French 依赖和
基准代理口径需要在数据底座补齐后单独回归。

## 3. 计划与里程碑

| 任务 | 复杂度 | 风险 | 依赖 | 完成条件 |
|---|---:|---|---|---|
| 核对公开公式和输入字段 | 2 | 中 | 公开文档、现有 Panel | 公式编号、回退口径冻结 |
| 编写向量化算子与 191 个方法 | 4 | 中 | Pandas/NumPy | 191 个方法可加载并返回宽表 |
| 接入索引、API 和总览 | 2 | 低 | FactorLoader、catalog | `gtja_alpha191` 可发现 |
| 代表性公式和全量执行测试 | 3 | 中 | 公式实现 | 定向测试、目录校验通过 |
| 文档和验收记录 | 2 | 低 | 测试结果 | Feature、批次说明同步 |

### 里程碑

- M1：公式与字段回退口径确定。
- M2：191 个方法和索引/API 接入完成。
- M3：公式、形状、回退、时点性测试通过并发布边界说明。

### 回滚

从 `Factor/libraries/index.yaml` 移除 `gtja_alpha191` 条目即可停止库发现；不删除源码、
不影响现有 Alpha101 和其他内置库。
