# 结构化因子组合策略：验证记录

- 验证日期：2026-07-21
- 状态：通过

| 验收项 | 验证结果 |
|---|---|
| 多个 `@factor` 与唯一 `@signal` 可回测 | API 端到端测试通过。 |
| 因子函数可组合并使用横截面处理 | 单元测试覆盖 `rank`、`zscore`、`normalize`。 |
| Top-N、等权、每 N 日调仓正确 | 单元测试验证权重和调仓日 `NaN` 语义。 |
| `@signal` 缺失时清晰失败 | 单元测试验证错误信息。 |
| 原策略回测兼容 | ResearchEngine API 全部测试通过。 |

验证命令：

```bash
D:\Devtools\anaconda3\envs\svquant\python.exe -m pytest -q
```

结果：`106 passed, 1 warning`。唯一 warning 来自 FastAPI 测试客户端依赖的弃用提示，与本 Feature 无关。
