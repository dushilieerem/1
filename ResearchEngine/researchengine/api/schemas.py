"""API 请求/响应模型（pydantic v2）。

定义 UI <-> ResearchEngine 之间的数据契约。所有 pandas/numpy 结构在
:mod:`researchengine.api.serializers` 里转成纯 Python 后再塞进这些模型。
"""

from __future__ import annotations

import math
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


# ---------------- 请求 ----------------

class UniverseSnapshotInput(BaseModel):
    """由 WebApp 鉴权、解析后传入的静态证券池快照。"""

    model_config = ConfigDict(extra="forbid")
    asset_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    content_hash: str = Field(min_length=1)
    symbols: list[str] = Field(min_length=1)
    membership_mode: Literal["static"] = "static"

    @model_validator(mode="after")
    def validate_symbols(self):
        if not all(symbol.strip() for symbol in self.symbols):
            raise ValueError("证券池快照含空证券代码")
        if len(self.symbols) != len(set(self.symbols)):
            raise ValueError("证券池快照的证券代码不可重复")
        return self


class BenchmarkSnapshotInput(BaseModel):
    """由 WebApp 鉴权、解析后传入的固定权重组合基准快照。"""

    model_config = ConfigDict(extra="forbid")
    asset_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    content_hash: str = Field(min_length=1)
    weights: dict[str, float] = Field(min_length=1)
    pricing: Literal["close_to_close"] = "close_to_close"

    @model_validator(mode="after")
    def validate_weights(self):
        if not all(symbol.strip() for symbol in self.weights):
            raise ValueError("组合基准快照含空证券代码")
        if not all(math.isfinite(weight) and weight >= 0 for weight in self.weights.values()):
            raise ValueError("组合基准快照的权重必须为有限非负数")
        if not math.isclose(sum(self.weights.values()), 1.0, abs_tol=1e-8):
            raise ValueError("组合基准快照的权重之和必须为 1")
        return self


class ResolvedAssetMeta(BaseModel):
    id: str
    version: str
    content_hash: str
    constituent_count: int
    membership_mode: Optional[Literal["static"]] = None
    pricing: Optional[Literal["close_to_close"]] = None

class FactorBacktestRequest(BaseModel):
    """``POST /api/backtest/factor`` 请求。"""

    model_config = ConfigDict(extra="forbid")

    #: 用户自定义因子的函数源码；未提供时执行内置因子
    factor_code: Optional[str] = Field(None, description="自定义因子 Python 函数源码")
    #: 内置因子库名；自定义因子可传一个或多个库以复用其中的方法
    library_name: Optional[str | list[str]] = Field(None, description="内置因子库名")
    #: 要跑的因子名（FactorLibrary 的方法名，或 BaseFactor 的 ``name``）
    factor_name: str = Field("alpha101", description="因子名")
    #: 组合构建方式：long_only=纯多头 | long_short=多空组合
    portfolio_type: str = Field("long_short", description="long_only | long_short")
    #: 股票池
    universe: str = Field("CSI_ALL", description="CSI_ALL | CSI300 | CSI500 | CSI1000 | CSI2000 | SSE50")
    universe_snapshot: Optional[UniverseSnapshotInput] = None
    #: 自定义回测区间
    start: Optional[str] = None
    end: Optional[str] = None
    #: 是否过滤涨停股
    filter_limit_up: bool = True
    #: 是否过滤停牌股
    filter_suspended: bool = True
    #: 调仓间隔（交易日）
    rebalance_days: int = Field(20, ge=1, description="调仓间隔，单位为交易日")
    #: 因子分层数
    groups: int = Field(5, ge=2, le=10, description="因子分层数，2-10 组")
    #: 对比基准
    benchmark: Literal["CSI300", "CSI500", "CSI1000", "SSE50"] = "CSI300"
    benchmark_snapshot: Optional[BenchmarkSnapshotInput] = None
    #: 手续费率（默认 3‱）
    commission_rate: float = 0.0003
    #: 印花税率（默认 1‰，仅卖出）
    stamp_tax: float = 0.001
    #: 滑点率（默认 1‰）
    slippage_rate: float = 0.001
    #: core 只计算回测和汇总指标；full 额外计算分层、FF3、行业曲线
    analysis_level: Literal["core", "full"] = Field(
        "core", description="core | full"
    )

    @model_validator(mode="after")
    def validate_factor_source(self):
        """内置因子或自定义因子必须有明确来源。"""
        libraries = self.library_names
        if self.factor_code is None and not libraries:
            raise ValueError("未提供 factor_code 时必须提供 library_name")
        if self.factor_code is None and len(libraries) != 1:
            raise ValueError("直接执行内置因子时 library_name 必须是单个库名")
        if len(libraries) != len(set(libraries)):
            raise ValueError("library_name 不可包含重复库名")
        return self

    @property
    def library_names(self) -> list[str]:
        """统一将单个库名和多库列表转换为列表。"""
        if self.library_name is None:
            return []
        return [self.library_name] if isinstance(self.library_name, str) else self.library_name

    @model_validator(mode="after")
    def validate_asset_refs(self):
        if self.universe_snapshot is not None and "universe" in self.model_fields_set:
            raise ValueError("universe 与 universe_snapshot 至多提供一个")
        if self.benchmark_snapshot is not None and "benchmark" in self.model_fields_set:
            raise ValueError("benchmark 与 benchmark_snapshot 至多提供一个")
        return self

