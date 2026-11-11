# -*- coding: utf-8 -*-
"""主观机构端业务门面（facade）。

按域拆分为：
  common / guards / stages       通用工具、审计与角色校验、六阶段状态机
  company_service                公司池与全局搜索
  research_service               立项、研究生成、六维、门禁、版本锁定
  debate_service                 多空辩论
  proposal_service               议案与三关审批
  exit_service                   退出案状态机
  execution_service              授权、预检、成交、对账
  portfolio_service              持仓、监控、论点、流水线与结果页
  ai_service                     AI 建议与 Agent 提示词

业务事实与状态机仍以本包为准；AI 只产生建议，不直接改状态。
硬约束在服务端校验：单股 ≤15%、交易后现金 ≥10%、版本一致、无有效批准不得授权。
授权是不可变快照；撤销写新行，不 UPDATE 旧行。

保留本模块是为了不破坏 `from services.institution.inst_service import ...` 的既有引用；
新代码请直接从对应域模块导入。
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
from typing import Any, Callable

from psycopg.types.json import Jsonb

from ai.runtime import agent_store
from ai.runtime.agent_store import (
    get_cached_output,
    get_effective_prompt,
    get_latest_output,
    input_hash as agent_input_hash,
    save_output,
)
from services.core.db import get_conn
from services.core.tenant import OrgScope
from . import repo
from services.institution.prompts import (
    CHAIRMAN_MEMO_PROMPT,
    PARTNER_MEMO_PROMPT,
    CHAT_PROMPT,
    INDUSTRY_PROMPT,
    DEBATE_PROMPT,
    DIMENSION_PROMPTS as _DIMENSION_PROMPTS,
    RESEARCH_MEMO_PROMPT,
    RISK_REVIEW_PROMPT,
    ROLE_PROMPTS as _ROLE_PROMPTS,
)
from services.institution import data_platform, inst_ai_store
from services.institution.report import render_research_report, report_filename
from services.marketdata import store as md

# 拆分后的公共部分（保持 inst_service 旧有名字可用，路由无需改动）
from .common import (  # noqa: F401
    _clip_brief,
    _evidence_grade,
    _hash,
    _iso,
    _j,
    _pc,
    _row_dict,
    _yi,
)
from .stages import (  # noqa: F401
    STAGE_BY_KEY,
    STAGE_BY_NO,
    STAGE_DEFS,
    _record_gate,
    _record_transition,
    _set_case_stage,
    _stage_def,
    _stage_payload,
)
from .guards import (  # noqa: F401
    AiUnavailable,
    POLICY_VERSION,
    _audit,
    _member,
    _require_role,
    _uid,
)
from .company_service import (  # noqa: F401
    DEFAULT_NAV,
    DEMO_COMPANIES,
    MAX_INDUSTRY_WEIGHT,
    MAX_SINGLE_WEIGHT,
    MIN_CASH_RATIO,
    _mapped_industry,
    _seed_companies,
    _sync_company_universe,
    ensure_and_seed,
    list_companies,
    search_companies,
    update_company_pool,
)
from .research_service import (  # noqa: F401
    DIMENSION_TASK_IDS,
    SIX_DIM_DEFS,
    _TERM_GLOSSARY,
    _VAGUE_REPLACEMENTS,
    _agent_payload,
    _apply_data_gate,
    _build_research,
    _clean_agent_text,
    _data_completeness,
    _derive_case_stage,
    _dim_status,
    _ensure_version_hash,
    _existing_case_id,
    _first_sentence,
    _score_fields,
    _history_summary,
    _idea_data_sufficiency,
    _idea_questions,
    _lock_company_case,
    _median,
    _merge_agent_results,
    _merge_industry,
    _net_debt_proxy,
    _overall_score,
    _peer_summary,
    _resample_bars,
    _run_dimension_agent,
    _run_dimension_agents,
    _run_industry_agent,
    _six_dim_list,
    _update_task_progress,
    company_bars,
    create_case,
    delete_case,
    evaluate_research_gate,
    export_research,
    generate_research,
    get_case,
    get_company,
    ideas_push,
    list_cases,
    lock_research,
    record_idea_decision,
    reopen_research,
    research_gate,
    review_research,
    review_research_dimension,
    start_research,
    start_research_job,
)
from .ai_service import (  # noqa: F401
    __all__,
    _ai_available,
    _ai_task,
    _apply_memo_data_gate,
    _chairman_context,
    _memo_metrics,
    _role_case_payload,
    _rule_memo,
    _sync_research_conclusion,
    ai_chairman_handover,
    ai_chairman_memo,
    ai_chairman_precheck,
    ai_chairman_simulate,
    ai_dimension_chat,
    ai_dimension_chat_history,
    ai_partner_memo,
    ai_research_memo,
    start_memo_job,
    ai_risk_review,
    ai_role_catalog,
    ai_role_run,
    institution_agent_catalog,
    institution_agent_prompt_history,
    list_audit,
    reset_institution_agent_prompt,
    save_institution_agent_prompt,
)
from .portfolio_service import (  # noqa: F401
    _pipeline_card,
    _position_for_symbol,
    _thesis_row,
    _validated_list,
    create_monitor_event,
    create_thesis,
    holding_detail,
    list_theses,
    monitor,
    overview,
    pipeline,
    playbook,
    portfolio,
    project_result,
    refresh_thesis,
    review_thesis,
    scan_holdings,
)
from .execution_service import (  # noqa: F401
    _execution_context,
    _record_blocked_execution,
    _record_execution_exception,
    approve_and_execute,
    authorization_for_proposal,
    authorize,
    execute_authorization,
    list_authorizations,
    list_execution_exceptions,
    precheck_execution,
    reconcile_authorization,
    resolve_execution_exception,
)
from .proposal_service import (  # noqa: F401
    STAGE_ROLE,
    _approval_rows,
    _approval_state,
    _authorization_summary,
    _clean_conditions,
    _current_version,
    _evidence_approval_check,
    _insert_approval,
    _issuer_key,
    _member_role_counts,
    _my_decision,
    _overall_score_for_case,
    _proposal_common,
    _proposal_progress,
    _proposal_row,
    _research_debate_summary,
    _risk_checks,
    _role_member_ids,
    _stage_summary,
    _stage_time,
    chairman_review,
    create_proposal,
    evaluate_proposal_gate,
    get_proposal,
    get_proposal_for_member,
    list_proposals,
    list_proposals_for_member,
    partner_review,
    proposal_advice,
    risk_check,
    submit_proposal,
)
from .debate_service import (  # noqa: F401
    _ai_debate,
    _debate_fallback,
    _evidence_payload,
    get_debate,
    start_debate,
    start_debate_job,
)
from .job_service import latest_job as latest_ai_job
from .exit_service import (  # noqa: F401
    _advance_exit_case,
    _exit_case_for_case,
    _exit_case_for_proposal,
    _transition_exit_case,
    create_exit_case,
    review_exit,
)

MAX_SINGLE_WEIGHT = 0.15
MAX_INDUSTRY_WEIGHT = 0.30
MIN_CASH_RATIO = 0.10

# ---------------------------------------------------------------- 种子

# ---------------------------------------------------------------- v3 流水线 / 结果页

# ---------------------------------------------------------------- 辩论

# ---------------------------------------------------------------- 退出案状态机

# ---------------------------------------------------------------- 执行前校验 / 对账 / 异常

# ---------------------------------------------------------------- AI Chairman 模式
