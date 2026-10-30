# -*- coding: utf-8 -*-
"""架构护栏：AI 调用必须经 `ai.router`，不得绕过到供应商层（ADR-037）。

新代码若直接 `from ai.gateway.llm_client import chat_completions`，
会重新长出第四套分支；这里用静态扫描把约定变成可执行的测试。
"""
import re
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
SCAN_DIRS = (BACKEND / "ai", BACKEND / "app", BACKEND / "services")

# 供应商层的实现与助手壳本身可以直连
ALLOWED_PREFIXES = (
    BACKEND / "ai" / "gateway",
    BACKEND / "ai" / "router",
)
ALLOWED_FILES = {BACKEND / "app" / "routers" / "ai.py"}

LEGACY_PATTERNS = (
    re.compile(r"\bchat_completions\s*\("),
    re.compile(r"from\s+ai\.gateway\.llm_client\s+import\s+[^\n]*chat_completions"),
)


def _iter_sources():
    for root in SCAN_DIRS:
        for path in root.rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            if any(path.is_relative_to(prefix) for prefix in ALLOWED_PREFIXES):
                continue
            if path in ALLOWED_FILES:
                continue
            yield path


class LayerBoundaryTest(unittest.TestCase):
    def test_no_direct_llm_client_calls_outside_gateway(self):
        offenders = []
        for path in _iter_sources():
            text = path.read_text(encoding="utf-8", errors="replace")
            for pattern in LEGACY_PATTERNS:
                if pattern.search(text):
                    offenders.append(path.relative_to(BACKEND).as_posix())
                    break
        self.assertEqual(offenders, [], f"这些模块绕过了 ai.router: {offenders}")

    def test_router_is_the_only_entry_for_tasks(self):
        """任务 id 必须能在注册表里找到，避免拼写漂移。"""
        import sys

        sys.path.insert(0, str(BACKEND))
        from ai.router import all_tasks

        ids = {spec.task_id for spec in all_tasks()}
        pattern = re.compile(r"run_task\(\s*[\"']([a-z0-9_.]+)[\"']")
        used = set()
        for path in _iter_sources():
            text = path.read_text(encoding="utf-8", errors="replace")
            used.update(pattern.findall(text))
        self.assertTrue(used, "没有扫描到任何 run_task 调用，护栏失效")
        self.assertEqual(used - ids, set(), f"存在未注册的任务 id: {sorted(used - ids)}")


if __name__ == "__main__":
    unittest.main()