class StrategyBacktestRequest(BaseModel):
    """``POST /api/backtest/strategy`` 请求。"""

    model_config = ConfigDict(extra="forbid")

    #: 回测引擎模式；省略时保持既有向量化策略行为。
    engine_mode: Literal["vectorized", "event"] = "vectorized"
    #: 策略 Python 源码（必须实现 generate_signals 方法）
    strategy_code: Optional[str] = Field(None, description="策略 Python 源码")
    #: 已保存策略的索引 ID；与 ``strategy_code`` 二选一
    strategy_id: Optional[str] = Field(None, description="Strategy/libraries/index.yaml 中的策略 ID")
    #: 已保存策略版本；省略时使用索引声明的 current_version
    strategy_version: Optional[str] = Field(None, description="已保存策略的版本号")
    universe: str = "CSI500"
    universe_snapshot: Optional[UniverseSnapshotInput] = None
    start: Optional[str] = None
    end: Optional[str] = None
    #: 对比基准
    benchmark: Literal["CSI300", "CSI500", "CSI1000", "SSE50"] = "CSI300"
    benchmark_snapshot: Optional[BenchmarkSnapshotInput] = None
    commission_rate: float = 0.0
    #: 印花税率（仅卖出时按成交额计提）
    stamp_tax: float = 0.001
    slippage_rate: float = 0.0
    initial_capital: float = 1_000_000.0
    #: 返回持仓权重（前端画持仓图用）
    include_positions: bool = False
    include_rebalance_logs: bool = False
    #: 返回统一执行时间线，供 Web 同时展示向量化调仓与事件策略成交过程。
    include_execution_timeline: bool = False

    @model_validator(mode="after")
    def validate_strategy_source(self):
        if bool(self.strategy_code) == bool(self.strategy_id):
            raise ValueError("strategy_code 与 strategy_id 必须且只能提供一个")
        if self.strategy_version is not None and self.strategy_id is None:
            raise ValueError("strategy_version 只能与 strategy_id 一起使用")
        if self.universe_snapshot is not None and "universe" in self.model_fields_set:
            raise ValueError("universe 与 universe_snapshot 至多提供一个")
        if self.benchmark_snapshot is not None and "benchmark" in self.model_fields_set:
            raise ValueError("benchmark 与 benchmark_snapshot 至多提供一个")
        if self.engine_mode == "event" and (self.universe_snapshot is not None or self.benchmark_snapshot is not None):
            raise ValueError("事件驱动策略暂不支持 universe_snapshot 或 benchmark_snapshot")
        return self


# ---------------- 响应 ----------------


class EquityPoint(BaseModel):
    date: str
    value: float
    drawdown: Optional[float] = None


class DrawdownInfo(BaseModel):
    start: str
    end: Optional[str] = None
    peak: Optional[float] = None
    trough: Optional[float] = None
    recovery: Optional[str] = None
    depth: float
    days: int


class AnnualReturn(BaseModel):
    year: int
    return_value: float


class Holding(BaseModel):
    symbol: str
    name: str
    weight: float


class PositionSnapshot(BaseModel):
    date: str
    holdings: list[Holding]


class RebalanceTrade(BaseModel):
    symbol: str
    name: str
    side: Literal["buy", "sell"]
    previous_weight: float
    target_weight: float
    weight_change: float


class RebalanceLog(BaseModel):
    date: str
    trades: list[RebalanceTrade]


class DateRange(BaseModel):
    start: Optional[str] = None
    end: Optional[str] = None


