# -*- coding: utf-8 -*-
"""主观机构端业务库表（PostgreSQL）。

设计口径见 `docs/数据设计/机构端与手机端-数据接入与库表设计-v0.1.md` §6.5。
核心约束：
- 研究、议案、审批、授权全部版本化；授权是不可变快照，只增不改。
- 提案人不得审批自己的议案；硬阻断在服务端校验，前端隐藏不算安全边界。
- 领域审计只增不改。
"""
from __future__ import annotations

import json

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
    CREATE TABLE IF NOT EXISTS inst_idea_decision (
      id                 BIGSERIAL PRIMARY KEY,
      org_id             BIGINT NOT NULL REFERENCES inst_orgs(id) ON DELETE CASCADE,
      company_id         BIGINT NOT NULL REFERENCES inst_company(id) ON DELETE CASCADE,
      source             TEXT NOT NULL,
      action             TEXT NOT NULL,
      reason             TEXT NOT NULL,
      circle_confirmed   BOOLEAN NOT NULL DEFAULT FALSE,
      data_sufficiency   TEXT,
      actor_member_id    BIGINT REFERENCES inst_members(id) ON DELETE SET NULL,
      created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      CONSTRAINT inst_idea_decision_source_chk CHECK (source IN ('push','watch','holdings')),
      CONSTRAINT inst_idea_decision_action_chk CHECK (action IN ('initiate','watch','reject')),
      CONSTRAINT inst_idea_decision_sufficiency_chk CHECK (
        data_sufficiency IS NULL OR data_sufficiency IN ('sufficient','partial','missing','insufficient')
      )
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
      stage_no    SMALLINT,
      stage_key   TEXT,
      stage_gate  JSONB,
      stage_locked_at TIMESTAMPTZ,
      stage_state TEXT NOT NULL DEFAULT 'in_progress',
      terminal_reason TEXT,
      reopened_at TIMESTAMPTZ,
      created_by  BIGINT REFERENCES inst_members(id) ON DELETE SET NULL,
      created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      CONSTRAINT inst_research_case_stage_chk CHECK (
        stage IN ('draft','planning','researching','package_ready','pending_review','approved','debate','proposal','closed')
      ),
      CONSTRAINT inst_research_case_stage_no_chk CHECK (stage_no IS NULL OR stage_no BETWEEN 0 AND 5),
      CONSTRAINT inst_research_case_no_key UNIQUE (org_id, case_no)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS inst_case_transition (
      id              BIGSERIAL PRIMARY KEY,
      org_id          BIGINT NOT NULL REFERENCES inst_orgs(id) ON DELETE CASCADE,
      case_id         BIGINT NOT NULL REFERENCES inst_research_case(id) ON DELETE CASCADE,
      from_stage      SMALLINT,
      to_stage        SMALLINT NOT NULL,
      from_state      TEXT,
      to_state        TEXT NOT NULL DEFAULT 'in_progress',
      trigger         TEXT NOT NULL,
      actor_member_id BIGINT REFERENCES inst_members(id) ON DELETE SET NULL,
      object_type     TEXT,
      object_id       BIGINT,
      detail          JSONB,
      created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS inst_gate_run (
      id          BIGSERIAL PRIMARY KEY,
      org_id      BIGINT NOT NULL REFERENCES inst_orgs(id) ON DELETE CASCADE,
      case_id     BIGINT REFERENCES inst_research_case(id) ON DELETE CASCADE,
      gate_key    TEXT NOT NULL,
      status      TEXT NOT NULL,
      checks      JSONB,
      object_type TEXT,
      object_id   BIGINT,
      created_by  BIGINT REFERENCES inst_members(id) ON DELETE SET NULL,
      created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      CONSTRAINT inst_gate_run_status_chk CHECK (status IN ('pass','warn','block'))
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
      industry_analysis JSONB,
      dim_reviews     JSONB NOT NULL DEFAULT '{}'::jsonb,
      content_hash    TEXT,
      cutoff          DATE,
      created_by      BIGINT REFERENCES inst_members(id) ON DELETE SET NULL,
      created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      frozen_at       TIMESTAMPTZ,
      locked_at       TIMESTAMPTZ,
      superseded_at   TIMESTAMPTZ,
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
      grade         TEXT NOT NULL DEFAULT 'D',
      title         TEXT NOT NULL,
      quote         TEXT,
      source        TEXT NOT NULL,
      as_of         DATE,
      event_time    DATE,
      available_time DATE,
      document_id   TEXT,
      page_ref      TEXT,
      source_uri    TEXT,
      cutoff        DATE,
      hash          TEXT,
      added_by      BIGINT REFERENCES inst_members(id) ON DELETE SET NULL,
      created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      CONSTRAINT inst_evidence_type_chk CHECK (
        evidence_type IN ('fact','filing','financial','market','news','research','counter')
      ),
      CONSTRAINT inst_evidence_grade_chk CHECK (grade IN ('A','B','C','D'))
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
      claim_id     TEXT,
      claim_type   TEXT NOT NULL DEFAULT 'inference',
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
    CREATE TABLE IF NOT EXISTS inst_evidence_check (
      id           BIGSERIAL PRIMARY KEY,
      session_id   BIGINT NOT NULL REFERENCES inst_debate_session(id) ON DELETE CASCADE,
      claim_id     TEXT NOT NULL,
      evidence_id  BIGINT NOT NULL REFERENCES inst_evidence(id) ON DELETE CASCADE,
      status       TEXT NOT NULL,
      grade        TEXT,
      issues       JSONB,
      checked_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      CONSTRAINT inst_evidence_check_status_chk CHECK (
        status IN ('verified','partially_verified','unverified','contradicted')
      ),
      CONSTRAINT inst_evidence_check_session_claim_ev_key UNIQUE (session_id, claim_id, evidence_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS inst_ai_chat_message (
      id                BIGSERIAL PRIMARY KEY,
      org_id            BIGINT NOT NULL REFERENCES inst_orgs(id) ON DELETE CASCADE,
      case_id           BIGINT NOT NULL REFERENCES inst_research_case(id) ON DELETE CASCADE,
      dim_key           TEXT NOT NULL,
      user_id           BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      member_id         BIGINT REFERENCES inst_members(id) ON DELETE SET NULL,
      role              TEXT NOT NULL,
      content           TEXT NOT NULL,
      client_message_id TEXT,
      created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      CONSTRAINT inst_ai_chat_role_chk CHECK (role IN ('user','assistant'))
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
      locked_at           TIMESTAMPTZ,
      stale_at            TIMESTAMPTZ,
      stale_reason        TEXT,
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
      locked_at     TIMESTAMPTZ,
      lock_hash     TEXT,
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
      policy_version      TEXT NOT NULL DEFAULT 'inst-policy-v1',
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
      case_id     BIGINT REFERENCES inst_research_case(id) ON DELETE SET NULL,
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
    ALTER TABLE inst_exit_case DROP CONSTRAINT IF EXISTS inst_exit_status_chk
    """,
    """
    ALTER TABLE inst_exit_case ADD CONSTRAINT inst_exit_status_chk
      CHECK (status IN ('draft','submitted','approved','rejected','closed','cancelled'))
    """,
    """
    CREATE OR REPLACE FUNCTION inst_audit_event_immutable() RETURNS trigger AS $$
    BEGIN
      RAISE EXCEPTION 'inst_audit_event 是只增不改的审计表（WORM）';
    END;
    $$ LANGUAGE plpgsql
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
      policy_version  TEXT NOT NULL DEFAULT 'inst-policy-v1',
      ip              TEXT,
      created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS inst_thesis_ledger (
      id               BIGSERIAL PRIMARY KEY,
      org_id           BIGINT NOT NULL REFERENCES inst_orgs(id) ON DELETE CASCADE,
      company_id       BIGINT NOT NULL REFERENCES inst_company(id) ON DELETE CASCADE,
      proposal_id      BIGINT REFERENCES inst_proposal(id) ON DELETE SET NULL,
      symbol           TEXT NOT NULL,
      thesis           TEXT NOT NULL,
      key_assumptions  JSONB,
      kpis             JSONB,
      falsifiers       JSONB,
      review_due       DATE,
      status           TEXT NOT NULL DEFAULT 'active',
      created_by       BIGINT REFERENCES inst_members(id) ON DELETE SET NULL,
      created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      CONSTRAINT inst_thesis_status_chk CHECK (status IN ('active','reviewed','invalidated','closed'))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS inst_thesis_review (
      id                 BIGSERIAL PRIMARY KEY,
      ledger_id          BIGINT NOT NULL REFERENCES inst_thesis_ledger(id) ON DELETE CASCADE,
      reviewer_member_id BIGINT REFERENCES inst_members(id) ON DELETE SET NULL,
      kpi_status         TEXT NOT NULL,
      conclusion         TEXT NOT NULL,
      note               TEXT,
      created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      CONSTRAINT inst_thesis_kpi_status_chk CHECK (kpi_status IN ('on_track','at_risk','broken')),
      CONSTRAINT inst_thesis_conclusion_chk CHECK (conclusion IN ('hold','reduce','exit','invalidate'))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS inst_execution_exception (
      id               BIGSERIAL PRIMARY KEY,
      org_id           BIGINT NOT NULL REFERENCES inst_orgs(id) ON DELETE CASCADE,
      authorization_id BIGINT REFERENCES inst_authorization(id) ON DELETE CASCADE,
      order_id         BIGINT REFERENCES inst_order(id) ON DELETE SET NULL,
      type             TEXT NOT NULL,
      detail           TEXT,
      status           TEXT NOT NULL DEFAULT 'open',
      resolution       TEXT,
      resolved_by      BIGINT REFERENCES inst_members(id) ON DELETE SET NULL,
      resolved_at      TIMESTAMPTZ,
      created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      CONSTRAINT inst_exc_status_chk CHECK (status IN ('open','resolved','ignored'))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS inst_exit_review (
      id                 BIGSERIAL PRIMARY KEY,
      exit_case_id       BIGINT NOT NULL UNIQUE REFERENCES inst_exit_case(id) ON DELETE CASCADE,
      realized_return    DOUBLE PRECISION,
      holding_days       INTEGER,
      thesis_verdict     TEXT NOT NULL,
      lessons            TEXT,
      reviewer_member_id BIGINT REFERENCES inst_members(id) ON DELETE SET NULL,
      created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      CONSTRAINT inst_exit_verdict_chk CHECK (thesis_verdict IN ('right','wrong','mixed'))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS inst_ai_job (
      id          BIGSERIAL PRIMARY KEY,
      org_id      BIGINT NOT NULL,
      case_id     BIGINT NOT NULL,
      kind        TEXT NOT NULL,
      status      TEXT NOT NULL DEFAULT 'running',
      progress    INTEGER NOT NULL DEFAULT 0,
      detail      TEXT,
      result      JSONB,
      error       TEXT,
      created_by  BIGINT,
      started_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      finished_at TIMESTAMPTZ,
      updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      CONSTRAINT inst_ai_job_status_chk CHECK (status IN ('running','done','failed'))
    )
    """,
)

INDEXES: tuple[str, ...] = (
    "CREATE INDEX IF NOT EXISTS idx_inst_company_org ON inst_company (org_id, pool_status)",
    "CREATE INDEX IF NOT EXISTS idx_inst_company_symbol ON inst_company (symbol, market)",
    "CREATE INDEX IF NOT EXISTS idx_inst_idea_decision_company ON inst_idea_decision (company_id, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_inst_research_case_company ON inst_research_case (company_id, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_inst_research_case_org_company ON inst_research_case (org_id, company_id, updated_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_inst_research_case_stage ON inst_research_case (org_id, stage_no, updated_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_inst_case_transition_case ON inst_case_transition (case_id, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_inst_gate_run_case ON inst_gate_run (case_id, gate_key, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_inst_research_version_case ON inst_research_version (case_id, version_no DESC)",
    "CREATE INDEX IF NOT EXISTS idx_inst_proposal_stale ON inst_proposal (org_id, stale_at)",
    "CREATE INDEX IF NOT EXISTS idx_inst_proposal_case_status ON inst_proposal (case_id, status)",
    "CREATE INDEX IF NOT EXISTS idx_inst_evidence_case ON inst_evidence (case_id, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_inst_debate_session_case ON inst_debate_session (case_id, started_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_inst_debate_argument_session ON inst_debate_argument (session_id, side, round)",
    "CREATE INDEX IF NOT EXISTS idx_inst_ai_job_case ON inst_ai_job (case_id, kind, id DESC)",
    "CREATE INDEX IF NOT EXISTS idx_inst_evidence_check_session ON inst_evidence_check (session_id, claim_id)",
    "CREATE INDEX IF NOT EXISTS idx_inst_ai_chat_thread ON inst_ai_chat_message (org_id, case_id, dim_key, user_id, id)",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_inst_ai_chat_client_msg ON inst_ai_chat_message "
    "(org_id, case_id, dim_key, user_id, client_message_id) WHERE client_message_id IS NOT NULL",
    "CREATE INDEX IF NOT EXISTS idx_inst_proposal_org ON inst_proposal (org_id, status, updated_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_inst_proposal_version_prop ON inst_proposal_version (proposal_id, version_no DESC)",
    "CREATE INDEX IF NOT EXISTS idx_inst_authorization_status ON inst_authorization (status, issued_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_inst_authorization_pv ON inst_authorization (proposal_version_id, status)",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_inst_approval_version_step_approver "
    "ON inst_approval (proposal_version_id, step, approver_member_id)",
    "CREATE INDEX IF NOT EXISTS idx_inst_position_portfolio ON inst_position_snapshot (portfolio_id, as_of DESC)",
    "CREATE INDEX IF NOT EXISTS idx_inst_monitor_org ON inst_monitor_event (org_id, status, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_inst_audit_org ON inst_audit_event (org_id, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_inst_thesis_org ON inst_thesis_ledger (org_id, status, review_due)",
    "CREATE INDEX IF NOT EXISTS idx_inst_thesis_review_ledger ON inst_thesis_review (ledger_id, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_inst_exc_org ON inst_execution_exception (org_id, status, created_at DESC)",
)


def _backfill_case_stages(conn) -> None:
    """把旧 case 幂等映射到 v3 阶段；只补空值，不覆盖新流程写入。"""
    stage_keys = {
        0: "find",
        1: "research",
        2: "debate",
        3: "approve",
        4: "execute",
        5: "manage",
    }
    gates = {
        0: "机会来源",
        1: "研究定稿",
        2: "议案锁定",
        3: "三关审批",
        4: "授权执行",
        5: "监控 / 退出",
    }
    rows = conn.execute(
        """
        SELECT c.id, c.org_id, c.stage_no, c.stage_key, co.symbol
          FROM inst_research_case c
          JOIN inst_company co ON co.id = c.company_id
         WHERE c.stage_no IS NULL OR c.stage_key IS NULL
         ORDER BY c.id
        """
    ).fetchall()
    for row in rows:
        case_id = int(row["id"])
        org_id = int(row["org_id"])
        symbol = str(row.get("symbol") or "")
        stage_no = row.get("stage_no")
        if stage_no is None:
            has_position = conn.execute(
                """
                SELECT 1 FROM inst_position_snapshot ps
                  JOIN inst_portfolio p ON p.id = ps.portfolio_id
                 WHERE p.org_id=%s AND ps.symbol=%s AND ps.qty > 0
                 LIMIT 1
                """,
                (org_id, symbol),
            ).fetchone()
            has_authorization = conn.execute(
                """
                SELECT 1 FROM inst_authorization a
                  JOIN inst_proposal_version pv ON pv.id = a.proposal_version_id
                  JOIN inst_proposal p ON p.id = pv.proposal_id
                 WHERE p.case_id=%s AND a.status IN ('qualified','filled')
                 LIMIT 1
                """,
                (case_id,),
            ).fetchone()
            submitted = conn.execute(
                """
                SELECT 1 FROM inst_proposal
                 WHERE case_id=%s
                   AND status IN ('partner_review','risk_precheck','chairman_review','authorized','executed')
                 LIMIT 1
                """,
                (case_id,),
            ).fetchone()
            approved = conn.execute(
                "SELECT 1 FROM inst_research_version WHERE case_id=%s AND status='approved' LIMIT 1",
                (case_id,),
            ).fetchone()
            if has_position:
                stage_no = 5
            elif has_authorization:
                stage_no = 4
            elif submitted:
                stage_no = 3
            elif approved:
                stage_no = 2
            else:
                stage_no = 1
        stage_no = int(stage_no)
        conn.execute(
            """
            UPDATE inst_research_case
               SET stage_no=%s,
                   stage_key=%s,
                   stage_gate=COALESCE(stage_gate, %s::jsonb),
                   stage_locked_at=COALESCE(stage_locked_at, CASE WHEN %s >= 2 THEN updated_at END)
             WHERE id=%s
            """,
            (
                stage_no,
                stage_keys.get(stage_no, "research"),
                json.dumps({"stage_no": stage_no, "gate": gates.get(stage_no, "研究定稿")}, ensure_ascii=False),
                stage_no,
                case_id,
            ),
        )


def ensure_inst_business_schema(*, include_indexes: bool = True) -> None:
    with get_conn() as conn:
        # 多 worker 同时启动时串行化 DDL，避免争用 ACCESS EXCLUSIVE 锁。
        conn.execute("SELECT pg_advisory_xact_lock(7400)")
        for ddl in DDL:
            conn.execute(ddl)
        # 兼容已存在的旧表：补退出案关联的研究案。
        conn.execute(
            "ALTER TABLE inst_exit_case ADD COLUMN IF NOT EXISTS case_id BIGINT "
            "REFERENCES inst_research_case(id) ON DELETE SET NULL"
        )
        # 立项三问资料枚举对齐 11.9 Prompt 规范：insufficient 取代 missing。
        conn.execute(
            "ALTER TABLE inst_idea_decision DROP CONSTRAINT IF EXISTS inst_idea_decision_sufficiency_chk"
        )
        conn.execute(
            "ALTER TABLE inst_idea_decision ADD CONSTRAINT inst_idea_decision_sufficiency_chk "
            "CHECK (data_sufficiency IS NULL OR data_sufficiency IN "
            "('sufficient','partial','missing','insufficient'))"
        )
        # 逐维审核记录：{dim_key: {decision, comment, reviewer_member_id, at}}
        conn.execute(
            "ALTER TABLE inst_research_version ADD COLUMN IF NOT EXISTS "
            "dim_reviews JSONB NOT NULL DEFAULT '{}'::jsonb"
        )
        # B2 证据可信层：旧库补列，保留已有证据（默认 D 级，需人工核验）。
        for column, ddl in (
            ("grade", "TEXT NOT NULL DEFAULT 'D'"),
            ("event_time", "DATE"),
            ("available_time", "DATE"),
            ("document_id", "TEXT"),
            ("page_ref", "TEXT"),
            ("source_uri", "TEXT"),
            ("cutoff", "DATE"),
        ):
            conn.execute(f"ALTER TABLE inst_evidence ADD COLUMN IF NOT EXISTS {column} {ddl}")
        conn.execute("ALTER TABLE inst_research_version ADD COLUMN IF NOT EXISTS industry_analysis JSONB")
        conn.execute("ALTER TABLE inst_research_version ADD COLUMN IF NOT EXISTS content_hash TEXT")
        conn.execute("ALTER TABLE inst_research_version ADD COLUMN IF NOT EXISTS cutoff DATE")
        # v3 阶段机与三次锁定：研究、议案、授权各自有不可回写的锁定时间。
        conn.execute("ALTER TABLE inst_research_case ADD COLUMN IF NOT EXISTS stage_no SMALLINT")
        conn.execute("ALTER TABLE inst_research_case ADD COLUMN IF NOT EXISTS stage_key TEXT")
        conn.execute("ALTER TABLE inst_research_case ADD COLUMN IF NOT EXISTS stage_gate JSONB")
        conn.execute("ALTER TABLE inst_research_case ADD COLUMN IF NOT EXISTS stage_locked_at TIMESTAMPTZ")
        conn.execute("ALTER TABLE inst_research_case ADD COLUMN IF NOT EXISTS stage_state TEXT NOT NULL DEFAULT 'in_progress'")
        conn.execute("ALTER TABLE inst_research_case ADD COLUMN IF NOT EXISTS terminal_reason TEXT")
        conn.execute("ALTER TABLE inst_research_case ADD COLUMN IF NOT EXISTS reopened_at TIMESTAMPTZ")
        conn.execute("ALTER TABLE inst_research_version ADD COLUMN IF NOT EXISTS locked_at TIMESTAMPTZ")
        conn.execute("ALTER TABLE inst_research_version ADD COLUMN IF NOT EXISTS superseded_at TIMESTAMPTZ")
        conn.execute("ALTER TABLE inst_proposal ADD COLUMN IF NOT EXISTS locked_at TIMESTAMPTZ")
        conn.execute("ALTER TABLE inst_proposal ADD COLUMN IF NOT EXISTS stale_at TIMESTAMPTZ")
        conn.execute("ALTER TABLE inst_proposal ADD COLUMN IF NOT EXISTS stale_reason TEXT")
        conn.execute("ALTER TABLE inst_proposal_version ADD COLUMN IF NOT EXISTS locked_at TIMESTAMPTZ")
        conn.execute("ALTER TABLE inst_proposal_version ADD COLUMN IF NOT EXISTS lock_hash TEXT")
        # 旧已批准研究视为已锁定；旧已进入审批的议案版本补锁定时间。
        conn.execute(
            "UPDATE inst_research_version SET locked_at=COALESCE(locked_at,frozen_at,approved_at,NOW()) "
            " WHERE status='approved' AND locked_at IS NULL"
        )
        conn.execute(
            "UPDATE inst_proposal_version SET locked_at=COALESCE(locked_at,created_at) "
            " WHERE status <> 'draft' AND locked_at IS NULL"
        )
        conn.execute(
            "UPDATE inst_proposal SET locked_at=COALESCE(locked_at,updated_at) "
            " WHERE status <> 'draft' AND locked_at IS NULL"
        )
        _backfill_case_stages(conn)
        conn.execute("ALTER TABLE inst_debate_argument ADD COLUMN IF NOT EXISTS claim_id TEXT")
        conn.execute(
            "ALTER TABLE inst_debate_argument ADD COLUMN IF NOT EXISTS claim_type TEXT NOT NULL DEFAULT 'inference'"
        )
        # 投委会审批：同角色可多人，各人独立留痕；附条件随议案向下传递。
        conn.execute("ALTER TABLE inst_approval ADD COLUMN IF NOT EXISTS conditions JSONB")
        conn.execute(
            """
            DO $$
            BEGIN
              IF EXISTS (
                SELECT 1 FROM pg_constraint
                 WHERE conrelid='inst_approval'::regclass
                   AND conname='inst_approval_version_step_key'
              ) THEN
                ALTER TABLE inst_approval DROP CONSTRAINT inst_approval_version_step_key;
              END IF;
            END $$;
            """
        )
        # 旧证据补等级与可用时间；只回填仍是默认 D 的行，避免覆盖人工调整。
        conn.execute(
            """
            UPDATE inst_evidence
               SET grade = CASE
                 WHEN evidence_type = 'filing' THEN 'A'
                 WHEN source LIKE 'ifind%' AND evidence_type IN ('financial','market') THEN 'B'
                 WHEN source = 'eastmoney' THEN 'C'
                 ELSE grade END
             WHERE grade = 'D'
            """
        )
        conn.execute(
            """
            UPDATE inst_evidence
               SET event_time = COALESCE(event_time, as_of),
                   available_time = COALESCE(available_time, as_of),
                   cutoff = COALESCE(cutoff, as_of)
             WHERE as_of IS NOT NULL
            """
        )
        if include_indexes:
            for idx in INDEXES:
                conn.execute(idx)
        # WORM：审计只增不改。测试/运维清理机构时需显式 DISABLE TRIGGER。
        conn.execute(
            """
            DO $$
            BEGIN
              IF NOT EXISTS (
                SELECT 1 FROM pg_trigger
                 WHERE tgname='inst_audit_event_worm'
                   AND tgrelid='inst_audit_event'::regclass
              ) THEN
                CREATE TRIGGER inst_audit_event_worm
                  BEFORE UPDATE OR DELETE ON inst_audit_event
                  FOR EACH ROW EXECUTE FUNCTION inst_audit_event_immutable();
              END IF;
            END $$
            """
        )


__all__ = ["DDL", "INDEXES", "ensure_inst_business_schema"]
