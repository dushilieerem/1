# -*- coding: utf-8 -*-
"""任务规格与注册表（ADR-037 L2）。

新增 AI 能力 = 注册一个 TaskSpec，不改路由层本身。
业务代码只引用 task_id，不引用供应商、base_url、Key。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from ai.gateway.providers import SLOT_DEFAULT

EXECUTOR_LOCAL = "local"
EXECUTOR_RE = "re"


@dataclass(frozen=True)
class TaskRequest:
    """一次任务调用的输入。messages 由调用方构造，路由层不外推 prompt。"""

    messages: list[dict[str, Any]] = field(default_factory=list)
    variables: dict[str, Any] = field(default_factory=dict)
    model: str | None = None
    temperature: float | None = None
    tools: list[dict[str, Any]] | None = None
    tool_choice: str | dict[str, Any] | None = None


@dataclass(frozen=True)
class TaskSpec:
    """一个 AI 能力的全部非业务参数。

    字段取舍见 ADR-037 §2；P0 只落地本地执行链所需的部分，
    `response_format` / `re_path` / `re_parse` 在 P1 迁移 RE 能力时启用。
    """

    task_id: str
    description: str = ""
    prompt_version: str = "v1"
    slot: str = SLOT_DEFAULT
    temperature: float = 0.4
    max_tokens: int | None = 2048
    timeout_sec: int | None = None
    response_format: dict[str, Any] | None = None
    allow_tools: bool = False
    allow_stream: bool = False
    executors: tuple[str, ...] = (EXECUTOR_LOCAL,)
    # 任务自带 prompt 与输出校验器（迁移 RE 能力时启用）
    prompt: Callable[[TaskRequest], list[dict[str, Any]]] | None = None
    validator: Callable[[str, TaskRequest], dict[str, Any]] | None = None
    # 执行链中的 re 成员需要目标路径与入参/出参映射
    re_path: str | None = None
    re_payload: Callable[[TaskRequest], dict[str, Any]] | None = None
    re_parse: Callable[[dict[str, Any]], dict[str, Any]] | None = None


_TASKS: dict[str, TaskSpec] = {}


def register(spec: TaskSpec) -> TaskSpec:
    if not spec.task_id:
        raise ValueError("TaskSpec.task_id 不能为空")
    if spec.task_id in _TASKS:
        raise ValueError(f"任务重复注册: {spec.task_id}")
    if EXECUTOR_RE in spec.executors and not spec.re_path:
        raise ValueError(f"任务 {spec.task_id} 声明了 re 执行器但未给 re_path")
    _TASKS[spec.task_id] = spec
    return spec


def get_task(task_id: str) -> TaskSpec:
    try:
        return _TASKS[task_id]
    except KeyError as exc:
        raise KeyError(f"未注册的 AI 任务: {task_id}") from exc


def all_tasks() -> tuple[TaskSpec, ...]:
    return tuple(_TASKS[k] for k in sorted(_TASKS))


def clear_registry() -> None:
    """仅供测试使用。"""
    _TASKS.clear()


__all__ = [
    "EXECUTOR_LOCAL",
    "EXECUTOR_RE",
    "TaskRequest",
    "TaskSpec",
    "all_tasks",
    "clear_registry",
    "get_task",
    "register",
]