class LayeredPoint(BaseModel):
    """分层净值点。"""
    date: str
    layer1: Optional[float] = None
    layer2: Optional[float] = None
    layer3: Optional[float] = None
    layer4: Optional[float] = None
    layer5: Optional[float] = None
    layer6: Optional[float] = None
    layer7: Optional[float] = None
    layer8: Optional[float] = None
    layer9: Optional[float] = None
    layer10: Optional[float] = None


class ValuePoint(BaseModel):
    """按日输出的单值序列点。"""
    date: str
    value: float


class ICPoint(ValuePoint):
    """日频截面 IC 及其有效样本数。"""
    sample_size: int


class RollingIRPoint(ValuePoint):
    """滚动 IC 信息比率。"""
    window: int
    sample_size: int


class IndustryEquityCurve(BaseModel):
    """单个行业的等权收益净值曲线。"""
    industry_code: str
    industry_name: str
    points: list[ValuePoint] = []


class IndustryGroupPoint(BaseModel):
    """单日行业内因子分组净值。"""
    date: str
    groups: "dict[str, float]" = {}


class IndustryGroupEquityCurve(BaseModel):
    """单个行业内各因子分组的净值曲线。"""
    industry_code: str
    industry_name: str
    points: list[IndustryGroupPoint] = []


class FactorAnalysis(BaseModel):
    """因子分析结果（因子回测特有）。"""
    ic_mean: Optional[float] = None
    ic_std: Optional[float] = None
    rank_ic_mean: Optional[float] = None
    layered_returns: "dict[str, Optional[float]]" = {}
    cumulative_series: list[LayeredPoint] = []
    definition: "dict[str, object]" = {}
    ic_series: list[ICPoint] = []
    cumulative_ic_series: list[ValuePoint] = []
    rolling_ir_series: list[RollingIRPoint] = []
    industry_equity_curves: list[IndustryEquityCurve] = []
    industry_group_equity_curves: list[IndustryGroupEquityCurve] = []


class FactorBacktestMeta(BaseModel):
    """因子回测元信息。"""
    factor: str
    universe: str
    portfolio_type: str
    rebalance_days: int
    groups: int
    benchmark: str
    filter_limit_up: bool
    filter_suspended: bool
    timings_seconds: "dict[str, float]" = {}
    universe_asset: Optional[ResolvedAssetMeta] = Field(None, exclude_if=lambda value: value is None)
    benchmark_asset: Optional[ResolvedAssetMeta] = Field(None, exclude_if=lambda value: value is None)


class StrategyBacktestMeta(BaseModel):
    """策略回测元信息。"""
    strategy: str
    universe: str
    benchmark: str
    engine_mode: Literal["vectorized", "event"] = "vectorized"
    strategy_id: Optional[str] = None
    strategy_version: Optional[str] = None
    code_hash: Optional[str] = None
    universe_asset: Optional[ResolvedAssetMeta] = Field(None, exclude_if=lambda value: value is None)
    benchmark_asset: Optional[ResolvedAssetMeta] = Field(None, exclude_if=lambda value: value is None)


class StrategyInfo(BaseModel):
    id: str
    name: str
    strategy_type: str
    execution_mode: Literal["vectorized", "event"]
    current_version: str
    entrypoint: str
    tags: list[str] = []


class EventOrderInfo(BaseModel):
    order_id: str
    symbol: str
    quantity: Optional[int] = None
    target_value: Optional[float] = None
    side: Optional[str] = None
    status: str
    reason_code: Optional[str] = None
    submitted_at: Optional[str] = None


class EventFillInfo(BaseModel):
    order_id: str
    symbol: str
    side: str
    quantity: int
    price: float
    timestamp: str
    commission: float
    stamp_tax: float


class EventPositionSnapshot(BaseModel):
    timestamp: str
    cash: float
    total_value: float
    positions: "dict[str, int]" = {}
    sellable_quantities: "dict[str, int]" = {}


class ExecutionTimelineItem(BaseModel):
    """统一的策略执行时间线条目。"""

    timestamp: str
    type: str
    payload: "dict[str, object]" = {}


class StrategyListResponse(BaseModel):
    strategies: list[StrategyInfo]


