# -*- coding: utf-8 -*-
"""AI 离线评测集与回归门槛（P1-A07）。

默认跑确定性契约用例（不调用模型、不需要密钥），供 CI/发布前门禁使用：
    cd backend && python -m ai.evals.run
    python -m ai.evals.run --json

用例 `cases.jsonl` 每行一个 JSON；新增用例不需要改代码。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

CASES_PATH = Path(__file__).with_name("cases.jsonl")


def load_cases(path: Path | None = None) -> list[dict[str, Any]]:
    p = path or CASES_PATH
    out: list[dict[str, Any]] = []
    for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            case = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{p.name}:{i} 不是合法 JSON: {exc}") from exc
        if "id" not in case or "kind" not in case:
            raise ValueError(f"{p.name}:{i} 缺少 id/kind")
        out.append(case)
    return out


def _check_factor_static(case: dict[str, Any]) -> tuple[bool, str]:
    from services.factor.generated_factor_validation import validate_generated_factor

    code = str(case.get("code") or "")
    name = "candidate"
    errors = validate_generated_factor({"factor_name": name, "factor_code": code})
    ok = not errors
    return ok, "; ".join(errors) or "静态校验通过"


def _check_json_keys(case: dict[str, Any]) -> tuple[bool, str]:
    payload = case.get("payload") or {}
    required = [str(x) for x in (case.get("required") or [])]
    missing = [k for k in required if k not in payload]
    return not missing, ("缺少字段: " + ", ".join(missing)) if missing else "字段齐全"


def _check_summary_numbers(case: dict[str, Any]) -> tuple[bool, str]:
    from ai.crews._shared.metrics_trust import summary_number_flags

    flags = summary_number_flags(str(case.get("summary") or ""), case.get("platform_ref"))
    return not flags, "; ".join(f.get("message", "") for f in flags) or "摘要数字与引用一致"


CHECKERS = {
    "factor_static": _check_factor_static,
    "json_keys": _check_json_keys,
    "summary_numbers": _check_summary_numbers,
}


def run(cases: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for case in cases if cases is not None else load_cases():
        checker = CHECKERS.get(str(case.get("kind")))
        if checker is None:
            rows.append({"id": case.get("id"), "ok": False, "detail": f"未知 kind: {case.get('kind')}"})
            continue
        try:
            ok, detail = checker(case)
        except Exception as exc:  # noqa: BLE001
            ok, detail = False, f"执行异常: {exc}"
        expected = bool(case.get("expect_ok", True))
        passed = ok == expected
        rows.append(
            {
                "id": case.get("id"),
                "ok": passed,
                "detail": detail,
                "expected_ok": expected,
                "actual_ok": ok,
            }
        )
    total = len(rows)
    passed = sum(1 for r in rows if r["ok"])
    return {
        "ok": passed == total,
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "results": rows,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AI 离线评测集")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    parser.add_argument("--cases", default=str(CASES_PATH), help="用例文件路径")
    args = parser.parse_args(argv)
    try:
        report = run(load_cases(Path(args.cases)))
    except ValueError as exc:
        print(f"[ai-eval] {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        for row in report["results"]:
            mark = "PASS" if row["ok"] else "FAIL"
            print(f"[{mark}] {row['id']}: {row.get('detail', '')}")
        print(f"[ai-eval] {report['passed']}/{report['total']} passed")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
