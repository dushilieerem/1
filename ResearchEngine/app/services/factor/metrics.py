"""因子评价辅助函数的兼容导出。

因子评价的实现归 ``MetricEngine`` 服务层所有。本模块保留原有导入路径，
避免已有 API、批量任务和测试调用内部函数时发生不必要的破坏性变更。
"""

from app.services.metric.factor_analysis import (
    _compute_quantile_metrics,
    _daily_ic,
    _finite_series,
    _geometric_annual_return,
    _industry_equity,
    _safe_metric,
)


__all__ = [
    "_compute_quantile_metrics",
    "_daily_ic",
    "_finite_series",
    "_geometric_annual_return",
    "_industry_equity",
    "_safe_metric",
]
