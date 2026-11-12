# -*- coding: utf-8 -*-
"""P1-O07：数据发布核对/回滚脚本。"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "data_release.py"


def _load():
    spec = importlib.util.spec_from_file_location("data_release", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _make_release(tmp_path: Path, *, missing: bool = False) -> Path:
    rel = tmp_path / "release"
    (rel / "market_data").mkdir(parents=True)
    (rel / "market_data" / "a.parquet").write_bytes(b"data")
    manifest = {
        "data_version": "test-1",
        "generated_at": "2026-10-31T00:00:00",
        "assets": [{"path": "market_data/a.parquet", "rows": 1, "symbols": 1}],
    }
    (rel / "data_manifest.yaml").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    (rel / "quality_report.json").write_text("{}", encoding="utf-8")
    if missing:
        (rel / "market_data" / "a.parquet").unlink()
    return rel


def test_check_release_ok(tmp_path) -> None:
    mod = _load()
    rel = _make_release(tmp_path)
    out = mod.check_release(rel)
    assert out["ok"] is True
    assert out["data_version"] == "test-1"


def test_check_release_detects_missing(tmp_path) -> None:
    mod = _load()
    rel = _make_release(tmp_path, missing=True)
    out = mod.check_release(rel)
    assert out["ok"] is False
    assert any("缺少文件" in e for e in out["errors"])


def test_rollback_dry_run_and_apply(tmp_path) -> None:
    mod = _load()
    rel = _make_release(tmp_path)
    target = tmp_path / "marketdata"
    (target / "market_data").mkdir(parents=True)
    (target / "market_data" / "a.parquet").write_bytes(b"old")
    (target / "data_manifest.yaml").write_text("data_version: old", encoding="utf-8")

    dry = mod.rollback(target, rel, apply=False)
    assert dry["dry_run"] is True
    assert (target / "market_data" / "a.parquet").read_bytes() == b"old"

    done = mod.rollback(target, rel, apply=True)
    assert done["dry_run"] is False
    assert (target / "market_data" / "a.parquet").read_bytes() == b"data"
    assert Path(done["backup"]).exists()
