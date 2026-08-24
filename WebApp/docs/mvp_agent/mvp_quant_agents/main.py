"""MVP 入口：跑一次完整研究循环。

链路：Boss 发起 → 数据 → 因子 → 策略(跨部门向因子请求) → 风控(否决权) → Boss 裁决 → 交易执行/拦截。
默认 config.yaml 中 mock=true，无需 API Key 即可看到全链路消息与裁决。
"""
from __future__ import annotations
import os
import sys
import uuid
import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core import LLMClient, MessageBus
from agents import (BossAgent, DataAgent, FactorAgent, StrategyAgent, RiskAgent, TradingAgent)


def load_config() -> dict:
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "config.yaml"), "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def main():
    cfg = load_config()
    bus = MessageBus()
    llm = LLMClient(cfg)
    tid_factory = lambda: uuid.uuid4().hex[:8]

    # 实例化主 Agent（各自内含分支 Agent）
    # research.enabled=true 时，数据/因子/策略三个 Agent 走真实研究链路
    use_real = bool(cfg.get("research", {}).get("enabled", False))
    boss = BossAgent(llm, bus, tid_factory)
    data = DataAgent(llm, bus, cfg=cfg, use_real=use_real)
    factor = FactorAgent(llm, bus, cfg=cfg, use_real=use_real)
    strategy = StrategyAgent(llm, bus, cfg=cfg, use_real=use_real)
    risk = RiskAgent(llm, bus, max_position_pct=cfg.get("trading", {}).get("max_position_pct", 0.05))
    trading = TradingAgent(llm, bus, default_mode=cfg.get("trading", {}).get("default_mode", "simulate"))

    pipe = cfg.get("pipeline", {})
    objective = pipe.get("objective", "中低频 alpha")
    universe = pipe.get("universe", "沪深300")

    print("================ AI 量化投研 MVP · 一次研究循环 ================")
    print(f"模式: {'MOCK(不花token)' if llm.mock else '真实外部Token'}")
    print(f"目标: {objective} | 标的池: {universe}")

    # 1) Boss 发起循环
    cycle_id = boss.start_cycle(objective, universe)

    # 2) 数据
    data_out = data.run(cycle_id, universe)

    # 3) 因子
    factor_out = factor.run(cycle_id, data_out)

    # 4) 策略（含西蒙斯式配对交易）
    proposal = strategy.run(cycle_id, factor_out, theme="pair_trading", style="balanced")

    # 5) 风控研判（一票否决）
    verdict = risk.review(cycle_id, proposal)

    # 6) Boss 执行裁决 Gate
    decision = boss.decide(cycle_id, proposal, verdict)

    # 7) 交易执行 / 拦截
    exec_report = trading.execute(cycle_id, proposal, decision)

    # 收尾：把异步消息（request/alert 等）清空，并打印总线日志
    bus.drain()
    bus.show_log()

    print("\n================ 循环结果 ================")
    print(f"循环ID     : {cycle_id}")
    print(f"策略       : {proposal.get('name')} (sharpe={proposal['backtest'].get('sharpe')}, "
          f"maxDD={proposal['backtest'].get('max_drawdown')})")
    print(f"风控裁决   : {verdict.get('verdict')} -> {verdict.get('reasons')}")
    print(f"Boss 裁决  : {decision.get('decision')} | {decision.get('reason')}")
    print(f"交易执行   : {'已执行(' + exec_report.get('mode','') + ')' if exec_report.get('executed') else '已拦截'}")
    print("===========================================")


if __name__ == "__main__":
    main()
