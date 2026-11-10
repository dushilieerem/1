-- V5 P0a append-only research ledger. No approval/publication/trading authority.
-- Topics bind a project to one data view and one development/validation split.
CREATE TABLE IF NOT EXISTS quant_factor_topics (
    id TEXT PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id),
    org_id BIGINT NOT NULL REFERENCES inst_orgs(id),
    project_id TEXT NOT NULL,
    view_id TEXT NOT NULL,
    release_id TEXT NOT NULL DEFAULT '',
    contract_revision TEXT NOT NULL DEFAULT '',
    as_of DATE,
    development_start DATE NOT NULL,
    development_end DATE NOT NULL,
    validation_start DATE NOT NULL,
    validation_end DATE NOT NULL,
    primary_holding_period INTEGER NOT NULL CHECK (primary_holding_period BETWEEN 1 AND 20),
    policy_version TEXT NOT NULL,
    max_trials INTEGER NOT NULL CHECK (max_trials BETWEEN 1 AND 1000),
    max_sealed INTEGER NOT NULL DEFAULT 3 CHECK (max_sealed BETWEEN 1 AND 3),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'archived')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    FOREIGN KEY (user_id, project_id) REFERENCES detect_projects(user_id, id) ON DELETE RESTRICT,
    UNIQUE (user_id, org_id, project_id),
    UNIQUE (user_id, org_id, id),
    CHECK (development_start <= development_end
           AND development_end < validation_start
           AND validation_start <= validation_end)
);

CREATE TABLE IF NOT EXISTS quant_factor_branches (
    id TEXT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    org_id BIGINT NOT NULL,
    topic_id TEXT NOT NULL,
    parent_id TEXT,
    source TEXT NOT NULL CHECK (source IN ('agent', 'manual')),
    owner_id BIGINT NOT NULL REFERENCES users(id),
    hypothesis_version INTEGER NOT NULL DEFAULT 1 CHECK (hypothesis_version >= 1),
    implementation_version INTEGER NOT NULL DEFAULT 1 CHECK (implementation_version >= 1),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'archived')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    FOREIGN KEY (user_id, org_id, topic_id)
        REFERENCES quant_factor_topics(user_id, org_id, id) ON DELETE RESTRICT,
    FOREIGN KEY (parent_id) REFERENCES quant_factor_branches(id) ON DELETE RESTRICT,
    UNIQUE (user_id, org_id, id)
);

-- Append-only: every completed or interrupted development test is one row.
CREATE TABLE IF NOT EXISTS quant_factor_trials (
    id TEXT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    org_id BIGINT NOT NULL,
    project_id TEXT NOT NULL,
    topic_id TEXT NOT NULL,
    branch_id TEXT NOT NULL,
    trial_no INTEGER NOT NULL CHECK (trial_no >= 1),
    kind TEXT NOT NULL DEFAULT 'research'
        CHECK (kind IN ('research', 'manual', 'agent', 'iteration', 'rerun',
                        'static_check', 'compile', 'smoke', 'smoke_test', 'sealed_validation')),
    implementation_hash TEXT NOT NULL,
    parameters JSONB NOT NULL DEFAULT '{}'::jsonb,
    result_summary JSONB NOT NULL DEFAULT '{}'::jsonb,
    report_id TEXT,
    executor TEXT NOT NULL CHECK (executor IN ('human', 'agent', 'service')),
    outcome TEXT NOT NULL
        CHECK (outcome IN ('passed', 'failed', 'error', 'timeout', 'cancelled', 'rerun')),
    returned_metrics BOOLEAN NOT NULL DEFAULT FALSE,
    rerun_of TEXT,
    holding_period INTEGER NOT NULL CHECK (holding_period BETWEEN 1 AND 20),
    view_id TEXT NOT NULL,
    release_id TEXT NOT NULL DEFAULT '',
    contract_revision TEXT NOT NULL DEFAULT '',
    as_of DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    FOREIGN KEY (user_id, org_id, topic_id)
        REFERENCES quant_factor_topics(user_id, org_id, id) ON DELETE RESTRICT,
    FOREIGN KEY (user_id, org_id, branch_id)
        REFERENCES quant_factor_branches(user_id, org_id, id) ON DELETE RESTRICT,
    FOREIGN KEY (user_id, project_id) REFERENCES detect_projects(user_id, id) ON DELETE RESTRICT,
    FOREIGN KEY (rerun_of) REFERENCES quant_factor_trials(id) ON DELETE RESTRICT,
    UNIQUE (user_id, org_id, project_id, trial_no)
);

-- One sealed validation per candidate; a second row is rejected by the unique key.
CREATE TABLE IF NOT EXISTS quant_factor_sealed_validations (
    id TEXT PRIMARY KEY,
    candidate_id TEXT NOT NULL REFERENCES quant_factor_candidates(id) ON DELETE RESTRICT,
    user_id BIGINT NOT NULL,
    org_id BIGINT NOT NULL,
    project_id TEXT NOT NULL,
    topic_id TEXT NOT NULL,
    snapshot_hash TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued', 'running', 'passed', 'failed', 'error', 'cancelled')),
    executor TEXT NOT NULL DEFAULT 'F5' CHECK (executor = 'F5'),
    result JSONB,
    report_id TEXT,
    view_id TEXT NOT NULL,
    release_id TEXT NOT NULL DEFAULT '',
    contract_revision TEXT NOT NULL DEFAULT '',
    as_of DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    FOREIGN KEY (user_id, org_id, topic_id)
        REFERENCES quant_factor_topics(user_id, org_id, id) ON DELETE RESTRICT,
    FOREIGN KEY (user_id, project_id) REFERENCES detect_projects(user_id, id) ON DELETE RESTRICT,
    UNIQUE (candidate_id)
);

CREATE OR REPLACE FUNCTION quant_factor_trials_append_only() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'quant_factor_trials 只允许追加，不允许 UPDATE 或 DELETE';
END;
$$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'quant_factor_trials_no_update') THEN
        CREATE TRIGGER quant_factor_trials_no_update
            BEFORE UPDATE ON quant_factor_trials
            FOR EACH ROW EXECUTE FUNCTION quant_factor_trials_append_only();
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'quant_factor_trials_no_delete') THEN
        CREATE TRIGGER quant_factor_trials_no_delete
            BEFORE DELETE ON quant_factor_trials
            FOR EACH ROW EXECUTE FUNCTION quant_factor_trials_append_only();
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS quant_factor_topics_owner
    ON quant_factor_topics(user_id, org_id, project_id);
CREATE INDEX IF NOT EXISTS quant_factor_branches_topic
    ON quant_factor_branches(user_id, org_id, topic_id, created_at);
CREATE INDEX IF NOT EXISTS quant_factor_trials_topic
    ON quant_factor_trials(user_id, org_id, topic_id, trial_no);
CREATE INDEX IF NOT EXISTS quant_factor_trials_branch
    ON quant_factor_trials(user_id, org_id, branch_id, trial_no);
CREATE INDEX IF NOT EXISTS quant_factor_sealed_topic
    ON quant_factor_sealed_validations(user_id, org_id, topic_id, created_at);
