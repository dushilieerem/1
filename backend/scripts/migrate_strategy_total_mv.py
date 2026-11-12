# -*- coding: utf-8 -*-
"""把策略项目源码里的 ``self.total_mv`` 迁移为 ``self.current_mv``。

ResearchEngine 面板已没有 ``total_mv`` 字段（iFinD 的
``ths_current_mv_stock`` 会归一化成 ``current_mv``），旧样例模板引用了它，
结算时会抛 AttributeError。脚本幂等：只处理仍含 ``self.total_mv`` 的项目。

在 ``backend`` 目录执行::

    python -m scripts.migrate_strategy_total_mv
"""
from __future__ import annotations

import json

from services.core.db import get_conn

OLD_FIELD = "self.total_mv"
NEW_FIELD = "self.current_mv"


def main() -> None:
    updated = 0
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, user_id, config FROM strategy_projects "
            "WHERE config::text LIKE %s ORDER BY id, user_id",
            (f"%{OLD_FIELD}%",),
        ).fetchall()
        for row in rows:
            config = row["config"]
            if isinstance(config, str):
                config = json.loads(config)
            code = str(config.get("strategy_code") or "")
            if OLD_FIELD not in code:
                continue
            config["strategy_code"] = code.replace(OLD_FIELD, NEW_FIELD)
            conn.execute(
                "UPDATE strategy_projects SET config = %s::jsonb, updated_at = NOW() "
                "WHERE id = %s AND user_id = %s",
                (json.dumps(config, ensure_ascii=False), row["id"], row["user_id"]),
            )
            updated += 1
            print(f"patched {row['id']} user={row['user_id']}")
    print(f"updated={updated}")


if __name__ == "__main__":
    main()
