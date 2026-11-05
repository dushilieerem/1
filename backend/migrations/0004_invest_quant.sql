-- 0004 量化研究：仅保留 H5 产品层的草稿/跟踪策略元数据。
-- 回测记录复用 strategy_runs；模拟盘复用 paper_accounts；策略广场复用 strategy_plaza_items。
-- 不在这里维护第二套回测/模拟盘/广场状态机。
CREATE TABLE IF NOT EXISTS invest_quant_draft (
  id BIGSERIAL PRIMARY KEY,
  user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name TEXT NOT NULL, factors JSONB NOT NULL DEFAULT '[]'::jsonb,
  universe TEXT NOT NULL DEFAULT 'hs300', project_id TEXT,
  last_backtest_id TEXT,
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
  project_id TEXT, backtest_id TEXT, paper_id BIGINT,
  created_at TEXT NOT NULL DEFAULT to_char(NOW(), 'YYYY-MM-DD HH24:MI:SS'),
  updated_at TEXT NOT NULL DEFAULT to_char(NOW(), 'YYYY-MM-DD HH24:MI:SS')
);
CREATE INDEX IF NOT EXISTS idx_invest_quant_strategy_user
  ON invest_quant_strategy (user_id, id DESC);
