-- 0007 机构量化复核角色：允许 inst_members.role='quant_reviewer'。
-- 只扩展 CHECK 约束；复核角色只能读候选/写复核意见，不能创建或计算。
-- 保留 0006_quant_factor_candidates，不建业务表、不清库、不 seed。
DO $$
BEGIN
  IF to_regclass('public.inst_members') IS NOT NULL THEN
    ALTER TABLE inst_members DROP CONSTRAINT IF EXISTS inst_members_role_chk;
    ALTER TABLE inst_members
      ADD CONSTRAINT inst_members_role_chk CHECK (
        role IN (
          'manager', 'partner', 'chairman', 'risk', 'execution',
          'monitoring', 'quant_researcher', 'quant_reviewer'
        )
      );
  END IF;
END $$;
