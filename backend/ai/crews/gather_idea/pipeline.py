# -*- coding: utf-8 -*-
"""gather_idea 流水线入口（Agent A gather + Agent B idea）。"""
from __future__ import annotations

from typing import Any

from ai.crews.gather_idea.gather_agent import run_gather
from ai.crews.gather_idea.idea_agent import run_idea
from ai.crews.gather_idea.factor_agent import run_factor
from ai.crews.gather_idea.backtest_agent import run_backtest_report
from ai.crews.gather_idea.eval_agent import run_eval
from ai.crews.gather_idea.schemas import EvidencePack, IdeaBundle
from ai.runtime import store as agent_store


def run_gather_pipeline(body: dict[str, Any], *, user_id: int) -> EvidencePack:
    """鉴权后的用户调用：占额度 → 搜集 → 记账。"""
    agent_store.assert_quota_available(user_id, need=1)
    run_id = agent_store.new_run_id()
    pack = run_gather(body, user_id=user_id)
    stats = dict(pack.get("stats") or {})
    agent_store.record_usage(
        user_id=user_id,
        run_id=run_id,
        skill="gather",
        tokens_in=int(stats.get("tokens_in") or 0),
        tokens_out=int(stats.get("tokens_out") or 0),
    )
    stats["run_id"] = run_id
    pack["stats"] = stats  # type: ignore[typeddict-item]
    return pack


def run_idea_pipeline(body: dict[str, Any], *, user_id: int) -> IdeaBundle:
    """鉴权后：占额度 → Idea 生成 → 记账 skill=idea。"""
    agent_store.assert_quota_available(user_id, need=1)
    run_id = agent_store.new_run_id()
    bundle = run_idea(body, user_id=user_id)
    stats = dict(bundle.get("stats") or {})
    agent_store.record_usage(
        user_id=user_id,
        run_id=run_id,
        skill="idea",
        tokens_in=int(stats.get("tokens_in") or 0),
        tokens_out=int(stats.get("tokens_out") or 0),
    )
    stats["run_id"] = run_id
    bundle["stats"] = stats  # type: ignore[typeddict-item]
    return bundle  # type: ignore[return-value]


def run_factor_pipeline(body: dict[str, Any], *, user_id: int) -> dict[str, Any]:
    agent_store.assert_quota_available(user_id, need=1)
    run_id = agent_store.new_run_id()
    out = run_factor(body, user_id=user_id)
    stats = dict(out.get("stats") or {})
    agent_store.record_usage(
        user_id=user_id,
        run_id=run_id,
        skill="factor",
        tokens_in=int(stats.get("tokens_in") or 0),
        tokens_out=int(stats.get("tokens_out") or 0),
    )
    stats["run_id"] = run_id
    out["stats"] = stats
    return out


def run_backtest_pipeline(body: dict[str, Any], *, user_id: int) -> dict[str, Any]:
    agent_store.assert_quota_available(user_id, need=1)
    run_id = agent_store.new_run_id()
    out = run_backtest_report(body, user_id=user_id)
    stats = dict(out.get("stats") or {})
    agent_store.record_usage(
        user_id=user_id,
        run_id=run_id,
        skill="factor_backtest",
        tokens_in=0,
        tokens_out=0,
    )
    stats["run_id"] = run_id
    out["stats"] = stats
    return out


def run_eval_pipeline(body: dict[str, Any], *, user_id: int) -> dict[str, Any]:
    agent_store.assert_quota_available(user_id, need=1)
    run_id = agent_store.new_run_id()
    out = run_eval(body, user_id=user_id)
    stats = dict(out.get("stats") or {})
    agent_store.record_usage(
        user_id=user_id,
        run_id=run_id,
        skill="factor_eval",
        tokens_in=0,
        tokens_out=0,
    )
    stats["run_id"] = run_id
    out["stats"] = stats
    return out
