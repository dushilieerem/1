# 因子面板 ResearchEngine API 接口契约

> 状态：接口提案，待 ResearchEngine 确认并实现。本文描述目标契约，不代表下述新增字段和接口当前均已上线。
> 范围：SVQuant 因子面板读取内置因子目录、提交批量计算、查询任务进度与面板指标。

## 1. 目标与职责边界

因子面板的行情读取、因子执行、回测指标计算、批任务编排和计算结果查询由 ResearchEngine（RE）负责；SVQuant 保留产品入口、展示、权限/校验状态管理，并将 RE 返回的指标结果缓存在 PostgreSQL，不自行计算指标。

| 职责 | ResearchEngine | SVQuant |
|---|---|---|
| 面板可用的内置因子目录 | 提供，声明哪些库/因子可进入面板 | 读取并展示 |
| 因子执行、分层回测、指标计算 | 负责 | 不实现、不重算 |
| 批量任务、进度、计算结果 | 负责并通过 API 提供 | BFF 转发、展示，并缓存指标到 PostgreSQL |
| 登录、用户权限、管理员校验状态 | 不负责 | 负责；校验状态保存在 SVQuant 自己的持久化层 |
| 搜索、排序、分页、分享 | 不负责 | 负责产品交互 |
| 浏览器访问 RE | 不允许 | 浏览器只访问 SVQuant API |

面板校验状态（待验证/已通过/未通过）是 SVQuant 的产品治理数据，不迁移到 RE；校验记录写入 PostgreSQL `factor_dashboard_verifications`。RE 计算出的指标结果由 SVQuant 缓存到 PostgreSQL `factor_dashboard_metrics`，不再使用本地 SQLite。因子身份使用 `library_name + factor_name`，不可仅用 `factor_name`，以免不同库的同名因子互相覆盖。旧 SQLite 中的指标和校验状态只作为升级时的一次性只读迁移来源，不再写入；迁移状态记在 PostgreSQL `factor_dashboard_legacy_imports`，旧校验记录以通配库名 `*` 导入，具体库记录优先。

### 1.1 因子代码的过渡约束

当前过渡阶段，面板只跑 RE 内置目录中的因子，SVQuant 传因子引用，不展示或复制因子源码。长期目标是因子源码以 SVQuant 数据库为事实来源；届时 SVQuant 可在相同批任务契约中提交待执行代码，RE 只负责执行，不承担源码 CRUD 或源码持久化。此迁移不改变下文的指标响应结构，也不要求 SVQuant 向 RE 发送算法版本号。

本契约 V1 不把 AI 生成草稿或用户自定义因子自动纳入内置因子面板。需要纳入时，必须由 SVQuant 明确传入被选中的因子，不得隐式扫描用户库。

## 2. 当前接口与差距

RE 已有可复用的接口：

| 方法与路径 | 当前用途 |
|---|---|
| `GET /api/factor-libraries` | 查询因子库目录 |
| `GET /api/factors/{library_name}` | 查询某个因子库中的因子 |
| `POST /api/internal/factor-backtest-batches` | 提交异步批量因子回测 |
| `GET /api/factor-backtest-batch-tasks/{task_id}` | 轮询批任务 |
| `GET /api/factor-backtest-batches/{batch_id}/factors` | 分页查询批次因子结果 |

现有批任务可以复用，但**不能直接满足当前面板**：它目前固定为 `CSI_ALL` 股票池、`CSI300` 基准、纯多头、5 组、每日调仓和至少 1 年回看；面板需要沪深 300/中证 500/中证 800/中证 1000/上证 50、近 3 个月/1 年/3 年、纯多空和 20 个交易日调仓。当前因子结果响应也只覆盖部分 IC 和分层指标，缺少面板展示所需的完整指标及任务实时进度。

建议**扩展现有批任务与结果接口**，不要另造一套并行的因子执行管线；另外增加一个按面板配置读取最新完整结果的查询接口。下文列出的差异均属于 RE 待实现项。

## 3. 面板因子目录

继续使用现有目录 API，并增加面板资格标记：

### 3.1 查询因子库

`GET /api/factor-libraries`

RE 响应中每个 library 增加：

| 字段 | 类型 | 说明 |
|---|---|---|
| `factor_dashboard_enabled` | `boolean` | 该库是否纳入内置因子面板；由 RE 管理，SVQuant 不再维护库名白名单 |

例如：

```json
{
  "libraries": [
    {
      "name": "momentum_lib",
      "description": "动量类因子",
      "factor_count": 12,
      "factor_dashboard_enabled": true
    }
  ]
}
```

### 3.2 查询因子

`GET /api/factors/{library_name}`

