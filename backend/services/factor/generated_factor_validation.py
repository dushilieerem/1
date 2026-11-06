# -*- coding: utf-8 -*-
"""AI 生成因子的静态校验（自 ResearchEngine `app/api/ai_factor.py` 迁入，ADR-037 P1-3）。

只做静态检查，不执行模型输出：字段/方法白名单、AST 结构、未来数据规则，
以及「能否按因子库外壳编译通过」。

编译检查沿用 ResearchEngine 的 `FactorLibrary` 外壳文本——只是 `compile()`，
不需要研究服务运行时在场。若将来 SVQuant 有自己的因子运行时，
只需替换 `compile_errors()` 的包装实现。
"""
from __future__ import annotations

import ast
from typing import Any

ALLOWED_FIELDS = frozenset({"open", "high", "low", "close", "volume", "amount", "turnover", "current_mv", "listed_status", "the_sw_industry_code", "up_and_down_status"})
ALLOWED_METHODS = frozenset(
    {
        "abs", "clip", "diff", "fillna", "mean", "median", "min", "max", "pct_change",
        "rank", "rolling", "shift", "std", "sum", "where",
        # Preprocessing primitives (QA-20): winsorize / cross-section standardise /
        # industry demean / liquidity percentile / suspended filter.
        "quantile", "groupby", "transform", "sub", "div", "add", "mul",
        "eq", "ne", "gt", "ge", "lt", "le", "isin", "notna", "isna",
        "mask", "replace", "between", "any", "all",
    }
)

# 与研究计算服务的因子库外壳保持一致（仅用于编译检查）。
_FACTOR_SHELL_HEAD = (
    "from app.services.factor.base import FactorLibrary\n\n"
    "import numpy as np\n"
    "import pandas as pd\n"
    "try:\n"
    "    from app.services.factor.sqlite_loader import load_factor_tool\n"
    "    tool = load_factor_tool()\n"
    "except (FileNotFoundError, ImportError):\n"
    "    from app.services.factor import tool\n\n"
    "class UserFactorLibrary(FactorLibrary):\n"
    '    author = "user"\n\n'
)


def wrap_for_compile(factor_code: str) -> str:
    """把单方法源码缩进成 FactorLibrary 子类，用于编译校验。"""
    wrapped = _FACTOR_SHELL_HEAD
    for line in factor_code.splitlines():
        wrapped += f"    {line}\n" if line.strip() else "\n"
    return wrapped


def compile_errors(factor_code: str) -> list[str]:
    try:
        compile(wrap_for_compile(factor_code), "<generated_factor>", "exec")
    except SyntaxError as exc:
        return [f"因子代码无法编译：{exc.msg}"]
    return []


