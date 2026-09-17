# Phase 2 项目规划：因子预处理 + 三层测试 + 策略研究模块

> 本文档为 SVQuant 下一阶段开发的项目规划。
> 关联：`../../01-需求文档/产品能力地图.md`（产品能力地图）、`../../../ResearchEngine/docs/04-项目管理/阶段汇报/因子研究功能阶段汇报.md`（阶段汇报）

---

## 一、整体目标

### 1.1 本期目标

1. **补齐因子预处理**：去极值 → 行业市值中性化 → Z-score 标准化
2. **建立三层测试体系**：手算验证 → 合理性验证 → 回归测试
3. **启动策略研究模块**：AI 策略生成 + AI 回测解读

### 1.2 依赖关系

```
Week 1: 因子预处理管道
  ├── 去极值（MAD/百分位截尾）
  ├── 行业市值中性化
  ├── Z-score 标准化
  └── 三层测试框架搭建
        ↓
Week 2: AI 策略生成（基础版）
  ├── LLM 接口集成
  ├── 自然语言 → 因子代码
  ├── 自动预处理 → 回测 → 输出结果
  └── 合理性测试验证
        ↓
Week 3: AI 回测解读 + 集成
  ├── AI 回测结果解读
  ├── 策略保存/管理
  ├── 端到端集成测试
  └── 回归测试
```

---

## 二、任务拆解

### Week 1：因子预处理管道 + 三层测试

---

#### Task 1.1：去极值处理

| 属性 | 内容 |
|------|------|
| **复杂度** | ⭐（低） |
| **风险** | 低 |
| **依赖** | 无 |
| **位置** | `QuantCore/quantcore/factor/preprocessor/extreme.py` |

**功能描述**：对因子值进行极值处理，防止极端值拉偏分析结果。

```
支持的算法：
├── MAD（Median Absolute Deviation）截尾
│   ├── 默认阈值：5 倍 MAD
│   └── 可配置：threshold
│
├── 百分位截尾（Winsorization）
│   ├── 默认：1% / 99% 截尾
│   └── 可配置：lower/upper 百分位
│
└── 缺失值：保持 NaN，不参与截尾计算

接口：
    class ExtremeHandler:
        def process(factor_values: pd.DataFrame) -> pd.DataFrame
        def method: str  # "mad" | "winsorize"
        def threshold: float  # MAD 倍数 / 百分位
```

**验收标准**：
- 输入 [1, 2, 3, 100, 5]，MAD 截尾后最大值 < 10
- 输入 [1, 2, 3, 100, 5]，1% 截尾后最大值 = 5
- NaN 值保持不变
- 全零列跳过（不处理）

---

#### Task 1.2：行业市值中性化

| 属性 | 内容 |
|------|------|
| **复杂度** | ⭐⭐⭐（中） |
| **风险** | 中（需要行业分类数据） |
| **依赖** | DataEngine（行业分类数据） |
| **位置** | `QuantCore/quantcore/factor/preprocessor/neutralize.py` |

**功能描述**：去除因子值中的行业和市值效应，让因子在不同行业和市值区间可比。

```
方法：横截面回归取残差
    因子值 = β₁ × 行业哑变量 + β₂ × ln(市值) + ε
    中性化后因子值 = ε（残差）

流程：
    1. 取当日所有股票的行业分类 + 市值数据
    2. 构建行业哑变量矩阵（K 个行业 → K-1 个哑变量，避免多重共线性）
    3. 加入 ln(市值) 作为连续变量
    4. 回归取残差 → 即为中性化后的因子值

支持：
├── 行业分类：申万一级 / 申万二级（可配置）
├── 市值：总市值 / 流通市值（可配置）
├── 缺失处理：缺失行业或市值的股票标记为 NaN
└── 逐日截面回归（每个交易日独立做一次）

接口：
    class NeutralizeHandler:
        def process(factor_values, industry_data, market_cap_data) -> pd.DataFrame
        def industry_level: str  # "sw_l1" | "sw_l2"
        def cap_type: str  # "total_mv" | "float_mv"
```

