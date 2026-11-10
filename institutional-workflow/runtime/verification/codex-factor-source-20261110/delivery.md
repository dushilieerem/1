# UX105 因子源码与详情交付（待加载）

331导入因子都可映射到私有RE真实SQLite定义。新增RE单因子GET源码DTO，机构BFF先按当前org查导入ID，再薄代理已配置私有RE；客户端不传文件/DB路径或RE地址。源码原文不改，不exec/compile。source_sha256为原始UTF-8摘要；source_hash由原RE仓库函数计算，包含稳定ID/适配器版本/原文/公共工具，二者分开。

正式列表打开右侧760px/边16px原DataDialog，默认概览、实现代码、验证记录；代码按需读，切换/关闭会取消并拒绝迟到结果。代码滚动、复制及dialog内反馈；临时复制textarea在原生dialog内，失败诚实提示手动复制。关闭/Esc回焦、原筛选保留。基础目录统一“基础因子”，不出现错误的源码不可见/内部版本口径。

原库研究复用仍按library+SV ID，不把源码塞入draftFactor.body/factor_code。新研究资产仍读原冻结资产API，详情移入同形态侧栏，未改其权限/批准/报告内容。当前基础库源码不当成历史报告版本、独立可执行保证或准入合格。

## 实际验证

- BFF source-bff-isolated.log：7项+14子测试通过；真实FastAPI路由/错误包装，身份/上游依赖替身，数据库与网络双卫兵。跨org无行时不发上游，源码/函数/库/哈希不一致拒绝；非在线HTTP鉴权全链路验收。
- 私有RE source-re-isolated-final.log：6项通过（5源码API+1既有SQLite loader兼容）。临时SQLite/ASGI真实读取，原文/两类hash/无执行/只读文件不变/空和404及不可用；缺稳定ID不会扫描另一条坏源码，原函数别名执行兼容保留。非市场数据回测。
- source-six-final.log：最终6实际组件全过，4.413s/344797184字节，heap512；包含按需读取、乱序、复制两条路径、真实机构client允许路径、只读、无自定义源码复用。
- source-components-final.log：前5源码组件+12机构鉴权兼容通过（不重复相加统计）。source-asset-compat.log：既有普通研究员冻结资产入口1项通过；2.808s/358670336字节。
- source-build-final.log：本批唯一最终构建exit0，34.720s/2400911360字节，heap2048/串行，RSS3GiB和主机可用16GiB停止线。早先复制用例有一次停止线事件及后续修复，见resource-incident.json，未隐藏/当通过。

命令：backend现有解释器 scripts/run_quant_isolated_tests.py tests/test_quant_factor_library_source.py；私有RE现有解释器 -m pytest -q tests/test_factor_source_api.py tests/test_sqlite_factor_loader.py::test_sqlite_repository_and_loader_use_stable_id_and_function_alias；前端run-node-bounded.py精确参数均在resources JSON。原文读取映射证据readonly-source-map.json仅元数据/函数/摘要，不导出331份源码。

## 加载边界

主仓实际commit见Git；私有REcommit见re-commit.json。两仓代码尚未加载。preload-readonly.json是加载前只读快照：五类/未知物理/owned active/unknown/slot、私有RE queued/running均0，原PID18799=249329、18804=3176526、原argv/cwd/受控与固定view设置保存，无凭证。

等PM审阅后重新核在途/内存，只温和重载自有18804→18799，保留原argv/env/19536与共享服务。若非零/退出不正常即停，不强杀/迁移/切库。目标svquant_zxd_dev仍prepared_verified_not_loaded；当前本批允许原库只读服务加载，无DDL/重导入/行情/模型/新研究。加载后真实HTTP与PM实页源码/复制验证另记，不把ASGI替身称在线联调。
