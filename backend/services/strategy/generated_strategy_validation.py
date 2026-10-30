# -*- coding: utf-8 -*-
"""AI 生成策略的静态校验（自 ResearchEngine `app/api/ai_strategy.py` 迁入，ADR-037 P1-3）。

只做静态检查，不执行模型输出：类结构、只允许 `import pandas as pd`、
仅 `self.close`、白名单面板方法、可编译。
"""
from __future__ import annotations

import ast

ALLOWED_FIELDS = frozenset({"close"})
ALLOWED_PANEL_METHODS = frozenset(
    {
        "abs", "astype", "clip", "diff", "fillna", "mean", "median", "min", "max",
        "div", "pct_change", "rank", "rolling", "shift", "std", "sum", "where", "ffill",
    }
)


class _StrategyVisitor(ast.NodeVisitor):
    _ALLOWED_NODES = {
        ast.Module, ast.Import, ast.alias, ast.ClassDef, ast.FunctionDef, ast.arguments,
        ast.arg, ast.Return, ast.Assign, ast.Name, ast.Load, ast.Store, ast.Attribute,
        ast.Call, ast.Constant, ast.BinOp, ast.UnaryOp, ast.Add, ast.Sub, ast.Mult,
        ast.Div, ast.Pow, ast.USub, ast.Compare, ast.Eq, ast.NotEq, ast.Gt, ast.GtE,
        ast.Lt, ast.LtE, ast.keyword, ast.Subscript, ast.Mod, ast.Slice,
    }

    def __init__(self) -> None:
        self.errors: list[str] = []

    def generic_visit(self, node: ast.AST) -> None:
        if type(node) not in self._ALLOWED_NODES:
            self.errors.append(f"不允许的代码结构：{type(node).__name__}")
            return
        super().generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        if len(node.names) != 1 or node.names[0].name != "pandas" or node.names[0].asname != "pd":
            self.errors.append("只允许 import pandas as pd")
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        method_names = [item.name for item in node.body if isinstance(item, ast.FunctionDef)]
        if method_names != ["__init__", "generate_signals"]:
            self.errors.append("策略类必须且只能定义 __init__ 与 generate_signals")
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        args = [arg.arg for arg in node.args.args]
        expected = ["self", "close"] if node.name == "__init__" else ["self"]
        if args != expected or node.decorator_list:
            self.errors.append(f"{node.name} 的签名不符合向量化策略契约")
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if node.attr.startswith("__"):
            self.errors.append("不允许访问双下划线属性")
        if isinstance(node.value, ast.Name) and node.value.id == "self" and node.attr != "close":
            self.errors.append(f"不允许的 self 属性：{node.attr}")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
            if node.func.value.id == "pd" and node.func.attr == "DataFrame":
                self.generic_visit(node)
                return
        if not isinstance(node.func, ast.Attribute) or node.func.attr not in ALLOWED_PANEL_METHODS:
            method = node.func.attr if isinstance(node.func, ast.Attribute) else type(node.func).__name__
            self.errors.append(f"不允许调用：{method}；仅允许 pandas.DataFrame 或白名单面板方法")
        self.generic_visit(node)


def validate_generated_strategy(strategy: dict[str, object]) -> list[str]:
    """返回错误列表；空列表表示通过。"""
    used_fields = strategy.get("used_fields") or []
    unknown_fields = sorted(set(used_fields) - ALLOWED_FIELDS)
    if unknown_fields:
        return [f"used_fields 包含未登记字段：{', '.join(unknown_fields)}"]

    code = str(strategy.get("strategy_code") or "")
    name = str(strategy.get("strategy_name") or "")
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return [f"策略代码语法错误：{exc.msg}"]

    classes = [node for node in tree.body if isinstance(node, ast.ClassDef)]
    if len(classes) != 1 or len(tree.body) not in {1, 2}:
        return ["策略代码必须只包含 pandas 导入和一个策略类定义"]
    if classes[0].name != name:
        return ["策略类名必须与 strategy_name 一致"]

    visitor = _StrategyVisitor()
    visitor.visit(tree)
    if visitor.errors:
        return visitor.errors

    try:
        compile(code, "<generated_strategy>", "exec")
    except SyntaxError as exc:
        return [f"策略代码无法编译：{exc.msg}"]
    return []


__all__ = ["ALLOWED_FIELDS", "ALLOWED_PANEL_METHODS", "validate_generated_strategy"]
