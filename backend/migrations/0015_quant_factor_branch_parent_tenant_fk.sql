-- Prevent a branch from referencing another tenant's parent branch.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'quant_factor_branches_parent_id_fkey') THEN
        ALTER TABLE quant_factor_branches DROP CONSTRAINT quant_factor_branches_parent_id_fkey;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'quant_factor_branches_parent_tenant_fk') THEN
        ALTER TABLE quant_factor_branches
            ADD CONSTRAINT quant_factor_branches_parent_tenant_fk
            FOREIGN KEY (user_id, org_id, parent_id)
            REFERENCES quant_factor_branches(user_id, org_id, id)
            ON DELETE RESTRICT;
    END IF;
END $$;
