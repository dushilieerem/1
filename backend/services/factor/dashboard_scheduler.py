# -*- coding: utf-8 -*-
"""因子面板日更的进程内定时器。

不依赖任何外部调度（cron / systemd / Windows 计划任务）：SVQuant 后端进程启动后，
本模块自带一个 daemon 线程，到点（默认每天 00:00）跑一遍面板全量组合。
与 `services/news/news_ingest.py:start_news_ingest_scheduler` 同一套路。

配置（backend/.env，均可省略）：
  SVQUANT_PANEL_DAILY_ENABLED=1      # 置 0 关闭
  SVQUANT_PANEL_DAILY_AT=00:00       # 每天触发时刻，本机时区，HH:MM
  SVQUANT_PANEL_DAILY_GRACE_MIN=120  # 触发时刻进程不在线时，多久内启动仍补跑一轮

约束：
  - 全量 12 组约 10–12 小时，需要后端进程持续存活（`scripts/svquant.sh` 以独立会话
    启动，关闭终端不会中断）。进程不在线期间错过的轮次只在 grace 窗口内补跑。
  - 整批持跨进程 flock，与 API「刷新指标」按钮/命令行日更互斥（抢不到锁即中止本轮）。
  - 上一轮没跑完时，本线程还在循环里，不会并发起第二轮。
"""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

from services.factor import dashboard_store as ds
from services.factor.dashboard_store import PANEL_COMBOS

STATE_PATH: Path = ds.OUTPUT_DIR / "panel_daily_state.json"

DEFAULT_AT = "00:00"
DEFAULT_GRACE_MIN = 120
# 单次 sleep 上限：便于进程退出/时间跳变后及时重算下一次触发
MAX_SLEEP_SEC = 300

_lock = threading.Lock()
_thread: threading.Thread | None = None
_started = False


def parse_hhmm(raw: str) -> tuple[int, int] | None:
    """'00:00' / '6:30' → (0, 0) / (6, 30)；非法返回 None。"""
    text = (raw or "").strip()
    if not text or ":" not in text:
        return None
    hh, _, mm = text.partition(":")
    try:
        hour, minute = int(hh), int(mm)
    except ValueError:
        return None
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return hour, minute


def next_run_at(now: datetime, hour: int, minute: int) -> datetime:
    """下一次触发时刻：今天的 HH:MM 已过则顺延到明天。"""
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return target


def _load_state() -> dict:
    if not STATE_PATH.exists():
        return {}
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _save_state(**fields: object) -> None:
    ds._ensure_dirs()
    payload = {**_load_state(), **fields}
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(STATE_PATH)


def run_full_matrix(*, reason: str = "daily") -> dict:
    """串行跑一遍面板全量组合。返回 {ok, failed, combos}。"""
    run_date = datetime.now().strftime("%Y-%m-%d")
    started = time.time()
    total = len(PANEL_COMBOS)
    ok = failed = 0
    for i, (universe, period, filt) in enumerate(PANEL_COMBOS, 1):
        print(f"[panel] ({reason}) [{i}/{total}] {universe}/{period} filter_up={filt}", flush=True)
        ds._run_batch(
            universe=universe,
            period=period,
            filter_limit_up=filt,
            filter_suspended=True,
            limit=None,
            skip_ok=False,
            analysis_level="core",
        )
        job = ds.read_job()
        if job.get("status") == "failed":
            failed += 1
            err = str(job.get("error") or "")
            print(f"[panel] ({reason}) [{i}/{total}] failed: {err}", flush=True)
            if "刷新锁" in err:
                print(
                    "[panel] 另一轮面板回测正在运行（未抢到刷新锁），本轮中止",
                    flush=True,
                )
                break
        else:
            ok += 1
    elapsed_min = round((time.time() - started) / 60, 1)
    _save_state(
        last_run_date=run_date,
        last_reason=reason,
        last_ok=ok,
        last_failed=failed,
        last_elapsed_min=elapsed_min,
        last_finished_at=datetime.now().isoformat(timespec="seconds"),
    )
    print(
        f"[panel] ({reason}) 完成 ok={ok} failed={failed} 用时≈{elapsed_min}min",
        flush=True,
    )
    return {"reason": reason, "ok": ok, "failed": failed, "combos": total}


def start_dashboard_daily_scheduler() -> None:
    """启动面板日更定时线程（幂等）。SVQUANT_PANEL_DAILY_ENABLED=0 关闭。"""
    global _thread, _started

    from services.core.env_config import env

    if (env("SVQUANT_PANEL_DAILY_ENABLED", "1") or "1").strip().lower() in (
        "0",
        "false",
        "no",
    ):
        print("  panel daily scheduler: disabled (SVQUANT_PANEL_DAILY_ENABLED=0)")
        return

    at_raw = (env("SVQUANT_PANEL_DAILY_AT", DEFAULT_AT) or DEFAULT_AT).strip()
    parsed = parse_hhmm(at_raw)
    if parsed is None:
        print(f"  panel daily scheduler: 时刻非法 '{at_raw}'，跳过")
        return
    hour, minute = parsed

    try:
        grace_min = int(env("SVQUANT_PANEL_DAILY_GRACE_MIN", str(DEFAULT_GRACE_MIN)))
    except (TypeError, ValueError):
        grace_min = DEFAULT_GRACE_MIN

    with _lock:
        if _started:
            return
        _started = True

    def _catch_up_due() -> bool:
        """进程启动时若刚过触发时刻且当天没跑过，补跑一轮（受 grace 限制）。"""
        if grace_min <= 0:
            return False
        now = datetime.now()
        today = now.strftime("%Y-%m-%d")
        if _load_state().get("last_run_date") == today:
            return False
        scheduled_today = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if scheduled_today > now:
            return False
        return (now - scheduled_today) <= timedelta(minutes=grace_min)

    def _loop() -> None:
        # 稍等再干活，避免拖慢 API 就绪
        time.sleep(30)
        try:
            if _catch_up_due():
                print(
                    f"[panel] 启动补跑：今天的 {hour:02d}:{minute:02d} 触发时刻已过且在 "
                    f"{grace_min} 分钟容错窗口内",
                    flush=True,
                )
                run_full_matrix(reason="startup-catchup")
        except Exception as exc:  # noqa: BLE001
            print(f"[panel] 启动补跑失败: {exc}", flush=True)

        while True:
            now = datetime.now()
            target = next_run_at(now, hour, minute)
            wait = (target - now).total_seconds()
            while wait > 0:
                time.sleep(min(wait, MAX_SLEEP_SEC))
                wait = (target - datetime.now()).total_seconds()
            try:
                run_full_matrix(reason="daily")
            except Exception as exc:  # noqa: BLE001
                print(f"[panel] 日更失败: {exc}", flush=True)

    _thread = threading.Thread(target=_loop, name="panel-daily", daemon=True)
    _thread.start()
    print(
        f"  panel daily scheduler: 每天 {hour:02d}:{minute:02d} · "
        f"{len(PANEL_COMBOS)} 组 · 补跑窗口 {grace_min}min"
    )
