# -*- coding: utf-8 -*-
from __future__ import annotations

import os

from fastapi import APIRouter

from app.bootstrap import FACTOR_DIR

router = APIRouter(tags=["health"])

PORT = int(os.environ.get("SVQUANT_BACKEND_PORT", "8766"))


@router.get("/api/health")
def health() -> dict:
    return {
        "ok": True,
        "service": "svquant",
        "port": PORT,
        "factor_dir": str(FACTOR_DIR),
        "note": "no market data stored; compute via YGQuant RE",
    }
