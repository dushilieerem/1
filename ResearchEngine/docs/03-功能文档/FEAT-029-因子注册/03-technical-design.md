# FEAT-029：数据库因子加载与回测执行器最小改造 — Technical Design

> 2026-08-28 架构修订：用户已确认 ADR-029 的常规 FastAPI 分层。
> 原 QuantCore 运行时边界取消；五个 Engine 的业务逻辑进入 `app.services`，
> Panel、MetricContext、回测规格/结果和实验上下文进入 `app.models`，数据访问进入 `app.database`。
> 配置为 `app.config`，通用工具为 `app.utils`；不增加 domain/application/infrastructure。
> 下文中的旧目录和旧分层仅作历史设计追溯，不再作为新代码约束；既有业务规则和历史验证记录保留。
> 详见根目录 FEAT-030/06-app-layout.md 与 ADR-029。FEAT-029 因子来源加载目标保持不变。


> FEAT-030 当前实现：完整执行入口为 BacktestEngine.run，因子来源由 FactorEngine 的
> `_resolve_factor(spec)` 统一处理；默认 loader 与注入式 loader 均属于 FactorEngine。
> 本文的原 Spec/Executor/算法不变设计已由 [FEAT-030](../../../../docs/03-功能文档/FEAT-030-因子回测流程重构/README.md)
> 的四引擎主链接替；本 Feature 不与新架构并行建设第二套因子流程。
> 数据库 schema、loader 实现和来源切换已由本 Feature 接入当前主链。

## 设计结论

本 Feature 的最终目标只替换因子来源，不重新设计运行时对象。当前四引擎主链由 FEAT-030
负责：`FactorEngine` 保持计算 API，并由 `_resolve_factor(spec)` 统一处理
因子来源；默认 loader 与注入式 loader 都返回项目已有的 `BaseFactor`。数据库记录已经
通过同一入口接入；`FactorBacktestSpec` 和 `BacktestEngine.run()` 保持，旧 Executor
已由 FEAT-030 删除。

## 当前链路

```text
FactorBacktestRequest
  → runner._request_spec()
  → FactorBacktestSpec(factor_name, library_names, factor_code, ...)
  → BacktestEngine.run(spec)
  → FactorEngine._resolve_factor(spec)
      ├─ factor_code：临时 .py + 代码 loader
      └─ library_name：SQLite + tool.py + SQLiteFactorLoader
  → FactorEngine 私有保存 BaseFactor；原始 spec 不变
  → DataEngine → FactorEngine → PortfolioEngine → MetricEngine
```

标准主链不再经过 Executor 或 `factor_resolver`；BacktestEngine 只调用
`FactorEngine._resolve_factor(...)`。当前默认 loader 为 `SQLiteFactorLoader`，替换数据库
实现仍只需替换 loader 或注入配置，不改变 BacktestEngine 的编排职责。

## 改造后链路

```text
FactorBacktestRequest / 批量入口
  → 现有 _request_spec（不改）
  → 现有 FactorBacktestSpec（不改）
  → BacktestEngine.run(spec)
  → FactorEngine._resolve_factor(spec)
  → SQLiteFactorLoader / 代码 loader（按规格选择 database / code）
  → 现有 BaseFactor
  → replace(spec, factor=base_factor)
  → DataEngine → FactorEngine → PortfolioEngine → MetricEngine
```

### 关键接线

当前 `runner.submit_factor_backtest()` 只创建统一的 BacktestEngine，不再注入来源 resolver；
实际来源加载统一经 `FactorEngine._resolve_factor(spec)`，这是 FactorEngine 的
任务级解析职责，不是 runner 的请求适配职责。

批量协调器的 `_catalog_items()` 直接读取 SQLite 目录，生成的 `FactorCatalogItem` 不携带
运行期因子对象，实际任务统一进入 `FactorEngine` 按 Spec 解析。目录扫描先读取元数据，
单条源码在实际加载时校验，错误因子不会阻断整库枚举。

## 数据库模型

当前部署使用只读 SQLite 文件；ResearchEngine 通过仓库封装 SQL，后续如需替换存储实现不改变
FactorEngine 的加载契约。实际数据库包含因子库、分类和因子三张表：

