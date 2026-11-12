-- 机构端原文抽取替换低质量治理行时的审计字段（前向兼容，只加列）
-- 旧值不物理删除：替换时把原 value/quote/page/review_status/extractor 写入 superseded_*。
ALTER TABLE svquant.doc_extract
    ADD COLUMN IF NOT EXISTS superseded_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS superseded_value_text TEXT,
    ADD COLUMN IF NOT EXISTS superseded_quote TEXT,
    ADD COLUMN IF NOT EXISTS superseded_page_no INTEGER,
    ADD COLUMN IF NOT EXISTS superseded_review_status TEXT,
    ADD COLUMN IF NOT EXISTS superseded_extractor_version TEXT;

CREATE INDEX IF NOT EXISTS idx_doc_extract_superseded
    ON svquant.doc_extract (superseded_at)
    WHERE superseded_at IS NOT NULL;

COMMENT ON COLUMN svquant.doc_extract.superseded_value_text IS
    '被机构端原文抽取行替换前的 value_text（保留原值，不物理删除）';
COMMENT ON COLUMN svquant.doc_extract.superseded_at IS
    '替换时间；为空表示当前行未被替换过';
