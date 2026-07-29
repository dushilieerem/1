from datetime import date
from pathlib import Path
import sys

import pandas as pd


ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))

from data_ingestion.akshare_quality import inspect_bars  # noqa: E402
from data_ingestion.akshare_publish import append_valuation_panels, publish_daily_bars  # noqa: E402
from data_ingestion.akshare_runtime_assets import append_runtime_assets  # noqa: E402
from data_ingestion.panel_quality import inspect_panels  # noqa: E402


def _write_bar(path: Path, rows: list[str], header: str | None = None) -> None:
    path.write_text(
        (header or "symbol,date,open,high,low,close,amount,change_ratio,source,volume,turn")
        + "\n" + "\n".join(rows) + "\n",
        encoding="utf-8",
    )


def test_inspect_bars_reports_stale_schema_and_date_issues(tmp_path):
    _write_bar(
        tmp_path / "000001.SZ.csv",
        [
            "000001.SZ,2026-07-22,1,1,1,1,1,0,akshare,1,1",
            "000001.SZ,2026-07-23,1,1,1,1,1,0,akshare,1,1",
        ],
    )
    _write_bar(
        tmp_path / "000002.SZ.csv",
        [
            "000002.SZ,2026-07-01,1,1,1,1,1,0,akshare,1,1",
            "000002.SZ,2026-06-30,1,1,1,1,1,0,akshare,1,1",
            "000002.SZ,2026-07-01,1,1,1,1,1,0,akshare,1,1",
        ],
    )
    _write_bar(tmp_path / "broken.csv", ["x,2026-07-23,1"], "symbol,date,close")

    report = inspect_bars(tmp_path, as_of=date(2026, 7, 23), max_lag_days=2)

    assert report["file_count"] == 3
    assert report["fresh_file_count"] == 1
    assert report["stale_file_count"] == 1
    assert report["missing_required_columns"] == {"amount,change_ratio,high,low,open,source": 1}
    assert report["missing_optional_column_count"] == {}
    assert any(issue["type"] == "date_integrity" for issue in report["issues"])


def test_inspect_bars_counts_optional_fields_without_rejecting_file(tmp_path):
    _write_bar(
        tmp_path / "000001.SZ.csv",
        ["000001.SZ,2026-07-23,1,1,1,1,1,0,akshare"],
        "symbol,date,open,high,low,close,amount,change_ratio,source",
    )

    report = inspect_bars(tmp_path, as_of=date(2026, 7, 23))

    assert report["fresh_file_count"] == 1
    assert report["missing_optional_column_count"] == {"turn": 1, "volume": 1}


def test_inspect_panels_reports_calendar_mismatch_and_missing_manifest(tmp_path):
    panels = tmp_path / "panels"
    panels.mkdir()
    index = pd.to_datetime(["2026-07-22", "2026-07-23"])
    pd.DataFrame({"000001": [1.0, 2.0]}, index=index).to_parquet(panels / "close.parquet")
    pd.DataFrame({"000001": [1.0]}, index=index[:1]).to_parquet(panels / "volume.parquet")

    report = inspect_panels(panels, metadata_dir=tmp_path / "metadata")

    assert report["field_count"] == 2
    assert report["manifest_files"] == []
    assert report["issue_count"] == 1
    assert report["issues"] == [{"field": "volume", "type": "calendar_mismatch"}]


def test_publish_daily_bars_creates_candidate_version(tmp_path):
    bars = tmp_path / "bars"
    bars.mkdir()
    for symbol in ("000001.SZ", "600519.SH"):
        _write_bar(
            bars / f"{symbol}.csv",
            [
                f"{symbol},2025-01-02,1,2,0.5,1.5,100,0.01,akshare,10,0.1",
                f"{symbol},2025-01-03,2,3,1,2.5,200,0.02,akshare,20,0.2",
            ],
        )

    output = tmp_path / "release"
    manifest = publish_daily_bars(
        bars, output, ["000001.SZ", "600519.SH"],
        start="2025-01-01", end="2025-01-31", data_version="akshare-test",
    )

    assert manifest["release_status"] == "candidate"
    assert manifest["price_adjustment"] == "hfq"
    assert len(manifest["assets"]) == 7
    assert (output / "data_manifest.yaml").is_file()
    assert (output / "quality_report.json").is_file()
    close = pd.read_parquet(output / "panels" / "close.parquet")
    assert list(close.columns) == ["000001", "600519"]


