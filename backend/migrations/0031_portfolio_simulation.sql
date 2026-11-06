-- M3 simulated portfolios: versioned plans, approval, orders, positions and NAV.
CREATE TABLE IF NOT EXISTS portfolio_plans (
    id TEXT PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id),
    org_id BIGINT NOT NULL REFERENCES inst_orgs(id),
    family_id TEXT NOT NULL,
    version INTEGER NOT NULL CHECK (version >= 1),
    name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'submitted', 'approved', 'rejected', 'stopped')),
    environment TEXT NOT NULL DEFAULT 'simulated' CHECK (environment = 'simulated'),
    capital DOUBLE PRECISION NOT NULL CHECK (capital > 0),
    weights JSONB NOT NULL,
    single_limit DOUBLE PRECISION NOT NULL CHECK (single_limit > 0 AND single_limit <= 1),
    industry_limit DOUBLE PRECISION NOT NULL CHECK (industry_limit > 0 AND industry_limit <= 1),
    valid_from DATE,
    valid_to DATE,
    submitted_by BIGINT REFERENCES users(id),
    submitted_at TIMESTAMPTZ,
    approved_by BIGINT REFERENCES users(id),
    approved_at TIMESTAMPTZ,
    note TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, org_id, family_id, version)
);

CREATE INDEX IF NOT EXISTS idx_portfolio_plans_org ON portfolio_plans (org_id, family_id, version DESC);

CREATE TABLE IF NOT EXISTS portfolio_orders (
    id TEXT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    org_id BIGINT NOT NULL,
    plan_id TEXT NOT NULL REFERENCES portfolio_plans(id) ON DELETE RESTRICT,
    trade_date DATE NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL CHECK (side IN ('buy', 'sell')),
    target_weight DOUBLE PRECISION NOT NULL,
    price DOUBLE PRECISION,
    quantity DOUBLE PRECISION,
    status TEXT NOT NULL DEFAULT 'intent' CHECK (status IN ('intent', 'filled', 'skipped')),
    reason TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (plan_id, trade_date, symbol, side)
);

CREATE TABLE IF NOT EXISTS portfolio_nav (
    plan_id TEXT NOT NULL REFERENCES portfolio_plans(id) ON DELETE RESTRICT,
    trade_date DATE NOT NULL,
    nav DOUBLE PRECISION NOT NULL,
    cash DOUBLE PRECISION NOT NULL,
    positions_value DOUBLE PRECISION NOT NULL,
    daily_return DOUBLE PRECISION,
    drawdown DOUBLE PRECISION,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (plan_id, trade_date)
);

CREATE TABLE IF NOT EXISTS portfolio_positions (
    plan_id TEXT NOT NULL REFERENCES portfolio_plans(id) ON DELETE RESTRICT,
    trade_date DATE NOT NULL,
    symbol TEXT NOT NULL,
    weight DOUBLE PRECISION NOT NULL,
    market_value DOUBLE PRECISION NOT NULL,
    PRIMARY KEY (plan_id, trade_date, symbol)
);
