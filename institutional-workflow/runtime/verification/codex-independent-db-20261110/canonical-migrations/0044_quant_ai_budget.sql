-- CR100: institution-quant only. No shared AI/account settings are changed.
-- No historical balance/grant is inferred or activated by this migration.
CREATE TABLE IF NOT EXISTS quant_ai_budget_accounts (
 org_id BIGINT NOT NULL REFERENCES inst_orgs(id),
 scope TEXT NOT NULL CHECK(scope IN ('space','factor')),
 limit_tokens BIGINT NOT NULL CHECK(limit_tokens>=0),
 baseline_state TEXT NOT NULL DEFAULT 'pending' CHECK(baseline_state IN ('pending','confirmed')),
 historical_tokens BIGINT CHECK(historical_tokens>=0),
 unknown_history JSONB NOT NULL DEFAULT '{}',
 baseline_reference TEXT,
 updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 PRIMARY KEY(org_id,scope),
 CHECK(baseline_state<>'confirmed' OR (historical_tokens IS NOT NULL AND baseline_reference IS NOT NULL))
);
CREATE TABLE IF NOT EXISTS quant_ai_budget_supplements (
 id TEXT PRIMARY KEY,
 org_id BIGINT NOT NULL REFERENCES inst_orgs(id),
 authorized_by BIGINT NOT NULL REFERENCES users(id),
 module TEXT NOT NULL CHECK(module='factor'),
 research_scope TEXT NOT NULL,
 limit_tokens BIGINT NOT NULL CHECK(limit_tokens>0),
 purpose TEXT NOT NULL,
 authorization_reference TEXT NOT NULL,
 authorization_hash TEXT NOT NULL UNIQUE,
 status TEXT NOT NULL CHECK(status IN ('authorized','closed')),
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 UNIQUE(org_id,research_scope)
);
CREATE TABLE IF NOT EXISTS quant_ai_budget_calls (
 id TEXT PRIMARY KEY,
 org_id BIGINT NOT NULL REFERENCES inst_orgs(id),
 user_id BIGINT NOT NULL REFERENCES users(id),
 module TEXT NOT NULL CHECK(module='factor'),
 project_id TEXT,
 call_key TEXT NOT NULL,
 task_id TEXT NOT NULL,
 budget_version TEXT NOT NULL DEFAULT 'quant-model-budget-v1',
 request_hash TEXT NOT NULL,
 funding TEXT NOT NULL DEFAULT 'base',
 supplement_id TEXT REFERENCES quant_ai_budget_supplements(id),
 reserved_tokens BIGINT NOT NULL CHECK(reserved_tokens>0),
 prompt_upper_tokens BIGINT NOT NULL CHECK(prompt_upper_tokens>0),
 max_output_tokens INTEGER NOT NULL CHECK(max_output_tokens>0),
 status TEXT NOT NULL CHECK(status IN ('reserved','dispatched','settled','unresolved')),
 actual_tokens BIGINT CHECK(actual_tokens>=0),
 provider_usage JSONB,
 response JSONB,
 note TEXT NOT NULL DEFAULT '',
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 UNIQUE(org_id,call_key),
 CHECK((funding='base' AND supplement_id IS NULL) OR (funding='supplement' AND supplement_id IS NOT NULL)),
 CHECK(status<>'settled' OR actual_tokens IS NOT NULL)
);
CREATE INDEX IF NOT EXISTS idx_quant_ai_budget_funding ON quant_ai_budget_calls(org_id,funding,supplement_id,status);
