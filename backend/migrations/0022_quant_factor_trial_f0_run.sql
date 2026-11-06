ALTER TABLE quant_factor_trials ADD COLUMN IF NOT EXISTS f0_run_id TEXT;
CREATE INDEX IF NOT EXISTS quant_factor_trials_f0 ON quant_factor_trials(user_id, org_id, f0_run_id);