**验收标准**：
- 中性化后因子值在各行业内的均值为 0
- 中性化后因子值与 ln(市值) 的截面相关性为 0
- 缺失行业/市值的股票因子值 = NaN
- 逐日截面回归，每日残差独立计算

---

#### Task 1.3：Z-score 标准化

| 属性 | 内容 |
|------|------|
| **复杂度** | ⭐（低） |
| **风险** | 低 |
| **依赖** | Task 1.1, 1.2（可选前置） |
| **位置** | `QuantCore/quantcore/factor/preprocessor/standardize.py` |

**功能描述**：将因子值标准化到同一量纲，便于跨因子比较和组合。

```
支持的算法：
├── Z-score：（x - mean） / std
│   ├── 截面 Z-score（每日截面独立标准化） ← 推荐
│   └── 时序 Z-score（每只股票独立标准化）
│
├── Rank 分位数：将因子值转为 0-1 分位数
│
└── Min-Max：（x - min） / （max - min）

参数：
├── method: "zscore_cross" | "zscore_ts" | "rank" | "minmax"
├── cap: Optional[float]  # 标准化后截尾（如 ±3）

接口：
    class StandardizeHandler:
        def process(factor_values: pd.DataFrame) -> pd.DataFrame
        def method: str
```

**验收标准**：
- 截面 Z-score 后，每日因子均值为 0，标准差为 1
- Rank 分位数后，值域在 [0, 1] 之间
- 全零列标准化后仍为全零
- 单列（1 只股票）不报错

---

#### Task 1.4：预处理管道编排

| 属性 | 内容 |
|------|------|
| **复杂度** | ⭐（低） |
| **风险** | 低 |
| **依赖** | Task 1.1, 1.2, 1.3 |
| **位置** | `QuantCore/quantcore/factor/preprocessor/pipeline.py` |

**功能描述**：将去极值、中性化、标准化编排为一个可配置的预处理管道。

```
接口：
    class FactorPreprocessor:
        def __init__(self, steps: List[PreprocessStep]):
            # steps = [ExtremeHandler, NeutralizeHandler, StandardizeHandler]
            pass

        def process(self, factor_values, **kwargs) -> pd.DataFrame:
            # 依次执行每个 step
            for step in self.steps:
                factor_values = step.process(factor_values, **kwargs)
            return factor_values

使用方式：
    preprocessor = FactorPreprocessor([
        ExtremeHandler(method="mad", threshold=5),
        NeutralizeHandler(industry_level="sw_l1", cap_type="total_mv"),
        StandardizeHandler(method="zscore_cross"),
    ])
    clean_factor = preprocessor.process(raw_factor, industry=ind_df, mcap=mcap_df)
```

**验收标准**：
- 支持任意 step 组合和顺序
- 单个 step 失败时给出明确错误信息
- 空管道（0 个 step）返回原数据

---

#### Task 1.5：三层测试框架

| 属性 | 内容 |
|------|------|
| **复杂度** | ⭐⭐（中低） |
| **风险** | 低 |
| **依赖** | Task 1.1-1.4 |
| **位置** | `QuantCore/tests/test_preprocessor.py` + `QuantCore/tests/test_factor_sanity.py` |

**功能描述**：建立三层测试体系，确保因子引擎输出正确。

