-- Imported SVQuant platform strategies kept as external-reference assets.
CREATE TABLE IF NOT EXISTS strategy_imported_assets (
    id TEXT PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id),
    org_id BIGINT NOT NULL REFERENCES inst_orgs(id),
    source_project_id TEXT NOT NULL,
    name TEXT NOT NULL,
    config JSONB NOT NULL DEFAULT '{}'::jsonb,
    implementation_hash TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'imported'
        CHECK (status IN ('imported', 'archived')),
    imported_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, org_id, source_project_id)
);

CREATE INDEX IF NOT EXISTS idx_strategy_imported_org
    ON strategy_imported_assets (org_id, imported_at DESC);
