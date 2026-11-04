-- 0004 量化研究：草稿、跟踪策略、回测记录、模拟盘、策略广场。
-- 只做服务端记账；不接券商、不生成真实委托。
CREATE TABLE IF NOT EXISTS invest_quant_draft (
  id BIGSERIAL PRIMARY KEY,
  user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name TEXT NOT NULL, factors JSONB NOT NULL DEFAULT '[]'::jsonb,
  universe TEXT NOT NULL DEFAULT 'hs300', last_backtest_id BIGINT,
  created_at TEXT NOT NULL DEFAULT to_char(NOW(), 'YYYY-MM-DD HH24:MI:SS'),
  updated_at TEXT NOT NULL DEFAULT to_char(NOW(), 'YYYY-MM-DD HH24:MI:SS')
);
CREATE INDEX IF NOT EXISTS idx_invest_quant_draft_user
  ON invest_quant_draft (user_id, id DESC);

CREATE TABLE IF NOT EXISTS invest_quant_strategy (
  id BIGSERIAL PRIMARY KEY,
  user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name TEXT NOT NULL, factors JSONB NOT NULL DEFAULT '[]'::jsonb,
  universe TEXT NOT NULL DEFAULT 'hs300', status TEXT NOT NULL DEFAULT 'tracking',
  backtest_id BIGINT, paper_id BIGINT,
  created_at TEXT NOT NULL DEFAULT to_char(NOW(), 'YYYY-MM-DD HH24:MI:SS'),
  updated_at TEXT NOT NULL DEFAULT to_char(NOW(), 'YYYY-MM-DD HH24:MI:SS')
);
CREATE INDEX IF NOT EXISTS idx_invest_quant_strategy_user
  ON invest_quant_strategy (user_id, id DESC);

CREATE TABLE IF NOT EXISTS invest_quant_backtest (
  id BIGSERIAL PRIMARY KEY,
  user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name TEXT NOT NULL, factors JSONB NOT NULL DEFAULT '[]'::jsonb,
  universe TEXT NOT NULL DEFAULT 'hs300', start_date TEXT, end_date TEXT,
  metrics JSONB NOT NULL DEFAULT '{}'::jsonb, curve JSONB NOT NULL DEFAULT '[]'::jsonb,
  assumptions JSONB NOT NULL DEFAULT '{}'::jsonb, holdings JSONB NOT NULL DEFAULT '[]'::jsonb,
  shortened BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TEXT NOT NULL DEFAULT to_char(NOW(), 'YYYY-MM-DD HH24:MI:SS')
);
CREATE INDEX IF NOT EXISTS idx_invest_quant_backtest_user
  ON invest_quant_backtest (user_id, id DESC);

CREATE TABLE IF NOT EXISTS invest_quant_paper (
  id BIGSERIAL PRIMARY KEY,
  user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name TEXT NOT NULL, strategy_id BIGINT, factors JSONB NOT NULL DEFAULT '[]'::jsonb,
  universe TEXT NOT NULL DEFAULT 'hs300', start_capital DOUBLE PRECISION NOT NULL DEFAULT 1000000,
  start_date TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'running',
  last_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TEXT NOT NULL DEFAULT to_char(NOW(), 'YYYY-MM-DD HH24:MI:SS'),
  updated_at TEXT NOT NULL DEFAULT to_char(NOW(), 'YYYY-MM-DD HH24:MI:SS')
);
CREATE INDEX IF NOT EXISTS idx_invest_quant_paper_user
  ON invest_quant_paper (user_id, id DESC);

CREATE TABLE IF NOT EXISTS invest_quant_plaza (
  id BIGSERIAL PRIMARY KEY,
  title TEXT NOT NULL, author_name TEXT, factors JSONB NOT NULL DEFAULT '[]'::jsonb,
  universe TEXT NOT NULL DEFAULT 'hs300', range TEXT NOT NULL DEFAULT '1y',
  metrics JSONB NOT NULL DEFAULT '{}'::jsonb, curve JSONB NOT NULL DEFAULT '[]'::jsonb,
  followers INTEGER NOT NULL DEFAULT 0, is_demo BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TEXT NOT NULL DEFAULT to_char(NOW(), 'YYYY-MM-DD HH24:MI:SS')
);

CREATE TABLE IF NOT EXISTS invest_quant_plaza_follow (
  user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  plaza_id BIGINT NOT NULL REFERENCES invest_quant_plaza(id) ON DELETE CASCADE,
  created_at TEXT NOT NULL DEFAULT to_char(NOW(), 'YYYY-MM-DD HH24:MI:SS'),
  PRIMARY KEY (user_id, plaza_id)
);
