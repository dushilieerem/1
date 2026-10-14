"""自定义因子入口校验；在 RE 生成绩效前拒绝全空/全无穷值的因子矩阵。"""
from __future__ import annotations

import ast


def validated_factor_code(source: str, entry: str) -> str:
    if not source.strip():
        raise ValueError("因子代码不能为空")
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise ValueError(f"因子代码语法错误（第 {exc.lineno} 行）：{exc.msg}") from exc
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == entry]
    if len(functions) != 1:
        raise ValueError(f"请提供唯一的入口函数 def {entry}(self)")
    fn = functions[0]
    used = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    tmp = "_svquant_factor_values"
    while tmp in used:
        tmp += "_"

    class CheckReturns(ast.NodeTransformer):
        def visit_FunctionDef(self, node):
            return node  # 不改嵌套辅助函数的返回类型。

        def visit_AsyncFunctionDef(self, node):
            return node

        def visit_Return(self, node):
            check = ast.parse(f'''
if {tmp} is None:
    raise ValueError("因子没有返回有效数据，请检查代码与历史行情范围")
if hasattr({tmp}, "notna") and hasattr({tmp}, "replace"):
    if not {tmp}.replace([float("inf"), -float("inf")], float("nan")).notna().to_numpy().any():
        raise ValueError("因子没有有效数值，可能是历史行情不足或回看窗口过长；请缩短窗口或调整数据范围")
''').body
            return [ast.Assign(targets=[ast.Name(id=tmp, ctx=ast.Store())], value=node.value or ast.Constant(None)), *check, ast.Return(value=ast.Name(id=tmp, ctx=ast.Load()))]

    transform = CheckReturns()
    body = []
    for statement in fn.body:
        transformed = transform.visit(statement)
        body.extend(transformed if isinstance(transformed, list) else [transformed])
    # 无 return 或分支未覆盖时不能静默返回 None。
    body.extend(ast.parse('raise ValueError("因子没有返回数据，请检查 return 语句")').body)
    fn.body = body
    return ast.unparse(ast.fix_missing_locations(tree))
