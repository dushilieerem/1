"""pytest 全局路径配置。

让 ``quantcore`` / ``researchengine`` 两个包在未 ``pip install`` 时也能被导入。
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
for sub in ("QuantCore", "ResearchEngine"):
    p = str(ROOT / sub)
    if p not in sys.path:
        sys.path.insert(0, p)
