-- 产品口径：成员离开机构时保留其导入记录用于审计，不阻塞成员移除。
-- 因此去掉 0033 的复合外键，保留独立的 user_id / org_id 外键与复合索引。
ALTER TABLE strategy_imported_assets
    DROP CONSTRAINT IF EXISTS strategy_imported_member_fk;

COMMENT ON TABLE strategy_imported_assets IS
    'SVQuant 平台策略导入登记（外部口径，未经 V5 复核）；成员移除后记录保留供审计。';
