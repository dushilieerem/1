"""app.assets 运行时资产验收。"""

from app.assets.strategies import (
    INDEX_PATH as STRATEGY_INDEX_PATH,
    LIBRARY_ROOT as STRATEGY_LIBRARY_ROOT,
)
from app.utils.paths import factor_database_path, factor_tool_path


def test_factor_and_strategy_assets_are_packaged_under_app_namespace():
    assert factor_database_path().is_file()
    assert factor_tool_path().is_file()
    factor_root = factor_database_path().parent
    assert not (factor_root / "index.yaml").exists()
    assert not (factor_root / "libraries").exists()
    assert STRATEGY_INDEX_PATH.is_file()
    assert STRATEGY_LIBRARY_ROOT.is_dir()
