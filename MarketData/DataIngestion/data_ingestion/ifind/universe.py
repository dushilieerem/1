"""iFinD 当前全 A 股证券池下载与 CSV 落盘。"""

from __future__ import annotations

import argparse
import csv
import json
import re
from datetime import date
from pathlib import Path
from typing import Protocol

from data_ingestion.ifind.client import IFindClient
from data_ingestion.ifind.raw import load_or_fetch_json


UNIVERSE_ID = "all_a_5537"
EXPECTED_EXCHANGE_COUNTS = {"SH": 2310, "SZ": 2894, "BJ": 333}
INDICATORS = (
    "ths_stock_short_name_stock",
    "ths_stock_code_stock",
    "ths_listing_exchange_stock",
    "ths_listed_date_stock",
    "ths_listedsector_stock",
)
UNIVERSE_COLUMNS = (
    "symbol",
    "thscode",
    "code",
    "exchange",
    "listing_exchange",
    "name",
    "list_date",
    "board",
    "security_type",
    "status",
    "universe_id",
    "as_of_date",
    "source",
)


class UniverseClient(Protocol):
    def post(self, path: str, payload: dict) -> dict: ...


def read_codes_from_super_command(path: Path) -> list[str]:
    """只从超级命令文本提取 ``formData.codes``，绝不读取或保存 token。"""
    content = path.read_text(encoding="utf-8")
    match = re.search(r'"codes":"([^"]+)"', content)
    if match is None:
        raise ValueError("超级命令文件中未找到 formData.codes")
    codes = match.group(1).split(",")
    if not all(re.fullmatch(r"\d{6}\.(?:SH|SZ|BJ)", code) for code in codes):
        raise ValueError("超级命令中存在不符合 6 位代码.交易所 格式的证券代码")
    if len(codes) != len(set(codes)):
        raise ValueError("超级命令中存在重复证券代码")
    return codes


def _response_tables(response: dict) -> list[dict]:
    try:
        tables = response["tables"]
    except KeyError as exc:
        raise ValueError("iFinD 基础函数返回缺少 tables") from exc
    if not isinstance(tables, list) or not all(isinstance(table, dict) for table in tables):
        raise ValueError("iFinD 基础函数返回的 tables 不是对象列表")
    return tables


def _table_column(table: dict, name: str) -> list[object]:
    for key, value in table.items():
        if key.lower() == name.lower():
            if isinstance(value, list):
                if len(value) == 1 and isinstance(value[0], list):
                    return value[0]
                if len(value) == 1 and isinstance(value[0], str) and "," in value[0]:
                    return value[0].split(",")
                return value
            raise ValueError(f"iFinD 字段 {name} 不是数组")
    raise ValueError(f"iFinD 基础函数返回缺少字段：{name}")


def _exchange_from_thscode(thscode: str) -> str:
    try:
        return thscode.rsplit(".", 1)[1]
    except IndexError as exc:
        raise ValueError(f"无效 thscode：{thscode}") from exc


def normalize_universe(response: dict, as_of_date: str) -> list[dict[str, str]]:
    """将 iFinD 按证券分组的基础函数结果标准化为证券主数据行。"""
    rows: list[dict[str, str]] = []
    for item in _response_tables(response):
        thscode = item.get("thscode")
        table = item.get("table")
        if not isinstance(thscode, str) or not isinstance(table, dict):
            raise ValueError("iFinD 基础函数单证券结果缺少 thscode 或 table")
        columns = {indicator: _table_column(table, indicator) for indicator in INDICATORS}
        if any(len(values) != 1 for values in columns.values()):
            lengths = {name: len(values) for name, values in columns.items()}
            raise ValueError(f"iFinD 单证券基础字段不是单值：{thscode}，{lengths}")
        exchange = _exchange_from_thscode(thscode)
        rows.append({
            "symbol": thscode,
            "thscode": thscode,
            "code": str(columns["ths_stock_code_stock"][0]),
            "exchange": exchange,
            "listing_exchange": str(columns["ths_listing_exchange_stock"][0]),
            "name": str(columns["ths_stock_short_name_stock"][0]),
            "list_date": str(columns["ths_listed_date_stock"][0]),
            "board": str(columns["ths_listedsector_stock"][0]),
            "security_type": "A_SHARE",
            "status": "listed",
            "universe_id": UNIVERSE_ID,
            "as_of_date": as_of_date,
            "source": "ifind",
        })
    return rows


def validate_universe(rows: list[dict[str, str]], requested_codes: list[str]) -> None:
    actual_codes = [row["thscode"] for row in rows]
    if len(actual_codes) != len(set(actual_codes)):
        raise ValueError("iFinD 返回存在重复证券代码")
    if set(actual_codes) != set(requested_codes):
        raise ValueError("iFinD 返回证券代码与请求证券池不一致")
    exchange_counts = {exchange: sum(row["exchange"] == exchange for row in rows) for exchange in EXPECTED_EXCHANGE_COUNTS}
    if exchange_counts != EXPECTED_EXCHANGE_COUNTS:
        raise ValueError(f"全 A 证券池交易所数量不符：{exchange_counts}")


def write_universe_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=UNIVERSE_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def download_universe(
    client: UniverseClient,
    super_command_file: Path,
    output_path: Path,
    raw_response_path: Path,
    as_of_date: str,
) -> int:
    codes = read_codes_from_super_command(super_command_file)
    response = load_or_fetch_json(
        client,
        raw_response_path,
        "/api/v1/basic_data_service",
        {
            "codes": ",".join(codes),
            "indipara": [{"indicator": indicator, "indiparams": []} for indicator in INDICATORS],
        },
    )
    rows = normalize_universe(response, as_of_date)
    validate_universe(rows, codes)
    write_universe_csv(output_path, rows)
    return len(rows)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--super-command-file", type=Path, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parents[3] / "sources" / "ifind" / "universe" / "a_share_5537.csv",
    )
    parser.add_argument("--as-of", default=date.today().isoformat())
    parser.add_argument("--raw-response", type=Path, help="原始 iFinD JSON 响应；已存在时只重放解析")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    raw_response = args.raw_response or (
        args.output.parent / "raw" / f"{UNIVERSE_ID}_{args.as_of.replace('-', '')}.json"
    )
    row_count = download_universe(
        IFindClient.from_environment(), args.super_command_file, args.output, raw_response, args.as_of
    )
    print(json.dumps({
        "universe_id": UNIVERSE_ID,
        "row_count": row_count,
        "output": str(args.output),
        "raw_response": str(raw_response),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
