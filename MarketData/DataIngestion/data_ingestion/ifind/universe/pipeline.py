"""iFinD 全 A 证券主表下载与在市/已摘牌/退市整理快照合并。"""

from __future__ import annotations

import argparse
import csv
import json
import re
from datetime import date, datetime
from pathlib import Path
from typing import Protocol

from data_ingestion.ifind.common.client import IFindClient, IFindRequestError
from data_ingestion.ifind.common.paths import DEFAULT_OUTPUT_ROOT
from data_ingestion.ifind.common.raw import load_or_fetch_json, save_json_response


UNIVERSE_ID = "all_a"
LEGACY_UNIVERSE_ID = "all_a_5537"
# 旧版静态超级命令仍保留这些校验常量，仅供兼容模式使用；新流程不按数量截断历史证券。
EXPECTED_EXCHANGE_COUNTS = {"SH": 2310, "SZ": 2894, "BJ": 333}
INDICATORS = (
    "ths_stock_short_name_stock",
    "ths_stock_code_stock",
    "ths_listing_exchange_stock",
    "ths_listed_date_stock",
    "ths_listedsector_stock",
)
UNIVERSE_COLUMNS = ("thscode", "name")
LEGACY_UNIVERSE_COLUMNS = (
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


# p03291“板块成份”只在每次更新时查询三个当前快照，不按历史交易日重复回放。
DATA_POOL_REPORT_NAME = "p03291"
LISTED_BLOCK_NAME = "001005010"
DELISTED_BLOCK_NAME = "001005334011"
DELISTING_BLOCK_NAME = "001005334025"
# 用完整语义保留一个可读别名，实际请求仍使用同一个 iFinD 板块编码。
DELISTING_ARRANGEMENT_BLOCK_NAME = DELISTING_BLOCK_NAME
DATA_POOL_CONTRACT_TYPE = "allcontract"
DATA_POOL_FIELDS = ("p03291_f002", "p03291_f003")
SNAPSHOT_DIRECTORIES = {
    "listed": "LISTED",
    "delisted": "DELISTED",
    "delisting": "DELISTING",
}
SNAPSHOT_STATUSES = tuple(SNAPSHOT_DIRECTORIES)
UNIVERSE_FILENAME = "a_share.csv"
LEGACY_UNIVERSE_FILENAME = "a_share_5537.csv"


def _normalize_query_date(value: str) -> str:
    """将日期统一为 ISO 格式；iFinD 请求体再转换为 YYYYMMDD。"""
    for pattern in ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"):
        try:
            return datetime.strptime(value, pattern).date().isoformat()
        except ValueError:
            continue
    raise ValueError(f"日期格式无效：{value}，应为 YYYY-MM-DD")


def data_pool_payload(
    as_of_date: str,
    blockname: str = LISTED_BLOCK_NAME,
    contract_type: str = DATA_POOL_CONTRACT_TYPE,
) -> dict:
    """构造 iFinD p03291 板块成份请求。"""
    normalized_date = _normalize_query_date(as_of_date)
    if not blockname:
        raise ValueError("板块名称不能为空")
    if not contract_type:
        raise ValueError("合约类型不能为空")
    return {
        "reportname": DATA_POOL_REPORT_NAME,
        "functionpara": {
            "date": normalized_date.replace("-", ""),
            "blockname": blockname,
            # 超级命令里的“合约类型”在 HTTP 协议中对应 iv_type。
            "iv_type": contract_type,
        },
        "outputpara": ",".join(DATA_POOL_FIELDS),
    }


def universe_payload(
    as_of_date: str,
    blockname: str = LISTED_BLOCK_NAME,
    contract_type: str = DATA_POOL_CONTRACT_TYPE,
) -> dict:
    """兼容证券池语义的 p03291 请求构造别名。"""
    return data_pool_payload(as_of_date, blockname, contract_type)


def snapshot_raw_path(output_root: Path, as_of_date: str, status: str) -> Path:
    """返回全 A 三类状态快照的原始 JSON 路径。"""
    if status not in SNAPSHOT_DIRECTORIES:
        raise ValueError(f"不支持的证券状态：{status}")
    normalized_date = _normalize_query_date(as_of_date)
    directory = SNAPSHOT_DIRECTORIES[status]
    return output_root / "universe" / "raw" / directory / f"{normalized_date}.json"


def listed_raw_path(output_root: Path, as_of_date: str) -> Path:
    return snapshot_raw_path(output_root, as_of_date, "listed")


def delisted_raw_path(output_root: Path, as_of_date: str) -> Path:
    return snapshot_raw_path(output_root, as_of_date, "delisted")


def delisting_raw_path(output_root: Path, as_of_date: str) -> Path:
    return snapshot_raw_path(output_root, as_of_date, "delisting")


def delisting_arrangement_raw_path(output_root: Path, as_of_date: str) -> Path:
    """退市整理快照路径的语义别名。"""
    return delisting_raw_path(output_root, as_of_date)


def default_universe_path(output_root: Path) -> Path:
    return output_root / "universe" / UNIVERSE_FILENAME


def existing_universe_path(output_root: Path) -> Path:
    """读取时优先使用新文件名；仅在不存在时回退旧版数量文件名。"""
    current = default_universe_path(output_root)
    if current.is_file():
        return current
    legacy = output_root / "universe" / LEGACY_UNIVERSE_FILENAME
    return legacy if legacy.is_file() else current


def read_universe_columns(path: Path) -> list[str]:
    """读取扁平证券主表中的完整代码列。"""
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames or "thscode" not in reader.fieldnames:
            raise ValueError(f"证券池缺少 thscode 列：{path}")
        symbols = [str(row.get("thscode", "")).strip() for row in reader]
    symbols = [symbol for symbol in symbols if symbol]
    if not symbols or len(symbols) != len(set(symbols)):
        raise ValueError(f"证券池缺失或存在重复代码：{path}")
    return symbols


def read_codes_from_super_command(path: Path) -> list[str]:
    """只从旧版超级命令文本提取 ``formData.codes``，绝不读取或保存 token。"""
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


def _as_data_pool_values(value: object, field: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"iFinD 板块成份字段 {field} 不是数组")
    if len(value) == 1 and isinstance(value[0], list):
        return value[0]
    if len(value) == 1 and isinstance(value[0], str) and "," in value[0]:
        return value[0].split(",")
    return value


def _data_pool_table_rows(table: dict) -> list[dict[str, object]]:
    """兼容 data_pool 常见的字段数组与 columns/data 两种返回形状。"""
    field_values: dict[str, list[object]] = {}
    for field in DATA_POOL_FIELDS:
        for key, value in table.items():
            if str(key).lower() == field.lower():
                field_values[field] = _as_data_pool_values(value, field)
                break
    if len(field_values) == len(DATA_POOL_FIELDS):
        lengths = {len(values) for values in field_values.values()}
        if len(lengths) != 1:
            raise ValueError("iFinD 板块成份返回字段长度不一致")
        length = lengths.pop()
        return [
            {field: field_values[field][number] for field in DATA_POOL_FIELDS}
            for number in range(length)
        ]

    columns, rows = table.get("columns"), table.get("data")
    if isinstance(columns, list) and isinstance(rows, list):
        if any(not isinstance(row, list) for row in rows):
            raise ValueError("iFinD 板块成份返回 data 行格式无效")
        try:
            mapped = [dict(zip(columns, row, strict=True)) for row in rows]
        except ValueError as exc:
            raise ValueError("iFinD 板块成份返回 columns 与 data 长度不一致") from exc
        return mapped
    raise ValueError("iFinD 板块成份返回格式无法识别；请保留原始 JSON 并核对接口返回")


def _data_pool_rows(response: dict) -> list[dict[str, object]]:
    if (
        response.get("errorcode") == -4001
        and str(response.get("errmsg", "")).strip().lower().rstrip(".") == "no data"
    ):
        return []
    candidate = response.get("data", response)
    tables = candidate.get("tables") if isinstance(candidate, dict) else None
    if isinstance(tables, list):
        rows: list[dict[str, object]] = []
        for item in tables:
            if not isinstance(item, dict):
                continue
            table = item.get("table", item)
            if isinstance(table, dict):
                rows.extend(_data_pool_table_rows(table))
        return rows
    if isinstance(candidate, dict):
        nested_table = candidate.get("table")
        if isinstance(nested_table, dict):
            return _data_pool_table_rows(nested_table)
        return _data_pool_table_rows(candidate)
    if isinstance(candidate, list):
        rows = []
        for item in candidate:
            if isinstance(item, dict):
                rows.extend(_data_pool_table_rows(item))
        return rows
    raise ValueError("iFinD 板块成份返回缺少数据表")


def _row_value(row: dict[str, object], field: str) -> object:
    for key, value in row.items():
        if str(key).lower() == field.lower():
            return value
    raise KeyError(field)


def _exchange_from_thscode(thscode: str) -> str:
    try:
        exchange = thscode.rsplit(".", 1)[1]
    except IndexError as exc:
        raise ValueError(f"无效 thscode：{thscode}") from exc
    if exchange not in {"SH", "SZ", "BJ"}:
        raise ValueError(f"无效交易所：{thscode}")
    return exchange


def normalize_data_pool_response(
    response: dict,
    as_of_date: str,
    status: str,
    blockname: str,
) -> list[dict[str, str]]:
    """将 p03291 快照转换为可合并的证券主表行。"""
    if status not in SNAPSHOT_STATUSES:
        raise ValueError(f"不支持的证券状态：{status}")
    normalized_date = _normalize_query_date(as_of_date)
    rows: list[dict[str, str]] = []
    for row in _data_pool_rows(response):
        try:
            thscode = str(_row_value(row, "p03291_f002")).strip()
            name = str(_row_value(row, "p03291_f003")).strip()
        except KeyError as exc:
            raise ValueError(f"iFinD 板块成份返回缺少字段：{exc.args[0]}") from exc
        if not re.fullmatch(r"\d{6}\.(?:SH|SZ|BJ)", thscode):
            raise ValueError(f"iFinD 板块成份返回无效证券代码：{thscode}")
        rows.append({
            "thscode": thscode,
            "name": name,
        })
    if not rows and status != "delisting":
        raise ValueError(f"iFinD {status} 板块成份在 {normalized_date} 返回空列表")
    codes = [row["thscode"] for row in rows]
    if len(codes) != len(set(codes)):
        raise ValueError(f"iFinD {status} 板块成份在 {normalized_date} 存在重复证券代码")
    return rows


def _snapshot_spec(status: str) -> tuple[str, str]:
    if status == "listed":
        return LISTED_BLOCK_NAME, "listed"
    if status == "delisted":
        return DELISTED_BLOCK_NAME, "delisted"
    if status == "delisting":
        return DELISTING_BLOCK_NAME, "delisting"
    raise ValueError(f"不支持的证券状态：{status}")


def run_universe_download(
    client: UniverseClient,
    output_root: Path,
    *,
    as_of: str,
) -> dict[str, int]:
    """下载目标日的三类全 A 快照；同日已有 raw 时不重复请求。"""
    normalized_date = _normalize_query_date(as_of)
    summary = {
        "snapshots": 0,
        "downloaded": 0,
        "skipped": 0,
        "data_vol": 0,
        "listed": 0,
        "delisted": 0,
        "delisting": 0,
    }
    snapshot_rows: dict[str, list[dict[str, str]]] = {}
    for status in SNAPSHOT_STATUSES:
        blockname, normalized_status = _snapshot_spec(status)
        raw_path = snapshot_raw_path(output_root, normalized_date, status)
        if raw_path.is_file():
            with raw_path.open("r", encoding="utf-8") as stream:
                response = json.load(stream)
            summary["skipped"] += 1
            print(f"[universe] {normalized_status} {normalized_date} 已缓存，跳过", flush=True)
        else:
            print(f"[universe] 正在下载 {normalized_status} {normalized_date}", flush=True)
            try:
                response = load_or_fetch_json(
                    client,
                    raw_path,
                    "/api/v1/data_pool",
                    data_pool_payload(normalized_date, blockname),
                )
            except IFindRequestError as exc:
                is_empty_delisting = (
                    normalized_status == "delisting"
                    and exc.errorcode == -4001
                    and str(exc.errmsg or "").strip().lower().rstrip(".") == "no data"
                    and isinstance(exc.response, dict)
                )
                if not is_empty_delisting:
                    raise
                response = exc.response
                save_json_response(raw_path, response)
            summary["downloaded"] += 1
        rows = normalize_data_pool_response(response, normalized_date, normalized_status, blockname)
        snapshot_rows[normalized_status] = rows
        summary["snapshots"] += 1
        summary[normalized_status] = len(rows)
        summary["data_vol"] += int(response.get("dataVol", 0) or 0)
    combine_universe_snapshots(
        snapshot_rows["listed"],
        snapshot_rows["delisted"],
        snapshot_rows["delisting"],
    )
    return summary


def combine_universe_snapshots(
    listed_rows: list[dict[str, str]],
    delisted_rows: list[dict[str, str]],
    delisting_rows: list[dict[str, str]] | None = None,
) -> list[dict[str, str]]:
    """校验快照互斥后直接合并，不覆盖任何重复证券。"""
    snapshots = [
        ("在市", listed_rows),
        ("已摘牌", delisted_rows),
    ]
    if delisting_rows is not None:
        snapshots.append(("退市整理", delisting_rows))

    merged_rows: list[dict[str, str]] = []
    seen_codes: dict[str, str] = {}
    for label, rows in snapshots:
        codes = [row["thscode"] for row in rows]
        if len(codes) != len(set(codes)):
            raise ValueError(f"{label}快照存在重复 thscode")
        for code in codes:
            previous_label = seen_codes.get(code)
            if previous_label is not None:
                raise ValueError(
                    f"{previous_label}与{label}快照存在重复 thscode，必须互斥：{code}"
                )
            seen_codes[code] = label
        merged_rows.extend(rows)

    return sorted(
        [
            {column: row.get(column, "") for column in UNIVERSE_COLUMNS}
            for row in merged_rows
        ],
        key=lambda row: row["thscode"],
    )


def write_universe_csv(
    path: Path,
    rows: list[dict[str, str]],
    columns: tuple[str, ...] = UNIVERSE_COLUMNS,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    with temporary_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows({column: row.get(column, "") for column in columns} for row in rows)
    temporary_path.replace(path)


def _load_snapshot_rows(output_root: Path, status: str, as_of: str) -> list[dict[str, str]]:
    blockname, normalized_status = _snapshot_spec(status)
    raw_path = snapshot_raw_path(output_root, as_of, status)
    if not raw_path.is_file():
        raise FileNotFoundError(f"缺少 {status} 快照：{raw_path}")
    with raw_path.open("r", encoding="utf-8") as stream:
        response = json.load(stream)
    return normalize_data_pool_response(response, as_of, normalized_status, blockname)


def _latest_common_snapshot_date(output_root: Path) -> str:
    dates_by_status = {}
    for status in SNAPSHOT_STATUSES:
        directory = output_root / "universe" / "raw" / SNAPSHOT_DIRECTORIES[status]
        dates_by_status[status] = {
            _normalize_query_date(path.stem)
            for path in directory.glob("*.json")
        }
    common_dates = set.intersection(*(dates_by_status[status] for status in SNAPSHOT_STATUSES))
    if not common_dates:
        raise FileNotFoundError("缺少同一日期的在市、已摘牌与退市整理 p03291 raw 快照")
    return max(common_dates)


def build_universe_csv(output_root: Path, output_path: Path | None = None) -> dict[str, int | str]:
    """取最新同日的三张快照，校验互斥后重建扁平全 A 证券主表。"""
    as_of = _latest_common_snapshot_date(output_root)
    listed_rows = _load_snapshot_rows(output_root, "listed", as_of)
    delisted_rows = _load_snapshot_rows(output_root, "delisted", as_of)
    delisting_rows = _load_snapshot_rows(output_root, "delisting", as_of)
    path = output_path or default_universe_path(output_root)
    rows = combine_universe_snapshots(listed_rows, delisted_rows, delisting_rows)
    write_universe_csv(path, rows)
    summary = {
        "rows": len(rows),
        "as_of_date": as_of,
        "listed": len(listed_rows),
        "delisted": len(delisted_rows),
        "delisting": len(delisting_rows),
    }
    print(f"[universe] 已重建 {as_of} 全 A 证券主表：{len(rows)} 只，写入 {path}", flush=True)
    return summary


def update_universe_csv(
    output_root: Path,
    as_of: str,
    output_path: Path | None = None,
) -> dict[str, int | str]:
    """校验目标日三张快照互斥后，直接替换扁平证券主表。"""
    normalized_date = _normalize_query_date(as_of)
    path = output_path or default_universe_path(output_root)
    listed_rows = _load_snapshot_rows(output_root, "listed", normalized_date)
    delisted_rows = _load_snapshot_rows(output_root, "delisted", normalized_date)
    delisting_rows = _load_snapshot_rows(output_root, "delisting", normalized_date)
    rows = combine_universe_snapshots(listed_rows, delisted_rows, delisting_rows)
    write_universe_csv(path, rows)
    summary = {
        "rows": len(rows),
        "as_of_date": normalized_date,
        "listed": len(listed_rows),
        "delisted": len(delisted_rows),
        "delisting": len(delisting_rows),
    }
    print(f"[universe] 已写入 {normalized_date} 全 A 证券主表：{len(rows)} 只，写入 {path}", flush=True)
    return summary


def normalize_universe(response: dict, as_of_date: str) -> list[dict[str, str]]:
    """将旧版 iFinD 按证券分组的基础函数结果标准化为证券主数据行。"""
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
            "universe_id": LEGACY_UNIVERSE_ID,
            "as_of_date": as_of_date,
            "source": "ifind",
        })
    return rows


