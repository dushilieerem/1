-- AC-12 全局暂停按机构生效，而不是按单个成员。保留 0036 表不删除，新逻辑使用机构级控制表。
CREATE TABLE IF NOT EXISTS quant_factor_org_controls (
    org_id BIGINT PRIMARY KEY REFERENCES inst_orgs(id),
    paused BOOLEAN NOT NULL DEFAULT FALSE,
    paused_by BIGINT REFERENCES users(id),
    paused_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO quant_factor_org_controls(org_id, paused, paused_by, paused_at, updated_at)
SELECT org_id, BOOL_OR(paused), MAX(paused_by), MAX(paused_at), NOW()
  FROM quant_factor_controls
 GROUP BY org_id
ON CONFLICT (org_id) DO NOTHING;
