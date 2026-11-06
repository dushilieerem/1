-- F0 constrained next-step runs. One idempotency key per topic.
CREATE TABLE IF NOT EXISTS quant_factor_f0_runs (
    id TEXT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    org_id BIGINT NOT NULL,
    project_id TEXT NOT NULL,
    topic_id TEXT NOT NULL,
    branch_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued', 'running', 'completed', 'stopped', 'failed')),
    decision JSONB NOT NULL DEFAULT '{}'::jsonb,
    rounds INTEGER NOT NULL DEFAULT 0,
    stop_reason TEXT NOT NULL DEFAULT '',
    view_id TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    FOREIGN KEY (user_id, org_id, topic_id)
        REFERENCES quant_factor_topics(user_id, org_id, id) ON DELETE RESTRICT,
    FOREIGN KEY (user_id, org_id, branch_id)
        REFERENCES quant_factor_branches(user_id, org_id, id) ON DELETE RESTRICT,
    FOREIGN KEY (user_id, project_id) REFERENCES detect_projects(user_id, id) ON DELETE RESTRICT,
    UNIQUE (user_id, org_id, topic_id, idempotency_key)
);

CREATE INDEX IF NOT EXISTS quant_factor_f0_topic
    ON quant_factor_f0_runs(user_id, org_id, topic_id, created_at DESC);
