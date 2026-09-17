# FEAT-029：数据库因子加载与回测执行器最小改造 — Product Requirements

## 目标与非目标

### 目标

- 用数据库集中保存因子名、代码、说明、库、版本和管理字段。
- 让已有因子回测请求仍转换为原来的 `FactorBacktestSpec`。
- 让 `FactorEngine.load_factor()` 在需要时从数据库加载因子并交给 `BacktestEngine`，得到现有 `BaseFactor`。
- 让代码哈希、版本和校验状态能支持缓存失效与问题追溯。

### 非目标

- 不新增 `factor_id` 请求契约，不要求调用方改写现有 `library_name + factor_name`。
- 不修改 `FactorBacktestSpec` 的字段、构造方法或 `to_dict()` 结构。
- 不改变 FactorEngine 的既有计算接口、回测算法、批量调度和 WebApp；加载门面和兼容接线先
  在数据库迁移前落地，数据库 loader 后续再接入。
- 不在本 Feature 解决 Python 沙箱、权限、审批或远程服务高可用。

## 用户故事

| 角色 | 用户故事 |
|------|----------|
| 因子维护者 | 我可以在数据库中保存因子代码、说明、标签和当前版本。 |
| 因子维护者 | 我可以根据库名和因子名找到一个因子，并知道代码哈希与校验状态。 |
| 回测调用方 | 我继续提交现有回测参数，不需要知道代码存在哪个 `.py` 文件。 |
| 批量任务 | 我仍然可以使用现有批量目录和 `FactorBacktestSpec` 执行因子。 |
| 运维人员 | 我可以从回测结果中的因子名、库名和代码哈希定位数据库记录。 |

## 业务流程

### 因子入库

1. 导入脚本或管理端提交 `library_name`、`factor_name`、代码和说明。
2. 仓库校验唯一键 `(library_name, factor_name)`、代码非空和基本 Python 语法。
3. 保存当前记录、代码哈希、版本号、标签、校验状态和更新时间；需要保留历史时写入版本表。
4. 导入脚本输出新增、更新、冲突和失败清单，不静默覆盖人工维护内容。

### 因子回测

1. API 或批量入口创建 `FactorBacktestSpec(factor_name=..., library_names=...)`。
2. `BacktestEngine.run(spec, context)` 将规格和数据面板交给 `FactorEngine.compute_from_spec()`。
3. FactorEngine 的 loader 调用数据库仓库读取代码记录。
4. 加载器把数据库代码编译/实例化成现有 `BaseFactor`，作为 FactorEngine 的私有运行态，必要时注入 `factor_tool` 和 NumPy/Pandas。
5. BacktestEngine 使用已有的 `replace(spec, factor=...)`，然后继续 DataEngine → FactorEngine → PortfolioEngine → MetricEngine。
6. 回测结果沿用原有字段，并写入数据库版本对应的 `factor_source_hash`。

### 兼容路径

- `factor_code` 非空时保留当前自定义因子解析方式，作为兼容和故障回退路径。
- 内置因子默认走数据库；旧 `.py + index.yaml` 只在迁移期间作为显式回退，不作为新的主路径。

## 因子管理字段

首期可以用一张当前表加一张可选版本表承载以下信息；这些是持久化字段，不对应运行时类：

| 业务概念 | 首期存储 |
|----------|----------|
| `factor_definition` | 因子名、说明、作者、所属库、状态、依赖字段 |
| `factor_version` | 当前版本、历史版本、代码、代码哈希、更新时间 |
| `factor_tag` | JSON 数组或关联表 |
| `factor_validation` | 语法/单测/数据覆盖/数值验证状态及摘要 |
| `factor_metric_snapshot` | 最近一次或指定批量回测指标摘要 |
| `factor_alias` | 旧名称、第三方名称和兼容名称 |
| `factor_library` | 库编码、展示名和来源 |

## 业务规则与异常

| 场景 | 规则 |
|------|------|
| 数据库找不到库/因子 | 返回现有因子参数错误，包含库名和因子名；不进入回测算法。 |
| 数据库代码为空或语法错误 | 返回因子参数错误；不得返回一个空因子。 |
| 代码哈希变化 | 新哈希参与 `FactorBacktestSpec.identity()` 使用的 `factor_source_hash`，旧缓存不可复用。 |
| 历史版本管理 | 数据库保留历史代码和哈希；首期回测默认读取当前版本。历史版本回测待后续在不破坏现有 Spec 的前提下补充入口。 |
| 数据库暂不可用 | 新任务失败并记录数据库错误；不得静默使用未知旧代码。迁移期可配置旧文件回退。 |
| 已有内存因子 | 直接使用，不重复查询数据库，保证兼容 `FactorBacktestSpec.from_legacy()`。 |
| 因子代码调用工具 | 只允许使用现有 `factor_tool.<method>()` 公共工具命名空间；不创建第二套工具类。 |

## 代码契约

数据库保存的代码必须保持现有项目支持的形态之一：

- 完整 `FactorLibrary` 子类/模块源码；或
- 当前自定义入口接受的因子方法代码，由加载器套用现有模板。

首期不强制把所有因子改写成新 DSL，也不强制拆分现有私有辅助函数。数据库加载器应优先保持
原代码的类、方法和辅助函数语义；需要抽取通用纯计算时，使用：

```python
from app.quantcore.factor import tool as factor_tool

return factor_tool.zscore(values)
```

## 非功能要求

- 单因子数据库查询在本机数据库正常运行时 P95 小于 100 ms；连接超时要在执行器边界内结束，
  不得无限等待行情任务。
- 列表/检索只返回管理字段，不默认返回全部源码；读取单个因子时才返回代码。
- 日志记录库名、因子名、版本和 `code_hash`，不输出完整因子代码。
- 导入脚本可重复执行，必须明确区分相同、变更、冲突和失败，不覆盖人工修改的记录。
- 因子数据库的备份和权限由部署方负责；本 Feature 不把数据库连接暴露给 QuantCore。

## 验收标准

1. 给定数据库记录，`BacktestEngine.run(spec, context)` 能得到可执行 `BaseFactor`。
2. `FactorBacktestSpec` 的字段和 `BacktestEngine.run(spec, context)` 契约保持兼容；旧 Executor 仅委托该入口。
3. 同一因子从旧文件和数据库读取时，固定小面板的结果在约定容差内一致。
4. 数据库代码更新后，结果中的 `factor_source_hash` 更新且旧回测缓存不命中。
5. 现有单因子、批量和兼容入口通过回归测试。
6. 缺失、语法错误、数据库连接错误均转换为可识别的领域错误。
7. 导入脚本可重复执行并输出差异，不删除原 `.py` 和 `index.yaml`。
8. `factor_tool` 继续由现有 `app.quantcore.factor.tool` 提供，无重复 `FactorTool` 类。
