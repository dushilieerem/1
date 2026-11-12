-- Robustness diagnostics for strategy branches. They never advance K.
CREATE TABLE IF NOT EXISTS strategy_diagnostics (
    id TEXT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    org_id BIGINT NOT NULL,
    topic_id TEXT NOT NULL,
    branch_id TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('cost_2x', 'neighborhood')),
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    FOREIGN KEY (user_id, org_id, topic_id) REFERENCES strategy_topics(user_id, org_id, id) ON DELETE RESTRICT,
    FOREIGN KEY (user_id, org_id, branch_id) REFERENCES strategy_branches(user_id, org_id, id) ON DELETE RESTRICT,
    UNIQUE (user_id, org_id, id)
);

CREATE INDEX IF NOT EXISTS idx_strategy_diagnostics_branch
    ON strategy_diagnostics (user_id, org_id, branch_id, created_at DESC);

CREATE OR REPLACE FUNCTION strategy_diagnostics_append_only() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'strategy_diagnostics 只允许追加，不允许 UPDATE 或 DELETE';
END;
$$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'strategy_diagnostics_no_update') THEN
        CREATE TRIGGER strategy_diagnostics_no_update BEFORE UPDATE ON strategy_diagnostics
            FOR EACH ROW EXECUTE FUNCTION strategy_diagnostics_append_only();
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'strategy_diagnostics_no_delete') THEN
        CREATE TRIGGER strategy_diagnostics_no_delete BEFORE DELETE ON strategy_diagnostics
            FOR EACH ROW EXECUTE FUNCTION strategy_diagnostics_append_only();
    END IF;
END $$;
