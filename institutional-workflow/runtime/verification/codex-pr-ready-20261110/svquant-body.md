机构因子研究此前在创建/恢复、人工接力、数据版本变化与模型回执异常时容易丢失正确身份或误显结果。本分支沿现有四环节接通真实任务、受控执行、研发诊断、研究复盘和机构研究资产审批，保留历史证据与独立审批边界。

这是累计开发分支的待整合PR，不是“整个因子模块/386文件均已验收”的声明。

### 源与目标

- source: `dev-zxd`，本次审查业务/证据快照 `573d05513ed35ff8e1e29ab394583cb073c0b603`（代码审查快照；实际已加载方法源为`7e78650`，仅startup安全补丁未重载）。
- target: 最新已fetch `origin/master` `3d7f1e7f5e8c594b6180d5e5754aa1a35d8a0468`；merge-base `3f20a9eba3bc24911d763f5b7e90d72930d22bda`。
- 此代码快照source-only74提交、target-only110提交、三点比较386文件；详见同目录`source-base-diff.json`。没有切分支、rebase或合并。后续仅PR说明文档提交应另核最终source，不静默沿用上述快照计数。

### 最终行为与累计范围

- 因子任务详情、四环节、真实E/H版本与报告身份；历史只读，暂停/接手/保存/交回有epoch保护，迟到产物不覆盖人工工作稿。
- 结构化研究规划→实现→真实RE工具→研发诊断→下一步；字段/方向/门槛由控制器冻结，RankIC证据对应实际父E/H。模型生成/技术等待/数值失败分别记录。
- 产品累计Token unlimited授权覆盖，保留真实物理用量、旧grant与未知历史；不改变公司全站账号日次数或模型。单次provider_default不意味着供应商无限输出，技术超时仍明确记录，不隐藏重试。
- 自有部署持久根研究并发1，保留FIFO/子动作/未知物理调用占位；重启不盲目重放半完成动作。固定发布view沿实际文件与provider路径验证，不能回落current。需要配套私有RE分支。
- 独立审批/冻结研究资产登记，事务幂等、本人/跨机构拒绝与白名单复用；失败复盘仅退回/驳回，不产生准入。真实新好因子审批入库尚未完成。
- 累计PR也包含CR094数据目录/字段检索/详情/版本/需求幂等与质量口径，以及PM原型/规格/验收证据。仅元数据与既有机构接口，不宣称采集清洗Agent或整个平台完成。
- 包含此前策略页两处UUID兼容替换及共享API适配，具体见`shared-integration-review.json`；不作为本轮策略功能或新验收。CR102仅规格/原型及runtime暂存纯函数，未整合、迁移或启用自动立项。

### 已有证据及其边界

- 最新scope修复：`codex-factor-cr101-20261110/scoped-diagnostic-epoch-final.log`5专项；`scoped-diagnostic-unit.log`14项+19子测；实际React组件1项；`scoped-diagnostic-build-resources.json`exit0、36.123s、峰2365341696B。原样模型代码8列诊断无法满足20列前提，40列合成Panel通过实际RE FactorEngine/前缀/未来扰动；这不是市场绩效。
- CR101前批：capacity-unit17+7子测、capacity-PG6、运行快照PG4、queuePG12+控制PG1；自有临时schema真实事务，模型/部分服务依赖替身。私有RE18合成文件与原引擎测试另仓说明。它们是对应提交的专项，不是最新master整合全测。
- CR094：23后端/8ASGI路由/12实际组件、4旧路径真实隔离PG及构建；真实元数据只读60数据集/993字段。ASGI鉴权/数据依赖替身不冒称在线HTTP。见`codex-data-cr094-20261109/delivery.md`及PM对应验收记录；未在本次重新验全部数据需求转交链。
- 已真实跑过自动、人工、人机接力及双身份复盘，均未获得合格新因子准入。PM已记录r4两次真实市场试验：K2、观测44→63仍未通过统计门槛；不是合格准入。本开发未代发新试验；不把页面/接口接通、生成成功或源码因果诊断当好因子。没有全331/334对照通过或生产成交证据。
- 普通后端验证须用`backend/scripts/run_quant_isolated_tests.py`，真实PG仅显式独立schema入口，避免继承业务DB/网络产生副作用。已有测试隔离事件和历史缺项继续留审计，不抹掉。

### 数据库与加载

- 累计分支还含0036/0037机构控制、0038机构预算。新增0039→0040→0041依序在已具备0038的开发库执行：追加unlimited政策覆盖→自有队列/槽/调用关联→单次输出容量可未知及请求参数。迁移不自动授予授权、不清零旧用量。
- 公司/生产环境需审核完整迁移状态和机构授权后另行执行；本次只在自有svquant_dev按不可变授权文件激活本机构单池，旧35210（当时实耗）及历史180331下限/46缺项保持，后续物理调用继续结算。
- 仅自有18799 BFF、18804私有RE加载；19536前端HMR，未重启共享服务/改共享current。0039–41与unlimited实际记录：`codex-factor-cr101-20261110/load-evidence.json`；r4仅BFF加载：`scoped-diagnostic-load.json`，PID3654585、health`ok=true/db=ok`。
- 部署flag/启动路径见`startup-map.json`；不从本PR自动启用其他实例，不把自有加载称公司发布。

### 合并前待处理

1. `frontend/package.json`双边同一test命令：保留master串行参数与机构新增测试，再合入quant用例；`test_quant_data_requests.py`结合双方固定发布集合替身和CR094契约。
2. 本仓startup风险已用`573d055`修复：默认lifespan只进入显式flag门控的既有owned dispatcher；旧全表候选恢复入口改无DB/no-op。16项+2子测（实际lifespan、外部bootstrap/prewarm替身）通过；默认不动研究表、own恢复路径/identity本体未改、恢复异常不伪装成功。证据`startup-scope-tests.log/json`。此后未重载任何服务；保留原发现，不把已修项继续丢给公司。
3. 共享detect/AI入口与最新master合并后的兼容/全量门禁尚未执行。最新master有110项source未含提交，不能认为当前开发环境测试已覆盖。
4. 最终由用户审批合并；本开发者不自合并、打tag或更改共享部署。Gitee当前未能鉴权读取PR列表，本文是ready正文，不是已创建PR回执。
