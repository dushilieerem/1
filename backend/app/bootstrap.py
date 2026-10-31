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
    from services.auth.auth_store import validate_auth_config

    validate_auth_config()
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
        from services.factor.factor_verification_store import (
            migrate_legacy_factor_verifications,
        )
        from services.factor.factor_dashboard_metrics_store import (
            migrate_legacy_factor_dashboard_metrics,
        )

        ensure_schema()
        from services.auth.password_reset_store import ensure_password_reset_schema

        ensure_password_reset_schema()
        seed_admin()
        # 手机 H5 的演示账号：主站账号体系 + 主站登录/注册/找回密码。
        try:
            from services.auth.auth_store import get_user_by_username, register_user

            if not get_user_by_username("demo"):
                register_user(username="demo", password="demo1234", display_name="演示用户")
                print("  手机 H5 演示账号 demo 就绪")
        except Exception as exc:
            print(f"  手机 H5 演示账号跳过: {exc}")
        try:
            from services.institution.inst_store import ensure_inst_schema, seed_inst_demo

            ensure_inst_schema()
            inst_seed = seed_inst_demo()
            if inst_seed.get("created_users"):
                print(f"  机构端就绪：新建演示账号 {inst_seed['created_users']} 个")
            else:
                print("  机构端就绪")
            from services.marketdata.schema import ensure_marketdata_schema

            # 只建表；索引由 ETL 在数据加载完成后创建，避免启动时锁大表。
            ensure_marketdata_schema(include_indexes=False)
            print("  市场数据服务层表就绪")
            from services.institution.inst_service import ensure_and_seed as ensure_inst_business

            from services.invest.schema import ensure_invest_schema

            ensure_invest_schema()
            print("  手机端 PG 读模型就绪")
            business = ensure_inst_business()
            if business.get("ok"):
                print(f"  机构端业务表就绪（org={business.get('org_id')}）")
            else:
                print(f"  机构端业务表跳过: {business.get('reason')}")
        except Exception as exc:
            print(f"  机构端 schema 跳过: {exc}")
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
        try:
            metric_migration = migrate_legacy_factor_dashboard_metrics()
            if metric_migration.get("source_rows"):
                print(
                    "  因子面板指标缓存迁移："
                    f"导入 {metric_migration['imported_rows']} 条，"
                    f"跳过 {metric_migration['skipped_rows']} 条"
                )
        except Exception as exc:
            print(f"  因子面板指标缓存迁移失败（旧 SQLite 保留）: {exc}")
        try:
            verify_migration = migrate_legacy_factor_verifications()
            if verify_migration.get("source_rows"):
                print(
                    "  因子校验状态迁移："
                    f"导入 {verify_migration['imported_rows']} 条，"
                    f"跳过 {verify_migration['skipped_rows']} 条"
                )
        except Exception as exc:
            print(f"  因子校验状态迁移失败（旧 SQLite 保留）: {exc}")
        from services.factor.user_library_store import ensure_user_libraries_schema

        ensure_user_libraries_schema()
        from services.strategy.user_strategy_library_store import (
            ensure_user_strategy_libraries_schema,
        )
        from services.strategy.builtin_strategies_store import (
            ensure_builtin_strategies_schema,
            list_builtin_strategies_from_db,
        )

        ensure_user_strategy_libraries_schema()
        try:
            ensure_builtin_strategies_schema()
            existing = list_builtin_strategies_from_db()
            print(
                f"  builtin_strategies RE 镜像就绪（{existing.get('total')} 条；"
                "管理员可在策略库页面手动同步）"
            )
        except Exception as exc:
            print(f"  builtin_strategies schema 跳过: {exc}")
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
        from knowledge_hub.store import ensure_kh_schema, migrate_provider_keys

        ensure_kh_schema()
        try:
            n = migrate_provider_keys()
            if n:
                print(f"  KH provider 密钥已加密 {n} 条")
        except Exception as exc:
            print(f"  KH provider 密钥迁移跳过: {exc}")
        mig = migrate_legacy_custom_to_admin()
        ensure_detect_schema()
        ensure_strategy_schema()
        ensure_strategy_plaza_schema()
        try:
            from services.paper.paper_store import ensure_paper_schema

            ensure_paper_schema()
            print("  paper_accounts / paper_settlements 就绪")
        except Exception as exc:
            print(f"  paper schema 初始化跳过: {exc}")
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
        from services.core.migrations import apply_migrations

        migration = apply_migrations()
        if migration.get("applied"):
            print(f"  数据库迁移已执行: {', '.join(migration['applied'])}")
        else:
            print(f"  数据库迁移已是最新（{migration.get('current') or 'baseline'}）")
    except Exception as exc:
        # P0-10：迁移失败必须 fail-fast，不能带着不确定 schema 启动。
        raise RuntimeError(f"数据库迁移失败: {exc}") from exc

    try:
        from services.news.news_ingest import start_news_ingest_scheduler

        start_news_ingest_scheduler()
    except Exception as exc:
        print(f"  news ingest scheduler 跳过: {exc}")

    try:
        from services.factor.dashboard_scheduler import start_dashboard_daily_scheduler

        start_dashboard_daily_scheduler()
    except Exception as exc:
        print(f"  panel daily scheduler 跳过: {exc}")

    try:
        from services.paper.scheduler import start_paper_settlement_scheduler

        start_paper_settlement_scheduler()
    except Exception as exc:
        print(f"  paper trading scheduler 跳过: {exc}")

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
