# -*- coding: utf-8 -*-
"""AI 提示词覆盖、50 字摘要与结果缓存。"""
from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path

import pytest

os.environ.setdefault("JWT_SECRET_KEY", "0123456789abcdef0123456789abcdef")
os.environ.setdefault("DEV_SKIP_AUTH", "0")
os.environ.setdefault("RE_CATALOG_SYNC_ENABLED", "0")
os.environ.setdefault("SVQUANT_PANEL_DAILY_ENABLED", "0")
os.environ.setdefault("SVQUANT_PAPER_TRADING_ENABLED", "0")
os.environ.setdefault("NEWS_INGEST_INTERVAL_SEC", "0")
os.environ.setdefault("RE_CATALOG_WARM_ENABLED", "0")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from psycopg.types.json import Jsonb  # noqa: E402

from ai.router.specs import TaskRequest  # noqa: E402
from ai.router.tasks.institution import (  # noqa: E402
    clip_brief,
    validate_dimension,
    validate_memo,
    validate_research_memo,
)
from ai.runtime import agent_store  # noqa: E402
from services.auth.auth_store import ensure_schema  # noqa: E402
from services.core.db import get_conn  # noqa: E402
from services.institution import inst_service as svc  # noqa: E402
from services.institution.inst_schema import ensure_inst_business_schema  # noqa: E402
from services.institution.inst_store import ensure_inst_schema  # noqa: E402

ensure_schema()
ensure_inst_schema()
ensure_inst_business_schema()
agent_store.ensure_ai_agent_schema()


def test_clip_brief_and_validators() -> None:
    long_text = "这是一个明显超过五十个字符的摘要，需要完整保留而不是截断，确保投资经理能看到全部依据。"
    assert clip_brief(long_text) == long_text
    dim = validate_dimension(
        json.dumps(
            {
                "summary": long_text,
                "checks": [long_text, "短句"],
                "counter": [long_text],
                "evidence": [{"title": "t", "quote": "q", "source": "s"}],
                "open_questions": [long_text],
                "data_gaps": [long_text],
            }
        ),
        TaskRequest(),
    )
    assert dim["summary"] == long_text
    assert long_text in dim["checks"]
    assert dim["counter"] == [long_text]
    assert dim["open_questions"] == [long_text]
    assert dim["data_gaps"] == [long_text]

    memo = validate_research_memo(
        json.dumps(
            {
                "summary": long_text,
                "decision": "proceed",
                "six_dim_scores": [{"key": "industry", "score": 3, "confidence": 0.5, "note": long_text}],
                "conflicts": [long_text],
                "key_variables": [long_text],
                "risks": [long_text],
                "open_questions": [long_text],
            }
        ),
        TaskRequest(),
    )
    assert memo["summary"] == long_text
    assert memo["six_dim_scores"][0]["note"] == long_text
    assert memo["conflicts"] == [long_text]
    assert memo["key_variables"] == [long_text]

    risk = validate_memo(json.dumps({"summary": long_text, "risks": [long_text]}), TaskRequest())
    assert risk["summary"] == long_text
    assert risk["risks"] == [long_text]


def test_prompt_override_and_reset() -> None:
    task_id = "inst.research_memo"
    original = agent_store.get_effective_prompt(task_id, "default")[0]
    agent_store.save_prompt(task_id, "自定义提示词：只输出结论", updated_by=None)
    prompt, version = agent_store.get_effective_prompt(task_id, "default")
    assert prompt.startswith("自定义提示词")
    assert version != "0"
    history = agent_store.list_prompt_history(task_id)
    assert history and history[0]["action"] == "save"

    agent_store.reset_prompt(task_id)
    prompt, version = agent_store.get_effective_prompt(task_id, "default")
    assert prompt == "default"
    assert version == "0"


def test_memo_cache_hit_and_refresh(monkeypatch) -> None:
    tag = uuid.uuid4().hex[:8]
    with get_conn() as conn:
        org = conn.execute(
            "INSERT INTO inst_orgs (code, name_cn) VALUES (%s,%s) RETURNING id",
            (f"cache-{tag}", f"缓存测试机构 {tag}"),
        ).fetchone()
        org_id = int(org["id"])
        company = conn.execute(
            "INSERT INTO inst_company (org_id, symbol, name, market) "
            "VALUES (%s,%s,'缓存测试公司','CN') RETURNING id",
            (org_id, f"CAH{tag[:4].upper()}.SH"),
        ).fetchone()
        case = conn.execute(
            "INSERT INTO inst_research_case (org_id, company_id, case_no) VALUES (%s,%s,%s) RETURNING id",
            (org_id, int(company["id"]), f"CA-{tag}"),
        ).fetchone()
        conn.execute(
            "INSERT INTO inst_research_version "
            "(case_id, version_no, status, six_dim, conclusion, evidence_ids) "
            "VALUES (%s,1,'pending_review',%s,'有条件通过',%s)",
            (int(case["id"]), Jsonb([]), Jsonb([])),
        )
    calls = {"n": 0, "systems": []}

    def fake_ai(task_id, payload, system):
        calls["n"] += 1
        calls["systems"].append(system)
        return {"summary": "缓存摘要", "engine": "agent"}

    monkeypatch.setattr(svc, "_ai_task", fake_ai)
    first = svc.ai_research_memo(org_id, int(case["id"]))
    second = svc.ai_research_memo(org_id, int(case["id"]))
    assert first["memo"]["summary"] == "缓存摘要"
    assert second["cached"] is True
    assert calls["n"] == 1

    refreshed = svc.ai_research_memo(org_id, int(case["id"]), refresh=True)
    assert refreshed["cached"] is False
    assert calls["n"] == 2


