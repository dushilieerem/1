# -*- coding: utf-8 -*-
"""SVQuant API 入口：FastAPI + uvicorn（端口 8766，路径与旧版兼容）。

用法:
  conda activate SVQuant
  cd WebApp/backend
  python api_server.py
  # 或: uvicorn app.main:app --host 0.0.0.0 --port 8766
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
_KH_BACKEND = ROOT.parent / "KnowledgeHub" / "backend"
for _p in (ROOT, _KH_BACKEND):
    s = str(_p)
    if _p.is_dir() and s not in sys.path:
        sys.path.insert(0, s)

HOST = "0.0.0.0"
PORT = 8766


def main() -> None:
    import uvicorn

    print("=" * 48)
    print(f"SVQuant API (FastAPI)  http://{HOST}:{PORT}")
    print(f"  docs → http://127.0.0.1:{PORT}/docs")
    print(f"  factor → {ROOT / 'factor'}")
    print("=" * 48)
    uvicorn.run(
        "app.main:app",
        host=HOST,
        port=PORT,
        log_level="info",
        # 同步路由占满时仍要接住短请求；workers=1 保进程内状态/job
        timeout_keep_alive=75,
    )


if __name__ == "__main__":
    main()
