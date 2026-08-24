# SVQuant · AI 包

```
ai/
├── gateway/          # 模型网关
├── runtime/          # 额度、编排、skills
└── crews/
    ├── community/    # 发帖/读帖
    ├── gather_idea/  # 信息搜集→idea（待实现）
    └── _shared/      # 跨 crew 工具
```

**新 Agent：** 见 `WebApp/docs/mvp_agent/ADDING_AN_AGENT.md`  
**兼容：** 旧路径 `services/agent_*.py` 等仍可 import（薄封装转发到本包）。