已有因子元数据（如 `name`、`display_name`、`description`、`category_name`）继续返回。每个因子应具有稳定身份；SVQuant 使用 `(library_name, name)` 组成唯一键。面板只展示 `factor_dashboard_enabled=true` 的库。

如果 RE 需要对单个因子排除面板，可在因子对象增加 `factor_dashboard_enabled`；未提供时按所属 library 的资格处理。

## 4. 提交面板批任务

### 4.1 请求

扩展现有接口：

```http
POST /api/internal/factor-backtest-batches
Content-Type: application/json
```

请求示例：

```json
{
  "as_of_date": "2026-09-20",
  "period": "3y",
  "universe": "CSI300",
  "benchmark": "CSI300",
  "portfolio_type": "long_short",
  "groups": 5,
  "rebalance_days": 20,
  "analysis_level": "core",
  "filter_limit_up": true,
  "filter_suspended": true,
  "selection": {
    "library_names": ["momentum_lib"],
    "factors": []
  },
  "force_recompute": false
}
```

字段约定：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| `as_of_date` | `YYYY-MM-DD` 或 `null` | 否 | 回测截止日期；省略/null 表示使用 RE 当前最新可用交易日。结果必须回显实际窗口 |
| `period` | `3m / 1y / 3y` | 是 | 面板预设窗口；RE 按实际可用行情解析起止日 |
| `universe` | 枚举 | 是 | `CSI300`、`CSI500`、`CSI800`、`CSI1000`、`SSE50` |
| `benchmark` | 枚举 | 否 | 基准；默认与 `universe` 相同 |
| `portfolio_type` | `long_short` | 是 | 当前面板口径为多空组合 |
| `groups` | 整数 | 是 | 当前面板固定为 5 组 |
| `rebalance_days` | 整数 | 是 | 调仓间隔，当前面板为 20 个交易日 |
| `analysis_level` | `core` | 是 | 当前面板使用核心指标 |
| `filter_limit_up` | `boolean` | 是 | 是否过滤涨停证券 |
| `filter_suspended` | `boolean` | 是 | 是否过滤停牌证券；当前面板默认 `true` |
| `selection.library_names` | `string[]` | 否 | 选择的面板库；省略或空数组表示全部面板库 |
| `selection.factors` | 对象数组 | 否 | 可选的因子子集，每项为 `{ "library_name": "...", "factor_name": "..." }`；非空时只计算选中因子 |
| `force_recompute` | `boolean` | 否 | 默认 `false`，复用配置完全一致的已完成结果；`true` 忽略旧结果并重新计算本次选择 |

`selection.library_names` 与 `selection.factors` 同时提供时，因子列表必须属于所选库；不匹配应返回 `422`。未显式选择因子时，只运行标记为面板可用的 RE 内置因子。SVQuant 不发送 `metric_version`、`execution_version` 或源码哈希；由 RE 在内部维护缓存失效与执行版本。

RE 必须将 `period`、实际行情窗口、证券池、基准、组合类型、组数、调仓间隔、过滤规则及因子选择都纳入批次配置和缓存键。只有配置完全一致的成功结果才可复用。

### 4.2 提交响应

HTTP `202 Accepted`。保留现有字段并返回任务标识：

```json
{
  "task_id": "task_abc123",
  "status": "queued",
  "poll_url": "/api/factor-backtest-batch-tasks/task_abc123",
  "created_at": 1789890000.0
}
```

`poll_url` 是 RE 相对路径；SVQuant 后端负责拼接 RE base URL，浏览器只轮询 SVQuant 的 BFF。

## 5. 任务状态与进度

### 5.1 轮询

```http
GET /api/factor-backtest-batch-tasks/{task_id}
```

在现有任务响应上增加 `progress`。状态取值：`queued`、`running`、`succeeded`、`failed`。任务正常结束但部分因子失败时，批任务状态仍为 `succeeded`，失败数由 `progress.failed` 和批次摘要表达；仅批级基础设施或任务错误使用 `failed`。

```json
{
  "task_id": "task_abc123",
  "status": "running",
  "created_at": 1789890000.0,
  "started_at": 1789890001.0,
  "finished_at": null,
  "batch_id": "batch_xyz",
  "batch_url": "/api/factor-backtest-batches/batch_xyz",
  "progress": {
    "done": 24,
    "total": 120,
    "succeeded": 21,
    "failed": 2,
    "skipped": 1,
    "current_factor": "momentum_20d",
    "updated_at": "2026-09-20T06:30:00Z"
  },
  "error": null
}
```

进度字段要求：

| 字段 | 类型 | 说明 |
|---|---|---|
| `done` | integer | 已处理数量，包含成功、失败、跳过 |
| `total` | integer | 本批次计划处理数量 |
| `succeeded` | integer | 成功数量 |
| `failed` | integer | 单因子失败数量 |
| `skipped` | integer | 因缓存、无数据或明确策略跳过的数量；具体原因由结果行说明 |
| `current_factor` | string/null | 正在处理的因子名 |
| `updated_at` | timestamp | 最近一次进度更新时间 |

