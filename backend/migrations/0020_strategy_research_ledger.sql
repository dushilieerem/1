-- M2 strategy research: topic -> frozen recipe branches -> append-only trials.
CREATE TABLE IF NOT EXISTS strategy_topics (
    id TEXT PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id),
    org_id BIGINT NOT NULL REFERENCES inst_orgs(id),
    name TEXT NOT NULL,
    objective TEXT NOT NULL DEFAULT '',
    universe TEXT NOT NULL,
    benchmark TEXT NOT NULL,
    development_start DATE NOT NULL,
    development_end DATE NOT NULL,
    validation_start DATE NOT NULL,
    validation_end DATE NOT NULL,
    cost_bps DOUBLE PRECISION NOT NULL CHECK (cost_bps >= 0 AND cost_bps <= 1000),
    policy_version TEXT NOT NULL,
    max_trials INTEGER NOT NULL CHECK (max_trials BETWEEN 1 AND 1000),
    view_id TEXT NOT NULL,
    release_ids JSONB NOT NULL DEFAULT '{}'::jsonb,
    view_manifest_sha256 TEXT NOT NULL DEFAULT '',
    contract_revision TEXT NOT NULL DEFAULT '',
    as_of DATE,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'paused', 'archived')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, org_id, id)
);

CREATE TABLE IF NOT EXISTS strategy_branches (
    id TEXT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    org_id BIGINT NOT NULL,
    topic_id TEXT NOT NULL,
    parent_id TEXT,
    source TEXT NOT NULL CHECK (source IN ('agent', 'manual')),
    owner_id BIGINT NOT NULL REFERENCES users(id),
    hypothesis TEXT NOT NULL,
    recipe JSONB NOT NULL,
    implementation_hash TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'frozen', 'submitted', 'approved', 'rejected', 'archived')),
    review_status TEXT NOT NULL DEFAULT '',
    review_decision TEXT NOT NULL DEFAULT '',
    review_note TEXT NOT NULL DEFAULT '',
    reviewer_id BIGINT,
    reviewed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    FOREIGN KEY (user_id, org_id, topic_id) REFERENCES strategy_topics(user_id, org_id, id) ON DELETE RESTRICT,
    FOREIGN KEY (parent_id) REFERENCES strategy_branches(id) ON DELETE RESTRICT,
    UNIQUE (user_id, org_id, id)
);

-- Every viewed backtest is one row. Same recipe + same data + same cost is a rerun.
CREATE TABLE IF NOT EXISTS strategy_trials (
    id TEXT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    org_id BIGINT NOT NULL,
    topic_id TEXT NOT NULL,
    branch_id TEXT NOT NULL,
    trial_no INTEGER NOT NULL CHECK (trial_no >= 1),
    recipe JSONB NOT NULL,
    implementation_hash TEXT NOT NULL,
    outcome TEXT NOT NULL CHECK (outcome IN ('passed', 'failed', 'error', 'timeout', 'cancelled', 'rerun')),
    metrics JSONB NOT NULL DEFAULT '{}'::jsonb,
    gate JSONB NOT NULL DEFAULT '{}'::jsonb,
    report_id TEXT,
    rerun_of TEXT REFERENCES strategy_trials(id) ON DELETE RESTRICT,
    view_id TEXT NOT NULL,
    release_ids JSONB NOT NULL DEFAULT '{}'::jsonb,
    view_manifest_sha256 TEXT NOT NULL DEFAULT '',
    contract_revision TEXT NOT NULL DEFAULT '',
    as_of DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    FOREIGN KEY (user_id, org_id, topic_id) REFERENCES strategy_topics(user_id, org_id, id) ON DELETE RESTRICT,
    FOREIGN KEY (user_id, org_id, branch_id) REFERENCES strategy_branches(user_id, org_id, id) ON DELETE RESTRICT,
    UNIQUE (user_id, org_id, topic_id, trial_no)
);

CREATE TABLE IF NOT EXISTS strategy_sealed_validations (
    id TEXT PRIMARY KEY,
    branch_id TEXT NOT NULL REFERENCES strategy_branches(id) ON DELETE RESTRICT,
    user_id BIGINT NOT NULL,
    org_id BIGINT NOT NULL,
    topic_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued', 'running', 'passed', 'failed', 'error', 'cancelled')),
    executor TEXT NOT NULL DEFAULT 'S5' CHECK (executor = 'S5'),
    result JSONB,
    report_id TEXT,
    view_id TEXT NOT NULL,
    release_ids JSONB NOT NULL DEFAULT '{}'::jsonb,
    view_manifest_sha256 TEXT NOT NULL DEFAULT '',
    contract_revision TEXT NOT NULL DEFAULT '',
    as_of DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (branch_id)
);

CREATE OR REPLACE FUNCTION strategy_trials_append_only() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'strategy_trials 只允许追加，不允许 UPDATE 或 DELETE';
END;
$$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'strategy_trials_no_update') THEN
        CREATE TRIGGER strategy_trials_no_update BEFORE UPDATE ON strategy_trials
            FOR EACH ROW EXECUTE FUNCTION strategy_trials_append_only();
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'strategy_trials_no_delete') THEN
        CREATE TRIGGER strategy_trials_no_delete BEFORE DELETE ON strategy_trials
            FOR EACH ROW EXECUTE FUNCTION strategy_trials_append_only();
    END IF;
END $$;
