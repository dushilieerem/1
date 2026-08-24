# -*- coding: utf-8 -*-
"""AI 策略生成冒烟：20 条自然语言 → POST /api/ai/strategy-generations。"""
from __future__ import annotations

import json
import time
import uuid
from datetime import datetime
from pathlib import Path
from urllib import error, request

API = "http://192.168.3.64:9527/api/ai/strategy-generations"
OUT_DIR = Path(r"E:\quant-lab\SV\SVQuant\WebApp\docs")
RAW = OUT_DIR / "ai-strategy-generation-smoke-2026-07-31.json"
DOC = OUT_DIR / "AI策略生成-冒烟测试报告-2026-07-31.md"

# 覆盖常见研究假设；部分故意越界以观察校验
PROMPTS: list[dict[str, str]] = [
    {
        "id": "T01",
        "tag": "动量等权",
        "prompt": "每 20 个交易日调仓一次，买入过去 20 日涨幅最高的 30 只股票，等权持有，其余清仓。",
    },
    {
        "id": "T02",
        "tag": "短动量",
        "prompt": "每 10 日调仓，买入过去 60 日收益率排名靠前的 20 只，等权；未入选标的权重设为 0。",
    },
    {
        "id": "T03",
        "tag": "反转",
        "prompt": "生成一个简单反转策略：每 5 日调仓，买入过去 5 日跌幅最大的 50 只，等权配置。",
    },
    {
        "id": "T04",
        "tag": "长动量",
        "prompt": "每月（约 21 个交易日）调仓，选过去 120 日动量最高的 40 只等权。",
    },
    {
        "id": "T05",
        "tag": "波动率低",
        "prompt": "每 20 日调仓，买入过去 20 日收益波动率最低的 30 只股票，等权持有。",
    },
    {
        "id": "T06",
        "tag": "双动量交叉",
        "prompt": "每 10 日调仓：过去 20 日涨幅为正且过去 60 日涨幅排名前 50 的股票等权持有，其余清仓。",
    },
    {
        "id": "T07",
        "tag": "TopN 变化",
        "prompt": "每 15 日调仓，买入过去 10 日涨幅最高的 10 只，等权。",
    },
    {
        "id": "T08",
        "tag": "BottomN",
        "prompt": "每 20 日调仓，做多过去 20 日跌幅最大的 25 只（反转），等权。",
    },
    {
        "id": "T09",
        "tag": "均线交叉表述",
        "prompt": "用收盘价：当短期 5 日均线高于 20 日均线时持有该股，否则清仓；组合等权，每日更新目标权重。",
    },
    {
        "id": "T10",
        "tag": "动量+均线过滤",
        "prompt": "每 20 日调仓，在收盘价高于 60 日均线的股票中，选过去 20 日动量最高的 30 只等权。",
    },
    {
        "id": "T11",
        "tag": "文档示例",
        "prompt": "生成一个每 20 日调仓、买入过去 20 日动量最高 30 只股票的等权策略。",
    },
    {
        "id": "T12",
        "tag": "周度动量",
        "prompt": "每 5 个交易日调仓，买入过去 5 日涨幅最高的 100 只，等权。",
    },
    {
        "id": "T13",
        "tag": "稀疏调仓",
        "prompt": "每 60 日调仓一次，买入过去 252 日涨幅最高的 20 只等权持有。",
    },
    {
        "id": "T14",
        "tag": "相对强度",
        "prompt": "每日计算过去 20 日收益率横截面排名，只在每周五（或每 5 日）调仓到排名前 30 等权。",
    },
    {
        "id": "T15",
        "tag": "极简一句话",
        "prompt": "做多近一个月涨得最多的股票，等权，定期调仓。",
    },
    {
        "id": "T16",
        "tag": "越界-成交量",
        "prompt": "每 20 日调仓，买入过去 20 日成交额最高的 30 只等权（需要成交量字段）。",
    },
    {
        "id": "T17",
        "tag": "越界-事件订单",
        "prompt": "写一个事件驱动策略：股价跌破前日低点时市价买入，涨超 5% 止盈卖出。",
    },
    {
        "id": "T18",
        "tag": "越界-基本面",
        "prompt": "按 PE 最低的 50 只股票等权持仓，每月调仓。",
    },
    {
        "id": "T19",
        "tag": "越界-多空对冲",
        "prompt": "多头持有动量最高 30 只、空头持有动量最低 30 只，多空等权对冲，每 20 日调仓。",
    },
    {
        "id": "T20",
        "tag": "越界-外部库",
        "prompt": "用 numpy 和 talib 计算 RSI，RSI 低于 30 买入高于 70 卖出，等权组合。",
    },
]


