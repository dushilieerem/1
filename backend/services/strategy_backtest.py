"""Build one controlled FactorPortfolioStrategy from frozen recipe source factors."""
from __future__ import annotations

import ast
import re


def _body(code: str, name: str) -> str:
    tree = ast.parse(code)
    fn = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name]
    if len(fn) != 1:
        raise ValueError("因子源码必须只有一个入口函数")
    return ast.unparse(ast.Module(body=fn[0].body, type_ignores=[]))


def build_code(recipe: dict) -> str:
    factors = recipe.get("factors") or []
    if not 1 <= len(factors) <= 3:
        raise ValueError("配方必须有 1—3 个有源码因子")
    methods = []
    terms = []
    for i, f in enumerate(factors):
        code = f.get("code")
        if not code:
            raise ValueError(f"因子 {f.get('factor')} 没有源码，暂不可用于策略回测")
        func = f"factor_{i}"
        body = _body(code, f.get("entry") or f.get("factor"))
        methods.append(f"    @factor\n    def {func}(self):\n" + "\n".join("        " + line for line in body.splitlines()))
        sign = "" if f.get("direction", "positive") == "positive" else "-"
        terms.append(f"{sign}self.{func}()")
    signal = " + ".join(terms)
    return f'''from app.services.strategy.vectorized.factor_strategy import (
    EqualWeight, EveryNTradingDays, FactorPortfolioStrategy, TopN, factor, signal,
)

class RecipeStrategy(FactorPortfolioStrategy):
    selector = TopN({int(recipe["top_n"])})
    weighting = EqualWeight()
    rebalance = EveryNTradingDays({int(recipe["rebalance_days"])})

{chr(10).join(methods)}

    @signal
    def score(self):
        raw = {signal}
        mean = raw.mean(axis=1)
        std = raw.std(axis=1).replace(0, float("nan"))
        return raw.sub(mean, axis=0).div(std, axis=0)
'''


__all__ = ["build_code"]
