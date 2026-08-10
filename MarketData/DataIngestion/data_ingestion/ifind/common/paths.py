"""iFinD 采集工具的共享路径约定。"""

from pathlib import Path


DEFAULT_OUTPUT_ROOT = Path(__file__).resolve().parents[4] / "sources" / "ifind"
