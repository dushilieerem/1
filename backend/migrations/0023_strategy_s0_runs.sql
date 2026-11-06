CREATE TABLE IF NOT EXISTS strategy_s0_runs (
 id TEXT PRIMARY KEY,
 user_id BIGINT NOT NULL, org_id BIGINT NOT NULL, topic_id TEXT NOT NULL,
 branch_id TEXT NOT NULL, idempotency_key TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'queued' CHECK(status IN ('queued','running','completed','stopped','failed')),
 decision JSONB NOT NULL DEFAULT '{}'::jsonb, rounds INTEGER NOT NULL DEFAULT 0,
 stop_reason TEXT NOT NULL DEFAULT '', created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 FOREIGN KEY(user_id,org_id,topic_id) REFERENCES strategy_topics(user_id,org_id,id) ON DELETE RESTRICT,
 FOREIGN KEY(user_id,org_id,branch_id) REFERENCES strategy_branches(user_id,org_id,id) ON DELETE RESTRICT,
 UNIQUE(user_id,org_id,topic_id,idempotency_key)
);