RE 应在任务开始后尽早分配并回显 `batch_id`，使任务运行中也能查看批次摘要。终态任务必须提供 `finished_at`；批级失败时提供 `error`，可查询的批次摘要可通过 `batch_url` 获取。

## 6. 查询面板最新结果

新增只读接口，按指定面板配置返回最近一次成功完成的整批快照：

```http
GET /api/factor-dashboard/results
  ?universe=CSI300
  &period=3y
  &as_of_date=2026-09-20
  &filter_limit_up=true
  &filter_suspended=true
  &library_name=momentum_lib
  &limit=1000
  &offset=0
```

筛选规则：

- 不传 `library_name` 返回所有面板库；传入则只返回该库。
- 查询的是“最近一次已完成批次”，不返回尚未完成的半批结果；运行进度走任务接口。
- 返回配置必须与查询条件精确匹配。没有匹配结果时返回 `200`、`batch: null`、`results: []`，不伪造指标。
- 支持 `limit`/`offset`，并返回 `total`；面板因子总数在当前规模下建议允许一次取完（`limit` 上限至少 1000），以便 SVQuant 继续完成搜索、排序、校验筛选和分页。
- 可以按 `library_name + factor_name` 过滤结果；列表中不得丢失未计算或失败的因子行。

响应示例：

```json
{
  "batch": {
    "id": "batch_xyz",
    "status": "succeeded",
    "universe": "CSI300",
    "benchmark": "CSI300",
    "period": "3y",
    "window_start": "2023-09-20",
    "window_end": "2026-09-20",
    "filter_limit_up": true,
    "filter_suspended": true,
    "total_count": 120,
    "succeeded_count": 115,
    "failed_count": 3,
    "skipped_count": 2,
    "finished_at": "2026-09-20T06:40:00Z"
  },
  "total": 12,
  "limit": 1000,
  "offset": 0,
  "results": [
    {
      "library_name": "momentum_lib",
      "factor_name": "momentum_20d",
      "display_name": "20日动量",
      "category_name": "动量",
      "status": "succeeded",
      "metrics": {
        "ic_mean": 0.031,
        "ic_std": 0.08,
        "rank_ic_mean": 0.027,
        "ic_ir": 0.388,
        "annual_return": 0.12,
        "max_drawdown": -0.18,
        "turnover": 0.35,
        "win_rate": 0.52,
        "sharpe": 0.81,
        "q1_return": 0.14,
        "q5_return": -0.02,
        "long_short_spread": 0.16,
        "q1_turnover": null,
        "q5_turnover": null
      },
      "error_code": null,
      "error_message": null
    }
  ]
}
```

结果行建议扩展现有 `FactorBacktestFactorRunResponse`，保留现有 `ic_mean`、`rank_ic_mean`、`ic_ir` 和 `quantile_metrics`，并提供上述面板标量字段。若某指标在 RE 当前计算中不可用，返回 `null`；不可把 `coverage_pool` 代填为胜率，也不可把组合总换手伪称为 Q1/Q5 换手。

## 7. 指标定义与单位

为避免不同服务重复换算，RE 响应采用以下规范化口径：

| 字段 | 口径 | 单位/示例 |
|---|---|---|
| `ic_mean`、`rank_ic_mean`、`ic_std` | 按时间序列聚合的截面 IC / RankIC | 相关系数原值；`0.03` 表示 `0.03` |
| `ic_ir` | IC 均值除以 IC 标准差，按 RE 指标定义计算 | 无量纲 |
| `annual_return`、`max_drawdown`、`turnover`、`win_rate`、`q1_return`、`q5_return`、`long_short_spread`、`q1_turnover`、`q5_turnover` | 比例值 | 小数；`0.12` 表示 `12%` |
| `sharpe` | 按 RE 固定年化规则计算 | 无量纲 |

`annual_return`、`max_drawdown`、`turnover`、`win_rate`、`sharpe` 对应请求所选 `portfolio_type`；**Q1 为因子值最高组、Q5 为因子值最低组**，`long_short_spread = Q1 - Q5`（做多最高组、做空最低组）。不按因子正负预测方向调整分组含义。

换手分两类，**不得互相冒充**：`turnover` 是**整条主组合**的平均单边换手
（`mean(Σ|Δw| / 2)`，逐日计算、不年化）；`q1_turnover` / `q5_turnover` 是**逐分位换手**，
口径同 `quantile_metrics[].turnover`（该分组的日均单边换手）。分组是等权诊断桶而非可交易策略，
其换手全部来自排名进出，量级通常显著高于主组合，不能拿来代表组合的换手成本。

