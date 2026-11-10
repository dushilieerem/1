-- 机构端 doc_extract 接入契约（docs/数据需求/机构端-doc-extract接入契约.md）
-- 数据业务负责写入；机构端只读并按 available_time 做 PIT。
CREATE SCHEMA IF NOT EXISTS svquant;

CREATE TABLE IF NOT EXISTS svquant.doc_extract (
    symbol            TEXT        NOT NULL,
    field_key         TEXT        NOT NULL,
    field_label       TEXT,
    value_text        TEXT,
    value_num         NUMERIC,
    unit              TEXT,
    report_period     DATE        NOT NULL,
    page_no           INTEGER,
    quote             TEXT,
    doc_id            TEXT        NOT NULL,
    pdf_sha256        TEXT,
    source_url        TEXT,
    available_time    TIMESTAMPTZ NOT NULL,
    extractor_version TEXT,
    confidence        NUMERIC,
    review_status     TEXT        NOT NULL DEFAULT 'pending',
    reviewed_by       TEXT,
    reviewed_at       TIMESTAMPTZ,
    PRIMARY KEY (doc_id, field_key)
);

CREATE INDEX IF NOT EXISTS idx_doc_extract_symbol_field_time
    ON svquant.doc_extract (symbol, field_key, available_time DESC);

CREATE INDEX IF NOT EXISTS idx_doc_extract_review
    ON svquant.doc_extract (review_status, symbol);

COMMENT ON TABLE svquant.doc_extract IS
    '年报/公告页级抽取；仅 approved/verified/reviewed 作为机构端正式证据；available_time 为 PIT 可用时间';

-- 生产环境数据业务写入角色；测试/精简环境可能不存在该角色，跳过授权。
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'svquant_data_loader') THEN
        EXECUTE 'GRANT INSERT, SELECT ON svquant.doc_extract TO svquant_data_loader';
    END IF;
END $$;
