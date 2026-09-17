# FEAT-017：策略资产目录与版本化持久化

- 状态：待验收
- 所属 Initiative：INIT-001 投研核心
- 所属能力：策略研究、研究基础设施
- 宏观影响：L1（补齐既有策略研究闭环，不改变产品模块边界）

## 文档索引

- `02-product-requirements.md`：用户流程、业务规则与验收标准

其余原分册（`01-feature-proposal.md`、`03-technical-design.md`、`04-project-plan.md`、`05-verification.md`）内容已收编至本 README。

## 1. 价值与范围

### 1. 功能名称

策略资产目录与版本化持久化。

### 2. 背景

策略通过 `ResearchEngine/app/assets/strategies/libraries/*.py` 和
`ResearchEngine/app/assets/strategies/index.yaml` 作为项目资产管理。
`/api/backtest/strategy` 同时支持临时 `strategy_code` 和版本化的 `strategy_id`，
回测结果可以关联到策略 ID、版本和源码哈希。

### 3. 用户价值

研究员可以保存、枚举和复用策略；同一策略的旧版本不被后续编辑覆盖，回测可以明确使用的策略 ID、版本与源码哈希。

### 4. 商业价值

策略是从研究走向模拟盘/实盘的核心资产。先建立可追溯的源码版本边界，可降低结果不可复现和未来迁移至资产管理服务的成本。

### 5. 竞品分析

主流量化平台通常提供云端策略编辑、版本和运行记录。SVQuant 当前是 CLI/SDK 到 Web 的过渡阶段，MVP 选择与既有因子库一致的 Git 管理文件目录，保留后续 SaaS 资产服务替换空间。

### 6. MVP 范围

**必须做**：`ResearchEngine/app/assets/strategies/index.yaml` 索引、版本化 `.py`
源码、目录读取/校验、策略列表 API、回测按 `strategy_id + strategy_version`
引用源码并返回内容哈希。

**可以以后做**：在线编辑、保存 API、回测运行历史、策略版本对比、团队权限、发布审批、对象存储和数据库资产目录。

**明确不做**：在线编辑与保存 API、用户不可信代码沙箱、实盘/模拟盘部署、将策略源码或回测产物自动写入数据库。

## 2. 方案设计

### 模块边界

`ResearchEngine/app/assets/strategies/` 是研究服务的策略资产目录，源码和索引由
Git 管理；`app.services.catalog.strategy_catalog.StrategyCatalog` 只读取、校验和
解析资产；`app.api.routes` 负责策略列表和回测路由；向量化和事件策略都由既有
回测编排执行。

```text
ResearchEngine/app/assets/strategies/index.yaml + libraries/*.py
              ↓
       StrategyCatalog（不执行源码）
              ↓
 GET /api/strategies  或  POST /api/backtest/strategy
                                      ↓
                            既有向量化回测流程
```

### 目录和索引

```text
ResearchEngine/app/assets/strategies/
├── index.yaml
└── libraries/
    ├── weekly_rotation_v1.py
    └── weekly_rotation_v2.py
```

版本映射位于单一 `index.yaml`：策略 ID 映射到业务策略类型、执行模式、当前版本、标签和每个版本的文件/入口。读取时以源码实际字节计算 SHA-256，不相信索引中人工维护的哈希。

### 接口

- `GET /api/strategies`：只返回索引元数据，不执行源码。
- `POST /api/backtest/strategy`：保留 `strategy_code`；支持互斥的 `strategy_id` 和可选 `strategy_version`，并通过 `engine_mode` 选择 `vectorized` 或 `event`。资产策略运行成功后，在 `meta` 返回 ID、解析版本和 `code_hash`。

### 兼容与回滚

原有内联 `strategy_code` 仍受支持。发生目录问题时，设置 `SVQUANT_STRATEGY_DIR` 指向可用库；需要回滚时停止使用 `strategy_id` 请求即可，既有回测路径不受影响。

### 测试策略

单元测试覆盖索引解析、默认版本、缺失版本和路径限制；API 测试覆盖列表、资产策略回测、内联回测回归以及向量化和事件策略契约。

### 风险

当前策略仍在可信开发环境内执行，不因“保存在文件中”而获得沙箱能力；生产执行隔离由 FEAT-006 的事件策略/安全设计另行解决。

## 3. 验收与证据

- 验证日期：2026-07-28
- 状态：通过，待产品/接口评审后标记完成

### 验收结果

| 验收标准 | 结果 | 证据 |
|---|---|---|
| AC-1 | 通过 | API 测试验证 `GET /api/strategies` 返回 ID、名称、类型、当前版本、入口和标签。 |
| AC-2 | 通过 | API 测试以 `strategy_id + strategy_version` 运行保存的源码，并断言返回 64 位 SHA-256。 |
| AC-3 | 通过 | `StrategyCatalog.load()` 在未传版本时解析 `current_version`；实现路径由资产策略 API 共用。 |
| AC-4 | 通过 | API 测试验证源码缺失返回业务错误；目录解析限制文件必须位于策略库根目录且为 `.py`。 |
| AC-5 | 通过 | 全量 pytest 覆盖内联自由策略、结构化策略和新增资产策略。 |

### 回归结果

2026-07-28 在 `svquant` 环境执行 `python -m pytest -q`：**157 passed**，仅有既有 FastAPI TestClient 弃用警告。

### 已知限制

- 空策略索引用于初始化目录；研究员需新增策略源码与索引条目后才会在列表中出现。
- 当前支持可信开发环境中的向量化和日频事件策略；不提供在线写入、用户权限、运行历史持久化或代码沙箱。
- 已保存策略返回源码哈希以便调用方记录；完整回测运行快照是后续 Feature 范围。

## 4. 计划与里程碑

| 任务 | 复杂度 | 风险 | 依赖 | 完成条件 |
|---|---:|---|---|---|
| 冻结目录、索引和版本规则 | 1 | 低 | FEAT-004 文件资产经验 | 文档与空索引入库 |
| 实现 StrategyCatalog | 2 | 低 | PyYAML | 索引、路径和版本校验通过测试 |
| 接入策略 API | 2 | 中 | 既有回测 API | 已保存策略可回测，内联请求兼容 |
| 测试和验收记录 | 2 | 中 | 前三项 | AC-1 至 AC-5 有自动化证据 |

### 排期与里程碑

- Week 1：完成目录契约、读取器与 API 接入；M1：已保存向量化策略可复现运行。
- Week 1：补齐异常与回归测试；M2：满足验收标准，进入待验收。

### 风险与缓解

| 类型 | 风险 | 缓解 |
|---|---|---|
| 产品 | 把项目源码库误解为多用户策略平台 | 文档明确 MVP 不承担用户资产、协作和审批。 |
| 技术 | 相对路径逃逸到任意源码 | 解析后要求文件位于策略库根目录且后缀为 `.py`。 |
| 安全 | 保存的代码仍可被执行 | 列表接口不执行代码；生产隔离不纳入本 Feature。 |
