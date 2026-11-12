-- Quant workflow only. Persistent drafting jobs do not grant investment authority.
CREATE TABLE IF NOT EXISTS quant_factor_agent_jobs (
 id TEXT PRIMARY KEY,
 user_id BIGINT NOT NULL REFERENCES users(id),
 org_id BIGINT NOT NULL CONSTRAINT quant_factor_agent_jobs_org_fk REFERENCES inst_orgs(id),
 project_id TEXT,
 stage TEXT NOT NULL CHECK (stage IN ('F1','F2','F3')),
 request_key TEXT NOT NULL,
 input JSONB NOT NULL,
 status TEXT NOT NULL CONSTRAINT quant_factor_agent_jobs_status_ck CHECK (status IN ('queued','running','ready','failed','cancelled')),
 output JSONB,
 events JSONB NOT NULL DEFAULT '[]'::jsonb,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 UNIQUE(user_id,org_id,request_key)
);
CREATE INDEX IF NOT EXISTS quant_factor_agent_jobs_owner ON quant_factor_agent_jobs(user_id,org_id,project_id,stage,created_at DESC);

-- Idempotent upgrade for the initial isolated development application.
DO $$ BEGIN
 IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='quant_factor_agent_jobs_org_fk') THEN
  ALTER TABLE quant_factor_agent_jobs ADD CONSTRAINT quant_factor_agent_jobs_org_fk FOREIGN KEY(org_id) REFERENCES inst_orgs(id);
 END IF;
 IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='quant_factor_agent_jobs_status_ck') THEN
  ALTER TABLE quant_factor_agent_jobs ADD CONSTRAINT quant_factor_agent_jobs_status_ck CHECK (status IN ('queued','running','ready','failed','cancelled'));
 END IF;
END $$;
