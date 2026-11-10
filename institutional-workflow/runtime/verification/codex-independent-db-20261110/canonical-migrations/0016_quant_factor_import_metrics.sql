-- AC-08a import-benchmark-v1 batch audit. Independent of 0011-0015.
ALTER TABLE quant_factor_imported_factors
    ADD COLUMN IF NOT EXISTS batch_id TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS benchmark_version TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS metrics_params JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS metrics_evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS metrics_attempted_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS metrics_updated_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS quant_factor_imported_batch
    ON quant_factor_imported_factors(org_id, batch_id, metrics_status);
