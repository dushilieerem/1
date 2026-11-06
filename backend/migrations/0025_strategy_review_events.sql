-- Strategy seal budget and append-only review trail.
ALTER TABLE strategy_topics
    ADD COLUMN IF NOT EXISTS max_sealed INTEGER NOT NULL DEFAULT 1
    CHECK (max_sealed BETWEEN 1 AND 3);

ALTER TABLE strategy_sealed_validations
    ADD COLUMN IF NOT EXISTS gate JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS idempotency_key TEXT NOT NULL DEFAULT '';

CREATE UNIQUE INDEX IF NOT EXISTS uq_strategy_sealed_idempotency
    ON strategy_sealed_validations (user_id, org_id, idempotency_key)
    WHERE idempotency_key <> '';

CREATE TABLE IF NOT EXISTS strategy_review_events (
    id TEXT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    org_id BIGINT NOT NULL,
    topic_id TEXT NOT NULL,
    branch_id TEXT NOT NULL,
    action TEXT NOT NULL CHECK (action IN ('submit', 'claim', 'approve', 'reject')),
    actor_id BIGINT NOT NULL REFERENCES users(id),
    note TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    FOREIGN KEY (user_id, org_id, topic_id) REFERENCES strategy_topics(user_id, org_id, id) ON DELETE RESTRICT,
    FOREIGN KEY (user_id, org_id, branch_id) REFERENCES strategy_branches(user_id, org_id, id) ON DELETE RESTRICT
);

CREATE OR REPLACE FUNCTION strategy_review_events_append_only() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'strategy_review_events 只允许追加，不允许 UPDATE 或 DELETE';
END;
$$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'strategy_review_events_no_update') THEN
        CREATE TRIGGER strategy_review_events_no_update BEFORE UPDATE ON strategy_review_events
            FOR EACH ROW EXECUTE FUNCTION strategy_review_events_append_only();
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'strategy_review_events_no_delete') THEN
        CREATE TRIGGER strategy_review_events_no_delete BEFORE DELETE ON strategy_review_events
            FOR EACH ROW EXECUTE FUNCTION strategy_review_events_append_only();
    END IF;
END $$;
