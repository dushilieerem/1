# Verification：AI 回测解读与优化建议

> 本记录随 MVP 迭代更新；当前为第 1 轮可验证实现，不代表 Feature 完成验收。

## 已验证能力

- 新增 `POST /api/ai/backtest-interpretations`，接受因子或向量化策略回测快照、原始运行上下文、关注点与 UUID 幂等键。
- 对净值序列执行日期递增、有限数值和 10,000 点上限校验；少于 60 点时返回 `insufficient`，不会调用供应商。
- 证据层生成稳定的结果指纹、净值点覆盖、总收益、最大回撤、基准收益、标准指标、成本/验证假设及因子 IC（如可用）。
- 诊断目录已覆盖短样本、缺少样本外验证、成本缺失/零成本、高换手、深回撤和弱因子信号，并生成最多 5 条 `manual_only` 实验建议。
- 未配置或不可用的 LLM Provider 时返回 `deterministic_fallback`，不影响已有回测端点；开关 `AI_BACKTEST_INTERPRETATION_ENABLED=false` 可关闭新入口。

## 自动化验证

2026-07-31，使用 `svquant` 环境执行：

```text
pytest ResearchEngine/tests/test_ai_backtest_interpretation.py ResearchEngine/tests/test_ai_factor_api.py -q
21 passed
```

覆盖：确定性证据和研究优先建议、短样本不调用 Provider、幂等重放、非递增日期拒绝，以及既有 AI 因子/策略生成契约。

## 尚待本 Feature 后续迭代验证

- AC-02 的完整黄金数据集及所有指标口径对照。
- AC-05 的 LLM 结构化输出、引用/合规攻击和隐私请求捕获测试。
- AC-08 的跨进程持久化幂等与审计保留策略。
- 30–50 个匿名样本的双人专家评测和 Beta 性能/成本门禁。
