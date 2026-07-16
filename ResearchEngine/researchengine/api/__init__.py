"""ResearchEngine HTTP API 层（FastAPI）。

把 ResearchEngine 的 SDK 能力（因子加载 + 回测 + 指标）暴露为 HTTP，供 SVQuant 界面调用。
是引擎之上的薄适配层，不新增回测逻辑。详见 ``docs/04-features/FEAT-002-research-engine/06-research-api.md``。

运行::

    uvicorn researchengine.api.app:app --reload
    # 或 python -m researchengine.api.server
    # Swagger UI: http://localhost:8000/docs
"""

from researchengine.api.app import app, create_app  # noqa: F401

__all__ = ["app", "create_app"]