def call_one(prompt: str, timeout: int = 45) -> dict:
    body = {
        "prompt": prompt,
        "context": {"universe": "CSI500", "frequency": "1d"},
        "idempotency_key": str(uuid.uuid4()),
    }
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = request.Request(
        API,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    t0 = time.perf_counter()
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            http = resp.status
    except error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        http = e.code
    except Exception as e:  # noqa: BLE001
        return {
            "http": None,
            "latency_ms": int((time.perf_counter() - t0) * 1000),
            "error": f"{type(e).__name__}: {e}",
            "status": "transport_error",
            "validation_errors": [],
            "strategy_name": None,
        }
    latency = int((time.perf_counter() - t0) * 1000)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {
            "http": http,
            "latency_ms": latency,
            "error": f"非 JSON: {raw[:300]}",
            "status": "parse_error",
            "validation_errors": [],
            "strategy_name": None,
        }
    strat = payload.get("strategy") or {}
    val = payload.get("validation") or {}
    return {
        "http": http,
        "latency_ms": latency,
        "status": payload.get("status") or ("http_error" if http != 200 else "unknown"),
        "generation_id": payload.get("generation_id"),
        "validation_status": val.get("status"),
        "validation_errors": list(val.get("errors") or []),
        "validation_warnings": list(val.get("warnings") or []),
        "strategy_name": strat.get("strategy_name"),
        "code_chars": len(strat.get("strategy_code") or ""),
        "meta": payload.get("meta") or {},
        "http_detail": payload.get("detail") or payload.get("error"),
        "raw_status_fields": {
            "status": payload.get("status"),
            "validation": val.get("status"),
        },
    }


def main() -> None:
    rows: list[dict] = []
    print(f"API={API}  cases={len(PROMPTS)}")
    for i, case in enumerate(PROMPTS, 1):
        print(f"[{i}/{len(PROMPTS)}] {case['id']} {case['tag']} ...", flush=True)
        r = call_one(case["prompt"])
        row = {**case, **r}
        rows.append(row)
        st = row.get("status")
        errs = "; ".join(row.get("validation_errors") or []) or row.get("error") or ""
        print(f"    -> {st}  {row.get('latency_ms')}ms  {errs[:120]}", flush=True)
        time.sleep(0.4)

    ready = [r for r in rows if r.get("status") == "ready"]
    rejected = [r for r in rows if r.get("status") == "rejected"]
    other = [r for r in rows if r.get("status") not in ("ready", "rejected")]

    # 错误归类
    err_bucket: dict[str, list[str]] = {}
    for r in rejected:
        key = "; ".join(r.get("validation_errors") or []) or "(无 errors 字段)"
        err_bucket.setdefault(key, []).append(r["id"])

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    pass_n = len(ready)
    total = len(rows)
    rate = 100.0 * pass_n / total if total else 0.0

    # 写 raw json
    RAW.write_text(
        json.dumps({"at": now, "api": API, "rows": rows}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    lines: list[str] = []
    a = lines.append
    a("# AI 策略生成 · 冒烟测试报告")
    a("")
    a(f"> **时间：** {now}  ")
    a(f"> **接口：** `{API}`  ")
    a("> **口径：** HTTP 200 且 `status=ready` 计为通过；`rejected` 计为未通过（模型有返回但 AST/白名单校验失败）。  ")
    a("> **上下文：** `universe=CSI500`, `frequency=1d`。端点只生成草稿，不回测。")
    a("")
    a("---")
    a("")
    a("## 1. 总览")
    a("")
    a("| 指标 | 值 |")
    a("|------|----|")
    a(f"| 用例数 | **{total}** |")
    a(f"| 通过 `ready` | **{pass_n}** |")
    a(f"| 拒绝 `rejected` | **{len(rejected)}** |")
    a(f"| 其它（传输/HTTP/解析） | **{len(other)}** |")
    a(f"| **通过率** | **{rate:.1f}%** |")
    if rows:
        lats = [r["latency_ms"] for r in rows if isinstance(r.get("latency_ms"), int)]
        if lats:
            a(f"| 延迟（min / median / max） | {min(lats)} / {sorted(lats)[len(lats)//2]} / {max(lats)} ms |")
    a("")
    a("### 预期分层（设计）")
    a("")
    a("| 组别 | 用例 | 说明 |")
    a("|------|------|------|")
    a("| 合规日频 close 策略 | T01–T15 | 应尽量 `ready` |")
    a("| 故意越界 | T16–T20 | 成交量 / 事件 / 基本面 / 空头 / 外部库，预期多为 `rejected` |")
    a("")

    in_scope = [r for r in rows if r["id"] <= "T15"]
    oos = [r for r in rows if r["id"] >= "T16"]
    in_ready = sum(1 for r in in_scope if r.get("status") == "ready")
    oos_ready = sum(1 for r in oos if r.get("status") == "ready")
    a("| 分层 | 通过 / 总数 | 通过率 |")
    a("|------|-------------|--------|")
    a(f"| 合规组 T01–T15 | {in_ready}/{len(in_scope)} | {100*in_ready/max(len(in_scope),1):.1f}% |")
    a(f"| 越界组 T16–T20 | {oos_ready}/{len(oos)} | {100*oos_ready/max(len(oos),1):.1f}% |")
    a("")

    a("## 2. 报错原因汇总（`rejected`）")
    a("")
    if not err_bucket:
        a("_无 rejected 样本。_")
    else:
        a("| 次数 | 校验错误原文 | 用例 |")
        a("|-----:|--------------|------|")
        for msg, ids in sorted(err_bucket.items(), key=lambda x: -len(x[1])):
            a(f"| {len(ids)} | `{msg}` | {', '.join(ids)} |")
    a("")

    if other:
        a("## 2b. 其它失败")
        a("")
        a("| 用例 | status | 说明 |")
        a("|------|--------|------|")
        for r in other:
            a(
                f"| {r['id']} | `{r.get('status')}` | "
                f"{r.get('error') or r.get('http_detail') or r.get('http')} |"
            )
        a("")

    a("## 3. 逐条明细")
    a("")
    a("| ID | 标签 | 结果 | 策略名 | 延迟ms | 错误 / 备注 |")
    a("|----|------|------|--------|-------:|-------------|")
    for r in rows:
        errs = "; ".join(r.get("validation_errors") or [])
        note = errs or r.get("error") or r.get("http_detail") or ""
        note = str(note).replace("|", "\\|")[:120]
        name = r.get("strategy_name") or "—"
        a(
            f"| {r['id']} | {r['tag']} | `{r.get('status')}` | `{name}` | "
            f"{r.get('latency_ms')} | {note or '—'} |"
        )
    a("")

    a("## 4. 用例原文")
    a("")
    for r in rows:
        a(f"### {r['id']} · {r['tag']}")
        a("")
        a(f"- **结果：** `{r.get('status')}`")
        if r.get("strategy_name"):
            a(f"- **策略类名：** `{r['strategy_name']}`")
        if r.get("validation_errors"):
            a(f"- **校验：** {'; '.join(r['validation_errors'])}")
        a("")
        a("```")
        a(r["prompt"])
        a("```")
        a("")

    a("## 5. 结论与建议")
    a("")
    a("1. **整体通过率**见上表；合规组与越界组请分开看，避免把「故意越界」算进产品可用性。")
    a("2. 前端已对 `rejected` 展示 `validation.errors`；用户改自然语言后换新 `idempotency_key` 重试。")
    a("3. 若合规组大量出现「只允许 import pandas / 白名单方法」类错误，需同事侧收紧模型提示词或放宽 AST 白名单。")
    a("4. 原始 JSON：`docs/ai-strategy-generation-smoke-2026-07-31.json`。")
    a("")

    DOC.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nPASS {pass_n}/{total} ({rate:.1f}%)")
    print(f"wrote {DOC}")
    print(f"wrote {RAW}")


if __name__ == "__main__":
    main()
