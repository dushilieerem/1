-- Immutable candidate snapshots. No changes to subjective product or live execution.
CREATE TABLE IF NOT EXISTS quant_factor_candidates (
 id TEXT PRIMARY KEY,
 user_id BIGINT NOT NULL REFERENCES users(id),
 org_id BIGINT NOT NULL,
 project_id TEXT NOT NULL,
 snapshot JSONB NOT NULL,
 snapshot_hash TEXT NOT NULL,
 status TEXT NOT NULL,
 evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
 events JSONB NOT NULL DEFAULT '[]'::jsonb,
 archive JSONB,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 UNIQUE(user_id,org_id,project_id,snapshot_hash)
);
CREATE INDEX IF NOT EXISTS quant_factor_candidates_owner ON quant_factor_candidates(user_id,org_id,project_id,created_at DESC);
