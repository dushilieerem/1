-- Immutable candidate snapshots. No changes to subjective product or live execution.
CREATE TABLE IF NOT EXISTS quant_factor_candidates (
 id TEXT PRIMARY KEY,
 user_id BIGINT NOT NULL REFERENCES users(id),
 org_id BIGINT NOT NULL REFERENCES inst_orgs(id),
 project_id TEXT NOT NULL,
 snapshot JSONB NOT NULL,
 snapshot_hash TEXT NOT NULL,
 status TEXT NOT NULL CHECK (status IN (
   'draft','development_running','development_passed','development_failed','development_error',
   'validation_running','validation_passed','validation_failed','validation_error','cancelled'
 )),
 evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
 events JSONB NOT NULL DEFAULT '[]'::jsonb,
 archive JSONB,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 UNIQUE(user_id,org_id,project_id,snapshot_hash),
 FOREIGN KEY(user_id,project_id) REFERENCES detect_projects(user_id,id) ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS quant_factor_candidates_owner ON quant_factor_candidates(user_id,org_id,project_id,created_at DESC);
