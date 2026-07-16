"""FastAPI 应用工厂。

``app = create_app()`` 在模块导入时即建好，可直接 ``uvicorn researchengine.api.app:app``。
开发期 CORS 放开（``allow_origins=["*"]``）；公网部署应收紧并加鉴权。
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from researchengine.api.routes import router


def create_app() -> FastAPI:
    app = FastAPI(
        title="SVQuant Research API",
        version="2.0.0",
        description="因子回测 + 策略回测 API。提交代码 -> 回测 -> 返回指标与净值。详见 /docs（Swagger）。",
    )
    # 开发期放开跨域；生产应收紧 allow_origins 到前端域名
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
        allow_credentials=False,
    )
    app.include_router(router)
    return app


app = create_app()
