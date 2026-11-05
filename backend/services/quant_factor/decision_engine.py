"""Module-agnostic bounded decision loop.

Factor F0 and strategy S0 share the same shape: read context -> model decision ->
whitelist validation (caller) -> execute a registered tool -> persist checkpoint.
Callers register their own actions/context/tools; this module owns stepping and
stop handling only.
"""
from __future__ import annotations

import time


def run_steps(*, decide, execute, max_steps: int = 3, stop_when=None, on_step=None, before_step=None):
    steps = []
    stop_reason = ""
    for step in range(1, max_steps + 1):
        if before_step:
            blocked = before_step(step)
            if blocked:
                stop_reason = blocked
                break
        decision, usage = decide(step)
        result = execute(decision, step)
        entry = {"step": step, "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                 "decision": decision.model_dump(), "usage": usage, "result": result}
        steps.append(entry)
        if on_step:
            on_step(step, entry, steps)
        if result.get("status") == "stopped" or decision.action == "stop":
            stop_reason = result.get("reason", "") or getattr(decision, "stop_reason", "") or "决策停止"
            break
        if stop_when and stop_when(decision, result):
            stop_reason = stop_when(decision, result)
            break
    else:
        stop_reason = f"连续 {max_steps} 步未达标，停止等待人工复盘"
    return steps, stop_reason


__all__ = ["run_steps"]