def validate_universe(rows: list[dict[str, str]], requested_codes: list[str]) -> None:
    """保留旧版超级命令的严格校验；新双快照流程不使用固定总数。"""
    actual_codes = [row["thscode"] for row in rows]
    if len(actual_codes) != len(set(actual_codes)):
        raise ValueError("iFinD 返回存在重复证券代码")
    if set(actual_codes) != set(requested_codes):
        raise ValueError("iFinD 返回证券代码与请求证券池不一致")
    exchange_counts = {
        exchange: sum(row["exchange"] == exchange for row in rows)
        for exchange in EXPECTED_EXCHANGE_COUNTS
    }
    if exchange_counts != EXPECTED_EXCHANGE_COUNTS:
        raise ValueError(f"全 A 证券池交易所数量不符：{exchange_counts}")


def download_universe(
    client: UniverseClient,
    super_command_file: Path,
    output_path: Path,
    raw_response_path: Path,
    as_of_date: str,
) -> int:
    """兼容旧版静态主数据采集。新流程请使用 run_universe_download。"""
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
    write_universe_csv(output_path, rows, LEGACY_UNIVERSE_COLUMNS)
    return len(rows)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        nargs="?",
        choices=("backfill", "update", "rebuild", "update-csv"),
        default="rebuild",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULT_OUTPUT_ROOT,
    )
    parser.add_argument("--output", type=Path, help="全 A 扁平证券主表路径")
    parser.add_argument("--as-of", help="快照目标日，格式 YYYY-MM-DD")
    # 保留旧版静态证券主数据命令，避免已有本地数据迁移时被强制覆盖。
    parser.add_argument("--super-command-file", type=Path)
    parser.add_argument("--raw-response", type=Path, help="旧版基础数据原始 iFinD JSON 响应")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    if args.super_command_file is not None:
        output = args.output or default_universe_path(args.output_root)
        as_of = args.as_of or date.today().isoformat()
        raw_response = args.raw_response or output.parent / "raw" / f"{LEGACY_UNIVERSE_ID}_{as_of.replace('-', '')}.json"
        row_count = download_universe(
            IFindClient.from_environment(), args.super_command_file, output, raw_response, as_of
        )
        print(json.dumps({
            "universe_id": LEGACY_UNIVERSE_ID,
            "row_count": row_count,
            "output": str(output),
            "raw_response": str(raw_response),
        }, ensure_ascii=False))
        return

    if args.command in {"backfill", "update"}:
        as_of = args.as_of or date.today().isoformat()
        download_summary = run_universe_download(
            IFindClient.from_environment(), args.output_root, as_of=as_of
        )
        csv_summary = update_universe_csv(args.output_root, as_of, args.output)
    elif args.command == "rebuild":
        download_summary = {}
        csv_summary = build_universe_csv(args.output_root, args.output)
    else:
        if not args.as_of:
            raise SystemExit("update-csv 必须提供 --as-of")
        download_summary = {}
        csv_summary = update_universe_csv(args.output_root, args.as_of, args.output)
    print(json.dumps({"download": download_summary, "csv": csv_summary}, ensure_ascii=False))


if __name__ == "__main__":
    main()
