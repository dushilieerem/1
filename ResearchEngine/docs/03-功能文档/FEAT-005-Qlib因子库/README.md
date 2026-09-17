# FEAT-005：Qlib Alpha 特征库

- 状态：已完成
- 所属 Initiative：INIT-001 投研核心
- 所属能力：因子研究
- 代码位置：`Factor/libraries/qlib_alpha.py`

## 1. 价值与范围

### 功能名称

Qlib 标准 Alpha158 / Alpha360 特征库。

### 背景

量化研究与机器学习模型常以 Qlib 的 Alpha158、Alpha360 作为可复现实验基线。SVQuant 现有因子库缺少这两组完整定义，研究员需要自行转换公式，成本高且易出现口径偏差。

### 用户与商业价值

量化开发者可直接使用业界常见特征集合进行研究、建模与结果对比，降低从 Qlib 迁移的门槛，提升平台基础研究能力的可验证性。

### 竞品与差异化

Qlib 提供特征定义和运行框架；SVQuant 将其复刻为独立的 Pandas 因子库，能直接使用现有数据引擎、因子分析和回测，无需绑定 Qlib 数据格式或运行时。

### MVP 范围

- 必须做：完整提供 Alpha158（158 个）与 Alpha360（360 个）特征；可由因子加载器和 API 枚举；含最小计算测试。
- 可以以后做：模型训练管道、Qlib 数据格式导入、与 Qlib 的逐值全量回归测试。
- 明确不做：引入 Qlib 作为运行时依赖、改变现有回测逻辑。

### 优先级评估

商业价值 4、用户价值 5、战略价值 4、开发成本 3，评分为 26.7，纳入 P1 因子库扩展。

## 2. 业务规则与场景

### 用户故事

作为量化开发者，我希望在 SVQuant 中看到并计算 Qlib Alpha158 / Alpha360 特征，以便复用公开研究基线。

### 业务规则与边界

- 特征以 `qlib_alpha158_`、`qlib_alpha360_` 为前缀，尾部为 Qlib 原始特征名的小写形式。
- Alpha158 包含 9 个 K 线特征、4 个当日价格特征和 29 类滚动特征 × 5 个窗口，共 158 个。
- Alpha360 包含 close/open/high/low/vwap/volume 各 60 个滞后特征，共 360 个。
- VWAP 优先读取 `vwap` 字段；不存在时使用 `amount / volume` 推导。
- 仍遵守 Qlib 的历史窗口定义；不使用未来数据。

### 非功能要求与验收

- 不新增 Qlib 依赖。
- 因子加载器可注册 518 个特征；`GET /api/factor-libraries` 可枚举因子库，`GET /api/factors/alpha_features` 可枚举 Alpha158 / Alpha360 特征。
- 代表性 K 线、滞后价格、VWAP 和滚动特征须通过确定性公式测试。

## 3. 方案设计

### 模块边界

```text
Factor/libraries/qlib_alpha.py
  └─ QlibAlphaLibrary（FactorLibrary）
       ├─ Alpha158：158 个方法因子
       └─ Alpha360：360 个方法因子
ResearchEngine FactorLoader / GET /api/factor-libraries / GET /api/factors/{library_name}
  └─ 加载并枚举上述因子
```

实现仅依赖 Pandas/NumPy，复刻 Microsoft Qlib `Alpha158DL`、`Alpha360DL` 的公式；不引入 Qlib 数据处理器、标签或模型组件。

### 数据与兼容

依赖 `open`、`high`、`low`、`close`、`volume` 和 `vwap` 或可推导它的 `amount`。缺少以上字段时由现有 Panel 的字段访问机制明确报错，不静默填充。新库不修改既有因子名称或行为；删除 `qlib_alpha.py` 并移除索引项即可回滚。

### 风险与缓解

部分滚动回归特征计算成本高。它们按需计算且沿用现有懒加载、单因子执行模型；后续如出现性能瓶颈，再针对热点因子优化，不预先引入额外抽象。

## 4. 验收与证据

- 已验证：`QlibAlphaLibrary` 注册 518 个方法因子（Alpha158 158 个、Alpha360 360 个）。
- 已验证：`KMID`、`CLOSE5`、`ROC5` 与 VWAP 回退公式的确定性测试。
- 已验证：不需要安装 Qlib；测试仅使用项目既有的 Pandas/NumPy 依赖。
- 回归：执行 `pytest ResearchEngine/tests/test_qlib_alpha.py -q`。

## 5. 计划与里程碑

| 任务 | 复杂度 | 风险 | 依赖 | 完成条件 |
|------|--------|------|------|----------|
| 复刻 Alpha360 | 2 | 低 | Panel OHLCV | 360 个滞后归一化特征可加载 |
| 复刻 Alpha158 | 4 | 中 | Panel OHLCV/VWAP | 158 个 K 线与滚动特征可加载 |
| 接入目录/API | 2 | 低 | FactorLoader | 索引、加载器和 API 可发现 |
| 验证 | 3 | 中 | 上述任务 | 数量、代表公式和回归测试通过 |

里程碑：M1 公式复刻完成；M2 自动化验证通过；M3 可供研究员从 API 发现与使用。
