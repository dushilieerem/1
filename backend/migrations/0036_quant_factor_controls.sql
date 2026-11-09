-- 因子工厂全局控制：负责人暂停全部后不再启动新的自动研究动作，在途计算保持原记录。
CREATE TABLE IF NOT EXISTS quant_factor_controls (
    user_id BIGINT NOT NULL REFERENCES users(id),
    org_id BIGINT NOT NULL REFERENCES inst_orgs(id),
    paused BOOLEAN NOT NULL DEFAULT FALSE,
    paused_by BIGINT REFERENCES users(id),
    paused_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, org_id)
);
