# -*- coding: utf-8 -*-
"""手机 Invest 的 PostgreSQL 读模型（替代原 invest-api SQLite）。

设计：
- `invest_stocks` 是服务层快照表（全市场代码 + 最新价/估值），由
  `refresh_invest_stocks()` 从 `ref_*` / `md_*` 重建；避免每次首页扫描 3000 万行。
- `bars` / `valuations` / `financials` / `news` / `indices` 是视图，按 code 查询时
  由 PostgreSQL 下推到主表索引。
- 用户数据落 `invest_*` 表；`watchlist` 等兼容视图保持 `rules.py` 的查询不变。
"""
from __future__ import annotations

from services.core.db import get_conn

DDL: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS invest_stocks (
      code TEXT PRIMARY KEY, name TEXT, pinyin TEXT, industry TEXT, asset TEXT,
      market TEXT,
      price DOUBLE PRECISION, prev_close DOUBLE PRECISION, open DOUBLE PRECISION,
      high DOUBLE PRECISION, low DOUBLE PRECISION, market_cap DOUBLE PRECISION,
      pe_ttm DOUBLE PRECISION, pb DOUBLE PRECISION, dividend_yield DOUBLE PRECISION,
      turnover DOUBLE PRECISION, volume DOUBLE PRECISION, amount DOUBLE PRECISION,
      beta DOUBLE PRECISION, next_report_date TEXT, updated_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS md_us_stock_snapshot (
      symbol       TEXT PRIMARY KEY,
      name         TEXT,
      last         DOUBLE PRECISION,
      prev_close   DOUBLE PRECISION,
      amount       DOUBLE PRECISION,
      turnover     DOUBLE PRECISION,
      trade_date   DATE,
      market       TEXT NOT NULL DEFAULT 'US',
      source       TEXT DEFAULT 'svquant-data',
      ingested_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS invest_etf (
      code TEXT PRIMARY KEY, name TEXT, pinyin TEXT, industry TEXT, asset TEXT,
      market TEXT,
      price DOUBLE PRECISION, prev_close DOUBLE PRECISION, open DOUBLE PRECISION,
      high DOUBLE PRECISION, low DOUBLE PRECISION, market_cap DOUBLE PRECISION,
      pe_ttm DOUBLE PRECISION, pb DOUBLE PRECISION, dividend_yield DOUBLE PRECISION,
      turnover DOUBLE PRECISION, volume DOUBLE PRECISION, amount DOUBLE PRECISION,
      beta DOUBLE PRECISION, next_report_date TEXT, updated_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS invest_watchlist (
      user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      code TEXT NOT NULL, group_name TEXT NOT NULL DEFAULT '默认',
      created_at TEXT NOT NULL DEFAULT to_char(NOW(), 'YYYY-MM-DD HH24:MI:SS'),
      PRIMARY KEY (user_id, code)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS invest_event (
      id BIGSERIAL PRIMARY KEY,
      user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      code TEXT NOT NULL, type TEXT NOT NULL DEFAULT '价格',
      condition TEXT NOT NULL DEFAULT '收盘后检查',
      status TEXT NOT NULL DEFAULT 'active',
      created_at TEXT NOT NULL DEFAULT to_char(NOW(), 'YYYY-MM-DD HH24:MI:SS'),
      condition_op TEXT, threshold DOUBLE PRECISION, unit TEXT,
      note TEXT, end_date TEXT, source TEXT NOT NULL DEFAULT 'manual', updated_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS invest_event_log (
      id BIGSERIAL PRIMARY KEY,
      user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      code TEXT NOT NULL, title TEXT, detail TEXT,
      triggered_at TEXT NOT NULL DEFAULT to_char(NOW(), 'YYYY-MM-DD HH24:MI:SS'),
      read BOOLEAN NOT NULL DEFAULT FALSE,
      source TEXT NOT NULL DEFAULT 'scan'
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS invest_glossary_feedback (
      id BIGSERIAL PRIMARY KEY,
      user_id BIGINT REFERENCES users(id) ON DELETE SET NULL,
      query TEXT NOT NULL,
      created_at TEXT NOT NULL DEFAULT to_char(NOW(), 'YYYY-MM-DD HH24:MI:SS')
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS invest_portfolio (
      user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      code TEXT NOT NULL, shares DOUBLE PRECISION NOT NULL DEFAULT 0,
      cost DOUBLE PRECISION NOT NULL DEFAULT 0, weight DOUBLE PRECISION NOT NULL DEFAULT 0,
      target_weight DOUBLE PRECISION NOT NULL DEFAULT 0, industry TEXT,
      PRIMARY KEY (user_id, code)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS invest_portfolio_meta (
      user_id BIGINT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
      trade_cost_pct DOUBLE PRECISION NOT NULL DEFAULT 0.4,
      annual_turnover DOUBLE PRECISION NOT NULL DEFAULT 35,
      impact_cost_pct DOUBLE PRECISION NOT NULL DEFAULT 0.08,
      updated_at TEXT NOT NULL DEFAULT to_char(NOW(), 'YYYY-MM-DD HH24:MI:SS')
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS invest_portfolio_trade (
      id BIGSERIAL PRIMARY KEY,
      user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      trade_date TEXT NOT NULL,
      code TEXT NOT NULL,
      name TEXT,
      weight_before DOUBLE PRECISION NOT NULL DEFAULT 0,
      weight_after DOUBLE PRECISION NOT NULL DEFAULT 0,
      weight_delta DOUBLE PRECISION NOT NULL DEFAULT 0,
      amount DOUBLE PRECISION NOT NULL DEFAULT 0,
      created_at TEXT NOT NULL DEFAULT to_char(NOW(), 'YYYY-MM-DD HH24:MI:SS')
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_invest_portfolio_trade_user
      ON invest_portfolio_trade (user_id, trade_date DESC, id DESC)
    """,
    """
    CREATE TABLE IF NOT EXISTS invest_risk_profile (
      user_id BIGINT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
      level TEXT NOT NULL DEFAULT '稳健型', score INTEGER NOT NULL DEFAULT 62,
      answers JSONB NOT NULL DEFAULT '{}'::jsonb,
      updated_at TEXT NOT NULL DEFAULT to_char(NOW(), 'YYYY-MM-DD HH24:MI:SS')
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS invest_auth_event (
      id BIGSERIAL PRIMARY KEY,
      ts TEXT NOT NULL DEFAULT to_char(NOW(), 'YYYY-MM-DD HH24:MI:SS'),
      action TEXT NOT NULL, username TEXT, ip TEXT, detail TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS invest_meta (
      key TEXT PRIMARY KEY, value TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS invest_topics (
      id TEXT PRIMARY KEY, name TEXT NOT NULL, summary TEXT,
      heat DOUBLE PRECISION NOT NULL DEFAULT 0,
      valuation_percentile DOUBLE PRECISION NOT NULL DEFAULT 50,
      turnover_percentile DOUBLE PRECISION NOT NULL DEFAULT 50,
      updated_at TEXT NOT NULL DEFAULT to_char(NOW(), 'YYYY-MM-DD HH24:MI:SS')
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS invest_topic_bars (
      topic_id TEXT NOT NULL REFERENCES invest_topics(id) ON DELETE CASCADE,
      date TEXT NOT NULL, close DOUBLE PRECISION, turnover DOUBLE PRECISION,
      valuation DOUBLE PRECISION, PRIMARY KEY (topic_id, date)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS invest_topic_stocks (
      topic_id TEXT NOT NULL REFERENCES invest_topics(id) ON DELETE CASCADE,
      code TEXT NOT NULL, PRIMARY KEY (topic_id, code)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS invest_quant_draft (
      id BIGSERIAL PRIMARY KEY,
      user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      name TEXT NOT NULL, factors JSONB NOT NULL DEFAULT '[]'::jsonb,
      universe TEXT NOT NULL DEFAULT 'hs300', project_id TEXT, last_backtest_id TEXT,
      created_at TEXT NOT NULL DEFAULT to_char(NOW(), 'YYYY-MM-DD HH24:MI:SS'),
      updated_at TEXT NOT NULL DEFAULT to_char(NOW(), 'YYYY-MM-DD HH24:MI:SS')
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_invest_quant_draft_user
      ON invest_quant_draft (user_id, id DESC)
    """,
    """
    CREATE TABLE IF NOT EXISTS invest_quant_strategy (
      id BIGSERIAL PRIMARY KEY,
      user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      name TEXT NOT NULL, factors JSONB NOT NULL DEFAULT '[]'::jsonb,
      universe TEXT NOT NULL DEFAULT 'hs300', status TEXT NOT NULL DEFAULT 'tracking',
      project_id TEXT, backtest_id TEXT, paper_id BIGINT,
      created_at TEXT NOT NULL DEFAULT to_char(NOW(), 'YYYY-MM-DD HH24:MI:SS'),
      updated_at TEXT NOT NULL DEFAULT to_char(NOW(), 'YYYY-MM-DD HH24:MI:SS')
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_invest_quant_strategy_user
      ON invest_quant_strategy (user_id, id DESC)
    """,
    """
    CREATE TABLE IF NOT EXISTS invest_ai_agent_prompt (
      user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      task_id TEXT NOT NULL,
      prompt TEXT NOT NULL,
      updated_at TEXT NOT NULL DEFAULT to_char(NOW(), 'YYYY-MM-DD HH24:MI:SS'),
      PRIMARY KEY (user_id, task_id)
    )
    """,
)


VIEWS: tuple[str, ...] = (
    "DROP VIEW IF EXISTS stocks, bars, valuations, financials, news, indices, topics, topic_bars, topic_stocks, watchlist, events, event_logs, portfolio, portfolio_meta, risk_profiles, meta, auth_events CASCADE",
    """
    CREATE VIEW stocks AS
    SELECT * FROM invest_stocks
    UNION ALL
    SELECT * FROM invest_etf
    """,
    """
    CREATE VIEW bars AS
    SELECT CASE WHEN n.symbol LIKE '%.SH' OR n.symbol LIKE '%.SZ' OR n.symbol LIKE '%.BJ' THEN split_part(n.symbol, '.', 1) ELSE n.symbol END AS code, n.trade_date::text AS date,
           n.open, n.high, n.low, n.close,
           COALESCE(n.volume, h.volume) AS volume,
           COALESCE(n.amount, h.amount) AS amount
      FROM md_daily_bar n
      LEFT JOIN md_daily_bar h
        ON h.symbol=n.symbol AND h.trade_date=n.trade_date AND h.adjust='hfq'
     WHERE n.adjust='none' AND n.close IS NOT NULL
    """,
    """
    CREATE VIEW valuations AS
    SELECT CASE WHEN symbol LIKE '%.SH' OR symbol LIKE '%.SZ' OR symbol LIKE '%.BJ' THEN split_part(symbol, '.', 1) ELSE symbol END AS code, trade_date::text AS date, pe_ttm, pb_mrq AS pb
      FROM md_valuation_daily
    """,
    """
    CREATE VIEW financials AS
    SELECT CASE WHEN i.symbol LIKE '%.SH' OR i.symbol LIKE '%.SZ' OR i.symbol LIKE '%.BJ' THEN split_part(i.symbol, '.', 1) ELSE i.symbol END AS code,
           to_char(i.report_date, 'YYYY"Q"Q') AS period,
           i.revenue/1e8 AS revenue,
           ind.revenue_yoy*100 AS revenue_yoy,
           i.net_profit/1e8 AS net_profit,
           ind.profit_yoy*100 AS profit_yoy,
           ind.gross_margin*100 AS gross_margin,
           ind.roe*100 AS roe,
           cf.operating_cf/1e8 AS ocf,
           i.report_date::text AS report_date
      FROM fin_income_statement i
      LEFT JOIN LATERAL (
        SELECT revenue_yoy, profit_yoy, gross_margin, roe
          FROM fin_indicator x
         WHERE x.symbol=i.symbol AND x.report_date=i.report_date
         ORDER BY x.notice_date DESC NULLS LAST LIMIT 1
      ) ind ON TRUE
      LEFT JOIN LATERAL (
        SELECT operating_cf FROM fin_cash_flow c
         WHERE c.symbol=i.symbol AND c.report_date=i.report_date
         ORDER BY c.notice_date DESC NULLS LAST LIMIT 1
      ) cf ON TRUE
     WHERE i.notice_date IS NOT NULL AND i.notice_date <= CURRENT_DATE
    """,
    """
    CREATE VIEW news AS
    SELECT 'doc-' || id AS id, title, COALESCE(summary, '') AS summary, source,
           COALESCE(publish_at::text, '') AS published_at,
           CASE doc_type WHEN 'announcement' THEN 'announcement' WHEN 'research' THEN 'research' ELSE 'news' END AS kind,
           CASE WHEN symbol LIKE '%.SH' OR symbol LIKE '%.SZ' OR symbol LIKE '%.BJ' THEN split_part(symbol, '.', 1) ELSE symbol END AS code,
           NULL::text AS topic_id, url
      FROM doc_item
    UNION ALL
    SELECT doc_id AS id, title, COALESCE(summary, '') AS summary, COALESCE(source, 'data_platform') AS source,
           COALESCE(published_at::text, '') AS published_at, 'news' AS kind,
           CASE WHEN symbol LIKE '%.SH' OR symbol LIKE '%.SZ' OR symbol LIKE '%.BJ' THEN split_part(symbol, '.', 1) ELSE symbol END AS code,
           NULL::text AS topic_id, url
      FROM derived_news d
     WHERE NOT EXISTS (SELECT 1 FROM doc_item i WHERE 'doc-' || i.id = d.doc_id)
    """,
    """
    CREATE VIEW indices AS
    WITH ranked AS (
      SELECT index_code, trade_date, close,
             ROW_NUMBER() OVER (PARTITION BY index_code ORDER BY trade_date DESC) AS rn
        FROM md_index_bar
    )
    SELECT split_part(r1.index_code, '.', 1) AS code,
           COALESCE(i.name, r1.index_code) AS name,
           r1.close AS price,
           COALESCE(r2.close, r1.close) AS prev_close,
           r1.trade_date::text AS updated_at
      FROM ranked r1
      LEFT JOIN ranked r2 ON r2.index_code=r1.index_code AND r2.rn=2
      LEFT JOIN ref_index i ON i.index_code=r1.index_code
     WHERE r1.rn=1
    """,
    "CREATE VIEW topics AS SELECT * FROM invest_topics",
    "CREATE VIEW topic_bars AS SELECT * FROM invest_topic_bars",
    "CREATE VIEW topic_stocks AS SELECT * FROM invest_topic_stocks",
    "CREATE VIEW watchlist AS SELECT user_id, code, group_name, created_at FROM invest_watchlist",
    "CREATE VIEW events AS SELECT id, user_id, code, type, condition, status, created_at, "
    "condition_op, threshold, unit, note, end_date, source, updated_at FROM invest_event",
    "CREATE VIEW event_logs AS SELECT id, user_id, code, title, detail, triggered_at, read, source FROM invest_event_log",
    "CREATE VIEW portfolio AS SELECT user_id, code, shares, cost, weight, target_weight, industry FROM invest_portfolio",
    "CREATE VIEW portfolio_meta AS SELECT user_id, trade_cost_pct, annual_turnover, impact_cost_pct, updated_at FROM invest_portfolio_meta",
    "CREATE VIEW risk_profiles AS SELECT user_id, level, score, answers::text AS answers, updated_at FROM invest_risk_profile",
    "CREATE VIEW meta AS SELECT key, value FROM invest_meta",
    "CREATE VIEW auth_events AS SELECT id, ts, action, username, ip, detail FROM invest_auth_event",
)


def refresh_invest_stocks(conn=None) -> int:
    """从 ref_*/md_* 重建服务层快照；ETL 后运行，不在每次请求中扫描大表。

    传入 conn 时复用调用方事务，保证数据同步和快照切换原子提交。
    """
    def _run(active) -> int:
        active.execute("DELETE FROM invest_stocks")
        active.execute(
            """
            WITH latest AS (
              SELECT symbol, trade_date, open, high, low, close, volume, amount, turnover,
                     ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY trade_date DESC) AS rn
                FROM md_daily_bar WHERE adjust='none'
            ), hfq AS (
              SELECT symbol, volume, amount, turnover,
                     ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY trade_date DESC) AS rn
                FROM md_daily_bar WHERE adjust='hfq'
            ), val AS (
              SELECT symbol, pe_ttm, pb_mrq, dividend_yield_ttm, float_mv, total_mv,
                     ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY trade_date DESC) AS rn
                FROM md_valuation_daily
            ), ind AS (
              SELECT symbol, industry_code,
                     ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY effective_from DESC) AS rn
                FROM ref_security_industry WHERE level=1
            ), risk AS (
              SELECT symbol, beta_1y,
                     ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY trade_date DESC) AS rn
                FROM md_risk_daily
            )
            INSERT INTO invest_stocks
              (code,name,pinyin,industry,asset,market,price,prev_close,open,high,low,market_cap,
               pe_ttm,pb,dividend_yield,turnover,volume,amount,beta,next_report_date,updated_at)
            SELECT CASE WHEN s.symbol LIKE '%.SH' OR s.symbol LIKE '%.SZ' OR s.symbol LIKE '%.BJ' THEN split_part(s.symbol, '.', 1) ELSE s.symbol END, s.name, NULL, COALESCE((SELECT f.raw->>'INDUSTRY_NAME' FROM fin_income_statement f WHERE f.symbol=s.symbol AND f.raw ? 'INDUSTRY_NAME' ORDER BY f.report_date DESC LIMIT 1), ri.name, i.industry_code, '未分类'), 'stock', s.market,
                   l.close, p.close, l.open, l.high, l.low,
                   COALESCE(v.total_mv, v.float_mv)/1e8, v.pe_ttm, v.pb_mrq,
                   v.dividend_yield_ttm,
                   COALESCE(l.turnover, h.turnover), COALESCE(l.volume, h.volume),
                   COALESCE(l.amount, h.amount), r.beta_1y, NULL, l.trade_date::text
              FROM ref_security s
              LEFT JOIN latest l ON l.symbol=s.symbol AND l.rn=1
              LEFT JOIN latest p ON p.symbol=s.symbol AND p.rn=2
              LEFT JOIN hfq h ON h.symbol=s.symbol AND h.rn=1
              LEFT JOIN val v ON v.symbol=s.symbol AND v.rn=1
              LEFT JOIN ind i ON i.symbol=s.symbol AND i.rn=1
              LEFT JOIN ref_industry ri ON ri.industry_code=i.industry_code AND ri.level=1
              LEFT JOIN risk r ON r.symbol=s.symbol AND r.rn=1
             WHERE s.status='listed' AND s.market IN ('CN','US')
            """
        )
        # 美股快照来自数据平台 us_stock_snapshot；与 A 股共用 invest_stocks，
        # 供 H5 英文模式查询。没有估值/财务就留空，不要填 0。
        active.execute(
            """
            INSERT INTO invest_stocks
              (code,name,industry,asset,market,price,prev_close,amount,turnover,updated_at)
            SELECT symbol, name, 'US equity', 'stock', COALESCE(market, 'US'),
                   last, prev_close, amount, turnover, trade_date::text
              FROM md_us_stock_snapshot
            ON CONFLICT (code) DO UPDATE SET
              name=EXCLUDED.name, industry=EXCLUDED.industry, asset=EXCLUDED.asset,
              market=EXCLUDED.market, price=EXCLUDED.price, prev_close=EXCLUDED.prev_close,
              amount=EXCLUDED.amount, turnover=EXCLUDED.turnover, updated_at=EXCLUDED.updated_at
            """
        )
        n = active.execute("SELECT COUNT(*) AS n FROM invest_stocks").fetchone()["n"]
        return int(n)

    if conn is not None:
        return _run(conn)
    with get_conn() as owned:
        return _run(owned)

def seed() -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO invest_meta (key,value) VALUES
              ('source','live'),('dataDate',COALESCE((SELECT MAX(trade_date)::text FROM md_daily_bar),''))
            ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value
            """
        )
        conn.execute(
            """
            INSERT INTO invest_topics (id,name,summary,heat,valuation_percentile,turnover_percentile)
            VALUES
              ('ai','AI 算力','算力与模型迭代驱动的产业链热度',86,88,72),
              ('dividend','高股息','现金流与分红确定性',64,42,38),
              ('new-energy','新能源','供需与价格周期',58,35,61)
            ON CONFLICT (id) DO NOTHING
            """
        )
        conn.execute(
            """
            INSERT INTO invest_etf (code,name,pinyin,industry,asset,price,prev_close,open,high,low,updated_at)
            VALUES
              ('510300','沪深300ETF','hushen300etf','宽基','etf',4.07,4.06,4.06,4.09,4.04,to_char(NOW(),'YYYY-MM-DD HH24:MI:SS')),
              ('510500','中证500ETF','zhongzheng500etf','宽基','etf',5.80,5.78,5.78,5.83,5.76,to_char(NOW(),'YYYY-MM-DD HH24:MI:SS')),
              ('512880','证券ETF','zhengquanetf','行业','etf',0.90,0.89,0.89,0.91,0.88,to_char(NOW(),'YYYY-MM-DD HH24:MI:SS'))
            ON CONFLICT (code) DO NOTHING
            """
        )


def ensure_invest_schema() -> None:
    with get_conn() as conn:
        for ddl in DDL:
            conn.execute(ddl)
        # 旧库先补列，再重建 stocks UNION 视图，避免列数不一致。
        conn.execute("ALTER TABLE invest_stocks ADD COLUMN IF NOT EXISTS market TEXT")
        conn.execute("ALTER TABLE invest_etf ADD COLUMN IF NOT EXISTS market TEXT")
        conn.execute("ALTER TABLE invest_quant_draft ADD COLUMN IF NOT EXISTS project_id TEXT")
        conn.execute("ALTER TABLE invest_quant_draft ALTER COLUMN last_backtest_id TYPE TEXT USING last_backtest_id::text")
        conn.execute("ALTER TABLE invest_quant_strategy ADD COLUMN IF NOT EXISTS project_id TEXT")
        conn.execute("ALTER TABLE invest_quant_strategy ALTER COLUMN backtest_id TYPE TEXT USING backtest_id::text")
        conn.execute("ALTER TABLE invest_event ADD COLUMN IF NOT EXISTS condition_op TEXT")
        conn.execute("ALTER TABLE invest_event ADD COLUMN IF NOT EXISTS threshold DOUBLE PRECISION")
        conn.execute("ALTER TABLE invest_event ADD COLUMN IF NOT EXISTS unit TEXT")
        conn.execute("ALTER TABLE invest_event ADD COLUMN IF NOT EXISTS note TEXT")
        conn.execute("ALTER TABLE invest_event ADD COLUMN IF NOT EXISTS end_date TEXT")
        conn.execute("ALTER TABLE invest_event ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'manual'")
        conn.execute("ALTER TABLE invest_event ADD COLUMN IF NOT EXISTS updated_at TEXT")
        conn.execute("ALTER TABLE invest_event_log ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'scan'")
        for ddl in VIEWS:
            conn.execute(ddl)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_invest_stocks_market ON invest_stocks (market)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_invest_stocks_industry ON invest_stocks (industry)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_invest_stocks_name ON invest_stocks (name)")
    seed()
    n = 0
    with get_conn() as conn:
        n = int(conn.execute("SELECT COUNT(*) AS n FROM invest_stocks").fetchone()["n"] or 0)
    if n == 0:
        refresh_invest_stocks()


__all__ = ["ensure_invest_schema", "refresh_invest_stocks", "seed"]
