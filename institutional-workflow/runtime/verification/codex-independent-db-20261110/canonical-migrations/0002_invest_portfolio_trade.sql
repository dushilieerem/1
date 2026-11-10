-- 0002 组合调仓记录：导入持仓时按权重变化生成，供 H5「最近调仓」展示。
-- 只记录权重变化，不区分买入/卖出；金额按导入当日组合市值折算。
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
);

CREATE INDEX IF NOT EXISTS idx_invest_portfolio_trade_user
  ON invest_portfolio_trade (user_id, trade_date DESC, id DESC);
