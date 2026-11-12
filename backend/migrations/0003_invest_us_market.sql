-- 0003：H5 美股快照 + invest_stocks.market
-- 美股快照由数据平台 us_stock_snapshot 派生；H5 用 market 区分 CN/US/HK。
ALTER TABLE invest_stocks ADD COLUMN IF NOT EXISTS market TEXT;
ALTER TABLE invest_etf ADD COLUMN IF NOT EXISTS market TEXT;

CREATE INDEX IF NOT EXISTS idx_invest_stocks_market ON invest_stocks (market);

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
);