class FactorBacktestResponse(BaseModel):
    """``POST /api/backtest/factor`` 响应。

    因子代码出错时不抛 500，置 ``error`` 字段返回 200，便于前端统一处理。
    前端根据返回的结构化数据自行渲染图表，不依赖后端预渲染图片。
    """

    # 核心指标
    metrics: "dict[str, Optional[float]]" = {}
    # 净值曲线（含回撤，前端画收益曲线+回撤面积图）
    equity_curve: Optional[list[EquityPoint]] = None
    # 回撤区间明细（前端画回撤标注）
    drawdowns: list[DrawdownInfo] = []
    # 分年收益（前端画柱状图）
    annual_returns: list[AnnualReturn] = []
    # 因子分析（因子回测特有）
    factor_analysis: Optional[FactorAnalysis] = None
    # 起止日期
    date_range: DateRange = DateRange()
    # 最终净值
    final_equity: Optional[float] = None
    # 基准净值曲线
    benchmark_curve: Optional[list[EquityPoint]] = None
    # 策略相对基准的区间超额收益
    excess_return: Optional[float] = None
    # 元信息
    meta: Optional[FactorBacktestMeta] = None
    # 错误信息
    error: Optional[str] = None


class StrategyBacktestResponse(BaseModel):
    """``POST /api/backtest/strategy`` 响应。"""

    # 核心指标
    metrics: "dict[str, Optional[float]]" = {}
    # 净值曲线（含回撤）
    equity_curve: Optional[list[EquityPoint]] = None
    # 回撤区间明细
    drawdowns: list[DrawdownInfo] = []
    # 分年收益
    annual_returns: list[AnnualReturn] = []
    # 起止日期
    date_range: DateRange = DateRange()
    # 最终净值
    final_equity: Optional[float] = None
    # 基准净值曲线
    benchmark_curve: Optional[list[EquityPoint]] = None
    # 策略相对基准的区间超额收益
    excess_return: Optional[float] = None
    # 元信息
    meta: Optional[StrategyBacktestMeta] = None
    # 持仓快照（可选）
    positions: Optional[list[PositionSnapshot]] = None
    rebalance_logs: Optional[list[RebalanceLog]] = None
    execution_timeline: Optional[list[ExecutionTimelineItem]] = None
    # 事件驱动模式的订单、成交和审计轨迹；向量化模式均为 null。
    orders: Optional[list[EventOrderInfo]] = None
    fills: Optional[list[EventFillInfo]] = None
    event_positions: Optional[list[EventPositionSnapshot]] = None
    events: Optional[list["dict[str, object]"]] = None
    assumptions: Optional["dict[str, str]"] = None
    # 错误信息
    error: Optional[str] = None


class FactorInfo(BaseModel):
    name: str
    description: Optional[str] = None


class FactorListResponse(BaseModel):
    factors: list[FactorInfo]


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "2.0.0"
    engines: list[str] = ["native"]


class DailyBar(BaseModel):
    """单个标的的完整日线 OHLC 数据点。"""

    date: str
    open: float
    high: float
    low: float
    close: float


class DailyBarsResponse(BaseModel):
    """``GET /api/market-data/daily/{symbol}`` 响应。"""

    symbol: str
    name: str
    bars: list[DailyBar]
    date_range: DateRange


# ---------------- AI 因子生成 ----------------


class FactorGenerationContext(BaseModel):
    """自然语言因子生成的非敏感研究上下文。"""

    model_config = ConfigDict(extra="forbid")

    universe: Optional[str] = None
    frequency: Literal["1d"] = "1d"
    allowed_library_names: list[str] = []
    preferred_factor_name: Optional[str] = None


class FactorGenerationRequest(BaseModel):
    """``POST /api/ai/factor-generations`` 请求。"""

    model_config = ConfigDict(extra="forbid")

    prompt: str = Field(..., min_length=1, max_length=2000)
    context: FactorGenerationContext = FactorGenerationContext()
    idempotency_key: UUID


class GeneratedFactor(BaseModel):
    """经静态校验的单个因子函数草稿。"""

    factor_name: str
    factor_code: str
    description: str
    used_fields: list[str]
    used_library_methods: list[str] = []
    assumptions: list[str] = []
    warnings: list[str] = []


class FactorGenerationValidation(BaseModel):
    status: Literal["passed", "failed"]
    capability_catalog_version: str
    errors: list[str] = []
    warnings: list[str] = []


class FactorGenerationMeta(BaseModel):
    model_alias: str
    prompt_version: str
    latency_ms: int


class FactorGenerationResponse(BaseModel):
    """AI 因子生成结果；拒绝的结果不会返回可回测代码。"""

    generation_id: str
    status: Literal["ready", "rejected"]
    factor: Optional[GeneratedFactor] = None
    validation: FactorGenerationValidation
    meta: FactorGenerationMeta


# ---------------- AI 向量化策略生成 ----------------


class StrategyGenerationContext(BaseModel):
    """自然语言策略生成的非敏感研究上下文。"""

    model_config = ConfigDict(extra="forbid")

    universe: Optional[str] = None
    frequency: Literal["1d"] = "1d"
    preferred_strategy_name: Optional[str] = None