def test_industry_agent_ai_failure_falls_back_without_raising(monkeypatch):
    from ai import router as ai_router

    monkeypatch.setattr(ai_router, "available_task", lambda _task: True)

    def boom(*_args, **_kwargs):
        raise RuntimeError("上游返回空内容")

    monkeypatch.setattr(ai_router, "run_task", boom)
    out = svc._run_industry_agent({"as_of": "2026-11-04", "company": {"symbol": "600519.SH"}})
    assert "error" in out
    assert "暂不可用" in out["error"]


def test_memo_survives_prompt_change_and_supports_peek(monkeypatch) -> None:
    tag = uuid.uuid4().hex[:8]
    with get_conn() as conn:
        org = conn.execute(
            "INSERT INTO inst_orgs (code, name_cn) VALUES (%s,%s) RETURNING id",
            (f"persist-{tag}", f"持久化测试机构 {tag}"),
        ).fetchone()
        org_id = int(org["id"])
        company = conn.execute(
            "INSERT INTO inst_company (org_id, symbol, name, market) "
            "VALUES (%s,%s,'持久化测试公司','CN') RETURNING id",
            (org_id, f"PST{tag[:4].upper()}.SH"),
        ).fetchone()
        case = conn.execute(
            "INSERT INTO inst_research_case (org_id, company_id, case_no) VALUES (%s,%s,%s) RETURNING id",
            (org_id, int(company["id"]), f"PS-{tag}"),
        ).fetchone()
        conn.execute(
            "INSERT INTO inst_research_version "
            "(case_id, version_no, status, six_dim, conclusion, evidence_ids) "
            "VALUES (%s,1,'pending_review',%s,'有条件通过',%s)",
            (int(case["id"]), Jsonb([]), Jsonb([])),
        )
    case_id = int(case["id"])
    calls = {"n": 0}

    def fake_ai(task_id, payload, system):
        calls["n"] += 1
        return {"summary": f"第 {calls['n']} 次结论", "engine": "agent"}

    monkeypatch.setattr(svc, "_ai_task", fake_ai)
    first = svc.ai_research_memo(org_id, case_id)
    assert first["cached"] is False
    assert calls["n"] == 1

    # 提示词改动后，旧结论仍然可读，不应重新调用模型。
    agent_store.save_prompt("inst.research_memo", "新的机构一页纸提示词", updated_by=None)
    try:
        stale = svc.ai_research_memo(org_id, case_id)
        assert stale["cached"] is True
        assert stale["stale"] is True
        assert stale["memo"]["summary"] == "第 1 次结论"
        assert calls["n"] == 1

        # 页面进入时的只读 peek：有持久化内容就直接返回，不生成。
        peek = svc.ai_research_memo(org_id, case_id, generate=False)
        assert peek["memo"]["summary"] == "第 1 次结论"
        assert calls["n"] == 1

        # 用户主动重新生成才覆盖。
        refreshed = svc.ai_research_memo(org_id, case_id, refresh=True)
        assert refreshed["cached"] is False
        assert refreshed["memo"]["summary"] == "第 2 次结论"
        assert calls["n"] == 2
    finally:
        agent_store.reset_prompt("inst.research_memo")


def test_rule_memo_is_persisted(monkeypatch) -> None:
    tag = uuid.uuid4().hex[:8]
    with get_conn() as conn:
        org = conn.execute(
            "INSERT INTO inst_orgs (code, name_cn) VALUES (%s,%s) RETURNING id",
            (f"rule-{tag}", f"规则落盘测试机构 {tag}"),
        ).fetchone()
        org_id = int(org["id"])
        company = conn.execute(
            "INSERT INTO inst_company (org_id, symbol, name, market) "
            "VALUES (%s,%s,'规则落盘测试公司','CN') RETURNING id",
            (org_id, f"RUL{tag[:4].upper()}.SH"),
        ).fetchone()
        case = conn.execute(
            "INSERT INTO inst_research_case (org_id, company_id, case_no) VALUES (%s,%s,%s) RETURNING id",
            (org_id, int(company["id"]), f"RU-{tag}"),
        ).fetchone()
        conn.execute(
            "INSERT INTO inst_research_version "
            "(case_id, version_no, status, six_dim, conclusion, evidence_ids) "
            "VALUES (%s,1,'pending_review',%s,'规则结论',%s)",
            (int(case["id"]), Jsonb([{"key": "financial", "summary": "现金流健康"}]), Jsonb([])),
        )
    case_id = int(case["id"])

    def unavailable(*_args, **_kwargs):
        raise svc.AiUnavailable("AI 未配置")

    monkeypatch.setattr(svc, "_ai_task", unavailable)
    first = svc.ai_research_memo(org_id, case_id)
    assert first["memo"]["engine"] == "rule"
    assert first["cached"] is False

    # 第二次进入直接读落盘结果，不再尝试模型。
    second = svc.ai_research_memo(org_id, case_id)
    assert second["cached"] is True
    assert second["memo"]["engine"] == "rule"

    peek = svc.ai_research_memo(org_id, case_id, generate=False)
    assert peek["memo"]["summary"] == first["memo"]["summary"]
