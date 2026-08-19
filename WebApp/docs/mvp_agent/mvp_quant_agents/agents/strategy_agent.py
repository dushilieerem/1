"""策略 Agent：策略生成、回测、评价、组合/风格切换（含西蒙斯式配对交易）。

分支 Agent：策略生成 / 回测 / 评价 / 组合·风格切换。
跨部门：向因子 Agent 请求专用因子（配对协整度等）。
"""
from __future__ import annotations
from core.base_agent import BaseAgent
from tools.mock_tools import generate_strategy, backtest_strategy, evaluate_strategy, portfolio_switch
from tools import research_tools


class StrategyAgent(BaseAgent):
    def __init__(self, llm, bus, cfg: dict | None = None, use_real: bool = False):
        self.cfg = cfg or {}
        self.use_real = use_real
        gen = BaseAgent("strat_gen", "策略生成",
                        "生成策略规格（含配对交易/ML alpha）", llm, bus,
                        tools={"generate_strategy": generate_strategy})
        bt = BaseAgent("strat_backtest", "策略回测",
                       "向量化回测+真实成本", llm, bus,
                       tools={"backtest_strategy": backtest_strategy})
        ev = BaseAgent("strat_eval", "策略评价",
                       "样本外稳定性与综合打分", llm, bus,
                       tools={"evaluate_strategy": evaluate_strategy})
        pf = BaseAgent("strat_portfolio", "组合·风格切换",
                       "风险预算与风格分配", llm, bus,
                       tools={"portfolio_switch": portfolio_switch})
        super().__init__("strategy", "策略", "你负责策略生成、回测、评价与组合切换。",
                         llm, bus,
                         sub_agents={"generation": gen, "backtest": bt, "evaluation": ev, "portfolio": pf})

    def run(self, cycle_id: str, factor_out: dict, theme: str = "pair_trading", style: str = "balanced") -> dict:
        # 跨部门：向因子 Agent 请求专用因子（演示通信，真实链路下同样保留）
        self.send("factor", "request",
                  {"cycle_id": cycle_id, "need": "pair_cointegration_factor"}, trace_id=cycle_id)
        if self.use_real:
            proposal = research_tools.build_strategy_stage(self.cfg)
            self.send("boss", "report",
                      {"cycle_id": cycle_id, "stage": "strategy_proposal",
                       "summary": "真实多因子策略提案（IC/IR 合成+回测）",
                       "metrics": {"sharpe": proposal["backtest"].get("sharpe"),
                                   "max_dd": proposal["backtest"].get("max_drawdown"),
                                   "score": proposal["evaluation"].get("score")},
                       "recommend_execute": proposal["recommend_execute"]},
                      trace_id=cycle_id)
            return proposal
        spec = self.sub_agents["generation"].act("generate", tool="generate_strategy", theme=theme)["result"]
        bt = self.sub_agents["backtest"].act("backtest", tool="backtest_strategy", spec=spec["spec"])["result"]
        ev = self.sub_agents["evaluation"].act("evaluate", tool="evaluate_strategy", backtest=bt)["result"]
        alloc = self.sub_agents["portfolio"].act("allocate", tool="portfolio_switch", style=style)["result"]
        proposal = {
            "name": spec["spec"].get("name"), "spec": spec["spec"],
            "backtest": bt, "evaluation": ev, "allocation": alloc,
            "recommend_execute": ev.get("verdict") == "pass",
        }
        self.send("boss", "report",
                  {"cycle_id": cycle_id, "stage": "strategy_proposal",
                   "summary": "策略提案（含回测/评价/组合）",
                   "metrics": {"sharpe": bt.get("sharpe"), "max_dd": bt.get("max_drawdown"),
                               "score": ev.get("score")},
                   "recommend_execute": proposal["recommend_execute"]},
                  trace_id=cycle_id)
        return proposal
