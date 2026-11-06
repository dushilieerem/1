-- Persist the RE report payload used by a trial: NAV/benchmark curves and annual returns.
ALTER TABLE strategy_trials
    ADD COLUMN IF NOT EXISTS report JSONB NOT NULL DEFAULT '{}'::jsonb;
