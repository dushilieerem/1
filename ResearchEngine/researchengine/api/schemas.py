"""API 请求/响应模型（pydantic v2）。

定义 UI <-> ResearchEngine 之间的数据契约。所有 pandas/numpy 结构在
:mod:`researchengine.api.serializers` 里转成纯 Python 后再塞进这些模型。
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------- 请求 ----------------

class FactorBacktestRequest(BaseModel):
    """``POST /api/backtest/factor`` 请求。"""

    model_config = ConfigDict(extra="forbid")

    #: Python 源码：定义 ``FactorLibrary`` 子类（方法即因子）或 ``BaseFactor`` 子类
    factor_code: str = Field(..., description="因子 Python 源码")
    #: 要跑的因子名（FactorLibrary 的方法名，或 BaseFactor 的 ``name``）
    factor_name: str = Field("alpha101", description="因子名")
    #: 组合构建方式：long_only=纯多头 | long_short=多空组合
    portfolio_type: str = Field("long_short", description="long_only | long_short")
    #: 股票池
    universe: str = Field("CSI_ALL", description="CSI_ALL | CSI300 | CSI500 | CSI1000 | CSI2000 | SSE50")
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
class StrategyBacktestRequest(BaseModel):
    """``POST /api/backtest/strategy`` 请求。"""

    model_config = ConfigDict(extra="forbid")

    #: 策略 Python 源码（必须实现 generate_signals 方法）
    strategy_code: str = Field(..., description="策略 Python 源码")
    #: 策略参数（透传给策略 __init__ 的 params）
    strategy_params: "dict[str, object]" = Field(default_factory=dict)
    #: 因子代码（可选，策略可能需要因子值作为输入）
    factor_code: Optional[str] = None
    #: 因子名（可选，与 factor_code 搭配使用）
    factor_name: Optional[str] = None
    universe: str = "CSI500"
    start: Optional[str] = None
    end: Optional[str] = None
    #: 数据目录；缺省走 env ``SVQUANT_DATA_DIR`` 或 ``<repo>/MarketData``
    data_dir: Optional[str] = None
    #: 回测后端：``native`` | ``vectorbt``
    backtest_engine: Literal["native", "vectorbt"] = Field(
        "native", description="native | vectorbt"
    )
    commission_rate: float = 0.0
    slippage_rate: float = 0.0
    initial_capital: float = 1_000_000.0
    #: 返回净值点序列（前端画图用）
    include_equity: bool = True
    #: 返回持仓权重（前端画持仓图用）
    include_positions: bool = False


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
    weight: float


class PositionSnapshot(BaseModel):
    date: str
    holdings: list[Holding]


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


class StrategyBacktestMeta(BaseModel):
    """策略回测元信息。"""
    strategy: str
    universe: str
    backtest_engine: str


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
    # 元信息
    meta: Optional[StrategyBacktestMeta] = None
    # 持仓快照（可选）
    positions: Optional[list[PositionSnapshot]] = None
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
    engines: list[str] = ["native", "vectorbt"]
