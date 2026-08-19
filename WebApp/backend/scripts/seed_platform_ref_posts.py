# -*- coding: utf-8 -*-
"""用 admin 发 5 条带 platform_ref 的面板验证帖，并跑读帖摘要抽检。

用法（在 backend 目录）:
  python -u scripts/seed_platform_ref_posts.py
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.factor.dashboard_store import lookup_panel_metric  # noqa: E402

API = "http://127.0.0.1:8766"
ADMIN_USER = "admin"
ADMIN_PASS = "admin123"

# 五条不同风格的面板帖（CSI300 · 3y · 过滤涨停）
CASES = [
    {
        "factor_name": "earnings_yield",
        "title": "【验证·面板真源】盈利收益率 earnings_yield：沪深300·近3年",
        "blurb": "价值因子面板摘录，指标均挂 platform_ref，供读帖助手核对数字。",
    },
    {
        "factor_name": "ln_cap",
        "title": "【验证·面板真源】对数市值 ln_cap：规模效应一瞥",
        "blurb": "规模相关因子；注意 IC 与年化符号含义，勿当实盘承诺。",
    },
    {
        "factor_name": "small_size",
        "title": "【验证·面板真源】小市值 small_size 面板指标",
        "blurb": "与 ln_cap 同库对照；摘要应复述引用数字，不得改夏普/年化。",
    },
    {
        "factor_name": "alpha360_close22",
        "title": "【验证·面板真源】alpha360_close22 负向样本",
        "blurb": "刻意选负年化样本，测摘要是否如实写局限而非美化。",
    },
    {
        "factor_name": "momentum_acceleration",
        "title": "【验证·面板真源】动量加速度 momentum_acceleration",
        "blurb": "动量库面板摘录；读帖应标明来自因子面板缓存。",
    },
]


def _req(method: str, path: str, body: dict | None = None, token: str | None = None):
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = urllib.request.Request(
        API + path, data=data, headers=headers, method=method
    )
    try:
        with urllib.request.urlopen(r, timeout=120) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw)
        except Exception:
            payload = {"error": raw}
        return e.code, payload


def _body_html(ref: dict, blurb: str) -> str:
    md = ref.get("metrics_display") or {}
    items = "".join(
        f"<li><strong>{k}</strong>：{v}</li>" for k, v in md.items()
    )
    return (
        f"<p>{blurb}</p>"
        f"<p><strong>因子</strong>：<code>{ref.get('factor_name')}</code></p>"
        f"<p><strong>股票池</strong>：沪深300（CSI300）</p>"
        f"<p><strong>周期</strong>：近3年（3y）</p>"
        f"<p><strong>涨跌停</strong>：过滤涨停</p>"
        f"<p><strong>指标摘要</strong>（来自因子面板缓存）</p>"
        f"<ul>{items}</ul>"
        "<blockquote><p>免责声明：内容不构成投资建议。"
        "面板指标为聚合缓存，与单次检测参数可能不同。</p></blockquote>"
    )


def main() -> int:
    # 补一条动量/波动类（若缓存有）
    extra_candidates = [
        "momentum_20",
        "stock_mom_20",
        "volatility_20",
        "ivol_20",
        "turnover_20",
        "ep",
        "bp",
        "roe",
    ]
    for name in extra_candidates:
        if len(CASES) >= 5:
            break
        if any(c["factor_name"] == name for c in CASES):
            continue
        if lookup_panel_metric(
            factor_name=name, universe="CSI300", period="3y", filter_limit_up=True
        ):
            CASES.append(
                {
                    "factor_name": name,
                    "title": f"【验证·面板真源】{name} 面板摘录",
                    "blurb": f"自动补选因子 {name}，用于真源落库与读帖摘要抽检。",
                }
            )

    st, login = _req(
        "POST",
        "/api/auth/login",
        {"username": ADMIN_USER, "password": ADMIN_PASS},
    )
    if st != 200 or not login.get("token"):
        print("登录失败", st, login)
        return 1
    token = login["token"]
    print("admin 登录 OK")

    created: list[dict] = []
    for case in CASES[:5]:
        ref = lookup_panel_metric(
            factor_name=case["factor_name"],
            universe="CSI300",
            period="3y",
            filter_limit_up=True,
        )
        if not ref:
            print("跳过（面板无数据）", case["factor_name"])
            continue
        # 展示用中文池/周期；查库码保留
        ref = {
            **ref,
            "universe": "沪深300",
            "period": "近3年",
            "universe_code": "CSI300",
            "period_code": "3y",
            "filter_limit_up": True,
            "label": f"因子面板 · {case['factor_name']} · 沪深300 · 近3年 · 过滤涨停",
        }
        body = {
            "title": case["title"],
            "body": _body_html(ref, case["blurb"]),
            "section": "factor",
            "status": "published",
            "platform_ref": ref,
        }
        st, res = _req("POST", "/api/community/posts", body, token=token)
        if st != 200 or not res.get("ok"):
            print("发帖失败", case["factor_name"], st, res)
            continue
        post = res["post"]
        pref = post.get("platform_ref") or {}
        print(
            f"发帖 OK id={post['id']} factor={case['factor_name']} "
            f"ref_keys={list((pref.get('metrics_display') or {}).keys())[:4]}"
        )
        created.append(post)

    if len(created) < 5:
        print(f"警告：只发出 {len(created)} 帖（需要 5 条有效面板行）")

    # 对每帖跑读帖摘要，检查是否带回 platform_ref / 是否漂移 flag
    print("\n=== 读帖摘要抽检 ===")
    for post in created:
        st, res = _req(
            "POST",
            "/api/agent/runs",
            {
                "mode": "multi",
                "crew": "community_read",
                "goal": "为社区帖生成 TL;DR 摘要",
                "context": {
                    "post_id": post["id"],
                    "title": post["title"],
                    "body": post["body"],
                    "code_snippet": post.get("code_snippet") or "",
                    "with_risks": True,
                    "platform_ref": post.get("platform_ref"),
                },
            },
            token=token,
        )
        ok = res.get("ok")
        summary = (res.get("outputs") or {}).get("summary_md") or ""
        flags = (res.get("outputs") or {}).get("flags") or []
        arts = ((res.get("board") or {}).get("artifacts") or {})
        has_ref = bool(arts.get("platform_ref"))
        drift = [f for f in flags if f.get("code") == "summary_metrics_drift"]
        print(
            f"post={post['id']} ok={ok} has_ref={has_ref} "
            f"flags={len(flags)} drift={len(drift)} "
            f"summary_len={len(summary)}"
        )
        if summary:
            print("  summary:", summary.replace("\n", " / ")[:180])
        if drift:
            print("  DRIFT:", drift[0].get("message"))

    print("\n帖子链接：")
    for p in created:
        print(f"  http://127.0.0.1:9530/community/post/{p['id']}")
    return 0 if len(created) >= 5 else 2


if __name__ == "__main__":
    raise SystemExit(main())
