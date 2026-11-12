-- AC-12: topics can be paused without deleting the ledger.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'quant_factor_topics_status_check') THEN
        ALTER TABLE quant_factor_topics DROP CONSTRAINT quant_factor_topics_status_check;
    END IF;
    ALTER TABLE quant_factor_topics
        ADD CONSTRAINT quant_factor_topics_status_check
        CHECK (status IN ('active', 'paused', 'archived'));
END $$;
