from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pyarrow.parquet as pq


ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))

from data_ingestion.ifind.sync_current import sync_ifind_to_current  # noqa: E402


def _wide_frame(dates, symbols, fields, value=1.0):
    columns = pd.MultiIndex.from_product((symbols, fields), names=("symbol", "field"))
    frame = pd.DataFrame(
        np.full((len(dates), len(columns)), value, dtype="float64"),
        index=pd.to_datetime(dates),
        columns=columns,
    )
    frame.index.name = "date"
    return frame


def _write_source_tree(source_root: Path):
    symbols = ["000001.SZ", "000002.SZ"]
    dates = ["2026-01-05", "2026-01-06"]
    market_fields = ["open", "high", "low", "close", "volume", "amount", "turnover"]

    _wide_frame(dates, symbols, market_fields).to_parquet(
        source_root / "market_data" / "market_data_hfq.parquet"
    )
    _wide_frame(dates, symbols, ["open", "high", "low", "close"]).to_parquet(
        source_root / "unadjusted_price" / "unadjusted_price.parquet"
    )

    for index in ("000300.SH", "000905.SH"):
        pd.DataFrame(
            {"open": [1.0, 1.1], "high": [1.2, 1.3], "low": [0.9, 1.0], "close": [1.1, 1.2]},
            index=pd.to_datetime(dates),
        ).rename_axis("date").to_parquet(
            source_root / "index" / "index_price" / f"index_price_{index}.parquet"
        )
        pd.DataFrame(
            {symbols[0]: [0.6, 0.5], symbols[1]: [0.4, 0.5]},
            index=pd.to_datetime(dates),
        ).rename_axis("date").to_parquet(
            source_root / "index" / "index_weights" / f"index_weights_{index}.parquet"
        )

    pd.DataFrame({"thscode": symbols, "name": ["甲", "乙"]}).to_parquet(
        source_root / "universe" / "a_share.parquet", index=False
    )
    pd.DataFrame(
        {
            "date": pd.to_datetime(dates),
            "exchange": ["ALL_A", "ALL_A"],
            "is_trade_day": [True, True],
            "source": ["ifind", "ifind"],
            "marketcode": ["212100", "212100"],
        }
    ).to_parquet(source_root / "calendar" / "calendar_all_a.parquet", index=False)

    # 明确确认：date_sequence 存在时也不会被脚本要求或复制。
    pd.DataFrame({"date": dates, "ignored": [1, 2]}).to_parquet(
        source_root / "date_sequence" / "date_sequence.parquet", index=False
    )


def _write_current_tree(current_root: Path):
    symbols = ["000001.SZ", "000002.SZ"]
    dates = ["2026-01-01", "2026-01-05"]
    market_fields = ["open", "high", "low", "close", "volume", "amount", "turnover"]
    _wide_frame(dates, symbols, market_fields, value=0.0).to_parquet(
        current_root / "panels" / "market_data.parquet"
    )
    _wide_frame(dates, symbols, ["open", "high", "low", "close"], value=0.0).to_parquet(
        current_root / "display" / "unadjusted_price.parquet"
    )
    for index in ("000300.SH", "000905.SH"):
        pd.DataFrame(
            {"open": [0.0], "high": [0.0], "low": [0.0], "close": [0.0]},
            index=pd.to_datetime(["2026-01-01"]),
        ).rename_axis("date").to_parquet(
            current_root / "benchmark" / f"index_price_{index}.parquet"
        )
        pd.DataFrame(
            {symbols[0]: [1.0], symbols[1]: [0.0]},
            index=pd.to_datetime(["2026-01-01"]),
        ).rename_axis("date").to_parquet(
            current_root / "benchmark" / f"index_weights_{index}.parquet"
        )
    pd.DataFrame({"thscode": symbols, "name": ["旧甲", "旧乙"]}).to_parquet(
        current_root / "universe" / "a_share.parquet", index=False
    )


def _make_trees(tmp_path):
    source_root = tmp_path / "sources" / "ifind"
    current_root = tmp_path / "current"
    source_root.mkdir(parents=True)
    for directory in (
        "market_data",
        "unadjusted_price",
        "index/index_price",
        "index/index_weights",
        "universe",
        "calendar",
        "date_sequence",
    ):
        (source_root / directory).mkdir(parents=True)
    for directory in ("panels", "display", "benchmark", "universe"):
        (current_root / directory).mkdir(parents=True)
    _write_source_tree(source_root)
    _write_current_tree(current_root)
    return source_root, current_root


def test_sync_copies_mapped_ifind_files_and_ignores_date_sequence(tmp_path):
    source_root, current_root = _make_trees(tmp_path)
    old_market = pd.read_parquet(current_root / "panels" / "market_data.parquet")

    summary = sync_ifind_to_current(
        source_root,
        current_root,
        backup_root=tmp_path / "backup",
    )

    assert summary["message"] == "iFinD 数据已完成校验、备份和替换"
    assert summary["ignored_sources"] == ["date_sequence/**/*.parquet"]
    new_market = pd.read_parquet(current_root / "panels" / "market_data.parquet")
    assert new_market.iloc[0, 0] != old_market.iloc[0, 0]
    assert pd.read_parquet(current_root / "universe" / "a_share.parquet").iloc[0, 1] == "甲"
    assert (current_root / "calendar" / "calendar_all_a.parquet").is_file()
    assert (tmp_path / "backup" / "panels" / "market_data.parquet").is_file()
    assert pq.ParquetFile(current_root / "display" / "unadjusted_price.parquet").metadata.num_rows == 2


def test_sync_dry_run_does_not_replace_current(tmp_path):
    source_root, current_root = _make_trees(tmp_path)
    target = current_root / "panels" / "market_data.parquet"
    before = target.read_bytes()

    summary = sync_ifind_to_current(source_root, current_root, dry_run=True)

    assert summary["dry_run"] is True
    assert target.read_bytes() == before
    assert not (current_root / "data_manifest.yaml").exists()