```
第一层：手算验证（单元测试）
  ├── 去极值：输入 [1,2,3,100,5]，手算 MAD=1.48，5×MAD=7.4
  │   → 验证处理后最大值 = 5（100 被截尾到 5）
  │
  ├── 中性化：构造 2 个行业、6 只股票
  │   → 手算回归残差 → 验证引擎输出一致
  │
  ├── Z-score：输入 [1,2,3]，mean=2, std=0.816
  │   → 验证输出 = [-1.225, 0, 1.225]
  │
  └── IC 计算：构造 3 只股票、5 天数据
      → 手算 Pearson IC → 验证引擎输出一致

第二层：合理性验证（市场常识）
  ├── 动量因子（过去 1 月收益）
  │   → 预期：IC > 0（A 股短期动量存在）
  │   → 验证：IC 为正
  │
  ├── 反转因子（过去 1 月收益的负值）
  │   → 预期：IC > 0（与动量对称）
  │   → 验证：IC 为正
  │
  ├── 低波动因子（过去 20 日波动率倒数）
  │   → 预期：IC > 0（低波动异象在 A 股存在）
  │   → 验证：IC 为正
  │
  └── 分层回测
      → 预期：第 1 层收益 > 第 N 层收益（单调性）
      → 验证：分层单调

第三层：回归测试
  ├── 固定种子，用一组历史数据跑全流程
  ├── 输出结果序列化保存（reference 文件）
  └── 每次修改后，结果必须与 reference 一致
```

**验收标准**：
- 第一层：所有手算测试 100% 通过
- 第二层：经典因子的 IC 正负号符合市场常识
- 第三层：回归测试脚本可用，reference 文件可管理

---

### Week 2：AI 策略生成（基础版）

---

#### Task 2.1：LLM 接口集成

| 属性 | 内容 |
|------|------|
| **复杂度** | ⭐⭐（中低） |
| **风险** | 中（依赖外部 AI API） |
| **依赖** | 无 |
| **位置** | `ResearchEngine/app/services/ai/llm.py` |

**功能描述**：封装 LLM 调用接口，支持将自然语言转换为策略代码。

```
接口：
    class LLMClient:
        def generate_strategy(self, user_request: str) -> StrategyCode:
            """自然语言 → 策略代码"""
            pass

        def explain_result(self, backtest_result, user_question: str) -> str:
            """解读回测结果"""
            pass

设计：
    ├── Prompt 模板管理
    │   ├── system_prompt：定义角色和输出格式
    │   ├── strategy_generation：策略生成模板
    │   └── result_explanation：结果解读模板
    │
    ├── API 接入
    │   ├── 当前：配置 API key + endpoint
    │   └── 可替换：不同 LLM 后端
    │
    └── 安全
        ├── 代码沙箱执行
        └── 合规免责声明
```

**注意**：MVP 阶段先接入通用 LLM API（如 GPT/Claude），后期可考虑微调模型。

---

#### Task 2.2：自然语言 → 因子代码

| 属性 | 内容 |
|------|------|
| **复杂度** | ⭐⭐⭐（中） |
| **风险** | 中（LLM 输出质量和稳定性） |
| **依赖** | Task 2.1, Week 1 全部 |
| **位置** | `ResearchEngine/app/services/ai/strategy_gen.py` |

**功能描述**：用户输入自然语言描述 → AI 生成可执行的因子代码。

```
用户输入：
  "写一个低估值高股息策略，用沪深300成分股"

流程：
  1. LLM 解析需求 → 生成 BaseFactor 子类代码
  2. 语法检查 → 编译
  3. 注册到 FactorEngine
  4. 自动执行预处理（去极值 → 中性化 → 标准化）
  5. 运行回测
  6. 输出结果

输出：
  ├── 策略代码（Python）
  ├── 因子值（清洗后）
  ├── 回测结果（净值 + 指标）
  └── 策略说明（AI 生成）
```

---

#### Task 2.3：AI 策略生成集成实验

| 属性 | 内容 |
|------|------|
| **复杂度** | ⭐⭐（中低） |
| **风险** | 低 |
| **依赖** | Task 2.2, Week 1 |
| **位置** | `ResearchEngine/app/services/ai/experiment.py` |

**功能描述**：将 AI 策略生成接入 Experiment 编排体系。

```
class AIStrategyExperiment:
    def run(user_request: str) -> AIStrategyResult:
        1. LLM 生成策略代码
        2. 编译并注册
        3. 获取数据
        4. 预处理
        5. 回测
        6. 计算指标
        7. 返回结果
```

