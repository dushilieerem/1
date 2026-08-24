"""风控 Agent：实盘风控 + 实盘分析，对 Boss 拥有否决权。

分支 Agent：实盘分析 / 实盘风控。
核心：review() 返回 verdict=approve/reject；reject 时 Boss 不得 override 直接执行。
"""
from __future__ import annotations
from core.base_agent import BaseAgent
from tools.mock_tools import risk_analysis, risk_control


class RiskAgent(BaseAgent):
    def __init__(self, llm, bus, max_position_pct: float = 0.05):
        analysis = BaseAgent("risk_analysis", "实盘分析",
                             "对策略提案做风险研判（否决来源）", llm, bus,
                             tools={"risk_analysis": risk_analysis})
        control = BaseAgent("risk_control", "实盘风控",
                            "落地硬约束与断路器", llm, bus,
                            tools={"risk_control": risk_control})
        super().__init__("risk", "风控", "你负责实盘风控与分析，对执行拥有一票否决权。",
                         llm, bus,
                         sub_agents={"analysis": analysis, "control": control})
        self.max_position_pct = max_position_pct

    def review(self, cycle_id: str, proposal: dict) -> dict:
        verdict = self.sub_agents["analysis"].act(
            "analyze", tool="risk_analysis", proposal=proposal,
            max_position_pct=self.max_position_pct)["result"]
        limits = verdict.get("limits")
        ctrl = self.sub_agents["control"].act("enforce", tool="risk_control", limits=limits)["result"]
        verdict["control"] = ctrl
        self.send("boss", "report",
                  {"cycle_id": cycle_id, "stage": "risk_verdict",
                   "summary": "风控研判完成",
                   "verdict": verdict.get("verdict"),
                   "reasons": verdict.get("reasons"),
                   "limits": limits},
                  trace_id=cycle_id)
        # 极端情况主动告警
        if verdict.get("verdict") == "reject":
            self.send("boss", "alert",
                      {"cycle_id": cycle_id, "level": "high",
                       "msg": "策略未通过风控：" + "; ".join(verdict.get("reasons", []))},
                      trace_id=cycle_id)
        return verdict
