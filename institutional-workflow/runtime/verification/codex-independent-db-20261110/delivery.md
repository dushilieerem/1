# 独立开发库准备交付（未切服务）

仅创建并准备 svquant_zxd_dev。原18799仍连接原源库，19536/18804均未重启。源连接全程READ ONLY，没有修改共享表/schema_migrations/角色/共享权限。

实际结果：53条捕获DDL、43规范迁移、55表；官方0036/37与最新origin/master字节相同。六份量化迁移仅在新库bundle编号0042–0047，原库/代码历史不改。29白名单数据表共 2405 行，另1046失活引用1行，无其凭证/会员/私人研究。QA三身份原权限/凭证仅内存DB→DB复制，无秘密日志/导出。

19任务/36分支/29候选/28试验/32F0/27委托/3历史封存、331导入因子/331原yg_v1参考缓存/2需求保留。逐表选定列有序SHA一致，独立只读后验再次一致；19任务原台账纯函数K一致，0cf仍K2/max2/剩0，3复盘已决定/0资产，旧封存不升级。报告/事件/审批/模型回执完整留数据库，不输出正文。

17调用121103实际Tokens、旧100m grant、unlimited覆盖、两scope重叠历史下限180331及46缺项全部保留。ai_usage93行254187属不同且重叠口径，不相加。源核心及schema历史无变化；审计按快照时间截断，仅安全元数据，之后追加 0 条另记、不覆盖。原生FK启用，单目标事务复制，序列仅新库设置；其他策略/行情/文档表空白。

本机 runtime/.private/quant-zxd-db.env 已准备0600/gitignored，未被服务加载。原模型/JWT继续既有未跟踪设置，秘密不进Git。

## 命令和证据

均用 /home/dev01/project/SVQuant/.ci/venv/bin/python，脚本位于本证据目录：
- initialize_database.py --create-approved-isolated-database：真实初始化成功。目标已存在即停，不能重跑/drop/recreate。
- copy_database.py --copy-approved-qa-history：真实白名单事务复制成功，非空目标/白名单变化即停，不能覆盖新记录。
- verify_prepared_database.py：独立READ ONLY读回成功，可重验；源变化即报差异。
- test_operator_guards.py：5项无网络边界回归通过，覆盖源写拒绝、未知DB、已存在目标、写表/目标校验和缺失祖先。

schema-capture.json/captured-scaffold.sql为执行前DDL；initialization-evidence.json为43链；copy-verification.json为源/目标hash；post-copy-readonly-verification.json为K/费用/角色后验；latest-master-migration-check.json为官方字节；operator-guards.log和target-private-config-check.json无秘密。

## 尚未切换

等PM结束浏览器验收/停QA写且确认五类在途、未知物理、owned队列/占槽、RE队列均0，先核源相对本快照变化。仅本产品launcher需显式选目标env、校验dbname、migration runner选规范43bundle；当前launcher仍断言旧dbname，未偷偷切库。未来只温和重载18799，原argv/cwd、19536/18804保持；dispatcher前核terminal/空槽，不重放历史。health需ok/db/schema和实际current_database等于目标，再核QA登录/原报告/用量。

新库首写前可按原env回退18799；首写后不得无声回旧库，须停本产品写并对账。源历史不删，新库失败不自动清空。切库登录/在线各路由尚未验证；没有新研究/模型/行情/因子准入。
