-- Own-deployment durable queue. No legacy F0 rows are adopted or reset.
CREATE TABLE IF NOT EXISTS quant_research_queue_jobs (
 id TEXT PRIMARY KEY,
 deployment_id TEXT NOT NULL,
 kind TEXT NOT NULL CHECK(kind IN ('f0','iteration','agent','development','validation','novelty','sealed')),
 object_id TEXT NOT NULL,
 payload JSONB NOT NULL DEFAULT '{}',
 external_calls JSONB NOT NULL DEFAULT '[]',
 user_id BIGINT NOT NULL REFERENCES users(id),
 org_id BIGINT NOT NULL REFERENCES inst_orgs(id),
 root_id TEXT NOT NULL,
 parent_id TEXT REFERENCES quant_research_queue_jobs(id),
 status TEXT NOT NULL CHECK(status IN ('queued','running','waiting','completed','cancelled')),
 owner_instance TEXT,
 owner_host TEXT,
 owner_pid INTEGER,
 owner_start TEXT,
 owner_epoch TEXT,
 reason TEXT NOT NULL DEFAULT '',
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 queued_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 UNIQUE(deployment_id,kind,object_id)
);
CREATE TABLE IF NOT EXISTS quant_research_queue_slots (
 deployment_id TEXT PRIMARY KEY,
 root_id TEXT REFERENCES quant_research_queue_jobs(id),
 updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_quant_research_queue_claim ON quant_research_queue_jobs(deployment_id,status,queued_at,id);
ALTER TABLE quant_ai_budget_calls ADD COLUMN IF NOT EXISTS queue_job_id TEXT REFERENCES quant_research_queue_jobs(id);
