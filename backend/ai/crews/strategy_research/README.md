# strategy_research crew

为 AI Agent 提供**真实策略回测工具**（经 ResearchEngine 网关执行，本 crew 不做任何计算）。

## 组件

| 文件 | 职责 |
|---|---|
| `backtest_tool.py` | `run_backtest` 工具：Pydantic 参数校验 → 提交 `/api/backtest/strategy` →（必要时）轮询 → 结果规范化（缺指标进 `missing_metrics`，不伪造） |
| `registry.py` | 轻量工具注册表；新工具加一项 `{description, parameters, handler}` 即可被 Agent 循环发现 |
| `agent_loop.py` | OpenAI function-calling 循环：自然语言 → 模型选工具 → 后端执行 → 基于真实结果作答（`_MAX_TOOL_ROUNDS=3`） |

## API（挂在主后端 :8766）

- `POST /api/agent/strategy-research/backtest` — 结构化直调（不经 LLM）
- `POST /api/agent/strategy-research/chat` — 自然语言 → 工具调用 → 中文回答

两者均 `require_user`，计入 AI 配额（skill：`run_backtest` / `strategy_research_chat`）。

## 使用示例

```bash
TOKEN=$(curl -s -X POST http://127.0.0.1:8766/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}' | python -c "import sys,json;print(json.load(sys.stdin)['token'])")

# ① 结构化直调
curl -s -X POST http://127.0.0.1:8766/api/agent/strategy-research/backtest \
  -H "Content-Type: application/json" -H "Authorization: Bearer $TOKEN" \
  -d '{"strategy_id":"ma_13_26_maotai","start":"2023-01-01","end":"2023-06-30"}'

# ② 自然语言（LLM 自动选工具、抽参数、解读真实结果）
curl -s -X POST http://127.0.0.1:8766/api/agent/strategy-research/chat \
  -H "Content-Type: application/json" -H "Authorization: Bearer $TOKEN" \
  -d '{"message":"请对 ma_13_26_maotai（贵州茅台 13/26 日双均线）回测 2023 年上半年，告诉我总收益率和最大回撤。"}'
```

## 环境变量

| 变量 | 默认 | 说明 |
|---|---|---|
| `SVQUANT_AGENT_BACKTEST_TIMEOUT_SEC` | 900 | 异步轮询总超时 |
| `SVQUANT_AGENT_BACKTEST_POLL_SEC` | 3 | 轮询间隔 |

## 测试

```bash
conda activate svquant
python backend/tests/run_backtest_tool_suite.py        # Mock 单测 + LIVE 集成（服务可用时）
SVQ_TOOL_SUITE_BASE=http://127.0.0.1:8767 python backend/tests/run_backtest_tool_suite.py  # 指向测试实例
```
