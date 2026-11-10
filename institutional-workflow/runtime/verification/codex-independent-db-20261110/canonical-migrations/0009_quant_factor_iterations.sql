-- Bounded automatic factor research. No approval/publication/trading authority.
CREATE TABLE IF NOT EXISTS quant_factor_iterations (
 id TEXT PRIMARY KEY,
 user_id BIGINT NOT NULL REFERENCES users(id),
 org_id BIGINT NOT NULL REFERENCES inst_orgs(id),
 project_id TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('queued','running','review_pending','limit_reached','validation_failed','paused','failed')),
 max_rounds INTEGER NOT NULL CHECK(max_rounds BETWEEN 1 AND 20),
 baseline JSONB NOT NULL,
 rounds JSONB NOT NULL DEFAULT '[]'::jsonb,
 events JSONB NOT NULL DEFAULT '[]'::jsonb,
 stop_reason TEXT NOT NULL DEFAULT '',
 candidate_id TEXT REFERENCES quant_factor_candidates(id),
 agent_job_id TEXT REFERENCES quant_factor_agent_jobs(id),
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 FOREIGN KEY(user_id,project_id) REFERENCES detect_projects(user_id,id)
);
CREATE UNIQUE INDEX IF NOT EXISTS quant_factor_iterations_active ON quant_factor_iterations(user_id,org_id,project_id) WHERE status IN ('queued','running');
CREATE INDEX IF NOT EXISTS quant_factor_iterations_owner ON quant_factor_iterations(user_id,org_id,project_id,created_at DESC);