---

### Week 3：AI 回测解读 + 集成

---

#### Task 3.1：AI 回测解读

| 属性 | 内容 |
|------|------|
| **复杂度** | ⭐⭐（中低） |
| **风险** | 中（LLM 输出质量） |
| **依赖** | Task 2.3 |
| **位置** | `ResearchEngine/app/services/ai/explainer.py` |

**功能描述**：AI 自动解读回测结果，用自然语言说明收益来源、回撤成因和改进方向。

```
输入：
  ├── 净值曲线
  ├── 绩效指标（夏普、回撤、胜率等）
  ├── 归因分析（FF3、行业）
  └── 用户问题（可选）

输出：
  ├── 策略表现总览（收益、风险、稳定性）
  ├── 收益来源分析（归因分解）
  ├── 回撤分析（最大回撤发生时间、原因）
  ├── 改进建议
  └── 合规免责声明
```

---

#### Task 3.2：策略保存/管理

| 属性 | 内容 |
|------|------|
| **复杂度** | ⭐⭐（中低） |
| **风险** | 低 |
| **依赖** | Task 2.3 |
| **位置** | `ResearchEngine/app/services/ai/strategy_store.py` |

**功能描述**：保存 AI 生成的策略，支持查看历史、对比、重新运行。

```
功能：
├── 保存策略代码 + 配置 + 结果
├── 列出历史策略
├── 对比两个策略的绩效
└── 重新运行已有策略
```

---

## 三、排期

```
Week 1（因子预处理 + 测试）
├── Day 1-2:  Task 1.1 去极值处理        ← 2 天
├── Day 3-4:  Task 1.2 行业市值中性化     ← 2 天
├── Day 5:    Task 1.3 Z-score 标准化     ← 1 天
├── Day 5:    Task 1.4 预处理管道编排      ← 0.5 天
└── Day 5-6:  Task 1.5 三层测试框架        ← 1.5 天

Week 2（AI 策略生成）
├── Day 1-2:  Task 2.1 LLM 接口集成       ← 2 天
├── Day 3-5:  Task 2.2 自然语言→因子代码   ← 3 天
└── Day 5-6:  Task 2.3 AI 策略集成实验     ← 1.5 天

Week 3（AI 回测解读 + 收尾）
├── Day 1-3:  Task 3.1 AI 回测解读         ← 3 天
├── Day 4-5:  Task 3.2 策略保存/管理       ← 2 天
├── Day 5:    整体集成测试                  ← 1 天
└── Day 6:    文档 + Demo                  ← 1 天
```

**总工期**：3 周（18 个工作日）

---

## 四、里程碑

| 里程碑 | 时间 | 验收标准 |
|--------|------|---------|
| **M1: 因子预处理可用** | Week 1 末 | 去极值+中性化+标准化可配置运行；三层测试通过 |
| **M2: AI 策略生成 Demo** | Week 2 末 | 输入自然语言 → 生成策略 → 预处理 → 回测 → 输出结果 |
| **M3: AI 全链路完成** | Week 3 末 | 策略生成 + 回测 + AI 解读 + 保存，端到端可用 |

---

## 五、风险

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|---------|
| 行业分类数据不可用 | 低 | Week 1 延期 | 先用模拟行业分类测试逻辑 |
| LLM API 不稳定/延迟高 | 中 | Week 2 延期 | 增加重试机制，缓存常见请求 |
| AI 生成的因子代码质量差 | 中 | Week 2 延期 | 增加代码检查步骤，限制 LLM 输出格式 |
| 三层测试发现引擎 bug | 低 | 修复时间不确定 | 提前安排 buffer day |

---

## 六、开发顺序建议

```
必须按顺序：
  Week 1（因子预处理）→ Week 2（AI 策略生成）

因为 AI 策略生成依赖因子预处理管道。

Week 3（AI 回测解读）可以与 Week 2 并行，
但建议顺序进行以保证质量。
```
