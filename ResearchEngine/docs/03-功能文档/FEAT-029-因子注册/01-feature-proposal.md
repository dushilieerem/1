# FEAT-029：数据库因子加载与回测执行器最小改造 — Feature Proposal

## 元数据

- 状态：开发中（引擎边界阶段；数据库迁移待决策）
- 所属 Initiative：INIT-001 投研核心
- 所属产品能力：因子研究、研究基础设施
- 优先级：P0
- 提出日期：2026-08-26
- 负责人：待定

## 背景与用户问题

当前因子实现保存在 `ResearchEngine/app/assets/factors/libraries/*.py`，目录元数据保存在
`index.yaml`。这种方式对代码计算本身没有问题，真正的问题是管理成本：因子数量已经超过一千，
还会继续增加，名称、说明、标签、版本、校验结果和回测指标需要被检索、更新和追溯。

现有来源加载已经有一个可替换的 FactorEngine loader。在 FEAT-030 实施后，运行时流程为：

1. 入口将请求转换成 `FactorBacktestSpec`；
2. `FactorEngine(spec)` 初始化时调用 `_resolve_factor(spec)` 解析并私有保存因子；
3. 得到 `BaseFactor` 后继续执行 Data/Factor/Portfolio/Metric 四引擎流程。

因此本 Feature 解决的是“因子来源从哪里读”的问题，不是重新设计回测运行时。

## 用户价值

- 研究员可以按因子名、库、说明、标签和状态搜索因子，不必打开大量 Python 文件。
- 修改代码或说明时可以保存版本和校验结果，回测仍能记录使用的代码哈希。
- 批量回测仍使用原来的 `FactorBacktestSpec` 和统一 `BacktestEngine`，不需要上层调用方迁移一套新契约。
- 因子代码可以继续是现有的 Python 类/`FactorLibrary` 方法代码，数据库只替换持久化介质。

## 商业价值

- 降低维护数千个因子的人工成本，支持后续 AI 生成因子和用户因子管理。
- 减少“名称存在但代码/说明/版本找不到”的情况，提高回测结果可解释性。
- 为后续权限、审核和 WebApp 管理页面提供结构化数据基础，但不把这些能力塞进本次执行器改造。

## 方案比较

| 方案 | 结论 |
|------|------|
| 继续 `.py + index.yaml` | 保留为迁移回退方案；不适合持续做在线管理和多条件检索。 |
| 新建独立 FactorRegistry 服务 | 后续可做，但当前会引入服务、网络、权限和部署复杂度，超出问题范围。 |
| 只在现有应用内增加数据库因子仓库，由 FactorEngine loader 读取 | 本 Feature 采用；改动面小，能解决因子管理和加载来源问题。 |
| 重写 Spec/执行链 | 不采用；FEAT-030 已统一执行链，本 Feature 只替换来源 loader，不复制回测流程。 |

## MVP 范围

### 必须做

- 建立因子数据库表，保存现有管理字段和因子源代码。
- 提供 `get(library_name, factor_name[, version])` 的仓库读取接口。
- 在 `FactorEngine.load_factor(source="database", ...)` 中使用数据库加载器，并由 BacktestEngine 调用该门面。
- 从数据库代码生成与现有加载器等价的 `BaseFactor`；不改变 `FactorEngine` 的输入类型。
- `factor_source_hash` 由数据库记录的代码哈希提供，确保代码更新后缓存失效。
- 提供一次性导入脚本，把现有 `.py + index.yaml` 导入数据库并生成差异报告。
- 保留 `factor_code` 自定义因子兼容路径；数据库故障和记录缺失返回明确的因子参数错误。

### 可以以后做

- 因子编辑、审核、权限和 WebApp 管理界面。
- PostgreSQL 远程仓库、缓存服务和多实例写入协调。
- 更细的依赖图、别名管理和指标快照查询 API。
- 不可信 Python 的子进程/容器隔离。

### 明确不做

- 不新增运行时身份对象和解析服务层；只给 FactorEngine 增加统一加载门面。
- 不改变 `FactorBacktestSpec`、`FactorBacktestResult`、FactorEngine 的既有计算接口；不在本 Feature 复制或改写 FEAT-030 的回测流程。
- 不修改 `D:\project\SVQuant\WebApp`。
- 不在首期删除 `.py` 文件和 `index.yaml`；迁移完成并验证前保留只读回退。

## 成功指标

- 现有因子可以按库名和因子名从数据库加载并完成回测。
- 同一份因子代码从文件加载和数据库加载时，固定面板结果在约定浮点容差内一致。
- 数据库代码更新后，`factor_source_hash` 和回测缓存键随之变化。
- `FactorBacktestSpec` 的字段和 `BacktestEngine.run(spec, context)` 契约不变；旧 Executor 已由 FEAT-030 删除。
- 现有单因子、批量因子和 Python 兼容入口继续通过同一个 BacktestEngine 执行。

## 初步成本与风险

| 项目 | 评估 |
|------|------|
| 工作量 | 1 名后端开发约 8–12 人天；含迁移核对约 2–3 周 |
| 复杂度 | 3/5 |
| 技术风险 | 中：数据库代码编译、类/方法依赖和缓存哈希需要兼容现有实现 |
| 产品风险 | 低：首期只替换存储和读取方式，不改变用户回测参数 |
| 项目风险 | 低到中：导入期间要保留旧路径并输出差异清单 |

## 建议决策

批准“数据库作为因子来源、FactorEngine loader 负责解析并由 BacktestEngine 继续执行”的最小方案。等实际使用
暴露出权限、服务化或多租户需求后，再单独立项，不把这些假设提前写进当前回测链路。
