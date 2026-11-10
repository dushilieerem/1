-- Provider-default output is an unknown single-call capacity, never zero/free.
ALTER TABLE quant_ai_budget_calls ALTER COLUMN max_output_tokens DROP NOT NULL;
ALTER TABLE quant_ai_budget_calls ADD COLUMN IF NOT EXISTS reservation_complete BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE quant_ai_budget_calls ADD COLUMN IF NOT EXISTS request_parameters JSONB NOT NULL DEFAULT '{}';
