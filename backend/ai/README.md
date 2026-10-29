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

新增 Agent 时，请在本目录 README 和对应的 `docs/模块设计/` 功能文档中记录入口、
权限、输入输出和失败语义。
**兼容：** 旧路径 `services/agent_*.py` 等仍可 import（薄封装转发到本包）。


