# -*- coding: utf-8 -*-
"""日历 + 核心指数 + A股后复权日线（bars-only）。

不依赖 NBQuant / SVQuant；数据默认写到本目录 data/a_share/。
"""
from __future__ import annotations

import argparse
import json
import os
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import pandas as pd

os.environ.setdefault("NO_PROXY", "*")
os.environ.setdefault("no_proxy", "*")

ROOT = Path(__file__).resolve().parent
DEFAULT_DATA = ROOT / "data" / "a_share"
DEFAULT_LOG = ROOT / "logs"

CORE_INDICES = [
    ("000001.SH", "sh000001", "上证指数"),
    ("399001.SZ", "sz399001", "深证成指"),
    ("399006.SZ", "sz399006", "创业板指"),
    ("000016.SH", "sh000016", "上证50"),
    ("000300.SH", "sh000300", "沪深300"),
    ("000905.SH", "sh000905", "中证500"),
    ("000852.SH", "sh000852", "中证1000"),
    ("000906.SH", "sh000906", "中证800"),
    ("000688.SH", "sh000688", "科创50"),
    ("000010.SH", "sh000010", "上证180"),
    ("000015.SH", "sh000015", "红利指数"),
    ("399005.SZ", "sz399005", "中小板指"),
    ("399330.SZ", "sz399330", "深证100"),
    ("399303.SZ", "sz399303", "国证2000"),
]

BAR_START_DEFAULT = "20100101"


def log(msg: str, lines: list[str], log_file: Path | None) -> None:
    line = f"{datetime.now().strftime('%H:%M:%S')} {msg}"
    print(line, flush=True)
    lines.append(line)
    if log_file is not None:
        try:
            with log_file.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError:
            pass


def next_day_ak(date_str: str) -> str:
    return (pd.Timestamp(date_str) + pd.Timedelta(days=1)).strftime("%Y%m%d")


