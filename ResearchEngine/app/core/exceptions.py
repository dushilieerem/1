"""应用层异常；不依赖 FastAPI。"""

from __future__ import annotations


class MarketDataError(RuntimeError):
    """行情查询业务错误，由 API 层映射为 HTTP 响应。"""

    status_code = 503

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class MarketDataValidationError(MarketDataError):
    status_code = 422


class MarketDataNotFoundError(MarketDataError):
    status_code = 404


__all__ = [
    "MarketDataError",
    "MarketDataValidationError",
    "MarketDataNotFoundError",
]
