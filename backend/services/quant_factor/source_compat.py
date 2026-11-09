# Frozen compatibility policy copied from this product isolated RE; parity-tested.
RE_POLICY_SHA256='8d2b0729667aa4fd89983905cb88595de90f7ffe2107d12440cf4ebdc45984db'
"""自定义查重输入的窄面板源码策略；不等同于操作系统级沙箱。"""

import ast

METHODS = set(
    "abs add sub mul div pow shift diff pct_change rolling ewm expanding sum mean std var min max median quantile rank count corr cov where mask clip fillna replace notna isna isnull notnull to_numpy any all astype round gt ge lt le eq ne".split()
)
FIELDS = set(
    "open high low close volume amount turnover returns vwap current_mv pb_mrq pe_ttm".split()
)
FUNCTIONS = {"float", "int", "abs", "min", "max", "hasattr", "ValueError"}
NP = {
    "log",
    "log1p",
    "sqrt",
    "sign",
    "abs",
    "maximum",
    "minimum",
    "where",
    "isfinite",
    "nan",
    "inf",
}
NODES = (
    ast.Module,
    ast.FunctionDef,
    ast.arguments,
    ast.arg,
    ast.Assign,
    ast.Return,
    ast.If,
    ast.Raise,
    ast.Expr,
    ast.Name,
    ast.Load,
    ast.Store,
    ast.Constant,
    ast.Attribute,
    ast.Call,
    ast.keyword,
    ast.BinOp,
    ast.UnaryOp,
    ast.BoolOp,
    ast.Compare,
    ast.IfExp,
    ast.List,
    ast.Tuple,
    ast.Dict,
    ast.operator,
    ast.unaryop,
    ast.boolop,
    ast.cmpop,
)


def validate_source(source, entry):
    if len(source) > 30000:
        raise ValueError("Custom source exceeds 30000 characters")
    tree = ast.parse(source)
    if len(tree.body) != 1 or not isinstance(tree.body[0], ast.FunctionDef):
        raise ValueError("A single panel function is required")
    f = tree.body[0]
    if (
        f.name != entry
        or f.decorator_list
        or f.returns
        or len(f.args.args) != 1
        or f.args.args[0].arg != "self"
        or f.args.defaults
        or f.args.vararg
        or f.args.kwarg
        or f.args.kwonlyargs
        or f.args.posonlyargs
    ):
        raise ValueError("Expected def factor(self) without decorators/defaults")
    local = {"self"}
    for node in ast.walk(tree):
        if not isinstance(node, NODES):
            raise ValueError(
                "Unsupported custom source construct: " + type(node).__name__
            )
        if isinstance(node, ast.FunctionDef) and node is not f:
            raise ValueError("Nested functions are not supported")
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if (
                    not isinstance(target, ast.Name)
                    or target.id in ("self", "np", "pd", "tool")
                    or target.id in FUNCTIONS
                ):
                    raise ValueError("Only local variable assignment is supported")
                local.add(target.id)
        if isinstance(node, ast.Attribute):
            if node.attr.startswith("_"):
                raise ValueError("Private attributes are not allowed")
            if isinstance(node.value, ast.Name) and node.value.id == "self":
                if node.attr not in FIELDS:
                    raise ValueError("Unsupported market field")
            elif isinstance(node.value, ast.Name) and node.value.id == "np":
                if node.attr not in NP:
                    raise ValueError("Unsupported numpy operation")
            elif node.attr not in METHODS:
                raise ValueError("Unsupported panel operation: " + node.attr)
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                if node.func.id not in FUNCTIONS:
                    raise ValueError("Unsupported callable")
                if node.func.id == "hasattr" and (
                    len(node.args) != 2
                    or not isinstance(node.args[1], ast.Constant)
                    or node.args[1].value not in METHODS
                ):
                    raise ValueError("Only panel capability checks are supported")
            elif not isinstance(node.func, ast.Attribute):
                raise ValueError("Indirect calls are not supported")
            for kw in node.keywords:
                if (
                    kw.arg is None
                    or kw.arg == "inplace"
                    or (
                        kw.arg == "center"
                        and not (
                            isinstance(kw.value, ast.Constant)
                            and kw.value.value is False
                        )
                    )
                ):
                    raise ValueError("Mutation/centered windows are not supported")
            if isinstance(node.func, ast.Attribute) and node.func.attr in (
                "shift",
                "diff",
                "pct_change",
            ):
                periods = node.args[:1] + [
                    kw.value for kw in node.keywords if kw.arg == "periods"
                ]
                if any(
                    not isinstance(x, ast.Constant)
                    or not isinstance(x.value, int)
                    or isinstance(x.value, bool)
                    or not 0 <= x.value <= 504
                    for x in periods
                ):
                    raise ValueError("Only bounded backward lags are supported")
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id not in local | FUNCTIONS | {"np"}:
            raise ValueError("Unknown global in custom source")
    return source
