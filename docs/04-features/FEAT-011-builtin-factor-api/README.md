# FEAT-011：内置因子库回测 API

- 状态：开发中
- 所属 Initiative：INIT-001 投研核心
- 所属能力：因子研究 / 研究 API
- 优先级：P0

## 目标

区分内置因子库与用户自定义因子的回测请求：内置因子由服务端完整加载库文件；用户因子继续只提交单个函数源码，并可声明一个或多个内置库，使组合函数直接调用 `self.<内置因子>()`。

## 文档索引

- `01-feature-proposal.md`
- `02-product-requirements.md`
- `03-technical-design.md`
- `04-project-plan.md`
