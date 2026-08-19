"""FastAPI 应用工厂。

``app = create_app()`` 在模块导入时即建好，可直接 ``uvicorn researchengine.api.app:app``。
开发期 CORS 放开（``allow_origins=["*"]``）；公网部署应收紧并加鉴权。
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from researchengine.api.routes import router
from researchengine.manager import ExperimentManager


@asynccontextmanager
async def lifespan(app: FastAPI):
    """由 FastAPI 负责生命周期，由 ExperimentManager 负责计算资源。"""
    manager: ExperimentManager = app.state.experiment_manager
    manager.start()
    try:
        yield
    finally:
        manager.shutdown()


def create_app() -> FastAPI:
    app = FastAPI(
        title="SVQuant Research API",
        version="2.0.0",
        description="因子/策略回测与已发布市场数据查询 API。详见 /docs（Swagger）。",
        lifespan=lifespan,
    )
    # Manager 是每个 ResearchEngine 进程一个的计算资源所有者；路由只提交任务。
    app.state.experiment_manager = ExperimentManager()
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
