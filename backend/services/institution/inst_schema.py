# -*- coding: utf-8 -*-
"""主观机构端业务库表（PostgreSQL）。

设计口径见 `docs/数据设计/机构端与手机端-数据接入与库表设计-v0.1.md` §6.5。
核心约束：
- 研究、议案、审批、授权全部版本化；授权是不可变快照，只增不改。
- 提案人不得审批自己的议案；硬阻断在服务端校验，前端隐藏不算安全边界。
- 领域审计只增不改。
"""
from __future__ import annotations

from services.core.db import get_conn

DDL: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS inst_company (
      id               BIGSERIAL PRIMARY KEY,
      org_id           BIGINT NOT NULL REFERENCES inst_orgs(id) ON DELETE CASCADE,
      symbol           TEXT NOT NULL,
      name             TEXT NOT NULL,
      market           TEXT NOT NULL DEFAULT 'CN',
      industry         TEXT,
      ref_price        DOUBLE PRECISION,
      research_points  JSONB,
      tags             JSONB,
      pending_items    JSONB,
      data_status      TEXT NOT NULL DEFAULT 'missing',
      pool_status      TEXT NOT NULL DEFAULT 'research',
      drop_reason      TEXT,
      owner_member_id  BIGINT REFERENCES inst_members(id) ON DELETE SET NULL,
      created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      CONSTRAINT inst_company_market_chk CHECK (market IN ('CN', 'US', 'HK')),
      CONSTRAINT inst_company_data_status_chk CHECK (data_status IN ('real', 'partial', 'missing', 'demo')),
      CONSTRAINT inst_company_pool_status_chk CHECK (pool_status IN ('research', 'watch', 'dropped')),
      CONSTRAINT inst_company_org_symbol_key UNIQUE (org_id, market, symbol)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS inst_portfolio (
      id            BIGSERIAL PRIMARY KEY,
      org_id        BIGINT NOT NULL REFERENCES inst_orgs(id) ON DELETE CASCADE,
      code          TEXT NOT NULL,
      name          TEXT NOT NULL,
      base_currency TEXT NOT NULL DEFAULT 'CNY',
      nav           DOUBLE PRECISION NOT NULL DEFAULT 10000000,
      cash          DOUBLE PRECISION NOT NULL DEFAULT 10000000,
      created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      CONSTRAINT inst_portfolio_org_code_key UNIQUE (org_id, code)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS inst_research_case (
      id          BIGSERIAL PRIMARY KEY,
      org_id      BIGINT NOT NULL REFERENCES inst_orgs(id) ON DELETE CASCADE,
      company_id  BIGINT NOT NULL REFERENCES inst_company(id) ON DELETE CASCADE,
      case_no     TEXT NOT NULL,
      stage       TEXT NOT NULL DEFAULT 'draft',
      created_by  BIGINT REFERENCES inst_members(id) ON DELETE SET NULL,
      created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      CONSTRAINT inst_research_case_stage_chk CHECK (
        stage IN ('draft','planning','researching','package_ready','pending_review','approved','debate','proposal','closed')
      ),
      CONSTRAINT inst_research_case_no_key UNIQUE (org_id, case_no)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS inst_research_task (
      id          BIGSERIAL PRIMARY KEY,
      case_id     BIGINT NOT NULL REFERENCES inst_research_case(id) ON DELETE CASCADE,
      task_key    TEXT NOT NULL,
      title       TEXT NOT NULL,
      agent       TEXT,
      status      TEXT NOT NULL DEFAULT 'pending',
      progress    SMALLINT NOT NULL DEFAULT 0,
      result      JSONB,
      created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      CONSTRAINT inst_research_task_status_chk CHECK (
        status IN ('pending','running','needs_review','done','failed')
      ),
      CONSTRAINT inst_research_task_case_key UNIQUE (case_id, task_key)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS inst_research_version (
      id              BIGSERIAL PRIMARY KEY,
      case_id         BIGINT NOT NULL REFERENCES inst_research_case(id) ON DELETE CASCADE,
      version_no      INTEGER NOT NULL,
      status          TEXT NOT NULL DEFAULT 'draft',
      six_dim         JSONB,
      valuation       JSONB,
      conclusion      TEXT,
      assumptions     JSONB,
      counter_evidence JSONB,
      open_questions  JSONB,
      evidence_ids    JSONB,
      created_by      BIGINT REFERENCES inst_members(id) ON DELETE SET NULL,
      created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      frozen_at       TIMESTAMPTZ,
      approved_by     BIGINT REFERENCES inst_members(id) ON DELETE SET NULL,
      approved_at     TIMESTAMPTZ,
      CONSTRAINT inst_research_version_status_chk CHECK (
        status IN ('draft','pending_review','approved','changed','rejected')
      ),
      CONSTRAINT inst_research_version_case_no_key UNIQUE (case_id, version_no)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS inst_evidence (
      id            BIGSERIAL PRIMARY KEY,
      org_id        BIGINT NOT NULL REFERENCES inst_orgs(id) ON DELETE CASCADE,
      case_id       BIGINT REFERENCES inst_research_case(id) ON DELETE CASCADE,
      version_id    BIGINT REFERENCES inst_research_version(id) ON DELETE SET NULL,
      doc_item_id   BIGINT,
      evidence_type TEXT NOT NULL DEFAULT 'fact',
      title         TEXT NOT NULL,
      quote         TEXT,
      source        TEXT NOT NULL,
      as_of         DATE,
      hash          TEXT,
      added_by      BIGINT REFERENCES inst_members(id) ON DELETE SET NULL,
      created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      CONSTRAINT inst_evidence_type_chk CHECK (
        evidence_type IN ('fact','filing','financial','market','news','research','counter')
      )
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS inst_debate_session (
      id                  BIGSERIAL PRIMARY KEY,
      case_id             BIGINT NOT NULL REFERENCES inst_research_case(id) ON DELETE CASCADE,
      research_version_id BIGINT REFERENCES inst_research_version(id) ON DELETE SET NULL,
      status              TEXT NOT NULL DEFAULT 'pending',
      agenda_step         SMALLINT NOT NULL DEFAULT 0,
      factpack            JSONB,
      factpack_hash       TEXT,
      conclusion          TEXT,
      started_at          TIMESTAMPTZ,
      ended_at            TIMESTAMPTZ,
      CONSTRAINT inst_debate_status_chk CHECK (status IN ('pending','running','completed','aborted'))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS inst_debate_argument (
      id           BIGSERIAL PRIMARY KEY,
      session_id   BIGINT NOT NULL REFERENCES inst_debate_session(id) ON DELETE CASCADE,
      side         TEXT NOT NULL,
      round        SMALLINT NOT NULL DEFAULT 1,
      claim        TEXT NOT NULL,
      evidence_ids JSONB,
      confidence   DOUBLE PRECISION,
      falsifier    TEXT,
      valid        BOOLEAN NOT NULL DEFAULT TRUE,
      created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      CONSTRAINT inst_debate_side_chk CHECK (side IN ('bull','bear','chair'))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS inst_proposal (
      id                 BIGSERIAL PRIMARY KEY,
      org_id              BIGINT NOT NULL REFERENCES inst_orgs(id) ON DELETE CASCADE,
      case_id             BIGINT NOT NULL REFERENCES inst_research_case(id) ON DELETE CASCADE,
      company_id          BIGINT NOT NULL REFERENCES inst_company(id) ON DELETE CASCADE,
      direction           TEXT NOT NULL DEFAULT 'buy',
      target_weight       DOUBLE PRECISION NOT NULL DEFAULT 0,
      current_version_no  INTEGER NOT NULL DEFAULT 0,
      status              TEXT NOT NULL DEFAULT 'draft',
      created_by          BIGINT REFERENCES inst_members(id) ON DELETE SET NULL,
      created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      CONSTRAINT inst_proposal_direction_chk CHECK (direction IN ('buy','sell','exit')),
      CONSTRAINT inst_proposal_status_chk CHECK (
        status IN ('draft','partner_review','chairman_review','risk_precheck','authorized','executed','rejected','frozen')
      )
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS inst_proposal_version (
      id            BIGSERIAL PRIMARY KEY,
      proposal_id   BIGINT NOT NULL REFERENCES inst_proposal(id) ON DELETE CASCADE,
      version_no    INTEGER NOT NULL,
      snapshot      JSONB NOT NULL,
      status        TEXT NOT NULL DEFAULT 'draft',
      created_by    BIGINT REFERENCES inst_members(id) ON DELETE SET NULL,
      created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      CONSTRAINT inst_proposal_version_status_chk CHECK (
        status IN ('draft','partner_submitted','chairman_approved','risk_passed','authorized','revoked','rejected')
      ),
      CONSTRAINT inst_proposal_version_no_key UNIQUE (proposal_id, version_no)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS inst_approval (
      id                  BIGSERIAL PRIMARY KEY,
      proposal_version_id BIGINT NOT NULL REFERENCES inst_proposal_version(id) ON DELETE CASCADE,
      step                TEXT NOT NULL,
      approver_member_id  BIGINT REFERENCES inst_members(id) ON DELETE SET NULL,
      decision            TEXT NOT NULL,
      comment             TEXT,
      policy_version      TEXT NOT NULL DEFAULT 'demo-v1',
      decided_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      CONSTRAINT inst_approval_step_chk CHECK (step IN ('partner','chairman','risk_precheck')),
      CONSTRAINT inst_approval_decision_chk CHECK (decision IN ('approve','conditional','reject','return','veto','pass','block')),
      CONSTRAINT inst_approval_version_step_key UNIQUE (proposal_version_id, step)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS inst_authorization (
      id                  BIGSERIAL PRIMARY KEY,
      proposal_version_id BIGINT NOT NULL REFERENCES inst_proposal_version(id) ON DELETE CASCADE,
      approval_id         BIGINT REFERENCES inst_approval(id) ON DELETE SET NULL,
      snapshot            JSONB NOT NULL,
      status              TEXT NOT NULL DEFAULT 'qualified',
      issued_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      revoked_at          TIMESTAMPTZ,
      revoke_reason       TEXT,
      CONSTRAINT inst_authorization_status_chk CHECK (status IN ('qualified','revoked','filled','expired'))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS inst_order (
      id               BIGSERIAL PRIMARY KEY,
      authorization_id BIGINT NOT NULL REFERENCES inst_authorization(id) ON DELETE RESTRICT,
      portfolio_id     BIGINT NOT NULL REFERENCES inst_portfolio(id) ON DELETE RESTRICT,
      symbol           TEXT NOT NULL,
      side             TEXT NOT NULL,
      qty              DOUBLE PRECISION NOT NULL,
      price            DOUBLE PRECISION NOT NULL,
      status           TEXT NOT NULL DEFAULT 'submitted',
      idempotency_key  TEXT NOT NULL,
      created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      filled_at        TIMESTAMPTZ,
      CONSTRAINT inst_order_side_chk CHECK (side IN ('buy','sell')),
      CONSTRAINT inst_order_status_chk CHECK (status IN ('submitted','filled','partial','rejected','cancelled')),
      CONSTRAINT inst_order_auth_key UNIQUE (authorization_id),
      CONSTRAINT inst_order_idem_key UNIQUE (idempotency_key)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS inst_fill (
      id         BIGSERIAL PRIMARY KEY,
      order_id   BIGINT NOT NULL REFERENCES inst_order(id) ON DELETE CASCADE,
      qty        DOUBLE PRECISION NOT NULL,
      price      DOUBLE PRECISION NOT NULL,
      fee        DOUBLE PRECISION NOT NULL DEFAULT 0,
      filled_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS inst_position_snapshot (
      id           BIGSERIAL PRIMARY KEY,
      portfolio_id BIGINT NOT NULL REFERENCES inst_portfolio(id) ON DELETE CASCADE,
      symbol       TEXT NOT NULL,
      qty          DOUBLE PRECISION NOT NULL,
      cost         DOUBLE PRECISION NOT NULL,
      market_value DOUBLE PRECISION NOT NULL,
      weight       DOUBLE PRECISION NOT NULL,
      as_of        DATE NOT NULL,
      CONSTRAINT inst_position_snapshot_key UNIQUE (portfolio_id, symbol, as_of)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS inst_monitor_event (
      id          BIGSERIAL PRIMARY KEY,
      org_id      BIGINT NOT NULL REFERENCES inst_orgs(id) ON DELETE CASCADE,
      company_id  BIGINT REFERENCES inst_company(id) ON DELETE SET NULL,
      position_id BIGINT REFERENCES inst_position_snapshot(id) ON DELETE SET NULL,
      type        TEXT NOT NULL,
      severity    TEXT NOT NULL DEFAULT 'info',
      status      TEXT NOT NULL DEFAULT 'open',
      detail      JSONB,
      created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      CONSTRAINT inst_monitor_severity_chk CHECK (severity IN ('info','warning','critical')),
      CONSTRAINT inst_monitor_status_chk CHECK (status IN ('open','reviewing','closed'))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS inst_exit_case (
      id          BIGSERIAL PRIMARY KEY,
      org_id      BIGINT NOT NULL REFERENCES inst_orgs(id) ON DELETE CASCADE,
      company_id  BIGINT NOT NULL REFERENCES inst_company(id) ON DELETE CASCADE,
      position_id BIGINT REFERENCES inst_position_snapshot(id) ON DELETE SET NULL,
      reason_type TEXT NOT NULL,
      memo        TEXT,
      status      TEXT NOT NULL DEFAULT 'draft',
      proposal_id BIGINT REFERENCES inst_proposal(id) ON DELETE SET NULL,
      created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      CONSTRAINT inst_exit_reason_chk CHECK (
        reason_type IN ('thesis_invalid','valuation','better_allocation','portfolio_constraint','other')
      ),
      CONSTRAINT inst_exit_status_chk CHECK (status IN ('draft','submitted','approved','rejected','closed'))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS inst_audit_event (
      id              BIGSERIAL PRIMARY KEY,
      org_id          BIGINT NOT NULL REFERENCES inst_orgs(id) ON DELETE CASCADE,
      actor_member_id BIGINT REFERENCES inst_members(id) ON DELETE SET NULL,
      action          TEXT NOT NULL,
      object_type     TEXT NOT NULL,
      object_id       BIGINT,
      before          JSONB,
      after           JSONB,
      policy_version  TEXT NOT NULL DEFAULT 'demo-v1',
      ip              TEXT,
      created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
)

INDEXES: tuple[str, ...] = (
    "CREATE INDEX IF NOT EXISTS idx_inst_company_org ON inst_company (org_id, pool_status)",
    "CREATE INDEX IF NOT EXISTS idx_inst_company_symbol ON inst_company (symbol, market)",
    "CREATE INDEX IF NOT EXISTS idx_inst_research_case_company ON inst_research_case (company_id, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_inst_research_version_case ON inst_research_version (case_id, version_no DESC)",
    "CREATE INDEX IF NOT EXISTS idx_inst_evidence_case ON inst_evidence (case_id, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_inst_debate_session_case ON inst_debate_session (case_id, started_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_inst_debate_argument_session ON inst_debate_argument (session_id, side, round)",
    "CREATE INDEX IF NOT EXISTS idx_inst_proposal_org ON inst_proposal (org_id, status, updated_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_inst_proposal_version_prop ON inst_proposal_version (proposal_id, version_no DESC)",
    "CREATE INDEX IF NOT EXISTS idx_inst_authorization_status ON inst_authorization (status, issued_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_inst_position_portfolio ON inst_position_snapshot (portfolio_id, as_of DESC)",
    "CREATE INDEX IF NOT EXISTS idx_inst_monitor_org ON inst_monitor_event (org_id, status, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_inst_audit_org ON inst_audit_event (org_id, created_at DESC)",
)


def ensure_inst_business_schema(*, include_indexes: bool = True) -> None:
    with get_conn() as conn:
        for ddl in DDL:
            conn.execute(ddl)
        if include_indexes:
            for idx in INDEXES:
                conn.execute(idx)


__all__ = ["DDL", "INDEXES", "ensure_inst_business_schema"]
