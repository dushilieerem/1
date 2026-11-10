-- Follow-up for the merged 0008 migration; do not rewrite 0008 after it shipped.
DO $$ BEGIN
 IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='quant_factor_agent_jobs_project_fk') THEN
  ALTER TABLE quant_factor_agent_jobs
   ADD CONSTRAINT quant_factor_agent_jobs_project_fk
   FOREIGN KEY(user_id,project_id) REFERENCES detect_projects(user_id,id) ON DELETE RESTRICT;
 END IF;
 IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='quant_factor_agent_jobs_stage_project_ck') THEN
  ALTER TABLE quant_factor_agent_jobs
   ADD CONSTRAINT quant_factor_agent_jobs_stage_project_ck
   CHECK (stage='F1' OR project_id IS NOT NULL);
 END IF;
END $$;
