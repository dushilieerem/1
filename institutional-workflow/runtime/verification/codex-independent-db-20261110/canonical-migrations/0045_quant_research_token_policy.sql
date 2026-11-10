-- Append-only product authorization overlay. Historic grants/calls remain unchanged.
CREATE TABLE IF NOT EXISTS quant_research_token_policies (
 id TEXT PRIMARY KEY,
 org_id BIGINT NOT NULL REFERENCES inst_orgs(id),
 scope TEXT NOT NULL CHECK(scope='institutional_quant.factor_research'),
 mode TEXT NOT NULL CHECK(mode='unlimited'),
 authorized_by BIGINT NOT NULL REFERENCES users(id),
 supersedes_grant_id TEXT NOT NULL REFERENCES quant_ai_budget_supplements(id),
 authorization_hash TEXT NOT NULL UNIQUE,
 authorization_reference TEXT NOT NULL,
 authorization_record JSONB NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 UNIQUE(org_id,scope)
);
ALTER TABLE quant_ai_budget_calls ADD COLUMN IF NOT EXISTS token_policy_id TEXT REFERENCES quant_research_token_policies(id);
