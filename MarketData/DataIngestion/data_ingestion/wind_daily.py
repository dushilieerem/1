"""从 WindPy 批量下载日频字段并写为 SVQuant 宽表 Parquet。"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Sequence

import pandas as pd


# 标准字段 -> Wind WSD 字段。仅包含已通过本地 WindPy 样本验证的日频字段。
WIND_DAILY_FIELDS = {
    "open": "open",
    "high": "high",
    "low": "low",
    "close": "close",
    "volume": "volume",
    "amount": "amt",
    "turnover": "turn",
    "total_mv": "mkt_cap_ard",
    "float_mv": "mkt_cap_float",
    "total_shares": "total_shares",
    "float_shares": "free_float_shares",
    "pe_ttm": "pe_ttm",
    "pb": "pb_lf",
    "ps_ttm": "ps_ttm",
    "adj_factor": "adjfactor",
}


def _chunks(items: Sequence[str], size: int) -> Iterable[Sequence[str]]:
    for index in range(0, len(items), size):
        yield items[index:index + size]


def _standard_symbol(wind_code: str) -> str:
    return wind_code.split(".", 1)[0]


def _wind_data_to_panel(data, codes: Sequence[str]) -> pd.DataFrame:
    """将单字段、多证券的 WindData 转为 ``日期 × 标的`` 宽表。"""
    if data.ErrorCode:
        message = data.Data[0][0] if data.Data and data.Data[0] else "未知 Wind 错误"
        raise RuntimeError(f"Wind wsd 失败（{data.ErrorCode}）：{message}")
    if len(data.Data) != len(codes):
        raise RuntimeError(
            f"Wind 返回证券数异常：期望 {len(codes)}，实际 {len(data.Data)}"
        )
    frame = pd.DataFrame(data.Data, index=[_standard_symbol(code) for code in codes]).T
    frame.index = pd.to_datetime(data.Times)
    frame.index.name = "datetime"
    return frame


def _require_nonempty_panel(panel: pd.DataFrame, field: str) -> None:
    """拒绝将 Wind 未返回有效值的字段发布为成功产物。"""
    if panel.empty or not panel.notna().any().any():
        raise ValueError(f"Wind 字段 {field} 未返回任何有效值，不能发布")


def download_daily_panels(
    symbols: Sequence[str],
    start: str,
    end: str,
    output_dir: Path,
    fields: Sequence[str] | None = None,
    chunk_size: int = 200,
    overwrite: bool = False,
) -> dict:
    """下载字段并写盘，返回可写入发布清单的元数据。"""
    if not symbols:
        raise ValueError("至少需要一个 Wind 证券代码")
    if chunk_size < 1:
        raise ValueError("chunk_size 必须大于 0")

    requested = list(fields) if fields else list(WIND_DAILY_FIELDS)
    unknown = [field for field in requested if field not in WIND_DAILY_FIELDS]
    if unknown:
        raise KeyError(f"不支持的标准字段: {unknown}；可用: {list(WIND_DAILY_FIELDS)}")

    try:
        from WindPy import w
    except ImportError as exc:  # pragma: no cover - 依赖外部 Wind 安装
        raise RuntimeError("未找到 WindPy，请在已安装 Wind 终端的环境中运行") from exc

    result = w.start()
    if getattr(result, "ErrorCode", 0):
        raise RuntimeError(f"Wind 启动失败：{result}")

    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_assets = []
    try:
        for field in requested:
            target = output_dir / f"{field}.parquet"
            if target.exists() and not overwrite:
                raise FileExistsError(f"输出已存在：{target}；如需替换请传 --overwrite")

            pieces = []
            for code_chunk in _chunks(list(symbols), chunk_size):
                data = w.wsd(
                    ",".join(code_chunk), WIND_DAILY_FIELDS[field],
                    start.replace("-", ""), end.replace("-", ""), "",
                )
                pieces.append(_wind_data_to_panel(data, code_chunk))
            panel = pd.concat(pieces, axis=1).sort_index().sort_index(axis=1)
            _require_nonempty_panel(panel, field)
            panel.to_parquet(target)
            manifest_assets.append({
                "field": field,
                "wind_field": WIND_DAILY_FIELDS[field],
                "path": target.name,
                "sha256": _sha256(target),
                "date_range": [str(panel.index.min().date()), str(panel.index.max().date())],
                "symbol_count": len(panel.columns),
            })
    finally:
        w.stop()

    manifest = {
        "schema_version": 1,
        "source": "WindPy",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "assets": manifest_assets,
    }
    (output_dir / "wind_daily_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    return manifest


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbols-file", type=Path, required=True)
    parser.add_argument("--start", required=True, help="YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="YYYY-MM-DD")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--field", action="append", dest="fields")
    parser.add_argument("--chunk-size", type=int, default=200)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    symbols = [line.strip() for line in args.symbols_file.read_text(encoding="utf-8").splitlines()]
    symbols = [symbol for symbol in symbols if symbol and not symbol.startswith("#")]
    manifest = download_daily_panels(
        symbols, args.start, args.end, args.output, args.fields,
        args.chunk_size, args.overwrite,
    )
    print(f"已发布 {len(manifest['assets'])} 个字段到 {args.output}")


if __name__ == "__main__":
    main()
