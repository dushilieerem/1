-- 平台策略导入列表按成员 + 机构 + 时间查询；补复合索引。
CREATE INDEX IF NOT EXISTS idx_strategy_imported_user_org
    ON strategy_imported_assets (user_id, org_id, imported_at DESC);

-- 导入记录必须对应真实机构成员，避免 token 之外写入孤立组合。
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE conname = 'strategy_imported_member_fk'
           AND conrelid = 'strategy_imported_assets'::regclass
    ) THEN
        ALTER TABLE strategy_imported_assets
            ADD CONSTRAINT strategy_imported_member_fk
            FOREIGN KEY (org_id, user_id)
            REFERENCES inst_members (org_id, user_id)
            ON DELETE CASCADE;
    END IF;
END $$;
