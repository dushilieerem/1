"""交易 Agent：模拟交易 + 实盘下单。

分支 Agent：模拟交易 / 实盘下单。
约束：实盘下单仅在收到 Boss decision=execute 且风控 approve 后调用。
"""
from __future__ import annotations
from core.base_agent import BaseAgent
from tools.mock_tools import simulate_trade, live_order


class TradingAgent(BaseAgent):
    def __init__(self, llm, bus, default_mode: str = "simulate"):
        sim = BaseAgent("trade_sim", "模拟交易",
                        "回放成交验证策略", llm, bus, tools={"simulate_trade": simulate_trade})
        live = BaseAgent("trade_live", "实盘下单",
                         "对接柜台 API 下单", llm, bus, tools={"live_order": live_order})
        super().__init__("trading", "交易", "你负责模拟交易与实盘下单。",
                         llm, bus, sub_agents={"simulation": sim, "live": live})
        self.default_mode = default_mode

    def execute(self, cycle_id: str, proposal: dict, decision: dict) -> dict:
        if decision.get("decision") != "execute":
            self.send("boss", "report",
                      {"cycle_id": cycle_id, "stage": "trade_skipped",
                       "summary": "未获执行裁决，跳过下单", "reason": decision.get("reason")},
                      trace_id=cycle_id)
            return {"executed": False, "reason": decision.get("reason")}
        limits = decision.get("limits")
        mode = self.default_mode
        if mode == "simulate":
            r = self.sub_agents["simulation"].act("simulate", tool="simulate_trade", proposal=proposal)["result"]
        else:
            r = self.sub_agents["live"].act("live", tool="live_order", proposal=proposal, limits=limits)["result"]
        self.send("boss", "report",
                  {"cycle_id": cycle_id, "stage": "trade_done", "summary": f"已{mode}执行", "detail": r},
                  trace_id=cycle_id)
        return {"executed": True, "mode": mode, "detail": r}
