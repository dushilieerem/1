-- Tenant-consistent keys for the M2 strategy ledger (0020 already applied).
ALTER TABLE strategy_branches
    ADD CONSTRAINT strategy_branches_topic_tenant_uq UNIQUE (user_id, org_id, topic_id, id);

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'strategy_branches_parent_id_fkey') THEN
        ALTER TABLE strategy_branches DROP CONSTRAINT strategy_branches_parent_id_fkey;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'strategy_branches_parent_tenant_fk') THEN
        ALTER TABLE strategy_branches
            ADD CONSTRAINT strategy_branches_parent_tenant_fk
            FOREIGN KEY (user_id, org_id, topic_id, parent_id)
            REFERENCES strategy_branches(user_id, org_id, topic_id, id) ON DELETE RESTRICT;
    END IF;
END $$;

ALTER TABLE strategy_trials
    ADD CONSTRAINT strategy_trials_topic_branch_tenant_uq UNIQUE (user_id, org_id, topic_id, branch_id, id);

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'strategy_trials_user_id_org_id_branch_id_fkey') THEN
        ALTER TABLE strategy_trials DROP CONSTRAINT strategy_trials_user_id_org_id_branch_id_fkey;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'strategy_trials_branch_topic_fk') THEN
        ALTER TABLE strategy_trials
            ADD CONSTRAINT strategy_trials_branch_topic_fk
            FOREIGN KEY (user_id, org_id, topic_id, branch_id)
            REFERENCES strategy_branches(user_id, org_id, topic_id, id) ON DELETE RESTRICT;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'strategy_trials_rerun_of_fkey') THEN
        ALTER TABLE strategy_trials DROP CONSTRAINT strategy_trials_rerun_of_fkey;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'strategy_trials_rerun_tenant_fk') THEN
        ALTER TABLE strategy_trials
            ADD CONSTRAINT strategy_trials_rerun_tenant_fk
            FOREIGN KEY (user_id, org_id, topic_id, branch_id, rerun_of)
            REFERENCES strategy_trials(user_id, org_id, topic_id, branch_id, id) ON DELETE RESTRICT;
    END IF;
END $$;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'strategy_sealed_validations_branch_id_fkey') THEN
        ALTER TABLE strategy_sealed_validations DROP CONSTRAINT strategy_sealed_validations_branch_id_fkey;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'strategy_sealed_branch_topic_fk') THEN
        ALTER TABLE strategy_sealed_validations
            ADD CONSTRAINT strategy_sealed_branch_topic_fk
            FOREIGN KEY (user_id, org_id, topic_id, branch_id)
            REFERENCES strategy_branches(user_id, org_id, topic_id, id) ON DELETE RESTRICT;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'strategy_branches_reviewer_fk') THEN
        ALTER TABLE strategy_branches
            ADD CONSTRAINT strategy_branches_reviewer_fk FOREIGN KEY (reviewer_id) REFERENCES users(id) ON DELETE RESTRICT;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS strategy_topics_org_status
    ON strategy_topics(user_id, org_id, status);
CREATE INDEX IF NOT EXISTS strategy_branches_topic
    ON strategy_branches(user_id, org_id, topic_id, created_at);
CREATE INDEX IF NOT EXISTS strategy_trials_topic
    ON strategy_trials(user_id, org_id, topic_id, trial_no);

CREATE OR REPLACE FUNCTION strategy_trials_append_only() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_RELID = 'strategy_trials'::regclass THEN
        RAISE EXCEPTION 'strategy_trials 只允许追加，不允许 UPDATE 或 DELETE';
    END IF;
    RETURN NEW;
END;
$$;
