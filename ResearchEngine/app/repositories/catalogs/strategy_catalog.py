"""项目级策略源码目录的读取与版本解析。"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class StrategyAsset:
    """可被回测引用的不可变策略源码版本。"""

    strategy_id: str
    name: str
    strategy_type: str
    execution_mode: str
    version: str
    entrypoint: str
    source_code: str
    code_hash: str


class StrategyCatalog:
    """读取 ``app/assets/strategies/index.yaml``，不执行策略源码。"""

    def __init__(self, library_dir: str | Path | None = None) -> None:
        if library_dir is None:
            from app.repositories.catalogs.paths import strategy_library_dir

            library_dir = strategy_library_dir()
        self.library_dir = Path(library_dir).resolve()

    def list_assets(self) -> list[dict[str, Any]]:
        """返回索引中的策略和当前版本，不读取或执行源码。"""
        strategies = self._strategies()
        assets = []
        for strategy_id, entry in sorted(strategies.items()):
            current_version = self._required_string(entry, "current_version", strategy_id)
            version_entry = self._version_entry(entry, current_version, strategy_id)
            assets.append(
                {
                    "id": strategy_id,
                    "name": self._required_string(entry, "name", strategy_id),
                    "strategy_type": self._required_string(entry, "strategy_type", strategy_id),
                    "execution_mode": self._required_string(entry, "execution_mode", strategy_id),
                    "current_version": current_version,
                    "entrypoint": self._required_string(version_entry, "entrypoint", strategy_id),
                    "tags": entry.get("tags", []),
                }
            )
        return assets

    def load(self, strategy_id: str, version: str | None = None) -> StrategyAsset:
        """按策略 ID 和版本读取源码，并返回其内容哈希。"""
        strategies = self._strategies()
        entry = strategies.get(strategy_id)
        if not isinstance(entry, dict):
            raise ValueError(f"策略不存在: {strategy_id}")
        resolved_version = version or self._required_string(entry, "current_version", strategy_id)
        version_entry = self._version_entry(entry, resolved_version, strategy_id)
        source_file = self._source_path(
            self._required_string(version_entry, "file", strategy_id)
        )
        if not source_file.is_file():
            raise ValueError(f"策略源码不存在: {source_file.name}")
        source_code = source_file.read_text(encoding="utf-8")
        return StrategyAsset(
            strategy_id=strategy_id,
            name=self._required_string(entry, "name", strategy_id),
            strategy_type=self._required_string(entry, "strategy_type", strategy_id),
            execution_mode=self._required_string(entry, "execution_mode", strategy_id),
            version=resolved_version,
            entrypoint=self._required_string(version_entry, "entrypoint", strategy_id),
            source_code=source_code,
            code_hash=hashlib.sha256(source_code.encode("utf-8")).hexdigest(),
        )

    def _strategies(self) -> dict[str, dict[str, Any]]:
        from app.repositories.catalogs.paths import strategy_index_path

        index_path = (
            strategy_index_path()
            if self.library_dir == self._default_library_dir()
            else self.library_dir / "index.yaml"
        )
        if not index_path.is_file():
            raise ValueError(f"策略索引不存在: {index_path}")
        try:
            payload = yaml.safe_load(index_path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            raise ValueError(f"策略索引格式错误: {exc}") from exc
        if payload.get("version") != 2:
            raise ValueError("策略索引 version 必须为 2")
        strategies = payload.get("strategies")
        if not isinstance(strategies, dict):
            raise ValueError("策略索引 strategies 必须为对象")
        return strategies

    def _default_library_dir(self) -> Path:
        from app.repositories.catalogs.paths import strategy_library_dir

        return strategy_library_dir().resolve()

    @staticmethod
    def _required_string(entry: dict[str, Any], field: str, strategy_id: str) -> str:
        value = entry.get(field)
        if not isinstance(value, str) or not value:
            raise ValueError(f"策略 {strategy_id} 缺少有效字段: {field}")
        return value

    def _version_entry(
        self, entry: dict[str, Any], version: str, strategy_id: str
    ) -> dict[str, Any]:
        versions = entry.get("versions")
        if not isinstance(versions, dict) or not isinstance(versions.get(version), dict):
            raise ValueError(f"策略 {strategy_id} 不存在版本: {version}")
        return versions[version]

    def _source_path(self, relative_path: str) -> Path:
        candidate = (self.library_dir / relative_path).resolve()
        if candidate.suffix != ".py" or candidate.parent != self.library_dir:
            raise ValueError("策略源码 file 必须是策略目录中的 .py 文件")
        return candidate
