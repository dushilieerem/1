# -*- coding: utf-8 -*-
"""运维巡检：把 health/metrics/磁盘信号转成告警列表（纯函数，便于测试）。

脚本 `scripts/ops/check_alerts.py` 负责采集信号与发送通知；这里只做判定。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Alert:
    level: str  # "critical" | "warning"
    code: str
    message: str


def evaluate_signals(
    *,
    health: dict[str, Any] | None,
    data_age_days: float | None = None,
    max_data_age_days: float = 2.0,
    open_reports: int = 0,
    max_open_reports: int = 200,
    disk_free_ratio: float | None = None,
    min_disk_free_ratio: float = 0.10,
    queue_backlog: int = 0,
    max_queue_backlog: int = 100,
    pending_migrations: int = 0,
    db_pool_used: int | None = None,
    db_pool_limit: int | None = None,
    db_pool_warn_ratio: float = 0.8,
    db_pool_critical_ratio: float = 0.95,
    db_connections_used: int | None = None,
    db_connections_limit: int | None = None,
    db_connections_warn_ratio: float = 0.8,
    db_connections_critical_ratio: float = 0.9,
) -> list[Alert]:
    alerts: list[Alert] = []
    if not health or health.get("ok") is not True:
        alerts.append(Alert("critical", "health_down", "健康检查不可用或返回非 ok"))
    elif health.get("db") != "ok":
        alerts.append(Alert("critical", "db_down", f"数据库异常：{health.get('db')}"))

    schema = (health or {}).get("schema") or {}
    pending = int(schema.get("pending_count", len(schema.get("pending") or [])) or 0)
    pending += int(pending_migrations or 0)
    if pending > 0:
        alerts.append(Alert("critical", "migrations_pending", f"存在 {pending} 个未应用迁移"))

    sync = (health or {}).get("data_sync") or {}
    if sync.get("status") == "failed":
        alerts.append(
            Alert(
                "critical",
                "data_sync_failed",
                f"数据同步失败：{sync.get('last_error') or 'unknown'}（view={sync.get('view_id') or '-'}）",
            )
        )

    if data_age_days is not None and data_age_days > max_data_age_days:
        alerts.append(
            Alert(
                "warning",
                "data_stale",
                f"行情数据已 {data_age_days:.1f} 天未更新（阈值 {max_data_age_days:.1f} 天）",
            )
        )

    if open_reports > max_open_reports:
        alerts.append(
            Alert("warning", "reports_backlog", f"待处理举报 {open_reports} 条（阈值 {max_open_reports}）")
        )

    if queue_backlog > max_queue_backlog:
        alerts.append(
            Alert("warning", "queue_backlog", f"后台任务积压 {queue_backlog}（阈值 {max_queue_backlog}）")
        )

    if db_pool_used is not None and db_pool_limit and db_pool_limit > 0:
        ratio = db_pool_used / db_pool_limit
        if ratio >= db_pool_critical_ratio:
            alerts.append(
                Alert("critical", "db_pool_high", f"数据库连接池 {db_pool_used}/{db_pool_limit}（{ratio:.0%}）")
            )
        elif ratio >= db_pool_warn_ratio:
            alerts.append(
                Alert("warning", "db_pool_high", f"数据库连接池 {db_pool_used}/{db_pool_limit}（{ratio:.0%}）")
            )

    if db_connections_used is not None and db_connections_limit and db_connections_limit > 0:
        ratio = db_connections_used / db_connections_limit
        if ratio >= db_connections_critical_ratio:
            alerts.append(
                Alert("critical", "db_connections_high", f"PostgreSQL 连接 {db_connections_used}/{db_connections_limit}（{ratio:.0%}）")
            )
        elif ratio >= db_connections_warn_ratio:
            alerts.append(
                Alert("warning", "db_connections_high", f"PostgreSQL 连接 {db_connections_used}/{db_connections_limit}（{ratio:.0%}）")
            )

    if disk_free_ratio is not None and disk_free_ratio < min_disk_free_ratio:
        alerts.append(
            Alert(
                "critical" if disk_free_ratio < min_disk_free_ratio / 2 else "warning",
                "disk_low",
                f"磁盘剩余 {disk_free_ratio:.1%}（阈值 {min_disk_free_ratio:.0%}）",
            )
        )
    return alerts


__all__ = ["Alert", "evaluate_signals"]
