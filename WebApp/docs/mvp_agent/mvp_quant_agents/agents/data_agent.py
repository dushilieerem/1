"""数据 Agent：数据治理、因子库、因子计算（确定性计算，几乎不碰 Token）。

分支 Agent：数据采集 / 因子库管理 / 因子计算。
"""
from __future__ import annotations
from core.base_agent import BaseAgent
from tools.mock_tools import fetch_market_data, build_factor_library, compute_factors
from tools import research_tools


class DataAgent(BaseAgent):
    def __init__(self, llm, bus, cfg: dict | None = None, use_real: bool = False):
        self.cfg = cfg or {}
        self.use_real = use_real
        ingestion = BaseAgent("data_ingestion", "数据采集",
                              "接入并清洗行情/基本面数据", llm, bus,
                              tools={"fetch_market_data": fetch_market_data})
        flib = BaseAgent("data_factor_lib", "因子库管理",
                         "维护因子注册表与版本", llm, bus,
                         tools={"build_factor_library": build_factor_library})
        fcomp = BaseAgent("data_factor_compute", "因子计算",
                          "向量化/RAPIDS 计算因子值", llm, bus,
                          tools={"compute_factors": compute_factors})
        super().__init__("data", "数据", "你管理数据、因子库与因子计算。",
                         llm, bus,
                         sub_agents={"ingestion": ingestion, "factor_lib": flib, "compute": fcomp})

    def run(self, cycle_id: str, universe: str) -> dict:
        if self.use_real:
            out = research_tools.ingest_and_compute(self.cfg)
            self.send("boss", "report",
                      {"cycle_id": cycle_id, "stage": "data_ready",
                       "summary": f"真实数据接入({out['raw']['source']}) + 四因子入库完成",
                       "metrics": {"symbols": len(out["raw"]["symbols"]),
                                   "factors": len(out["factors"]["computed"]),
                                   "source": out["raw"]["source"]}},
                      trace_id=cycle_id)
            return out
        raw = self.sub_agents["ingestion"].act("collect", tool="fetch_market_data", universe=universe)["result"]
        libs = self.sub_agents["factor_lib"].act("register", tool="build_factor_library", raw=raw)["result"]
        factors = self.sub_agents["compute"].act("compute", tool="compute_factors",
                                                 raw=raw, libs=libs.get("registered", []))["result"]
        out = {"raw": raw, "libs": libs, "factors": factors}
        self.send("boss", "report",
                  {"cycle_id": cycle_id, "stage": "data_ready", "summary": "数据/因子库/因子计算完成",
                   "metrics": {"symbols": len(raw.get("symbols", [])), "factors": len(factors.get("computed", []))}},
                  trace_id=cycle_id)
        return out
