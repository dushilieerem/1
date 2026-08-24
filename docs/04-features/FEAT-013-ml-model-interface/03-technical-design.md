# Technical Design：机器学习模型接入与预测回测

## 设计原则

1. **预测与交易分离**：模型只产出截面预测分数；组合构建、交易规则、成本和回测仍由既有 QuantCore / ResearchEngine 负责。
2. **框架无关、依赖可选**：核心只依赖 Pandas/NumPy。算法组可在模型实现内采用 sklearn、PyTorch 或 TensorFlow，并以 extras 管理其依赖。
3. **时间显式且默认保守**：训练、验证、测试和信号生效时点由研究配置固定；任何不满足样本外规则的结果均拒绝进入分析/回测。
4. **先接入后平台化**：MVP 提供内部受信任 Python 插件接口；模型注册、容器隔离、GPU/队列和在线推理留给独立 Feature。

## 模块边界

```text
ResearchEngine
├── model/
│   ├── base.py              BasePredictiveModel、ModelMetadata
│   ├── dataset.py           ModelDataset、时间切片和标签构造
│   ├── runner.py            ModelExperimentRunner、输出校验
│   ├── validation.py        预测面板与时点校验
│   └── reference.py         可测试的线性参考模型
├── experiment.py            复用/调用模型运行入口
└── result/storage/          保存 manifest、预测与既有回测产物

QuantCore
├── data / factor            只提供已声明的特征面板，不感知模型框架
├── metric                   接收标准预测面板，完成 IC/IR、分层等因子分析
└── backtest/adapter         接收目标权重矩阵，执行既有向量化回测
```

模型接口位于 `ResearchEngine`，因为它负责一次研究实验的训练、预测和产物编排；`QuantCore` 保持通用计算内核，不引入模型生命周期、框架依赖或模型资产管理。

## 公共契约（MVP）

```python
class BasePredictiveModel(ABC):
    metadata: ModelMetadata

    def fit(
        self,
        train: ModelDataset,
        validation: ModelDataset | None = None,
    ) -> "BasePredictiveModel": ...

    def predict(self, test_features: pd.DataFrame) -> pd.Series: ...

@dataclass(frozen=True)
class ModelMetadata:
    model_id: str
    version: str
    feature_names: tuple[str, ...]
    frequency: Literal["1d"]
    score_direction: Literal["higher_is_bullish", "lower_is_bullish"]
    supports_determinism: bool

@dataclass(frozen=True)
class ModelDataset:
    features: pd.DataFrame  # MultiIndex(date, instrument) × feature columns
    labels: pd.Series       # 同一 MultiIndex，仅训练/验证集提供
    as_of_dates: pd.Series  # 每条特征的可得日期
```

为了兼容深度学习框架，运行器在入模型前将宽面板转换为标准长表 `MultiIndex(date, instrument)` 特征集；模型内部可以自行转为 ndarray、DataLoader 或 Tensor。`predict` 的返回 `Series` 必须携带同一 MultiIndex。运行器再将其转换回现有因子/回测使用的宽面板。

## 研究配置与数据流

```yaml
model:
  class_path: my_models.return_model.ReturnPredictor
  params: {lookback: 20, seed: 42}
dataset:
  features: [alpha158_kdj_k, alpha158_roc5]
  label: forward_return_5d
  availability: close
split:
  train: [2018-01-01, 2022-12-30]
  validation: [2023-01-03, 2023-12-29]
  test: [2024-01-02, 2024-12-31]
backtest:
  rebalance: 5D
  portfolio: {method: top_n_equal_weight, n: 50}
```

```text
配置 + 模型类
  → ConfigValidator（类路径、切片、特征/标签、日频约束）
  → DatasetBuilder（DataEngine / FactorEngine → 仅声明字段）
  → ModelExperimentRunner（fit train/validation → predict test）
  → PredictionValidator（索引、覆盖率、非有限值、样本外/时点）
  → PredictionPanel（date × instrument）+ manifest
  ├→ MetricEngine（IC/IR、分层）
  └→ PortfolioBuilder（预测分数 → 目标权重）→ IBacktestEngine
```

日频执行时序：在 `t` 日收盘后，以可得数据生成 `t` 的预测分数；`PortfolioBuilder` 将该分数滞后一交易日生成权重，回测从 `t+1` 开始计收益。标签仅在训练和离线评估中出现，绝不传入测试预测输入。

## 数据与产物影响

- 原始行情、因子值和既有回测结果存储方式不变。
- 每次模型实验新增 `model_manifest.json`、可选 `predictions.parquet` 和模型自己的受控产物目录；默认位于既有 `ResearchEngine/output/experiments/<run_id>/`，不入库。
- 预测面板不成为永久因子资产。后续若要注册、共享和版本化模型/预测，应与 FEAT-004 的资产目录能力协同另建 Feature。

## 兼容与回滚

- 新模型入口为独立 API/配置分支，不修改 `Experiment.run()` 的既有因子参数和 `/api/backtest` 请求契约。
- 原有因子研究继续直接调用 FactorEngine 与回测适配器。
- 回滚时移除模型入口、模型配置和新增产物读取逻辑；历史回测产物和原有运行路径不受影响。

## 测试策略

| 层级 | 覆盖内容 |
|---|---|
| 单元测试 | 时间切片、标签可得性、长宽表转换、模型元信息、预测索引/数值校验 |
| 契约测试 | 参考线性模型以及模拟的 sklearn/PyTorch 风格适配模型均能符合 BasePredictiveModel |
| 集成测试 | 合成面板 → 模型训练/预测 → 因子分析 → NativeEngine 回测的端到端闭环 |
| 负向测试 | 特征缺失、时间重叠、预测跨样本、重复索引、全 NaN、异常抛出和依赖缺失 |
| 回归测试 | 既有 QuantCore / ResearchEngine 全量测试通过；模型功能关闭时无行为变化 |

## 关键风险与缓解

| 风险 | 影响 | 缓解 |
|---|---|---|
| 未来函数 / 标签泄露 | 回测虚高，结论失真 | 时间切片校验、`as_of_dates`、预测仅接收测试特征、信号强制滞后 |
| 深度学习依赖与 CUDA 冲突 | 核心环境不稳定 | 不把框架写入核心依赖；按模型/框架使用可选 extras 与独立环境说明 |
| 训练超时或内存溢出 | 回测服务受阻 | MVP 限定内部受信任模型和资源配置；后续以独立进程/容器、队列与配额扩展 |
| 多框架输出格式不一致 | 集成失败或错误回测 | 强制 MultiIndex 预测契约和集中验证器；提供模板和契约测试 |
| 模型不可复现 | 研究结果难审计 | 固定并记录随机种子、模型版本、配置、数据范围与依赖版本 |

## 架构决策

该 Feature 采用“框架无关预测模型插件 + 平台统一编排与回测”的长期边界，详见 `../../06-decisions/ADR-009-为什么采用框架无关的预测模型接口.md`。