### `factor_libraries`

| 字段 | 类型 | 说明 |
|------|------|------|
| `library_id` | INTEGER PRIMARY KEY | 因子库 ID |
| `library_name` | TEXT UNIQUE | 因子库名称 |
| `description` | TEXT | 因子库说明 |

### `categories`

| 字段 | 类型 | 说明 |
|------|------|------|
| `category_id` | TEXT PRIMARY KEY | 分类 ID |
| `category_name` | TEXT UNIQUE | 分类名称 |
| `description` | TEXT | 分类说明 |

### `factors`

| 字段 | 类型 | 说明 |
|------|------|------|
| `sv_id` | TEXT PRIMARY KEY | 稳定因子标识，作为批量和目录键 |
| `library_id` | INTEGER | 所属因子库 |
| `factor_name` | TEXT | 中文展示名称 |
| `factor_name_en` | TEXT | 英文展示名称 |
| `factor_code` | TEXT | 一个顶层因子函数的源码 |
| `category_id` | TEXT | 所属分类 |
| `description` | TEXT | 因子说明 |

加载器按 `sv_id`、中文名、英文名或源码函数名查找；执行指纹由 `sv_id`、`factor_code` 和
项目内 `tool.py` 共同计算。当前数据库未保存历史版本表，历史结果通过指纹和批量结果仓库追溯。

## FactorEngine 与加载器

FactorEngine 保留现有计算入口，并增加一个统一的加载门面，但不直接依赖数据库驱动：

```python
class FactorEngine:
    def load_factor(
        self,
        source: str = "database",
        *,
        library_name: str | None = None,
        factor_name: str,
        factor_code: str | None = None,
        loader: object | None = None,
    ) -> BaseFactor: ...
```

`FactorEngine.load_factor()` 按 `source` 调用统一 loader，并把结果注册到自身的
`factors` 字典；`compute()` / `compute_panel()` 仍只接收已注册的 `BaseFactor`。

loader 的实现做三件事：

1. 读取一条记录，检查状态、代码和哈希；
2. 用当前项目的模板/加载约定在内存中编译代码，不要求代码文件落盘；
3. 返回现有 `BaseFactor` 实例，必要时把记录中的参数作为 `params` 传入。

`source` 的最小取值为：

- `database`：通过 SQLite 仓库读取因子记录（默认）；
- `code`：复用当前自定义代码模板，根据代码构造因子。

数据库仓库只负责只读数据读取，不负责回测；它由 `SQLiteFactorLoader` 持有。这样
FactorEngine 对调用方提供统一入口，但 QuantCore 不直接导入 SQL 驱动。

代码加载策略按保存形态选择：

- SQLite 因子记录：在受控 namespace 中执行唯一顶层函数源码，注入外部 `tool`、`numpy`、
  `pandas` 和现有 `FactorLibrary` 面板字段，再适配为 `_MethodFactor`；
- 用户方法源码：复用 `_wrap_factor_code()` 的模板语义，在内存 namespace 中生成临时库，再取目标因子；
- 旧完整 `FactorLibrary` 文件：仅由迁移期 `FactorLoader` 显式兼容，默认主链不枚举。

加载结果必须满足：

```python
isinstance(factor, BaseFactor)
factor.name == requested_factor_name
callable(factor.compute)
```

加载器不实现行情读取、不实现分组回测；FactorEngine 只负责调用并注册加载结果。

## Executor 变化

数据库来源迁移时，标准运行时仍以 `BacktestEngine.run()` 为主入口；旧 Executor 只保留
兼容委托。数据库 loader 的公开调用示例如下：

```python
BacktestEngine.run(spec, context) -> FactorBacktestResult
```

来源判断委托给 FactorEngine 的解析方法，公开错误边界保持：

```python
factor = factor_engine._resolve_factor(spec)
```

新的默认路径不再由 Executor 或 runner 自己拼装文件 loader；`factor_resolver` 已从因子主链
删除。

BacktestEngine 中已有的以下行为全部保留：

