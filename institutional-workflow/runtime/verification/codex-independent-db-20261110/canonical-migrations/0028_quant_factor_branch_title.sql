-- Short business title for a research branch; full hypothesis stays in evidence.
ALTER TABLE quant_factor_branches
    ADD COLUMN IF NOT EXISTS title TEXT NOT NULL DEFAULT '';