class _GeneratedFactorVisitor(ast.NodeVisitor):
    """默认拒绝的 AST 检查器，仅接受简单面板计算表达式。"""

    _ALLOWED_NODES = {
        ast.Module, ast.FunctionDef, ast.arguments, ast.arg, ast.Return, ast.Assign,
        ast.Name, ast.Load, ast.Store, ast.Attribute, ast.Call, ast.Constant,
        ast.BinOp, ast.UnaryOp, ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow,
        ast.USub, ast.Compare, ast.Eq, ast.NotEq, ast.Gt, ast.GtE, ast.Lt, ast.LtE,
        ast.keyword,
    }

    def __init__(self) -> None:
        self.errors: list[str] = []
        self.scalar_values: dict[str, object] = {}

    def _scalar(self, node: ast.AST) -> object:
        """仅推导简单参数/赋值常量，不执行模型表达式。"""
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name):
            return self.scalar_values.get(node.id)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            value = self._scalar(node.operand)
            return -value if type(value) in (int, float) else None
        if isinstance(node, ast.BinOp):
            left, right = self._scalar(node.left), self._scalar(node.right)
            if type(left) not in (int, float) or type(right) not in (int, float):
                return None
            if abs(left) > 1_000_000 or abs(right) > 1_000_000:
                return None
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
        return None

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        args = node.args.posonlyargs + node.args.args
        for arg, default in zip(args[len(args) - len(node.args.defaults):], node.args.defaults):
            self.scalar_values[arg.arg] = self._scalar(default)
        for arg, default in zip(node.args.kwonlyargs, node.args.kw_defaults):
            self.scalar_values[arg.arg] = self._scalar(default)
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        self.visit(node.value)
        value = self._scalar(node.value)
        for target in node.targets:
            self.visit(target)
            if isinstance(target, ast.Name):
                self.scalar_values[target.id] = value

    def generic_visit(self, node: ast.AST) -> None:
        if type(node) not in self._ALLOWED_NODES:
            self.errors.append(f"不允许的代码结构：{type(node).__name__}")
            return
        super().generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if node.attr.startswith("__"):
            self.errors.append("不允许访问双下划线属性")
        if isinstance(node.value, ast.Name) and node.value.id == "self" and node.attr not in ALLOWED_FIELDS:
            self.errors.append(f"不允许的字段：{node.attr}")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if not isinstance(node.func, ast.Attribute) or node.func.attr not in ALLOWED_METHODS:
            self.errors.append("只允许调用白名单中的面板方法")
        elif node.func.attr in ("shift", "pct_change"):
            period_node = next(
                (kw.value for kw in node.keywords if kw.arg == "periods"),
                node.args[0] if node.args else ast.Constant(1),
            )
            period = self._scalar(period_node)
            if type(period) is not int or period < 0:
                self.errors.append("禁止未来数据：shift/pct_change回看周期须为可确定的非负整数")
            if any(
                kw.arg == "freq" and not (isinstance(kw.value, ast.Constant) and kw.value.value is None)
                for kw in node.keywords
            ):
                self.errors.append("禁止未来数据：请使用交易行回看，不使用freq日期偏移")
            if any(
                kw.arg == "fill_method" and self._scalar(kw.value) in ("bfill", "backfill")
                for kw in node.keywords
            ):
                self.errors.append("禁止未来数据：不允许用未来价格反向填充缺失值")
        elif node.func.attr == "rolling":
            centered = next(
                (kw.value for kw in node.keywords if kw.arg == "center"),
                node.args[2] if len(node.args) > 2 else ast.Constant(False),
            )
            if self._scalar(centered) is not False:
                self.errors.append("禁止未来数据：rolling必须使用非居中窗口center=False")
        elif node.func.attr == "fillna":
            if any(
                kw.arg == "method" and self._scalar(kw.value) not in ("ffill", "pad")
                for kw in node.keywords
            ):
                self.errors.append("禁止未来数据：不允许反向填充或无法确定方向的缺失值填充")
        self.generic_visit(node)


def validate_generated_factor(factor: dict[str, Any]) -> list[str]:
    """返回错误列表；空列表表示通过。"""
    used_fields = factor.get("used_fields") or []
    unknown_fields = sorted(set(used_fields) - ALLOWED_FIELDS)
    if unknown_fields:
        return [f"used_fields 包含未登记字段：{', '.join(unknown_fields)}"]

    code = str(factor.get("factor_code") or "")
    name = str(factor.get("factor_name") or "")
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return [f"因子代码语法错误：{exc.msg}"]

    if len(tree.body) != 1 or not isinstance(tree.body[0], ast.FunctionDef):
        return ["因子代码必须且只能包含一个函数定义"]
    function = tree.body[0]
    if function.name != name or not function.args.args or function.args.args[0].arg != "self":
        return ["函数名必须与 factor_name 一致，且第一个参数必须为 self"]
    if function.decorator_list:
        return ["因子代码不允许使用装饰器"]

    visitor = _GeneratedFactorVisitor()
    visitor.visit(tree)
    if visitor.errors:
        return visitor.errors

    return compile_errors(code)


__all__ = [
    "ALLOWED_FIELDS",
    "ALLOWED_METHODS",
    "compile_errors",
    "validate_generated_factor",
    "wrap_for_compile",
]
