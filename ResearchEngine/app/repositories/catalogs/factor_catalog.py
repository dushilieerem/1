"""因子库索引生成与一致性校验。

源码目录 ``app/assets/factors/libraries`` 是可执行实现的事实来源。此模块从运行时
``FactorLoader`` 发现每个公开因子方法，只生成和校验
``app/assets/factors/index.yaml``，供 API 与前端使用。

``Factor/因子库总览.md`` 是研究员维护的手工文档，故意不属于本模块的写入或
校验范围。库级标签、来源和验证状态等治理元数据保留在现有 ``index.yaml``
中；因子名称、说明、默认参数、实现文件、类名和数量由源码自动生成。
"""

from __future__ import annotations

import argparse
import importlib
import inspect
import os
import sys
import tempfile
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from app.repositories.catalogs.paths import factor_index_path, factor_library_dir
from app.repositories.catalogs.factor_loader import FactorLoader


_SKIP_MODULES = {"__init__"}


def default_index_path() -> Path:
    return factor_index_path()


def _read_index(index_path: Path) -> dict[str, Any]:
    if not index_path.is_file():
        return {}
    payload = yaml.safe_load(index_path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"因子索引必须是 YAML 映射: {index_path}")
    libraries = payload.get("libraries")
    if libraries is not None and not isinstance(libraries, dict):
        raise ValueError(f"因子索引 libraries 必须是 YAML 映射: {index_path}")
    return payload


def _jsonable(value: Any) -> Any:
    """把签名默认值转换为可稳定写入 YAML 的值。"""
    if value is inspect.Parameter.empty:
        return None
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    return repr(value)


def _factor_params(method: Any) -> dict[str, Any]:
    """提取公开因子参数，忽略动态注册器的私有闭包参数。"""
    params: dict[str, Any] = {}
    for name, parameter in inspect.signature(method).parameters.items():
        if name.startswith("_") or parameter.kind in {
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        }:
            continue
        if parameter.default is not inspect.Parameter.empty:
            params[name] = _jsonable(parameter.default)
    return params


def _first_doc_line(value: Any, fallback: str) -> str:
    doc = inspect.getdoc(value) or ""
    for line in doc.splitlines():
        line = line.strip()
        if line:
            return line
    return fallback


def _source_date(factor_dir: Path) -> str:
    files = [
        path
        for path in factor_dir.glob("*.py")
        if path.stem not in _SKIP_MODULES and not path.name.startswith("_")
    ]
    if not files:
        return datetime.now().date().isoformat()
    timestamp = max(path.stat().st_mtime for path in files)
    return datetime.fromtimestamp(timestamp).date().isoformat()


def _module_names(factor_dir: Path) -> list[str]:
    return sorted(
        path.stem
        for path in factor_dir.glob("*.py")
        if path.stem not in _SKIP_MODULES and not path.name.startswith("_")
    )


def _load_library(factor_dir: Path, module_name: str):
    """在目录变更后重新加载模块，避免同一进程使用旧源码缓存。"""
    importlib.invalidate_caches()
    sys.modules.pop(module_name, None)
    loader = FactorLoader(factor_dir=str(factor_dir))
    return loader, loader.load(module_name)


