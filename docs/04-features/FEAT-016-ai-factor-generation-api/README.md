# FEAT-016：AI 自然语言因子生成 API

- 状态：开发中（受控 MVP）
- 所属 Initiative：INIT-004 投研能力 Phase 2
- 所属能力：AI 研究助手 / 因子研究
- 优先级：P0

## 目标

让 Web 应用把研究员填写的自然语言研究想法发送到平台；平台通过服务端托管的第三方大语言模型，将其转换为符合 SVQuant `FactorLibrary` 单函数契约、可由既有 `POST /api/backtest/factor` 回测的因子草稿。

## 文档索引

- `01-feature-proposal.md`
- `02-product-requirements.md`
- `03-technical-design.md`
- `04-project-plan.md`
- `05-verification.md`
