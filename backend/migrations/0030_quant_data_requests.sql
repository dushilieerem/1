-- Research-side data requests; data platform owns collection/cleaning/publishing.
CREATE TABLE IF NOT EXISTS quant_data_requests (
    id TEXT PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id),
    org_id BIGINT NOT NULL REFERENCES inst_orgs(id),
    title TEXT NOT NULL,
    purpose TEXT NOT NULL DEFAULT '',
    period TEXT NOT NULL DEFAULT '',
    fields TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'submitted'
        CHECK (status IN ('submitted', 'in_progress', 'delivered', 'unsupported')),
    note TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, org_id, id)
);

CREATE INDEX IF NOT EXISTS idx_quant_data_requests_org
    ON quant_data_requests (org_id, created_at DESC);
