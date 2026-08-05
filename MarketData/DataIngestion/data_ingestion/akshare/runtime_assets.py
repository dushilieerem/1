"""为 AkShare 候选版本生成运行时 benchmark 与 metadata 资产。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd
import yaml


INDEX_CONFIG = {
    "000016.SH": ("index_000016", "SSE50_constituents"),
    "000300.SH": ("index_000300", "CSI300_constituents"),
    "000852.SH": ("index_000852", "CSI1000_constituents"),
    "000905.SH": ("index_000905", "CSI500_constituents"),
}


def _build_index_panel(path: Path, code: str) -> pd.DataFrame:
    frame = pd.read_csv(path, usecols=["date", "open", "high", "low", "close", "volume"])
    frame["date"] = pd.to_datetime(frame["date"])
    frame = frame.set_index("date").sort_index()
    prefix = code.split(".", 1)[0]
    return frame.rename(columns={field: f"{prefix}_{field}" for field in frame.columns})


def _build_constituents(history_dir: Path, code: str) -> pd.DataFrame:
    snapshots = []
    for path in sorted(history_dir.glob(f"{code}_*.csv")):
        frame = pd.read_csv(path, usecols=["date", "symbol"])
        snapshots.append(frame)
    if not snapshots:
        raise FileNotFoundError(f"缺少指数成分历史：{code}")
    records = pd.concat(snapshots, ignore_index=True).drop_duplicates(["date", "symbol"])
    records["date"] = pd.to_datetime(records["date"])
    matrix = pd.crosstab(records["date"], records["symbol"]).astype("int8")
    matrix.index.name = "date"
    return matrix.sort_index().sort_index(axis=1)


def _build_stock_info(meta_dir: Path, industry_dir: Path) -> pd.DataFrame:
    listed = pd.read_csv(meta_dir / "stock_basic.csv")
    delisted = pd.read_csv(meta_dir / "delisted_basic.csv")
    stocks = pd.concat([listed, delisted], ignore_index=True).drop_duplicates("symbol", keep="last")
    latest_industry = pd.read_csv(sorted(industry_dir.glob("sw_l1_industry_daily_*.csv"))[-1])
    industry = latest_industry.drop_duplicates("symbol").set_index("symbol")["sw_l1_name"]
    stocks["code"] = stocks["symbol"].str.split(".").str[0]
    stocks["industry"] = stocks["symbol"].map(industry)
    return stocks.set_index("code")[["name", "industry", "symbol", "exchange", "list_date", "delist_date", "status", "source"]].sort_index()


def append_runtime_assets(source_root: Path, release_dir: Path) -> dict:
    """向 candidate 版本补齐基准与证券主数据。"""
    manifest_path = release_dir / "data_manifest.yaml"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"候选版本缺少清单：{manifest_path}")
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("release_status") != "candidate":
        raise ValueError("只能扩展 candidate 状态的数据版本")

    benchmark_dir = release_dir / "benchmark"
    metadata_dir = release_dir / "metadata"
    if benchmark_dir.exists() or metadata_dir.exists():
        raise FileExistsError("候选版本已存在 benchmark 或 metadata，拒绝覆盖")
    benchmark_dir.mkdir()
    metadata_dir.mkdir()

    history_dir = source_root / "02_universe" / "index_constituents" / "history"
    for code, (index_name, constituent_name) in INDEX_CONFIG.items():
        index = _build_index_panel(source_root / "04_index" / "daily" / f"{code}.csv", code)
        index.to_parquet(benchmark_dir / f"{index_name}.parquet")
        constituents = _build_constituents(history_dir, code)
        constituents.to_parquet(benchmark_dir / f"{constituent_name}.parquet")

    stock_info = _build_stock_info(source_root / "01_meta", source_root / "01_meta" / "sw_l1_daily")
    stock_info.to_parquet(metadata_dir / "stock_info.parquet")

    runtime_assets = [str(path.relative_to(release_dir)).replace("\\", "/") for path in sorted(benchmark_dir.glob("*.parquet"))]
    runtime_assets.append("metadata/stock_info.parquet")
    manifest["runtime_assets"] = runtime_assets
    manifest_path.write_text(yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False), encoding="utf-8")
    report = {
        "benchmark_file_count": len(list(benchmark_dir.glob("*.parquet"))),
        "stock_info_rows": len(stock_info),
        "runtime_assets": runtime_assets,
    }
    (metadata_dir / "runtime_assets_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--release", type=Path, required=True)
    args = parser.parse_args()
    report = append_runtime_assets(args.source_root, args.release)
    print(f"已写入 {report['benchmark_file_count']} 个基准文件和 {report['stock_info_rows']} 条证券主数据")


if __name__ == "__main__":
    main()
