"""因子 Agent：因子评价、挖掘、组合/正交。

分支 Agent：因子评价 / 因子挖掘 / 因子组合。
"""
from __future__ import annotations
from core.base_agent import BaseAgent
from tools.mock_tools import evaluate_factor, mine_factors
from tools import research_tools


class FactorAgent(BaseAgent):
    def __init__(self, llm, bus, cfg: dict | None = None, use_real: bool = False):
        self.cfg = cfg or {}
        self.use_real = use_real
        ev = BaseAgent("factor_eval", "因子评价",
                       "用 IC/IR/衰减评价因子有效性", llm, bus,
                       tools={"evaluate_factor": evaluate_factor})
        mine = BaseAgent("factor_mine", "因子挖掘",
                         "遗传规划/搜索新因子", llm, bus,
                         tools={"mine_factors": mine_factors})
        combo = BaseAgent("factor_combo", "因子组合",
                          "正交/加权合成因子", llm, bus, tools={})
        super().__init__("factor", "因子", "你负责因子的评价、挖掘与组合。",
                         llm, bus,
                         sub_agents={"evaluation": ev, "mining": mine, "combination": combo})

    def run(self, cycle_id: str, data_out: dict) -> dict:
        if self.use_real:
            out = research_tools.evaluate_factors_stage(self.cfg)
            keep = [e["factor"] for e in out["evaluations"] if e["verdict"] == "keep"]
            self.send("boss", "report",
                      {"cycle_id": cycle_id, "stage": "factor_ready",
                       "summary": "真实因子 IC/IR 评价完成",
                       "metrics": {"evaluated": len(out["evaluations"]), "kept": len(keep)}},
                      trace_id=cycle_id)
            return out
        computed = data_out.get("factors", {}).get("computed", [])
        evals = [self.sub_agents["evaluation"].act("evaluate", tool="evaluate_factor",
                                                   factor_name=f)["result"] for f in computed]
        mined = self.sub_agents["mining"].act("mine", tool="mine_factors", top_n=5)["result"]
        combo_prompt = f"基于 {len(evals)} 个评价因子与 {mined.get('candidates')} 个挖掘候选，给出正交合成思路"
        combo = self.sub_agents["combination"].act("combine", prompt=combo_prompt)["narrative"]
        out = {"evaluations": evals, "mined": mined, "combination_note": combo}
        self.send("boss", "report",
                  {"cycle_id": cycle_id, "stage": "factor_ready",
                   "summary": "因子评价+挖掘完成", "metrics": {"evaluated": len(evals), "mined": mined.get("candidates")}},
                  trace_id=cycle_id)
        return out
