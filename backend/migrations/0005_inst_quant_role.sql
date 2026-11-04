-- 0005 机构量化角色：允许 inst_members.role='quant_researcher'。
-- 只扩展 CHECK 约束；不建第二套成员表、不清库、不 seed 真实机构。
-- 新库由 ensure_inst_schema 直接建含 quant_researcher 的约束；旧库由本迁移幂等修正。
DO $$
BEGIN
  IF to_regclass('public.inst_members') IS NOT NULL THEN
    ALTER TABLE inst_members DROP CONSTRAINT IF EXISTS inst_members_role_chk;
    ALTER TABLE inst_members
      ADD CONSTRAINT inst_members_role_chk CHECK (
        role IN ('manager', 'partner', 'chairman', 'risk', 'execution', 'monitoring', 'quant_researcher')
      );
  END IF;
END $$;
