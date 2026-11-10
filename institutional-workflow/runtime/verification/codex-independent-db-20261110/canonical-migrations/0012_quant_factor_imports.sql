-- 独立表，不依赖 0011/0013/0014/0015；允许在已有 0015 的 dev 库上补跑。
-- 新库仍按 0011→0012→0013→0014→0015 数字顺序执行。
-- AC-08a: import SVQuant existing factors into the org-shared library.
CREATE TABLE IF NOT EXISTS quant_factor_imported_factors (
    id TEXT PRIMARY KEY,
    org_id BIGINT NOT NULL REFERENCES inst_orgs(id),
    created_by BIGINT NOT NULL REFERENCES users(id),
    source TEXT NOT NULL DEFAULT 'svquant_existing'
        CHECK (source = 'svquant_existing'),
    source_library TEXT NOT NULL,
    source_factor_id TEXT NOT NULL,
    factor_name TEXT NOT NULL,
    display_name TEXT NOT NULL DEFAULT '',
    definition TEXT NOT NULL,
    definition_source TEXT NOT NULL DEFAULT '源码不可见（RE 内置）',
    import_hash TEXT NOT NULL,
    source_repo TEXT NOT NULL DEFAULT '',
    source_path TEXT NOT NULL DEFAULT '',
    source_commit TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'imported_unreviewed'
        CHECK (status IN ('imported_unreviewed', 'reviewed', 'retired')),
    metrics JSONB,
    metrics_status TEXT NOT NULL DEFAULT 'pending'
        CHECK (metrics_status IN ('pending', 'ok', 'not_computable')),
    metrics_reason TEXT NOT NULL DEFAULT '',
    metric_version TEXT NOT NULL DEFAULT '',
    view_id TEXT NOT NULL DEFAULT '',
    release_ids JSONB NOT NULL DEFAULT '{}'::jsonb,
    view_manifest_sha256 TEXT NOT NULL DEFAULT '',
    contract_revision TEXT NOT NULL DEFAULT '',
    as_of DATE,
    imported_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (org_id, source_library, source_factor_id)
);

CREATE INDEX IF NOT EXISTS quant_factor_imported_org
    ON quant_factor_imported_factors(org_id, status, metrics_status);
