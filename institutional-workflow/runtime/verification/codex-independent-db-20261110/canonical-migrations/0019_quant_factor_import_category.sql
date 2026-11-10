-- QA-03: imported factors keep the real catalogue category.
ALTER TABLE quant_factor_imported_factors
    ADD COLUMN IF NOT EXISTS category TEXT NOT NULL DEFAULT '';