def atomic_write_csv(path: Path, df: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    df.to_csv(tmp, index=False, encoding="utf-8")
    tmp.replace(path)


def merge_csv(path: Path, new_df: pd.DataFrame, date_col: str = "date") -> int:
    if new_df.empty:
        return 0 if not path.exists() else len(pd.read_csv(path))
    new_df = new_df.drop_duplicates(subset=[date_col], keep="last")
    if path.exists():
        old = pd.read_csv(path)
        merged = pd.concat([old, new_df], ignore_index=True)
        merged = merged.drop_duplicates(subset=[date_col], keep="last").sort_values(date_col)
    else:
        merged = new_df.sort_values(date_col)
    for col in ("open", "high", "low", "close"):
        if col in merged.columns:
            merged[col] = pd.to_numeric(merged[col], errors="coerce").round(4)
    for col in ("amount", "volume"):
        if col in merged.columns:
            merged[col] = pd.to_numeric(merged[col], errors="coerce").round(2)
    for col in ("change_ratio", "turn"):
        if col in merged.columns:
            merged[col] = pd.to_numeric(merged[col], errors="coerce").round(10)
    atomic_write_csv(path, merged)
    return len(merged)


def resolve_end_date(calendar_path: Path, end_date: str | None) -> str:
    """未收盘用上一交易日，避免拉不完整当日 K。"""
    if end_date:
        return pd.Timestamp(end_date).strftime("%Y-%m-%d")
    now = datetime.now()
    today = pd.Timestamp.now().normalize()
    if not calendar_path.exists():
        return today.strftime("%Y-%m-%d")
    cal = pd.read_csv(calendar_path)
    dates = pd.to_datetime(cal["date"]).sort_values().reset_index(drop=True)
    trading = dates[dates <= today]
    if trading.empty:
        return today.strftime("%Y-%m-%d")
    ltd = pd.Timestamp(trading.iloc[-1]).normalize()
    market_closed = now.hour > 15 or (now.hour == 15 and now.minute >= 30)
    if ltd == today and not market_closed:
        before = trading[trading < today]
        if len(before):
            return pd.Timestamp(before.iloc[-1]).strftime("%Y-%m-%d")
    return ltd.strftime("%Y-%m-%d")


def step_calendar(data_root: Path, lines: list[str], log_file: Path | None) -> Path:
    import akshare as ak

    log("[1/4] 更新交易日历", lines, log_file)
    raw = ak.tool_trade_date_hist_sina()
    df = raw.rename(columns={"trade_date": "date"})
    df["date"] = pd.to_datetime(df["date"])
    cap = pd.Timestamp.now().normalize()
    df = df[df["date"] <= cap].copy()
    df["date"] = df["date"].dt.strftime("%Y-%m-%d")
    df["is_trading"] = 1
    out = data_root / "01_meta" / "trading_calendar.csv"
    atomic_write_csv(out, df)
    log(f"  日历 {len(df)} 行 → {out}", lines, log_file)
    return out


def step_stock_basic(data_root: Path, lines: list[str], log_file: Path | None) -> Path:
    import akshare as ak

    log("[2/4] 更新全 A 列表（在市）", lines, log_file)
    raw = ak.stock_info_a_code_name()
    df = raw.copy()
    df["code"] = df["code"].astype(str).str.zfill(6)
    df["exchange"] = df["code"].apply(
        lambda x: "SH" if x.startswith(("5", "6", "9")) else "SZ"
    )
    df["symbol"] = df["code"] + "." + df["exchange"]
    df["list_date"] = pd.NA
    df["delist_date"] = pd.NA
    df["status"] = "L"
    df = df[["symbol", "code", "name", "exchange", "list_date", "delist_date", "status"]]
    out = data_root / "01_meta" / "stock_basic.csv"
    atomic_write_csv(out, df)
    log(f"  stock_basic {len(df)} 行 → {out}", lines, log_file)
    return out


def step_indices(
    data_root: Path, end_date: str, lines: list[str], log_file: Path | None
) -> dict:
    import akshare as ak

    log("[3/4] 增量更新核心指数日 K", lines, log_file)
    end_ak = pd.Timestamp(end_date).strftime("%Y%m%d")
    stats: dict[str, int] = {}
    for index_code, ak_sym, name in CORE_INDICES:
        out = data_root / "04_index" / "daily" / f"{index_code}.csv"
        start_ak = BAR_START_DEFAULT
        if out.exists():
            last = pd.read_csv(out, usecols=["date"])["date"].max()
            start_ak = next_day_ak(str(last))
        if pd.Timestamp(start_ak) > pd.Timestamp(end_ak):
            log(f"  skip {index_code} 已最新", lines, log_file)
            stats[index_code] = 0
            continue
        try:
            raw = ak.stock_zh_index_daily(symbol=ak_sym)
            raw["date"] = pd.to_datetime(raw["date"])
            s, e = pd.to_datetime(start_ak), pd.to_datetime(end_ak)
            df = raw[(raw["date"] >= s) & (raw["date"] <= e)].copy()
            if df.empty:
                stats[index_code] = 0
                continue
            df["date"] = df["date"].dt.strftime("%Y-%m-%d")
            df.insert(0, "index_code", index_code)
            df.insert(1, "name", name)
            cols = ["index_code", "name", "date", "open", "high", "low", "close", "volume"]
            df = df[[c for c in cols if c in df.columns]]
            n = merge_csv(out, df)
            stats[index_code] = n
            log(f"  {index_code} ({name}) → {n} 行", lines, log_file)
        except Exception as exc:  # noqa: BLE001
            log(f"  FAIL {index_code}: {exc}", lines, log_file)
            stats[index_code] = -1
        time.sleep(0.25)
    return stats


def load_listed_symbols(data_root: Path) -> list[str]:
    path = data_root / "01_meta" / "stock_basic.csv"
    if not path.exists():
        return []
    df = pd.read_csv(path, usecols=["symbol", "status"])
    return sorted(df.loc[df["status"] == "L", "symbol"].astype(str).tolist())


def _bar_worker(item: tuple[str, str, str, str]) -> tuple[str, bool, str]:
    """(symbol, start_ak, end_ak, bars_dir) → (symbol, ok, err)."""
    sym, start_ak, end_ak, bars_dir = item
    try:
        from fetch_bars import fetch_stock_bar

        bar = fetch_stock_bar(sym, start_ak, end_ak)
        if bar.empty:
            return sym, False, "empty"
        merge_csv(Path(bars_dir) / f"{sym}.csv", bar)
        return sym, True, ""
    except Exception as exc:  # noqa: BLE001
        return sym, False, str(exc)[:200]


def step_bars(
    data_root: Path,
    end_date: str,
    lines: list[str],
    log_file: Path | None,
    *,
    max_symbols: int | None,
    workers: int,
    sleep: float,
    bar_start: str,
) -> dict:
    log("[4/4] 增量更新 A 股后复权日线", lines, log_file)
    bars_dir = data_root / "03_market" / "daily" / "bars_hfq"
    bars_dir.mkdir(parents=True, exist_ok=True)
    end_ak = pd.Timestamp(end_date).strftime("%Y%m%d")

    listed = load_listed_symbols(data_root)
    if not listed:
        log("  无 stock_basic，跳过日线", lines, log_file)
        return {"todo": 0, "ok": 0, "fail": 0}

    if max_symbols is not None:
        listed = listed[: max(1, int(max_symbols))]

    todo: list[tuple[str, str, str, str]] = []
    for sym in listed:
        path = bars_dir / f"{sym}.csv"
        if path.exists():
            try:
                last = str(pd.read_csv(path, usecols=["date"])["date"].max())
                start_ak = next_day_ak(last)
            except Exception:
                start_ak = bar_start
        else:
            start_ak = bar_start
        if pd.Timestamp(start_ak) > pd.Timestamp(end_ak):
            continue
        todo.append((sym, start_ak, end_ak, str(bars_dir)))

    log(
        f"  在市 {len(listed)} 只，待补 {len(todo)} 只 → {end_date}（workers={workers}）",
        lines,
        log_file,
    )
    if not todo:
        return {"todo": 0, "ok": 0, "fail": 0, "symbols": len(listed)}

    ok = fail = 0
    fail_syms: list[str] = []

    def consume(sym: str, success: bool, err: str, done: int) -> None:
        nonlocal ok, fail
        if success:
            ok += 1
        else:
            fail += 1
            fail_syms.append(sym)
            if err and err != "empty" and fail <= 20:
                log(f"  WARN 跳过 {sym}: {err}", lines, log_file)
        if done % 50 == 0 or done == len(todo):
            log(f"  bars {done}/{len(todo)} ok={ok} fail={fail} last={sym}", lines, log_file)

    if workers <= 1:
        from fetch_bars import fetch_stock_bar

        for i, (sym, start_ak, end_ak_sym, _) in enumerate(todo, start=1):
            try:
                bar = fetch_stock_bar(sym, start_ak, end_ak_sym)
                if bar.empty:
                    consume(sym, False, "empty", i)
                else:
                    merge_csv(bars_dir / f"{sym}.csv", bar)
                    consume(sym, True, "", i)
            except Exception as exc:  # noqa: BLE001
                consume(sym, False, str(exc)[:200], i)
            if sleep > 0:
                time.sleep(sleep)
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futs = {pool.submit(_bar_worker, item): item[0] for item in todo}
            done = 0
            for fut in as_completed(futs):
                done += 1
                sym, success, err = fut.result()
                consume(sym, success, err, done)

    return {
        "todo": len(todo),
        "ok": ok,
        "fail": fail,
        "symbols": len(listed),
        "fail_syms": fail_syms[:50],
    }


def run(
    *,
    data_root: Path,
    log_dir: Path,
    end_date: str | None = None,
    max_symbols: int | None = None,
    bar_workers: int = 1,
    bar_sleep: float = 0.05,
    bar_start: str = BAR_START_DEFAULT,
    skip_stock_basic: bool = False,
    skip_bars: bool = False,
) -> dict:
    data_root = data_root.resolve()
    log_dir = log_dir.resolve()
    log_dir.mkdir(parents=True, exist_ok=True)
    (data_root / "01_meta").mkdir(parents=True, exist_ok=True)
    (data_root / "03_market" / "daily" / "bars_hfq").mkdir(parents=True, exist_ok=True)
    (data_root / "04_index" / "daily").mkdir(parents=True, exist_ok=True)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"bars_only_{stamp}.log"
    lines: list[str] = []
    t0 = time.time()
    log("=" * 56, lines, log_file)
    log(f"data = {data_root}", lines, log_file)

    report: dict = {
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "data_root": str(data_root),
        "ok": False,
    }
    try:
        cal_path = step_calendar(data_root, lines, log_file)
        if not skip_stock_basic:
            step_stock_basic(data_root, lines, log_file)
        end = resolve_end_date(cal_path, end_date)
        report["end_date"] = end
        log(f"目标截止交易日: {end}", lines, log_file)
        report["indices"] = step_indices(data_root, end, lines, log_file)
        if not skip_bars:
            report["bars"] = step_bars(
                data_root,
                end,
                lines,
                log_file,
                max_symbols=max_symbols,
                workers=max(1, int(bar_workers)),
                sleep=float(bar_sleep),
                bar_start=bar_start,
            )
        report["ok"] = True
    except Exception as exc:  # noqa: BLE001
        report["error"] = str(exc)
        log(f"FAIL {exc}", lines, log_file)
        raise
    finally:
        report["elapsed_sec"] = round(time.time() - t0, 1)
        report["finished_at"] = datetime.now().isoformat(timespec="seconds")
        (log_dir / f"bars_only_{stamp}.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        log(f"完成 ok={report.get('ok')} 耗时 {report['elapsed_sec']}s", lines, log_file)
        log(f"日志 {log_file}", lines, log_file)
    return report


def main() -> None:
    p = argparse.ArgumentParser(description="akshare_bars：日历 / 指数 / A股日线")
    p.add_argument("--data-dir", default=str(DEFAULT_DATA), help="数据根目录（含 a_share 结构）")
    p.add_argument("--log-dir", default=str(DEFAULT_LOG))
    p.add_argument("--end-date", default=None, help="YYYY-MM-DD，默认自动（未收盘用上一交易日）")
    p.add_argument("--max-symbols", type=int, default=None, help="调试：只拉前 N 只在市股票")
    p.add_argument("--bar-workers", type=int, default=1, help="日线并行进程数（建议 1）")
    p.add_argument("--bar-sleep", type=float, default=0.05)
    p.add_argument("--bar-start", default=BAR_START_DEFAULT, help="无历史文件时的起始日 YYYYMMDD")
    p.add_argument("--skip-stock-basic", action="store_true")
    p.add_argument("--skip-bars", action="store_true", help="只更日历+指数")
    args = p.parse_args()
    run(
        data_root=Path(args.data_dir),
        log_dir=Path(args.log_dir),
        end_date=args.end_date,
        max_symbols=args.max_symbols,
        bar_workers=args.bar_workers,
        bar_sleep=args.bar_sleep,
        bar_start=args.bar_start,
        skip_stock_basic=args.skip_stock_basic,
        skip_bars=args.skip_bars,
    )


if __name__ == "__main__":
    main()
