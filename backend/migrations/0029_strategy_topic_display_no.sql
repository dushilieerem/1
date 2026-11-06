-- Stable human-readable strategy topic numbers (S1, S2, ...) per member + org.
ALTER TABLE strategy_topics
    ADD COLUMN IF NOT EXISTS display_no INTEGER;

WITH numbered AS (
    SELECT id,
           ROW_NUMBER() OVER (PARTITION BY user_id, org_id ORDER BY created_at, id) AS rn
    FROM strategy_topics
)
UPDATE strategy_topics t
SET display_no = n.rn
FROM numbered n
WHERE t.id = n.id AND t.display_no IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_strategy_topic_display_no
    ON strategy_topics (user_id, org_id, display_no)
    WHERE display_no IS NOT NULL;