> **方向以 RE 实现为准，已核对 RE 源码**：`app/services/portfolio/grouping.py` 的 `rank_groups` 文档与实现均声明「Q1 为因子值最高组，QN 为最低组」；`app/services/factor/runner.py` 的 `spread` 用分层净值首列减末列（即 Q1 − QN）。
> 本文件早期版本曾写作「Q1/Q5 为因子分值从低到高的第 1/5 组，`long_short_spread = Q5 - Q1`」，**方向与公式均与 RE 相反，已更正**；面板展示层同步改为在列名标明「最高分位 Q1 / 最低分位 Q5」。纯做多的参考收益即 `q1_return`（最高分位）。

现有 SVQuant 面板数据库中的部分百分比字段采用“百分数点”存储（如 12 表示 12%），新 BFF 适配时必须只转换一次；不得把 RE 的 `0.12` 当作 `12` 再显示成 `1200%`。IC 字段直接按相关系数展示。

## 8. 错误处理与缓存语义

- 请求级参数错误：`400` 或 `422`，返回机器可读的 `detail`/错误码。
- 任务或批次不存在/过期：`404`。
- RE 停止接收任务或任务系统不可用：`503`。
- 单因子数据缺失、因子异常或计算失败：批任务继续处理其它因子，该因子以 `status: "failed"` 返回，并附 `error_code`、`error_message`；数值字段全部为 `null`。
- `force_recompute=false` 时只复用配置、因子定义及数据范围都匹配的成功结果；失败结果允许重试。`true` 创建一次新的计算批次。
- 面板读接口只读取 RE 批次结果或其 PostgreSQL 缓存，不回退到 SVQuant 本地逐因子回测；RE 不可达时，由 SVQuant 清晰显示服务不可用，不以过期指标冒充最新结果。
- 计算结果及其数据/执行元信息由 RE 自行维护；SVQuant 不向请求中硬编码或指定 RE 内部版本号。

## 9. SVQuant BFF 映射

浏览器仍使用 SVQuant API。SVQuant 后端新增/调整 BFF 路由，薄转发到 RE，并负责登录校验、超时、错误映射：

| SVQuant API（建议） | RE API |
|---|---|
| `GET /api/factor/dashboard` | `GET /api/factor-dashboard/results` |
| `GET /api/factor/dashboard/status?task_id=...` | `GET /api/factor-backtest-batch-tasks/{task_id}` |
| `POST /api/factor/dashboard/refresh` | `POST /api/internal/factor-backtest-batches` |
| `POST /api/factor/dashboard/verify` | **不转发**，继续写 SVQuant 持久化层 |

SVQuant 可以把验证状态合并到结果行，默认值为 `pending`。刷新接口返回 RE 的 `task_id`；面板状态轮询应以该 `task_id` 为准，避免依赖 RE 全局单任务文件。页面搜索、分类选择、排序、校验筛选及分享行为保持产品层实现。

## 10. 验收条件

1. 目录 API 能标记面板可用库；SVQuant 不再维护 RE 官方库名白名单。
2. RE 可按支持的五类证券池、三个面板周期、过滤条件和因子选择创建批任务。
3. 相同配置能读取最新完整批次；强制刷新能创建新批次，查询结果不混入旧配置指标。
4. 轮询响应包含实时 `done/total/succeeded/failed/skipped/current_factor`；完成态可关联 `batch_id`。
5. 结果支持面板全部指标、逐因子失败状态和分页；单因子失败不会让整批中止。
6. 空值保持 `null`，百分比和 IC 的单位符合本契约；没有旧数据或 RE 不可达时不伪造结果、不静默回退到 SVQuant 本地计算。
7. SVQuant 管理员验证状态仍独立于 RE 指标并保存在 SVQuant 数据库。

## 11. 实现前需要 RE 确认的事项

- RE 对纯多空组合的年化、回撤、胜率、换手和 Sharpe 的精确定义，以及 Q1/Q5 收益的累计区间口径。
- RE 是否能直接提供 20 交易日调仓；若 `rebalance_days` 的单位当前不是交易日，需在契约与测试中明确。
- RE 最新行情日的解析规则、预设周期的起止日期算法，以及按实际窗口复用缓存的条件。
- 批任务期间 `batch_id` 的可用时点、进度快照更新频率和任务 ID 保留时长。
- RE 批次结果的保留期与运维容量；未来若“RE 无状态”也要求 RE 不保存结果，则需另行设计由 SVQuant 持久化结果快照的方案。

以上接口一旦由 RE 接受，应在 ResearchEngine 仓库维护权威 OpenAPI schema、契约测试和版本兼容说明；本文件作为 SVQuant 集成侧需求，随契约变更同步更新。
