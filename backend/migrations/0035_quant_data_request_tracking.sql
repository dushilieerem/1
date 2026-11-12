-- 数据需求单补齐 PRD §5 的追踪字段：频率、关联对象、交付视图与处理记录。
ALTER TABLE quant_data_requests
    ADD COLUMN IF NOT EXISTS frequency TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS related_type TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS related_id TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS delivered_view TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS handled_by BIGINT REFERENCES users(id),
    ADD COLUMN IF NOT EXISTS handled_at TIMESTAMPTZ;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE conname = 'quant_data_requests_related_type_chk'
           AND conrelid = 'quant_data_requests'::regclass
    ) THEN
        ALTER TABLE quant_data_requests
            ADD CONSTRAINT quant_data_requests_related_type_chk
            CHECK (related_type IN ('', 'factor_topic', 'strategy_topic', 'portfolio_plan'));
    END IF;
END $$;