class StrategyGenerationRequest(BaseModel):
    """``POST /api/ai/strategy-generations`` 请求。"""

    model_config = ConfigDict(extra="forbid")

    prompt: str = Field(..., min_length=1, max_length=2000)
    context: StrategyGenerationContext = StrategyGenerationContext()
    idempotency_key: UUID


class GeneratedStrategy(BaseModel):
    """经静态校验的自由向量化策略草稿。"""

    strategy_name: str
    strategy_code: str
    description: str
    used_fields: list[str]
    assumptions: list[str] = []
    warnings: list[str] = []


class StrategyGenerationValidation(BaseModel):
    status: Literal["passed", "failed"]
    capability_catalog_version: str
    errors: list[str] = []
    warnings: list[str] = []


class StrategyGenerationMeta(BaseModel):
    model_alias: str
    prompt_version: str
    latency_ms: int


class StrategyGenerationResponse(BaseModel):
    """AI 策略生成结果；拒绝结果不会返回可回测代码。"""

    generation_id: str
    status: Literal["ready", "rejected"]
    strategy: Optional[GeneratedStrategy] = None
    validation: StrategyGenerationValidation
    meta: StrategyGenerationMeta


# ---------------- AI 回测解读 ----------------


class BacktestInterpretationRequest(BaseModel):
    """``POST /api/ai/backtest-interpretations`` 请求。"""

    model_config = ConfigDict(extra="forbid")

    backtest_type: Literal["factor", "strategy"]
    result: dict[str, object]
    run_context: dict[str, object] = Field(default_factory=dict)
    focus: Literal["overall", "risk", "robustness", "factor", "execution"] = "overall"
    question: Optional[str] = Field(None, min_length=1, max_length=500)
    idempotency_key: UUID


class BacktestEvidenceItem(BaseModel):
    evidence_id: str
    category: Literal["identity", "coverage", "performance", "risk", "stability", "execution", "factor", "assumption"]
    label: str
    value: Optional[float | int | str | bool] = None
    unit: Optional[str] = None
    status: Literal["observed", "derived", "unknown", "not_applicable"]
    source_paths: list[str] = []
    limitations: list[str] = []


class BacktestEvidencePackage(BaseModel):
    schema_version: str
    result_fingerprint: str
    coverage: Literal["complete", "partial", "insufficient"]
    warnings: list[str] = []
    items: list[BacktestEvidenceItem]


class BacktestFinding(BaseModel):
    finding_id: str
    candidate_id: str
    severity: Literal["info", "warning", "critical"]
    title: str
    explanation: str
    evidence_refs: list[str]
    confidence: Literal["high", "medium", "low"]
    limitations: list[str] = []


class BacktestExperiment(BaseModel):
    experiment_id: str
    priority: int
    hypothesis: str
    primary_variable: str
    expected_direction: list[str]
    tradeoffs: list[str]
    validation_method: str
    pass_criteria: list[str]
    evidence_refs: list[str]
    manual_only: bool = True


class BacktestInterpretation(BaseModel):
    summary: str
    findings: list[BacktestFinding] = []
    experiments: list[BacktestExperiment] = []


class BacktestInterpretationMeta(BaseModel):
    model_alias: str
    prompt_version: str
    diagnostic_catalog_version: str
    latency_ms: int


class BacktestInterpretationResponse(BaseModel):
    interpretation_id: str
    status: Literal["ready", "insufficient", "rejected"]
    mode: Literal["llm_grounded", "deterministic_fallback", "not_applicable"]
    evidence: BacktestEvidencePackage
    interpretation: Optional[BacktestInterpretation] = None
    disclaimer: str
    meta: BacktestInterpretationMeta


class StockInfo(BaseModel):
    """股票代码与名称。"""

    symbol: str
    name: str


class SymbolListResponse(BaseModel):
    """``GET /api/market-data/symbols`` 响应。"""

    symbols: list[StockInfo]
    unmapped_count: int = 0


class IndexInfo(BaseModel):
    """已发布股指的代码与名称。"""

    code: str
    name: str


class IndexListResponse(BaseModel):
    """``GET /api/market-data/indices`` 响应。"""

    indices: list[IndexInfo]


class IndexConstituentsResponse(BaseModel):
    """``GET /api/market-data/indices/{code}/constituents`` 响应。"""

    index: IndexInfo
    constituents: list[StockInfo]
    unmapped_count: int = 0