- 校验 `FactorBacktestSpec`；
- 构造 `FactorEngine(spec)` 并调用 `compute()`；
- FactorEngine 私有持有解析后的 `BaseFactor`，不会改写原始 `spec`；
- 将因子面板交给 DataEngine → FactorEngine → PortfolioEngine → MetricEngine；
- 结果元数据继续记录 `factor_source_hash`、`spec_hash`、数据 release 和执行版本。

## 哈希、缓存与版本

`runner._request_factor_source_hash()` 不再以旧 `.py` 文件 SHA 作为数据库因子主值，而是
根据数据库中的因子源码、项目内 `tool.py` 和 loader 适配版本生成执行指纹。这样：

- 说明、标签变化不影响计算缓存；
- `factor_code` 变化必然生成新哈希并使旧缓存失效；
- 版本表中的历史代码可按旧哈希复现；
- `FactorBacktestSpec` 无需新增任何字段。

迁移期间若数据库没有记录，`load_factor_from_spec()` 对不属于数据库的旧库名保留
`.py + index.yaml` 兼容回退；默认目录、回测和批量入口只枚举数据库。数据库路径和公共
工具路径可由 `SVQUANT_FACTOR_DB_PATH`、`SVQUANT_FACTOR_TOOL_PATH` 覆盖。

## FactorTool 约定

继续使用项目内 `app/assets/factors/tool.py` 的模块级函数。模块名本身就是 Python
里接近 C++ namespace 的静态函数集合；数据库因子直接使用注入的 `tool`：

```python
def factor(self, window=20):
    return tool._sma(self.close, window)
```

不新增 `FactorTool` 实例类，也不要求在 `BaseFactor` 上添加 `self.tool`。若后续确实需要
`self.tool` 语法，应作为独立兼容性小改动，不能与本次数据库加载耦合。

## 兼容、迁移与回滚

### 导入

1. 读取 `index.yaml` 的库和因子清单。
2. 读取对应 `.py` 源码并计算 `code_hash`。
3. 将库、因子、说明、标签和校验状态写入数据库；原文件保持不变。
4. 对重复键比较哈希和元数据，输出相同、变更、冲突和失败清单。
5. 固定面板抽样验证数据库加载结果与文件加载结果。

### 当前切换状态

- 默认目录、单因子回测和批量协调器均使用项目内 SQLite 因子库。
- `tool.py` 作为数据库源码的公共算子模块，随因子执行指纹参与缓存失效判断。
- 旧 `.py + index.yaml` 保留为迁移期兼容路径，不作为默认目录或默认因子来源。
- 数据库目录扫描先读取元数据，单条因子源码在实际加载时校验，错误因子可单独失败。

### 回滚

将 `SVQUANT_FACTOR_DB_PATH` 指向已验收的 SQLite 快照即可切换数据库版本；需要临时使用旧
因子时，调用迁移期 `FactorLoader`/旧库名兼容路径。由于本次不修改 Spec 和 FactorEngine
的计算入口，回滚不需要恢复回测代码。

## 影响分析

### 不受影响

- `FactorBacktestSpec` 字段、哈希结构和序列化。
- `FactorEngine` 的 `register`、`compute`、`compute_panel`、`compute_all` 及 Vector/Native 后端。
- 单因子、批量因子和 Python 兼容入口的公开请求参数。
- WebApp 文件和现有结果仓库表结构。

### 后续补强

- 数据库历史版本表、写入/导入脚本和差异报告。
- 因子审核状态、权限和生产沙箱。
- 更多代表性因子的数据库与旧文件数值对比测试。

### 主要风险

- 现有完整库代码包含私有辅助函数或方法依赖：首期保存完整源码，避免强行拆分；之后再按数据验证结果抽取 `factor_tool`。
- 数据库代码执行仍是可信 Python，不是安全沙箱；只允许可信部署使用。
- 多实例同时更新需要仓库层乐观锁或事务；不把并发策略塞入 Executor。

## 测试策略

- 仓库：不存在、禁用、版本读取、哈希和连接错误。
- 加载器：完整库源码、方法源码、`factor_tool` 调用、语法错误和名称不存在。
- Executor：Spec 不变、resolver 返回 `BaseFactor`、数据库失败错误映射和已传入 factor 的短路。
- 回归：单因子、批量因子、兼容入口和缓存键。
- 数值：代表性库在固定小面板上比较文件与数据库来源结果。
