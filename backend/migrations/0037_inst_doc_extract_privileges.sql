-- schema svquant 的默认 ACL 会给新建表带上 UPDATE/DELETE；
-- doc_extract 只允许数据业务插入与读取，收紧为最小权限。
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'svquant_data_loader') THEN
        EXECUTE 'REVOKE UPDATE, DELETE ON svquant.doc_extract FROM svquant_data_loader';
    END IF;
END $$;
