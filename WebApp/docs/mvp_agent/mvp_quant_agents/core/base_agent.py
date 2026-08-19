"""Agent 基类：所有主 Agent 与分支 Agent 的共用能力。

能力：
- send(recipient, msg_type, content)：向总线发消息（自动带 trace_id）
- act(stage, tool, **kwargs)：组合「工具计算 + LLM 叙述」完成一个细分任务
- think(stage, prompt)：单纯 LLM 推理（过合规闸）
- call_tool(name, **kwargs)：调用本地工具（确定性计算，不出网）
- handle(msg)：默认接收 report/request，子类可覆盖
"""
from __future__ import annotations
import json
from core.llm_client import LLMClient
from core.message_bus import MessageBus, Message


class BaseAgent:
    def __init__(self, name: str, role: str, system_prompt: str,
                 llm: LLMClient, bus: MessageBus,
                 sub_agents: dict | None = None, tools: dict | None = None):
        self.name = name
        self.role = role
        self.system_prompt = system_prompt
        self.llm = llm
        self.bus = bus
        self.sub_agents = sub_agents or {}     # name -> BaseAgent（分支 Agent）
        self.tools = tools or {}               # name -> callable
        bus.register(self)

    # ---------- 通信 ----------
    def send(self, recipient: str, msg_type: str, content: dict, trace_id: str | None = None) -> Message:
        msg = Message(sender=self.name, recipient=recipient,
                      msg_type=msg_type, content=content,
                      trace_id=trace_id or _new_trace())
        self.bus.post(msg)
        return msg

    # ---------- 计算 / 推理 ----------
    def call_tool(self, tool_name: str, **kwargs):
        fn = self.tools.get(tool_name)
        if not fn:
            return {"error": f"未注册工具: {tool_name}"}
        return fn(**kwargs)

    def think(self, stage: str, prompt: str) -> str:
        return self.llm.chat(self.role, stage, prompt)

    def act(self, stage: str, tool: str | None = None, prompt: str = "", **kwargs) -> dict:
        """完成一个细分任务：先本地工具计算（确定性），再 LLM 生成叙述。"""
        result = self.call_tool(tool, **kwargs) if tool else None
        narrative = self.think(stage, prompt or f"针对阶段[{stage}]做研判") if prompt or not tool else ""
        parsed = _try_json(narrative)
        return {"stage": stage, "result": result, "narrative": parsed or narrative}

    # ---------- 默认消息处理 ----------
    def handle(self, msg: Message) -> None:
        # 默认：分支 Agent 收到 request 时回一个 report
        if msg.msg_type == "request" and self.sub_agents == {}:
            self.send(msg.sender, "report", {"echo": msg.content, "by": self.name})


def _new_trace() -> str:
    import uuid
    return uuid.uuid4().hex[:8]


def _try_json(text: str):
    try:
        return json.loads(text)
    except Exception:
        return None