def test_publish_daily_bars_keeps_missing_optional_field_as_nan(tmp_path):
    bars = tmp_path / "bars"
    bars.mkdir()
    _write_bar(
        bars / "000001.SZ.csv",
        ["000001.SZ,2025-01-02,1,2,0.5,1.5,100,0.01,akshare,10,0.1"],
    )
    _write_bar(
        bars / "600519.SH.csv",
        ["600519.SH,2025-01-01,2,3,1,2.5,200,0.02,akshare"],
        "symbol,date,open,high,low,close,amount,change_ratio,source",
    )

    output = tmp_path / "release"
    manifest = publish_daily_bars(
        bars, output, ["000001.SZ", "600519.SH"],
        start="2025-01-01", end="2025-01-31", data_version="akshare-test",
    )

    volume = pd.read_parquet(output / "panels" / "volume.parquet")
    turnover = pd.read_parquet(output / "panels" / "turnover.parquet")
    assert pd.isna(volume.loc[pd.Timestamp("2025-01-01"), "600519"])
    assert pd.isna(turnover.loc[pd.Timestamp("2025-01-01"), "600519"])
    assert manifest["missing_symbols_by_field"] == {
        "turnover": ["600519.SH"], "volume": ["600519.SH"],
    }


def test_append_valuation_panels_extends_candidate_with_aligned_calendar(tmp_path):
    bars = tmp_path / "bars"
    bars.mkdir()
    for symbol in ("000001.SZ", "600519.SH"):
        _write_bar(
            bars / f"{symbol}.csv",
            [
                f"{symbol},2025-01-02,1,2,0.5,1.5,100,0.01,akshare,10,0.1",
                f"{symbol},2025-01-03,2,3,1,2.5,200,0.02,akshare,20,0.2",
            ],
        )
    output = tmp_path / "release"
    publish_daily_bars(bars, output, ["000001.SZ", "600519.SH"], start="2025-01-01", end="2025-01-31", data_version="test")
    valuations = tmp_path / "valuations"
    valuations.mkdir()
    (valuations / "000001.SZ.csv").write_text(
        "date,total_mv,circ_mv,total_shares,float_shares,pe_ttm,pb,ps_ttm,source\n"
        "2025-01-02,10,9,8,7,6,5,4,akshare:value\n",
        encoding="utf-8",
    )

    manifest = append_valuation_panels(valuations, output, ["000001.SZ", "600519.SH"])

    assert len(manifest["assets"]) == 14
    total_mv = pd.read_parquet(output / "panels" / "total_mv.parquet")
    assert list(total_mv.index) == list(pd.to_datetime(["2025-01-02", "2025-01-03"]))
    assert pd.isna(total_mv.loc[pd.Timestamp("2025-01-03"), "000001"])
    assert pd.isna(total_mv.loc[pd.Timestamp("2025-01-02"), "600519"])


def test_append_runtime_assets_creates_compatible_benchmark_and_metadata(tmp_path):
    source = tmp_path / "source"
    (source / "04_index" / "daily").mkdir(parents=True)
    history = source / "02_universe" / "index_constituents" / "history"
    history.mkdir(parents=True)
    meta = source / "01_meta"
    industry = meta / "sw_l1_daily"
    industry.mkdir(parents=True)
    for code in ("000016.SH", "000300.SH", "000852.SH", "000905.SH"):
        pd.DataFrame({"date": ["2025-01-02"], "open": [1], "high": [2], "low": [0.5], "close": [1.5], "volume": [10]}).to_csv(source / "04_index" / "daily" / f"{code}.csv", index=False)
        pd.DataFrame({"date": ["2025-01-02"], "symbol": ["000001.SZ"]}).to_csv(history / f"{code}_2025-01-02.csv", index=False)
    pd.DataFrame({"symbol": ["000001.SZ"], "name": ["平安银行"], "exchange": ["SZ"], "list_date": ["1991-04-03"], "delist_date": [None], "status": ["L"], "source": ["akshare"]}).to_csv(meta / "stock_basic.csv", index=False)
    pd.DataFrame({"symbol": [], "name": [], "exchange": [], "list_date": [], "delist_date": [], "status": [], "source": []}).to_csv(meta / "delisted_basic.csv", index=False)
    pd.DataFrame({"date": ["2025-01-02"], "symbol": ["000001.SZ"], "sw_l1_name": ["银行"]}).to_csv(industry / "sw_l1_industry_daily_2025-01-02.csv", index=False)
    release = tmp_path / "release"
    (release / "panels").mkdir(parents=True)
    pd.DataFrame({"000001": [1]}, index=pd.to_datetime(["2025-01-02"])).to_parquet(release / "panels" / "open.parquet")
    (release / "data_manifest.yaml").write_text("release_status: candidate\nassets: []\n", encoding="utf-8")

    report = append_runtime_assets(source, release)

    assert report["benchmark_file_count"] == 8
    stock_info = pd.read_parquet(release / "metadata" / "stock_info.parquet")
    assert stock_info.loc["000001", "industry"] == "银行"
    index = pd.read_parquet(release / "benchmark" / "index_000300.parquet")
    assert list(index.columns) == ["000300_open", "000300_high", "000300_low", "000300_close", "000300_volume"]
