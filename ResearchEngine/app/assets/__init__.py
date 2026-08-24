"""随应用发布的运行时因子与策略资产。"""

from pathlib import Path


ASSET_ROOT = Path(__file__).resolve().parent
FACTOR_ASSET_ROOT = ASSET_ROOT / "factors"
STRATEGY_ASSET_ROOT = ASSET_ROOT / "strategies"

__all__ = ["ASSET_ROOT", "FACTOR_ASSET_ROOT", "STRATEGY_ASSET_ROOT"]
