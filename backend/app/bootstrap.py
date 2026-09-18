# -*- coding: utf-8 -*-
"""FastAPI 启动时 schema / seed（从旧 api_server.main 抽出）。"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FACTOR_DIR = ROOT / "factor"


def bootstrap_schemas() -> None:
    if not FACTOR_DIR.exists():
        raise RuntimeError(f"missing factor dir: {FACTOR_DIR}")
    try:
        from services.core.env_config import load_env

        load_env()
    except Exception:
        pass
    try:
        from services.core.lan_http import ensure_lan_no_proxy

        ensure_lan_no_proxy()
    except Exception:
        pass

    try:
        from services.auth.auth_store import ensure_schema, seed_admin
        from ai.runtime.store import ensure_ai_usage_schema
        from services.community.community_store import ensure_posts_schema, seed_sample_posts
        from services.factor.detect_store import ensure_detect_schema, reassign_misowned_named_projects
        from services.strategy.strategy_store import ensure_strategy_schema
        from services.strategy.strategy_plaza_store import ensure_strategy_plaza_schema
        from services.factor.user_factor_store import (
            ensure_user_factors_schema,
            migrate_legacy_custom_to_admin,
        )

        ensure_schema()
        seed_admin()
        from services.auth.profile_store import ensure_schema as ensure_profile_schema

        ensure_profile_schema()
        from services.core.audit_log_store import ensure_audit_schema

        ensure_audit_schema()
        print("  app_audit_logs 就绪")
        try:
            import os

            from services.core.audit_log_store import purge_audit_logs

            days = int(os.environ.get("AUDIT_LOG_RETENTION_DAYS", "30") or "30")
            if days > 0:
                n = purge_audit_logs(days=days)
                if n:
                    print(f"  app_audit_logs 清理 {n} 条（>{days} 天）")
        except Exception as exc:
            print(f"  app_audit_logs 清理跳过: {exc}")
        ensure_ai_usage_schema()
        ensure_posts_schema()
        n = seed_sample_posts()
        ensure_user_factors_schema()
        from services.factor.user_library_store import ensure_user_libraries_schema

        ensure_user_libraries_schema()
        from services.strategy.user_strategy_library_store import (
            ensure_user_strategy_libraries_schema,
        )
        from services.strategy.builtin_strategies_store import (
            ensure_builtin_strategies_schema,
            seed_builtin_strategies_from_yaml,
            list_builtin_strategies_from_db,
        )

        ensure_user_strategy_libraries_schema()
        try:
            ensure_builtin_strategies_schema()
            existing = list_builtin_strategies_from_db()
            if int(existing.get("total") or 0) <= 0:
                seed = seed_builtin_strategies_from_yaml(replace=True)
                print(
                    f"  builtin_strategies 种子导入: {seed.get('upserted')} 条"
                    + (
                        f"（跳过 {len(seed.get('skipped') or [])}）"
                        if seed.get("skipped")
                        else ""
                    )
                )
            else:
                print(f"  builtin_strategies 就绪（{existing.get('total')} 条）")
        except Exception as exc:
            print(f"  builtin_strategies schema/种子跳过: {exc}")
        from services.data.watchlist_store import ensure_watchlist_schema

        ensure_watchlist_schema()
        from services.news.news_store import (
            ensure_news_schema,
            seed_sample_news,
            enforce_news_retention,
        )

        ensure_news_schema()
        news_n = seed_sample_news()
        try:
            enforce_news_retention()
        except Exception as exc:
            print(f"  news retention 跳过: {exc}")
        from knowledge_hub.store import ensure_kh_schema

        ensure_kh_schema()
        mig = migrate_legacy_custom_to_admin()
        ensure_detect_schema()
        ensure_strategy_schema()
        ensure_strategy_plaza_schema()
        try:
            from services.factor.re_factor_catalog import ensure_re_factor_catalog_schema

            ensure_re_factor_catalog_schema()
            print("  re_factor_catalog_snapshot 就绪")
        except Exception as exc:
            print(f"  re_factor_catalog schema 跳过: {exc}")
        moved = reassign_misowned_named_projects()
        print("  auth / community / detect / strategy 就绪")
        if n:
            print(f"  community 种子 {n} 条")
        if news_n:
            print(f"  news 种子 {news_n} 条")
        if mig.get("migrated"):
            print(f"  custom 迁移 {mig.get('migrated')}")
        if moved:
            print(f"  detect 错归属修正: {'; '.join(moved)}")
    except Exception as exc:
        print(f"  schema 初始化失败（登录可能不可用）: {exc}")

    try:
        from services.news.news_ingest import start_news_ingest_scheduler

        start_news_ingest_scheduler()
    except Exception as exc:
        print(f"  news ingest scheduler 跳过: {exc}")

    try:
        from services.factor.dashboard_store import read_job

        job = read_job()
        if job.get("status") == "running":
            print(
                f"  dashboard job 仍为 running（{job.get('done')}/{job.get('total')}）"
            )
    except Exception:
        pass

    try:
        from services.factor.re_factor_catalog import warm_re_catalog_async

        warm_re_catalog_async()
        print("  re-catalog 后台预热已启动")
    except Exception as exc:
        print(f"  re-catalog 预热跳过: {exc}")