def discover_catalog(factor_dir: Path, previous: dict[str, Any] | None = None) -> dict[str, Any]:
    """从因子源码发现完整目录，并保留库级治理元数据。"""
    previous_libraries = (previous or {}).get("libraries") or {}
    if not isinstance(previous_libraries, dict):
        previous_libraries = {}

    libraries: "OrderedDict[str, dict[str, Any]]" = OrderedDict()
    for module_name in _module_names(factor_dir):
        _loader, library = _load_library(factor_dir, module_name)
        methods = library._factor_methods()
        if not methods:
            raise ValueError(f"因子库 {module_name!r} 没有公开因子方法")

        old_library = previous_libraries.get(module_name) or {}
        if not isinstance(old_library, dict):
            old_library = {}
        old_factors = {
            item.get("name"): item
            for item in (old_library.get("factors") or [])
            if isinstance(item, dict) and item.get("name")
        }

        factors: list[dict[str, Any]] = []
        for factor_name in sorted(methods):
            method = methods[factor_name]
            old_factor = old_factors.get(factor_name) or {}
            item: dict[str, Any] = {
                "name": factor_name,
                "description": _first_doc_line(method, factor_name),
            }
            params = _factor_params(method)
            if params:
                item["params"] = params

            # 逐因子标签、字段依赖、可用性和人工验证说明等治理元数据，按名称保留。
            # 只替换源码可以确定的字段，避免同步时丢失未来新增的人工元数据。
            for key, value in old_factor.items():
                if key not in {"name", "description", "params"}:
                    item[key] = value
            factors.append(item)

        class_name = type(library).__name__
        library_description = old_library.get("description") or _first_doc_line(
            type(library), module_name
        )
        metadata: dict[str, Any] = OrderedDict()
        metadata["file"] = f"{module_name}.py"
        metadata["class"] = class_name
        metadata["description"] = library_description
        metadata["author"] = getattr(library, "author", old_library.get("author", "anonymous"))

        # 保留已有库级治理字段的顺序和内容，再写入自动生成字段。
        for key, value in old_library.items():
            if key not in {"file", "class", "description", "author", "factor_count", "factors"}:
                metadata[key] = value
        metadata["factor_count"] = len(factors)
        metadata["factors"] = factors
        libraries[module_name] = metadata

    version = previous.get("version", 1) if previous else 1
    return OrderedDict(
        [
            ("version", version),
            ("updated", _source_date(factor_dir)),
            ("total_factors", sum(item["factor_count"] for item in libraries.values())),
            ("libraries", libraries),
        ]
    )


def _yaml_text(catalog: dict[str, Any]) -> str:
    def plain(value: Any) -> Any:
        if isinstance(value, dict):
            return {key: plain(item) for key, item in value.items()}
        if isinstance(value, list):
            return [plain(item) for item in value]
        if isinstance(value, tuple):
            return [plain(item) for item in value]
        return value

    return yaml.safe_dump(
        plain(catalog),
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
        width=120,
    )


def _write_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def render_index(
    *,
    factor_dir: Path | None = None,
    index_path: Path | None = None,
) -> tuple[str, dict[str, Any]]:
    use_default_paths = factor_dir is None
    factor_dir = (factor_dir or factor_library_dir()).resolve()
    if index_path is None:
        index_path = factor_index_path() if use_default_paths else factor_dir / "index.yaml"
    index_path = Path(index_path).resolve()
    catalog = discover_catalog(factor_dir, _read_index(index_path))
    return _yaml_text(catalog), catalog


def sync_catalog(
    *,
    factor_dir: Path | None = None,
    index_path: Path | None = None,
) -> dict[str, Any]:
    use_default_paths = factor_dir is None
    factor_dir = (factor_dir or factor_library_dir()).resolve()
    if index_path is None:
        index_path = factor_index_path() if use_default_paths else factor_dir / "index.yaml"
    index_path = Path(index_path).resolve()
    index_text, catalog = render_index(factor_dir=factor_dir, index_path=index_path)
    _write_atomic(index_path, index_text)
    return catalog


def check_catalog(
    *,
    factor_dir: Path | None = None,
    index_path: Path | None = None,
) -> list[str]:
    use_default_paths = factor_dir is None
    factor_dir = (factor_dir or factor_library_dir()).resolve()
    if index_path is None:
        index_path = factor_index_path() if use_default_paths else factor_dir / "index.yaml"
    index_path = Path(index_path).resolve()
    expected_index, _catalog = render_index(factor_dir=factor_dir, index_path=index_path)
    errors: list[str] = []
    if not index_path.is_file():
        errors.append(f"缺少索引文件: {index_path}")
    elif index_path.read_text(encoding="utf-8") != expected_index:
        errors.append(f"索引未同步: {index_path}")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="同步或校验 SVQuant 因子库目录")
    parser.add_argument("command", choices=("sync", "check"), help="sync 生成文件；check 只校验")
    parser.add_argument("--factor-dir", type=Path, default=None)
    parser.add_argument("--index", dest="index_path", type=Path, default=None)
    args = parser.parse_args(argv)

    if args.command == "sync":
        catalog = sync_catalog(
            factor_dir=args.factor_dir,
            index_path=args.index_path,
        )
        print(f"已同步 {len(catalog['libraries'])} 个库、{catalog['total_factors']} 个因子。")
        return 0

    errors = check_catalog(
        factor_dir=args.factor_dir,
        index_path=args.index_path,
    )
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        print("请先运行: python -m app.repositories.catalogs.factor_catalog sync", file=sys.stderr)
        return 1
    print("因子源码和 index.yaml 已同步。")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
