"""FastAPI 入口和生命周期契约验收。"""

from fastapi.testclient import TestClient

from app.main import create_app
from app.services.daily_factor_backtest import DailyFactorBacktestCoordinator
from app.services.experiment.manager import ExperimentManager


def test_app_main_owns_single_manager_and_coordinator_lifecycle():
    application = create_app()
    with TestClient(application) as client:
        assert isinstance(application.state.experiment_manager, ExperimentManager)
        assert isinstance(
            application.state.daily_factor_backtest,
            DailyFactorBacktestCoordinator,
        )
        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    assert application.state.experiment_manager.runtime._closed is True


def test_all_application_routes_use_api_prefix():
    application = create_app()
    try:
        paths = list(application.openapi()["paths"])
        assert paths
        assert all(path.startswith("/api") for path in paths)
        assert "/api/v2/health" not in paths
    finally:
        application.state.experiment_manager.shutdown()
