"""消息总线：跨部门通信 + 全链路留痕。

- 每个 Agent 注册后拥有收件箱；
- post() 写入总线日志并可定向/广播投递；
- deliver() 同步把消息交给接收方 handle()（带最大轮次防止死循环）；
- trace_id 串联一次研究循环，便于审计与复盘。
"""
from __future__ import annotations
import time
import uuid
from dataclasses import dataclass, field


@dataclass
class Message:
    sender: str
    recipient: str          # Agent 名 或 "broadcast"
    msg_type: str           # task | report | request | decision | alert
    content: dict
    trace_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    timestamp: float = field(default_factory=time.time)


class MessageBus:
    def __init__(self):
        self.agents: dict[str, object] = {}
        self.inbox: dict[str, list[Message]] = {}
        self.log: list[Message] = []

    def register(self, agent) -> None:
        self.agents[agent.name] = agent
        self.inbox[agent.name] = []

    def post(self, msg: Message) -> None:
        self.log.append(msg)
        if msg.recipient == "broadcast":
            for name in self.agents:
                if name != msg.sender:
                    self.inbox[name].append(msg)
        elif msg.recipient in self.inbox:
            self.inbox[msg.recipient].append(msg)

    def deliver_once(self) -> int:
        """把当前收件箱消息交给接收方处理，返回本次处理条数。"""
        delivered = 0
        for name, msgs in self.inbox.items():
            agent = self.agents.get(name)
            if not agent:
                continue
            for m in list(msgs):
                if hasattr(agent, "handle"):
                    agent.handle(m)
                    delivered += 1
        for name in self.inbox:
            self.inbox[name] = []
        return delivered

    def drain(self, max_rounds: int = 20) -> None:
        for _ in range(max_rounds):
            if self.deliver_once() == 0:
                break

    def show_log(self) -> None:
        print("\n===== 跨部门消息总线日志 =====")
        for m in self.log:
            tag = {
                "task": "▸派活", "report": "◤汇报", "request": "⇄请求",
                "decision": "⚑裁决", "alert": "⚠告警",
            }.get(m.msg_type, m.msg_type)
            print(f"[{m.timestamp:.0f}|{m.trace_id}] {tag} {m.sender:>8} -> {m.recipient:>8} : {m.msg_type}")
