"""app.assets 运行时资产验收。"""

from app.assets.factors import INDEX_PATH as FACTOR_INDEX_PATH, LIBRARY_ROOT as FACTOR_LIBRARY_ROOT
from app.assets.strategies import INDEX_PATH as STRATEGY_INDEX_PATH, LIBRARY_ROOT as STRATEGY_LIBRARY_ROOT


def test_factor_and_strategy_assets_are_packaged_under_app_namespace():
    assert FACTOR_INDEX_PATH.is_file()
    assert FACTOR_LIBRARY_ROOT.is_dir()
    assert STRATEGY_INDEX_PATH.is_file()
    assert STRATEGY_LIBRARY_ROOT.is_dir()
