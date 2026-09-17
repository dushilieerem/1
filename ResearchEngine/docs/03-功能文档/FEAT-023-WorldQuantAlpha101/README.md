# FEAT-023：WorldQuant Alpha 101 因子库迁移

- 状态：已完成
- 所属 Initiative：INIT-001 投研核心
- 所属能力：因子研究
- 优先级：P0
- 代码位置：`Factor/libraries/worldquant_alpha101.py`

## 文档索引

- `02-product-requirements.md`：用户故事、边界与验收标准。
- `03-technical-design.md`：算子、数据契约与兼容设计。

其余原分册（`01-feature-proposal.md`、`04-project-plan.md`、`05-verification.md`）内容已收编至本 README。

## 1. 价值与范围

### 1. 功能名称

WorldQuant Alpha 101 公式因子库（SVQuant 原生实现）。

### 2. 背景

现有 `alpha_library.py` 中的 `alpha101` 只是一个 5 日动量示例，不能满足产品文档中“101 个经典技术因子，开箱即用”的承诺。研究员也无法按公开论文中的标准编号复现 Alpha 101 研究。

### 3. 用户价值

量化开发者可以直接枚举并计算 `alpha001`–`alpha101`，使用现有的因子分析和向量化回测链路验证公开研究基线，减少手工翻译公式的成本。

### 4. 商业价值

- 补齐专业量化平台应具备的内置因子基线，降低试用和迁移门槛。
- 形成可追溯的公式、字段和验证契约，为后续 AI 因子生成提供算子样例。
- 不引入第三方运行时、账号或受限因子值，保持数据源可替换。

### 5. 竞品与差异化

聚宽、米筐和其他研究平台通常提供 Alpha 类因子或表达式能力；SVQuant 采用独立库、原生面板计算和可审计索引，能够接入自身数据引擎与因子分析，不绑定第三方运行环境。

### 6. MVP 范围

#### 必须做

- 实现 101 条公式，稳定命名为 `alpha001`–`alpha101`。
- 通过 `FactorLoader` 和 `/api/factors/worldquant_alpha101` 可发现，并通过内置库回测 API 调用。
- 支持 OHLCV 面板；对 `amount`/`vwap`/市值/行业字段声明明确的优先级和降级口径。
- 补充因子数量、代表性公式、全量计算、无未来数据测试。

#### 可以以后做

- 与同源供应商参考值的逐值回归。
- 前端按 Alpha 编号、依赖字段和分类筛选。
- Alpha191 及其他公式集合。

#### 明确不做

- 不接入 WorldQuant 运行时、账号或 API。
- 不保存、分发或依赖第三方受限因子值。
- 不覆盖现有 `alpha_library.py` 的旧示例因子行为。

### 7. 优先级评估

商业价值 4、用户价值 5、战略价值 4、开发成本 4，评分为 20。纳入 P0，作为现有因子研究闭环的基线能力补齐。

## 2. 验收与证据

### 自动化验证

- `FactorLoader.load("worldquant_alpha101")` 注册 101 个方法因子。
- `alpha041` 与 `alpha101` 通过确定性公式对照。
- 101 个因子在含 OHLCV、amount、市值和行业字段的标准面板上全部返回日期×标的宽表。
- 改变最后一行数据后，Alpha 1、41、58、101 的历史输出保持不变。
- 缺少 `amount` 时，VWAP 相关公式按约定回退到典型价格。
- `/api/factor-libraries` 可发现 `worldquant_alpha101`；`/api/factors/worldquant_alpha101` 可发现 `alpha001`、`alpha101`，且 API 可用库与 `Factor/libraries/index.yaml` 登记一致。

### 执行命令

```bash
conda run --no-capture-output -n svquant python -m pytest ResearchEngine/tests/test_worldquant_alpha101.py -q
```

### 未覆盖项

当前状态为 `implemented`，尚未取得与本项目数据源完全同源的参考因子值，因此不宣称与第三方平台逐值一致。行业分类、复权和成交额口径应在数据底座稳定后补充回归样本。

## 3. 计划与里程碑

| 任务 | 复杂度 | 风险 | 依赖 | 完成条件 |
|---|---:|---|---|---|
| 统一 Alpha 101 算子与字段回退 | 3 | 中 | Panel / Pandas | 算子可复用且不读未来数据 |
| 实现 alpha001–alpha101 | 4 | 中 | 公式来源、OHLCV | 101 个方法可被 FactorLoader 注册 |
| 接入索引与内置 API 注册 | 2 | 低 | FactorLoader / runner | 库名和因子名可发现、可调用；唯一来源为 `Factor/libraries/index.yaml` |
| 确定性与全量执行测试 | 3 | 中 | 上述任务 | 定向测试全部通过 |
| 文档与验收记录 | 2 | 低 | 测试结果 | README、索引、Verification 同步 |

### 排期与里程碑

- M1：公式、字段契约和命名确定。
- M2：101 个因子和加载链路完成。
- M3：公式、形状、无未来数据测试通过并完成交付记录。

### 回滚方案

从 `index.yaml` 移除 `worldquant_alpha101` 条目即可停止新库发现；不删除旧 `alpha_library` 或其他因子文件。
