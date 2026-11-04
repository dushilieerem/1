# -*- coding: utf-8 -*-
"""市场数据服务层库表（PostgreSQL）。

设计口径见 `docs/数据设计/机构端与手机端-数据接入与库表设计-v0.1.md`：
- parquet 是行情/估值/状态的权威源；本 schema 是 PG 服务层，可重建。
- 所有采集数据必须带 source / as_of / raw_hash；财务必须带 notice_date。
- 表按域前缀：ref_ / md_ / fin_ / doc_ / ingest_。
"""
from __future__ import annotations

from services.core.db import get_conn

DDL: tuple[str, ...] = (
    # ---------------------------------------------------------------- 主数据
    """
    CREATE TABLE IF NOT EXISTS ref_security (
      symbol        TEXT PRIMARY KEY,
      name          TEXT,
      market        TEXT NOT NULL DEFAULT 'CN',
      exchange      TEXT,
      board         TEXT,
      list_date     DATE,
      delist_date   DATE,
      status        TEXT NOT NULL DEFAULT 'listed',
      source        TEXT NOT NULL DEFAULT 'ifind',
      updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS ref_trading_calendar (
      market        TEXT NOT NULL DEFAULT 'CN',
      trade_date    DATE NOT NULL,
      is_open       BOOLEAN NOT NULL DEFAULT TRUE,
      source        TEXT NOT NULL DEFAULT 'ifind',
      PRIMARY KEY (market, trade_date)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS ref_industry (
      industry_code TEXT NOT NULL,
      level         SMALLINT NOT NULL DEFAULT 1,
      name          TEXT,
      parent_code   TEXT,
      source        TEXT NOT NULL DEFAULT 'ifind',
      PRIMARY KEY (industry_code, level)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS ref_security_industry (
      symbol           TEXT NOT NULL,
      industry_code    TEXT NOT NULL,
      level            SMALLINT NOT NULL DEFAULT 1,
      effective_from   DATE NOT NULL,
      effective_to     DATE,
      source           TEXT NOT NULL DEFAULT 'ifind',
      PRIMARY KEY (symbol, industry_code, level, effective_from)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS ref_index (
      index_code    TEXT PRIMARY KEY,
      name          TEXT,
      market        TEXT NOT NULL DEFAULT 'CN',
      source        TEXT NOT NULL DEFAULT 'ifind'
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS ref_index_member (
      index_code       TEXT NOT NULL,
      symbol           TEXT NOT NULL,
      effective_from   DATE NOT NULL,
      effective_to     DATE,
      weight           DOUBLE PRECISION,
      source           TEXT NOT NULL DEFAULT 'ifind',
      PRIMARY KEY (index_code, symbol, effective_from)
    )
    """,
    # ---------------------------------------------------------------- 行情服务层
    """
    CREATE TABLE IF NOT EXISTS md_daily_bar (
      symbol       TEXT NOT NULL,
      trade_date   DATE NOT NULL,
      open         DOUBLE PRECISION,
      high         DOUBLE PRECISION,
      low          DOUBLE PRECISION,
      close        DOUBLE PRECISION,
      pre_close    DOUBLE PRECISION,
      volume       DOUBLE PRECISION,
      amount       DOUBLE PRECISION,
      turnover     DOUBLE PRECISION,
      adjust       TEXT NOT NULL DEFAULT 'hfq',
      source       TEXT NOT NULL DEFAULT 'ifind',
      ingested_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      PRIMARY KEY (symbol, trade_date, adjust),
      CONSTRAINT md_daily_bar_adjust_chk CHECK (adjust IN ('hfq', 'none'))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS md_valuation_daily (
      symbol                TEXT NOT NULL,
      trade_date            DATE NOT NULL,
      pe_ttm                DOUBLE PRECISION,
      pb_mrq                DOUBLE PRECISION,
      pcf_ocf_ttm           DOUBLE PRECISION,
      dividend_yield_ttm    DOUBLE PRECISION,
      float_mv              DOUBLE PRECISION,
      total_mv              DOUBLE PRECISION,
      total_shares          DOUBLE PRECISION,
      source                TEXT NOT NULL DEFAULT 'ifind',
      ingested_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      PRIMARY KEY (symbol, trade_date)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS md_status_daily (
      symbol         TEXT NOT NULL,
      trade_date     DATE NOT NULL,
      listed_status  TEXT,
      up_down_status TEXT,
      is_st          BOOLEAN,
      is_suspended   BOOLEAN,
      limit_up       DOUBLE PRECISION,
      limit_down     DOUBLE PRECISION,
      source         TEXT NOT NULL DEFAULT 'ifind',
      PRIMARY KEY (symbol, trade_date)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS md_index_bar (
      index_code   TEXT NOT NULL,
      trade_date   DATE NOT NULL,
      open         DOUBLE PRECISION,
      high         DOUBLE PRECISION,
      low          DOUBLE PRECISION,
      close        DOUBLE PRECISION,
      volume       DOUBLE PRECISION,
      amount       DOUBLE PRECISION,
      source       TEXT NOT NULL DEFAULT 'ifind',
      PRIMARY KEY (index_code, trade_date)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS md_risk_daily (
      symbol          TEXT NOT NULL,
      trade_date      DATE NOT NULL,
      beta_1y         DOUBLE PRECISION,
      vol_1y          DOUBLE PRECISION,
      max_drawdown_1y DOUBLE PRECISION,
      calc_version    TEXT NOT NULL DEFAULT 'v1',
      PRIMARY KEY (symbol, trade_date, calc_version)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS derived_news (
      doc_id       TEXT PRIMARY KEY,
      source       TEXT,
      published_at TIMESTAMPTZ,
      title        TEXT NOT NULL,
      url          TEXT,
      symbol       TEXT,
      summary      TEXT,
      as_of        DATE,
      created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    # ---------------------------------------------------------------- 财务与公司行动
    """
    CREATE TABLE IF NOT EXISTS fin_income_statement (
      symbol          TEXT NOT NULL,
      report_date     DATE NOT NULL,
      notice_date     DATE,
      statement_type  TEXT NOT NULL DEFAULT 'accumulated',
      revenue         DOUBLE PRECISION,
      operating_profit DOUBLE PRECISION,
      net_profit      DOUBLE PRECISION,
      gross_profit    DOUBLE PRECISION,
      total_profit    DOUBLE PRECISION,
      eps             DOUBLE PRECISION,
      raw             JSONB,
      source          TEXT NOT NULL,
      as_of           DATE,
      raw_hash        TEXT,
      PRIMARY KEY (symbol, report_date, statement_type, source)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS fin_balance_sheet (
      symbol           TEXT NOT NULL,
      report_date      DATE NOT NULL,
      notice_date      DATE,
      statement_type   TEXT NOT NULL DEFAULT 'accumulated',
      total_assets     DOUBLE PRECISION,
      total_liabilities DOUBLE PRECISION,
      total_equity     DOUBLE PRECISION,
      current_assets   DOUBLE PRECISION,
      current_liabilities DOUBLE PRECISION,
      cash             DOUBLE PRECISION,
      inventory        DOUBLE PRECISION,
      receivables      DOUBLE PRECISION,
      raw              JSONB,
      source           TEXT NOT NULL,
      as_of            DATE,
      raw_hash         TEXT,
      PRIMARY KEY (symbol, report_date, statement_type, source)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS fin_cash_flow (
      symbol           TEXT NOT NULL,
      report_date      DATE NOT NULL,
      notice_date      DATE,
      statement_type   TEXT NOT NULL DEFAULT 'accumulated',
      operating_cf     DOUBLE PRECISION,
      investing_cf     DOUBLE PRECISION,
      financing_cf     DOUBLE PRECISION,
      free_cash_flow   DOUBLE PRECISION,
      capex            DOUBLE PRECISION,
      raw              JSONB,
      source           TEXT NOT NULL,
      as_of            DATE,
      raw_hash         TEXT,
      PRIMARY KEY (symbol, report_date, statement_type, source)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS fin_indicator (
      symbol        TEXT NOT NULL,
      report_date   DATE NOT NULL,
      notice_date   DATE,
      roe           DOUBLE PRECISION,
      gross_margin  DOUBLE PRECISION,
      net_margin    DOUBLE PRECISION,
      eps_ttm       DOUBLE PRECISION,
      revenue_yoy   DOUBLE PRECISION,
      profit_yoy    DOUBLE PRECISION,
      source        TEXT NOT NULL,
      as_of         DATE,
      raw           JSONB,
      PRIMARY KEY (symbol, report_date, source)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS fin_dividend (
      symbol         TEXT NOT NULL,
      plan_id        TEXT NOT NULL,
      announce_date  DATE,
      record_date    DATE,
      ex_date        DATE,
      pay_date       DATE,
      cash_per_share DOUBLE PRECISION,
      source         TEXT NOT NULL,
      as_of          DATE,
      raw            JSONB,
      PRIMARY KEY (symbol, plan_id, source)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS fin_buyback (
      symbol        TEXT NOT NULL,
      plan_id       TEXT NOT NULL,
      announce_date DATE,
      start_date    DATE,
      end_date      DATE,
      amount        DOUBLE PRECISION,
      shares        DOUBLE PRECISION,
      progress      TEXT,
      source        TEXT NOT NULL,
      as_of         DATE,
      raw           JSONB,
      PRIMARY KEY (symbol, plan_id, source)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS fin_share_capital (
      symbol        TEXT NOT NULL,
      effective_date DATE NOT NULL,
      announce_date DATE,
      total_shares  DOUBLE PRECISION,
      float_shares  DOUBLE PRECISION,
      source        TEXT NOT NULL,
      as_of         DATE,
      raw           JSONB,
      PRIMARY KEY (symbol, effective_date, source)
    )
    """,
    # ---------------------------------------------------------------- 文档与证据
    """
    CREATE TABLE IF NOT EXISTS doc_source (
      source_code  TEXT PRIMARY KEY,
      name         TEXT NOT NULL,
      type         TEXT,
      license_note TEXT,
      enabled      BOOLEAN NOT NULL DEFAULT TRUE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS doc_item (
      id           BIGSERIAL PRIMARY KEY,
      doc_type     TEXT NOT NULL,
      symbol       TEXT,
      title        TEXT NOT NULL,
      publish_at   TIMESTAMPTZ,
      url          TEXT,
      source       TEXT NOT NULL,
      content_hash TEXT NOT NULL,
      summary      TEXT,
      raw          JSONB,
      as_of        DATE,
      created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      CONSTRAINT doc_item_type_chk CHECK (doc_type IN ('announcement', 'research', 'news', 'filing', 'other')),
      CONSTRAINT doc_item_source_hash_key UNIQUE (source, content_hash)
    )
    """,
    # ---------------------------------------------------------------- 采集元数据
    """
    CREATE TABLE IF NOT EXISTS ingest_run (
      run_id       BIGSERIAL PRIMARY KEY,
      job          TEXT NOT NULL,
      source       TEXT,
      started_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      finished_at  TIMESTAMPTZ,
      status       TEXT NOT NULL DEFAULT 'running',
      rows         BIGINT,
      error        TEXT,
      detail       JSONB
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS ingest_watermark (
      job             TEXT NOT NULL,
      source          TEXT NOT NULL,
      last_success_at TIMESTAMPTZ,
      last_data_date  DATE,
      PRIMARY KEY (job, source)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS ingest_quality_check (
      id         BIGSERIAL PRIMARY KEY,
      run_id     BIGINT REFERENCES ingest_run(run_id) ON DELETE SET NULL,
      check_name TEXT NOT NULL,
      status     TEXT NOT NULL,
      detail     JSONB,
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS ingest_field_provenance (
      table_name TEXT NOT NULL,
      field_name TEXT NOT NULL,
      source     TEXT NOT NULL,
      as_of      DATE,
      priority   SMALLINT NOT NULL DEFAULT 100,
      note       TEXT,
      PRIMARY KEY (table_name, field_name, source)
    )
    """,
)

INDEXES: tuple[str, ...] = (
    "CREATE INDEX IF NOT EXISTS idx_md_daily_bar_date ON md_daily_bar (trade_date)",
    "CREATE INDEX IF NOT EXISTS idx_md_daily_bar_symbol ON md_daily_bar (symbol, adjust)",
    "CREATE INDEX IF NOT EXISTS idx_md_valuation_date ON md_valuation_daily (trade_date)",
    "CREATE INDEX IF NOT EXISTS idx_md_valuation_symbol ON md_valuation_daily (symbol)",
    "CREATE INDEX IF NOT EXISTS idx_md_status_date ON md_status_daily (trade_date)",
    "CREATE INDEX IF NOT EXISTS idx_md_status_symbol ON md_status_daily (symbol)",
    "CREATE INDEX IF NOT EXISTS idx_ref_security_name ON ref_security (name)",
    "CREATE INDEX IF NOT EXISTS idx_ref_security_market ON ref_security (market, status)",
    "CREATE INDEX IF NOT EXISTS idx_ref_calendar_date ON ref_trading_calendar (trade_date)",
    "CREATE INDEX IF NOT EXISTS idx_ref_security_industry_symbol ON ref_security_industry (symbol, level)",
    "CREATE INDEX IF NOT EXISTS idx_ref_index_member_symbol ON ref_index_member (symbol, effective_from)",
    "CREATE INDEX IF NOT EXISTS idx_fin_income_symbol ON fin_income_statement (symbol, report_date)",
    "CREATE INDEX IF NOT EXISTS idx_fin_balance_symbol ON fin_balance_sheet (symbol, report_date)",
    "CREATE INDEX IF NOT EXISTS idx_fin_cash_symbol ON fin_cash_flow (symbol, report_date)",
    "CREATE INDEX IF NOT EXISTS idx_fin_indicator_symbol ON fin_indicator (symbol, report_date)",
    "CREATE INDEX IF NOT EXISTS idx_doc_item_symbol ON doc_item (symbol, publish_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_doc_item_type_time ON doc_item (doc_type, publish_at DESC)",
)


def ensure_marketdata_schema(*, include_indexes: bool = True) -> None:
    with get_conn() as conn:
        for ddl in DDL:
            conn.execute(ddl)
        if include_indexes:
            for idx in INDEXES:
                conn.execute(idx)


def ensure_marketdata_indexes() -> None:
    with get_conn() as conn:
        for idx in INDEXES:
            conn.execute(idx)


__all__ = ["DDL", "INDEXES", "ensure_marketdata_indexes", "ensure_marketdata_schema"]
