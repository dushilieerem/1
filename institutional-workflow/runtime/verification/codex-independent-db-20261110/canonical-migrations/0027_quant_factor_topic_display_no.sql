-- Stable human-readable topic numbers (T1, T2, ...) scoped to member + org.
ALTER TABLE quant_factor_topics
    ADD COLUMN IF NOT EXISTS display_no INTEGER;

WITH numbered AS (
    SELECT id,
           ROW_NUMBER() OVER (PARTITION BY user_id, org_id ORDER BY created_at, id) AS rn
    FROM quant_factor_topics
)
UPDATE quant_factor_topics t
SET display_no = n.rn
FROM numbered n
WHERE t.id = n.id AND t.display_no IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_quant_factor_topic_display_no
    ON quant_factor_topics (user_id, org_id, display_no)
    WHERE display_no IS NOT NULL;
