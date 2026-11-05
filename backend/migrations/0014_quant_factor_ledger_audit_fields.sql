-- Data-side audit fields for the V5 ledger. Keeps 0011 immutable.
-- release_ids holds the actual iFind/derived/free releases locked by the view;
-- as_of is the maximum data date in the view (not wall-clock time).
ALTER TABLE quant_factor_topics
    ADD COLUMN IF NOT EXISTS release_ids JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS view_manifest_sha256 TEXT NOT NULL DEFAULT '';

ALTER TABLE quant_factor_trials
    ADD COLUMN IF NOT EXISTS release_ids JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS view_manifest_sha256 TEXT NOT NULL DEFAULT '';

ALTER TABLE quant_factor_sealed_validations
    ADD COLUMN IF NOT EXISTS release_ids JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS view_manifest_sha256 TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS evaluated_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS trial_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS metric_version TEXT NOT NULL DEFAULT '';
