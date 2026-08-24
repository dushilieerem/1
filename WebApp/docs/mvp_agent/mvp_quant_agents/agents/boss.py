"""Boss 大脑 Agent：总控编排 + 执行裁决 + 复盘。

分支 Agent：调度器 / 裁决器 / 复盘器。
核心权力：对「交易 Agent 是否执行」拥有最终裁决权；风控 reject 时不得 override。
"""
from __future__ import annotations
from core.base_agent import BaseAgent


class BossAgent(BaseAgent):
    def __init__(self, llm, bus, trace_id_factory):
        sched = BaseAgent("boss_scheduler", "调度器",
                          "拆解研究目标为可下发任务", llm, bus, tools={})
        dec = BaseAgent("boss_decider", "裁决器",
                        "依据各 Agent 汇报做执行裁决", llm, bus, tools={})
        rev = BaseAgent("boss_reviewer", "复盘器",
                        "对已完成循环做归因复盘", llm, bus, tools={})
        super().__init__("boss", "大脑", "你是 AI 量化投研系统的总控大脑，负责编排与执行裁决。",
                         llm, bus, sub_agents={"scheduler": sched, "decider": dec, "reviewer": rev})
        self._tid = trace_id_factory

    def start_cycle(self, objective: str, universe: str) -> str:
        tid = self._tid()
        self.send("broadcast", "task",
                  {"action": "start_research_cycle", "objective": objective, "universe": universe},
                  trace_id=tid)
        return tid

    def decide(self, cycle_id: str, proposal: dict, verdict: dict) -> dict:
        """执行裁决 Gate：风控 approve 且策略达标才 execute。"""
        bt = proposal.get("backtest", {})
        ev = proposal.get("evaluation", {})
        risk_ok = verdict.get("approve", False)
        strategy_ok = bt.get("sharpe", 0) >= 1.0 and ev.get("verdict") == "pass"
        if risk_ok and strategy_ok:
            decision = "execute"
            reason = "风控通过且策略样本外达标，准予执行"
        elif not risk_ok:
            decision = "block"
            reason = "风控一票否决：" + "; ".join(verdict.get("reasons", []))
        else:
            decision = "revise"
            reason = "策略未达标，退回策略 Agent 修订"
        self.send("trading", "decision",
                  {"cycle_id": cycle_id, "decision": decision, "reason": reason,
                   "limits": verdict.get("limits")}, trace_id=cycle_id)
        return {"decision": decision, "reason": reason, "limits": verdict.get("limits")}

    def block(self, cycle_id: str, reason: str) -> dict:
        self.send("strategy", "decision",
                  {"cycle_id": cycle_id, "decision": "revise", "reason": reason},
                  trace_id=cycle_id)
        return {"decision": "block", "reason": reason}
