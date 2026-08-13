"""将 iFinD Parquet 数据校验后同步到 ``MarketData/current``。

默认用法（在 ``MarketData/DataIngestion`` 目录执行）：

    python -m data_ingestion.ifind.sync_current

当前脚本只处理已经有明确目标文件的 Parquet：行情、未复权价格、指数、
股票池和日历。``date_sequence.parquet`` 暂不处理，也不会改写
``daily_basic.parquet`` 或 ``security_status.parquet``。
替换前默认会在 ``MarketData/backups`` 下创建可恢复备份。
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import shutil
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

if __package__ in (None, ""):
    # 允许直接传入绝对路径运行，而不要求用户先 cd 到 DataIngestion。
    script_dir = Path(__file__).resolve().parent
    if sys.path and Path(sys.path[0] or ".").resolve() == script_dir:
        # 避免同目录下的 data_ingestion/ifind/calendar 遮蔽 Python 标准库 calendar。
        sys.path.pop(0)
    sys.path.insert(0, str(script_dir.parents[1]))

import pandas as pd
import pyarrow.parquet as pq
import yaml

from data_ingestion.ifind.common.file_ops import replace_with_retry


PROJECT_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_SOURCE_ROOT = PROJECT_ROOT / "MarketData" / "sources" / "ifind"
DEFAULT_CURRENT_ROOT = PROJECT_ROOT / "MarketData" / "current"
DEFAULT_BACKUP_PARENT = PROJECT_ROOT / "MarketData" / "backups"


@dataclass(frozen=True)
class DirectMapping:
    source: str
    target: str


DIRECT_MAPPINGS = (
    DirectMapping(
        "market_data/market_data_hfq.parquet",
        "panels/market_data.parquet",
    ),
    DirectMapping(
        "unadjusted_price/unadjusted_price.parquet",
        "display/unadjusted_price.parquet",
    ),
    DirectMapping(
        "index/index_price/index_price_000300.SH.parquet",
        "benchmark/index_price_000300.SH.parquet",
    ),
    DirectMapping(
        "index/index_price/index_price_000905.SH.parquet",
        "benchmark/index_price_000905.SH.parquet",
    ),
    DirectMapping(
        "index/index_weights/index_weights_000300.SH.parquet",
        "benchmark/index_weights_000300.SH.parquet",
    ),
    DirectMapping(
        "index/index_weights/index_weights_000905.SH.parquet",
        "benchmark/index_weights_000905.SH.parquet",
    ),
    DirectMapping(
        "universe/a_share.parquet",
        "universe/a_share.parquet",
    ),
    # current 目前没有日历文件；保留 iFinD 原始长表，不伪造 SH/SZ/BJ 三列。
    DirectMapping(
        "calendar/calendar_all_a.parquet",
        "calendar/calendar_all_a.parquet",
    ),
)


def _pair(value: str) -> tuple[str, str] | None:
    try:
        parsed = ast.literal_eval(value)
    except (SyntaxError, ValueError, TypeError):
        return None
    if not isinstance(parsed, tuple) or len(parsed) != 2:
        return None
    symbol, field = parsed
    if not isinstance(symbol, str) or not isinstance(field, str):
        return None
    return symbol, field


def _index_column(path: Path) -> str | None:
    schema = pq.read_schema(path)
    names = set(schema.names)
    metadata = schema.pandas_metadata or {}
    for item in metadata.get("index_columns", []):
        if isinstance(item, str) and item in names:
            return item
    for candidate in ("date", "datetime", "__index_level_0__"):
        if candidate in names:
            return candidate
    return None


def _validate_required_sources(source_root: Path) -> None:
    required = [source_root / item.source for item in DIRECT_MAPPINGS]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError("iFinD 源文件不完整，缺少：\n" + "\n".join(missing))

    for path in required:
        parquet = pq.ParquetFile(path)
        if parquet.metadata is None or parquet.metadata.num_rows <= 0:
            raise ValueError(f"Parquet 文件为空：{path}")


def _copy_direct_files(source_root: Path, stage_root: Path) -> list[str]:
    targets: list[str] = []
    for mapping in DIRECT_MAPPINGS:
        source = source_root / mapping.source
        target = stage_root / mapping.target
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        targets.append(mapping.target)
    return targets


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _asset_summary(path: Path, relative: str) -> dict[str, object]:
    parquet = pq.ParquetFile(path)
    schema = parquet.schema_arrow
    pairs = [parsed for name in schema.names if (parsed := _pair(name)) is not None]
    if pairs:
        symbols = len({symbol for symbol, _ in pairs})
        fields = sorted({field for _, field in pairs})
    else:
        index_column = _index_column(path)
        fields = [name for name in schema.names if name != index_column]
        if relative.startswith("benchmark/index_weights/"):
            symbols = len(fields)
            fields = ["weight"]
        elif relative.startswith("benchmark/index_price/"):
            symbols = 1
        elif relative.startswith("universe/"):
            symbols = parquet.metadata.num_rows
        else:
            symbols = 1
    return {
        "path": relative.replace("\\", "/"),
        "rows": parquet.metadata.num_rows,
        "symbols": symbols,
        "fields": fields,
        "sha256": _sha256(path),
    }


def _sources_for(relative: str, fields: list[str]) -> dict[str, list[str]]:
    if relative.startswith(("panels/", "display/", "benchmark/", "universe/", "calendar/")):
        return {field: ["ifind"] for field in fields}
    return {field: ["current"] for field in fields}


def _load_existing_manifest(current_root: Path) -> dict[str, object]:
    path = current_root / "data_manifest.yaml"
    if not path.is_file():
        return {}
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    return loaded if isinstance(loaded, dict) else {}


def _write_release_metadata(
    stage_root: Path,
    current_root: Path,
    target_files: list[str],
    active: bool,
) -> None:
    """更新被同步文件的清单，同时保留未处理资产（如 date_sequence 对应的旧数据）。"""
    existing = _load_existing_manifest(current_root)
    updated_paths = set(target_files)
    assets_by_path: dict[str, dict[str, object]] = {}

    old_assets = existing.get("assets", [])
    if isinstance(old_assets, list):
        for old_asset in old_assets:
            if not isinstance(old_asset, dict) or not isinstance(old_asset.get("path"), str):
                continue
            relative = old_asset["path"]
            path = stage_root / relative if relative in updated_paths else current_root / relative
            if not path.is_file():
                continue
            summary = _asset_summary(path, relative)
            if relative in updated_paths:
                summary["sources"] = _sources_for(relative, summary["fields"])
            else:
                summary["sources"] = old_asset.get(
                    "sources", _sources_for(relative, summary["fields"])
                )
            assets_by_path[relative] = summary

    # 没有旧 manifest 或旧 manifest 未登记的现有 Parquet 也保留在清单中。
    for path in current_root.rglob("*.parquet"):
        relative = path.relative_to(current_root).as_posix()
        if relative in assets_by_path or relative in updated_paths:
            continue
        summary = _asset_summary(path, relative)
        summary["sources"] = _sources_for(relative, summary["fields"])
        assets_by_path[relative] = summary

    for relative in target_files:
        summary = _asset_summary(stage_root / relative, relative)
        summary["sources"] = _sources_for(relative, summary["fields"])
        assets_by_path[relative] = summary

    generated_at = datetime.now(timezone.utc)
    manifest = {
        "schema_version": existing.get("schema_version", 2),
        "data_version": "ifind-sync-" + generated_at.strftime("%Y%m%d-%H%M%S"),
        "generated_at": generated_at.isoformat(),
        "layout": existing.get("layout", "domain_multi_field_parquet"),
        "missing_value_policy": existing.get(
            "missing_value_policy", "原样保留，由研究员在使用阶段处理"
        ),
        "assets": list(assets_by_path.values()),
        "release_status": "active" if active else "candidate",
    }
    (stage_root / "data_manifest.yaml").write_text(
        yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    (stage_root / "quality_report.json").write_text(
        json.dumps(
            {
                "status": "active_validated" if active else "candidate_validated",
                "checks": [
                    "source_files_present",
                    "parquet_schema",
                    "date_unique_sorted",
                    "sha256",
                    "staged_before_replace",
                ],
                "assets": list(assets_by_path.values()),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _validate_parquet(path: Path, relative: str) -> None:
    metadata = pq.read_metadata(path)
    if metadata.num_rows <= 0:
        raise ValueError(f"生成文件为空：{path}")
    index_column = _index_column(path)
    if index_column is None:
        return
    table = pq.read_table(path, columns=[index_column])
    dates = pd.to_datetime(table.column(0).to_pandas())
    try:
        if not dates.is_unique:
            duplicated = dates[dates.duplicated(keep=False)].dt.strftime("%Y-%m-%d").unique()
            duplicate_text = ", ".join(duplicated[:10])
            raise ValueError(f"{relative} 日期存在重复：{duplicate_text}")
        if not dates.is_monotonic_increasing:
            raise ValueError(f"{relative} 日期未按升序排列")
    finally:
        # Windows 下 Arrow 可能暂时持有文件句柄；异常时也要先释放再清理临时目录。
        del dates
        del table


def _validate_stage(stage_root: Path, target_files: list[str]) -> None:
    for relative in target_files:
        _validate_parquet(stage_root / relative, relative)


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _new_backup_root(parent: Path) -> Path:
    stamp = datetime.now().strftime("ifind-sync-%Y%m%d-%H%M%S-%f")
    candidate = parent / stamp
    candidate.parent.mkdir(parents=True, exist_ok=True)
    return candidate


def _backup_current(
    current_root: Path,
    target_files: list[str],
    backup_root: Path,
) -> list[str]:
    if backup_root.exists():
        raise FileExistsError(f"备份目录已存在，为避免覆盖而停止：{backup_root}")
    backup_root.mkdir(parents=True)
    backed_up: list[str] = []
    for relative in target_files:
        source = current_root / relative
        if not source.is_file():
            continue
        target = backup_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        backed_up.append(relative)
    return backed_up


def _restore_file(backup: Path, target: Path) -> None:
    restore = target.with_name(target.name + ".restore.tmp")
    try:
        shutil.copy2(backup, restore)
        replace_with_retry(restore, target)
    finally:
        if restore.exists():
            restore.unlink()


def _commit_stage(
    stage_root: Path,
    current_root: Path,
    target_files: list[str],
    backup_root: Path | None,
) -> None:
    original_exists = {
        relative: (current_root / relative).is_file()
        for relative in target_files
    }
    replaced: list[str] = []
    try:
        for relative in target_files:
            staged = stage_root / relative
            target = current_root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            replace_with_retry(staged, target)
            replaced.append(relative)
    except Exception:
        if backup_root is not None:
            for relative in reversed(replaced):
                target = current_root / relative
                backup = backup_root / relative
                if backup.is_file():
                    _restore_file(backup, target)
                elif not original_exists[relative] and target.exists():
                    target.unlink()
        raise


def sync_ifind_to_current(
    source_root: Path = DEFAULT_SOURCE_ROOT,
    current_root: Path = DEFAULT_CURRENT_ROOT,
    *,
    backup_root: Path | None = None,
    make_backup: bool = True,
    dry_run: bool = False,
) -> dict[str, object]:
    """执行一次 iFinD → current 同步，返回可打印的执行摘要。"""
    source_root = Path(source_root).resolve()
    current_root = Path(current_root).resolve()
    if not source_root.is_dir():
        raise NotADirectoryError(f"iFinD 源目录不存在：{source_root}")
    if not current_root.is_dir():
        raise NotADirectoryError(f"current 目录不存在：{current_root}")
    if source_root == current_root or _is_within(current_root, source_root):
        raise ValueError("source_root 与 current_root 不能相互嵌套")

    _validate_required_sources(source_root)

    stage_parent = current_root.parent
    with tempfile.TemporaryDirectory(
        prefix=f".{current_root.name}.ifind-sync-",
        dir=stage_parent,
    ) as temporary:
        stage_root = Path(temporary)
        target_files = _copy_direct_files(source_root, stage_root)
        target_files = list(dict.fromkeys(target_files))
        _validate_stage(stage_root, target_files)
        _write_release_metadata(stage_root, current_root, target_files, active=not dry_run)
        target_files.extend(("data_manifest.yaml", "quality_report.json"))

        summary: dict[str, object] = {
            "source_root": str(source_root),
            "current_root": str(current_root),
            "dry_run": dry_run,
            "files": target_files,
            "ignored_sources": ["date_sequence/**/*.parquet"],
        }
        if dry_run:
            summary["message"] = "校验通过，未替换 current"
            return summary

        if backup_root is not None and not make_backup:
            raise ValueError("backup_root 与 make_backup=False 不能同时使用")
        if make_backup:
            if backup_root is None:
                backup_root = _new_backup_root(DEFAULT_BACKUP_PARENT)
            else:
                backup_root = Path(backup_root).resolve()
            if _is_within(backup_root, current_root) or _is_within(backup_root, source_root):
                raise ValueError("备份目录不能放在 source_root 或 current_root 内部")
            backed_up = _backup_current(current_root, target_files, backup_root)
            summary["backup_root"] = str(backup_root)
            summary["backed_up_files"] = backed_up

        _commit_stage(stage_root, current_root, target_files, backup_root if make_backup else None)
        summary["replaced_files"] = target_files
        summary["message"] = "iFinD 数据已完成校验、备份和替换"
        return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE_ROOT)
    parser.add_argument("--current-root", type=Path, default=DEFAULT_CURRENT_ROOT)
    parser.add_argument(
        "--backup-root",
        type=Path,
        help="指定备份目录；默认写入 MarketData/backups/ifind-sync-时间戳",
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="不创建替换前备份；仅建议在已确认可恢复时使用",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只生成并校验候选文件，不替换 current",
    )
    args = parser.parse_args()
    if args.no_backup and args.backup_root is not None:
        parser.error("--no-backup 与 --backup-root 不能同时使用")
    summary = sync_ifind_to_current(
        args.source_root,
        args.current_root,
        backup_root=args.backup_root,
        make_backup=not args.no_backup,
        dry_run=args.dry_run,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
