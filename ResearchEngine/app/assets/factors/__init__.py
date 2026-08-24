"""因子运行时资产。"""

from pathlib import Path


ASSET_ROOT = Path(__file__).resolve().parent
LIBRARY_ROOT = ASSET_ROOT / "libraries"
INDEX_PATH = ASSET_ROOT / "index.yaml"

__all__ = ["ASSET_ROOT", "LIBRARY_ROOT", "INDEX_PATH"]
