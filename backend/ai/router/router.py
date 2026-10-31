# -*- coding: utf-8 -*-
"""L2 任务路由层：业务唯一的 AI 入口。

调用方只说“我要哪个 task、这些消息、这些变量”，模型档位、超时、
降级顺序、异常语义都由注册表决定。见 ADR-037。
"""
from __future__ import annotations

import time
from typing import Any, Iterator

from ai.errors import AiInvalidRequest, AiNotConfigured
from ai.gateway import providers
from ai.router.executors import EXECUTORS, can_run
from ai.router.specs import EXECUTOR_RE, TaskRequest, get_task


def run_task(
    task_id: str,
    *,
    messages: list[dict[str, Any]] | None = None,
    variables: dict[str, Any] | None = None,
    model: str | None = None,
    temperature: float | None = None,
    tools: list[dict[str, Any]] | None = None,
    tool_choice: str | dict[str, Any] | None = None,
) -> dict[str, Any]:
    """执行一次 AI 任务，返回统一结果字典。

    返回值固定包含：content / model / provider / tokens_in / tokens_out /
    tool_calls / task / latency_ms；出错抛 `ai.errors` 中的类型化异常。
    """
    spec = get_task(task_id)
    request = TaskRequest(
        messages=list(messages or []),
        variables=dict(variables or {}),
        model=model,
        temperature=temperature,
        tools=tools,
        tool_choice=tool_choice,
    )
    if not request.messages and spec.prompt is None and spec.executors[0] != EXECUTOR_RE:
        raise AiInvalidRequest("messages 不能为空")

    started = time.perf_counter()
    last_error: Exception | None = None
    for name in spec.executors:
        executor = EXECUTORS.get(name)
        if executor is None:
            raise KeyError(f"任务 {task_id} 引用了未实现的执行器: {name}")
        try:
            result = executor(spec, request)
        except AiNotConfigured as exc:
            last_error = exc
            continue
        out = dict(result)
        out["task"] = task_id
        out["prompt_version"] = spec.prompt_version
        out["latency_ms"] = int((time.perf_counter() - started) * 1000)
        return out

    raise last_error or AiNotConfigured(f"任务 {task_id} 没有可用执行器")


def stream_task(
    task_id: str,
    *,
    messages: list[dict[str, Any]],
    model: str | None = None,
    temperature: float | None = None,
    timeout: int | None = None,
) -> Iterator[str]:
    """流式执行（仅 assistant 类任务）；帧格式由调用方负责封装。"""
    spec = get_task(task_id)
    if not spec.allow_stream:
        raise AiInvalidRequest(f"任务 {task_id} 不支持流式")
    target = providers.resolve_target(slot=spec.slot, model=model)
    yield from providers.stream(
        target,
        messages=list(messages),
        temperature=spec.temperature if temperature is None else temperature,
        max_tokens=spec.max_tokens,
        timeout=timeout or spec.timeout_sec,
    )


def available_task(task_id: str) -> bool:
    """该任务当前是否具备执行条件（供 feature 决定是否使用本地 mock）。"""
    return can_run(get_task(task_id))


__all__ = ["available_task", "run_task", "stream_task"]
