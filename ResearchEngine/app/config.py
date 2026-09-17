"""``ConfigManager`` - 统一配置读取。

依据 ``ResearchEngine/docs/03-功能文档/FEAT-002-研究引擎/04-class-design.md`` ConfigManager 节：

    属性：
      config: dict

    方法：
      load(path: str)
      get(key: str, default=None) -> Any
      set(key: str, value)
      to_dict() -> dict

支持 YAML / JSON 两种来源（按扩展名判断）。键支持点号嵌套，如 ``get("data.dir")``。
未来 GUI 接入只需替换配置来源，无需修改核心流程。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import yaml

class ConfigManager:
    """统一配置管理器。"""

    def __init__(self, config: dict | None = None, config_path: str | None = None) -> None:
        self.config: dict = dict(config) if config else {}
        if config_path is not None:
            self.load(config_path)

    def load(self, path: str) -> None:
        """从文件加载配置（YAML 或 JSON，按扩展名判断）。"""
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"配置文件不存在: {p}")
        suffix = p.suffix.lower()
        text = p.read_text(encoding="utf-8")
        if suffix in (".yaml", ".yml"):
            data = yaml.safe_load(text) or {}
        elif suffix == ".json":
            data = json.loads(text)
        else:
            raise ValueError(f"不支持的配置格式 {suffix!r}，仅支持 yaml/yml/json")
        if not isinstance(data, dict):
            raise ValueError(f"配置根必须是字典，得到 {type(data).__name__}")
        self.config.update(data)

    def get(self, key: str, default: Any = None) -> Any:
        """获取配置项，支持点号嵌套。"""
        node: Any = self.config
        for part in key.split("."):
            if isinstance(node, dict) and part in node:
                node = node[part]
            else:
                return default
        return node

    def set(self, key: str, value: Any) -> None:
        """设置配置项，支持点号嵌套（自动创建中间字典）。"""
        parts = key.split(".")
        node = self.config
        for part in parts[:-1]:
            if part not in node or not isinstance(node[part], dict):
                node[part] = {}
            node = node[part]
        node[parts[-1]] = value

    def to_dict(self) -> dict:
        return dict(self.config)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ConfigManager keys={list(self.config)}>"
