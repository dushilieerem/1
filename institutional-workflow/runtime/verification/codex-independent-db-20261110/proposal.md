# 自有开发库迁移方案 v1（只读调研，未执行）

范围：仅服务器SVQuant-zxd/dev-zxd，本产品现有18799。目标svquant_zxd_dev，不建新PostgreSQL服务/端口，不改19536/18804/共享current，不合master、不启动研究。本方案等PM审查后才实施；目前未建库、导出数据、赋权、重编号、迁移或切服务。

## 1. 已核事实

- 已读CX-20261110-004。远端v0.5.30 annotated tag实际指9c7ae105b5cd2602165799e7abbc8fe9d77e220f；本次fetch master为2fd49cec6a3dd5c3904fada04c1632de3be7fbd3，其包含该基线。官方0036_inst_doc_extract.sql/0037_inst_doc_extract_privileges.sql在两提交逐字相同，SHA见migration-manifest-proposal.json。
- 当前连接数据库svquant_dev、role svquant；只读检查rolcreatedb/rolcreaterole/rolsuper均true。目标svquant_zxd_dev尚不存在。无需把申请新角色设为硬前置：经批准可用现有已授权身份仅创建这个隔离库；不CREATE/ALTER ROLE、不扩大既有账号权限、不修改共享DB ACL/表/历史。
- 源当前41条schema_migrations与本分支41个文件内容SHA均匹配。源0036/37是旧量化控制迁移，不能删/改其历史，也不能用公司同号文件去覆盖源记录。
- QA作者2527(test)：19机构课题/19已关联工程、36分支、29候选、28台账试验、32F0、27Agent委托、3历史封存、0iteration。29候选行本体约3498200B，非全库体积。已决定复盘3、批准资产0；3个历史sealed状态passed仅按原事实保留，不升级为新方法封存或资产。
- 另有3个未关联机构课题、无researchPlan的QA工程（含一个sample）及其2条runs，默认不迁；源记录不删。实际相关detect_runs28条。19课题范围的candidate/job/F0/sealed/iteration没有越出该工程集的project外键。
- 计量：本产品17调用均settled，known actual121103；两scope历史下限180331是同一重叠基线，不能加成360662；46缺失历史继续pending。ai_usage的93行、254187tokens是该QA账号旧共享调用口径，和新产品账本有重叠/缺项，不能相加声称总费用已核清。两套记录均原样保留。
- 现org261有其他研究员/复核员，不能据同org复制其私人项目。只选择明确QA研究员2527、数据QA负责人2973(cx_quant_data_qa_manager)、因子QA复核员3033(cx_quant_factor_qa_reviewer_067)。导入目录created_by=1046仅是历史依赖，不复制其凭证/会员/私人研究。

## 2. 空库和规范迁移链

### 创建与权限（未执行）

仅在批准后，以当前已授权连接身份创建svquant_zxd_dev、owner=现有svquant、template0、UTF8/en_US.utf8（与源一致）。这是新空库，不以svquant_dev为template、不pg_dump整库、不新建角色/赋权/开放端口。连接串仅在受保护本机环境/内存使用，不放命令行、日志、Git。若当前身份或目标存在状态与本报告不同，停止核对，不尝试超级权限扩权。

### 结构准备的必要顺序

不能直接对空库机械执行apply：0001只有SELECT1；0002引用users；0003直接ALTER invest_stocks/invest_etf。也不能执行完整app.bootstrap_schemas：其中会seed管理员/demo/机构、清理审计/通知、迁移旧因子/重归属工程、刷新行情和启动调度器。

拟采用现有DDL来源，目标库强断言后分两步：
1. 建最小空baseline：auth_store.ensure_schema、inst_store.ensure_inst_schema、detect_store.ensure_detect_schema的已审DDL；invest/schema.py DDL常量中仅invest_stocks和invest_etf的CREATE定义。绝不调用ensure_invest_schema（它会seed和refresh）或整个bootstrap。所有SQL先做无连接捕获审查，目标确认才执行。
2. 复用services.core.migrations逐文件执行规范43文件链：0001–0035 + 官方0036/37 + 本分支六迁移0042–0047。六份仅改文件名前缀，内容/表名/FK顺序/SHA不变；0038–0041缺号不编造文件或历史。候选号实施前再fetch核空闲，若被占先停报PM。
3. 必要运行辅助表仅建空结构：ai_usage、app_audit_logs、user_factor_libraries/user_library_factors/user_custom_factors、factor_dashboard_metrics及其legacy标记、re_factor_catalog_snapshot/sync_log；现总览依赖的strategy_projects/runs只建空schema，不迁策略资料、不启策略计算。来源为各已审ensure_*的DDL，排除seed/旧库导入/刷新/后台作业；user_library的UPDATE仅可能在新空表上，或直接只取CREATE/ALTER/INDEX。不是完整平台初始化。

六映射：0036_quant_factor_controls→0042；0037_quant_factor_org_controls→0043；0038_quant_ai_budget→0044；0039_quant_research_token_policy→0045；0040_quant_research_queue→0046；0041_quant_model_capacity→0047。0044依赖users/inst_orgs，0045引用0044 grant，0046创建queue并关联calls，0047放开可未知的单次容量字段。详见逐文件manifest。

### 避免影响正在服务的源库

初始化时先在runtime下准备不可变规范migration bundle，复用现有runner的MIGRATIONS_DIR配置常量指向该目录（不是新迁移框架）。不能先改live backend/migrations使源库health误报pending，也不能让普通bootstrap读到新链后写源库。
私有launcher仅在DATABASE_URL明确为svquant_zxd_dev时选择已审bundle；源环境仍原目录/原状态，lifespan=off/skip bootstrap。将来稳定/集成时再把同一内容落实为backend正式0036/37和0042–47文件；新库schema_migrations已是规范名字，无需改旧记录。若PM选择直接落正式文件，应与切换同一维护窗口，并保留原migration-layout只读回退manifest；不能忽略健康检查的目录差异。
官方0036仅在新空库doc_extract上按既有文件条件GRANT现有loader角色，0037收紧其UPDATE/DELETE；不改角色属性/共享库权限，不搬doc_extract数据。若不接受该原文件授权，应先协调，不私改正式SQL。

## 3. 精确最小数据白名单（实施时同一只读snapshot重新计数）

| 表/范围 | 只复制条件及本次计数 |
|---|---|
| users | QA2527/2973/3033三行最小登录列；1046仅失活历史引用行，见下文 |
| inst_orgs / inst_members | org261一行；仅上述3个QA在该org的原membership，不复制其他成员 |
| detect_projects | quant_factor_topics WHERE user_id=2527 AND org_id=261所引用的19工程；排除3未归属工程 |
| detect_runs | 同作者且project落上述集合，28条 |
| quant_factor_topics/branches/candidates/trials | 同user/org及上述课题/工程闭包：19/36/29/28 |
| quant_factor_f0_runs/agent_jobs/iterations | 同user/org及上述工程（F1允许project NULL）：32/27/0 |
| quant_factor_sealed_validations | 同user/org及候选/课题集合，3条；原状态/曝光/报告不动 |
| quant_factor_imported_factors | org261已授权机构导入目录331；不是其他人的项目/聊天/私有库 |
| quant_factor_controls/org_controls | 保留该org现控制两种各1行，暂停标志和paused_by2973原样，不用缺省false代替 |
| quant_ai_budget_accounts/supplements/token_policies/calls | org261两基线/1旧grant/1unlimited覆盖/17已计量调用，所有版本、未知信息、usage/原回执完整保留，不新发grant |
| quant_research_queue_jobs/slots | 仅本deployment且属于QA研究的7条completed及1空槽；保留根/父/原对象/外部回执/原控制身份，不重排旧动作 |
| quant_data_requests | user2527/org261两笔既有验收需求，handled_by2973/真实交付版本保留；不新增/转发需求 |
| ai_usage | QA3身份的原行，本次只有2527的93条；保留日期/skill/run/计数/用量，避免日调用历史清零，不与产品账本重复相加 |
| user_factor_libraries/user_library_factors/user_custom_factors | 仅2527，当前各0；不是把1046的私有库跟着导入目录搬来 |
| factor_dashboard_metrics | 仅已导入331个内置因子的yg_v1首选参考元组（与现reference_inventory同一LATERAL排序），本次331；继续标公开面板参考，绝不升级成正式研发/全库查重结果 |
| app_audit_logs | 仅上述QA3且path在/api/inst/quant/的元数据，共1352/21/15；仅id/time/user/role/action/module/resource/method/path/status/duration/request_id，排除IP/UA/自由detail和其他模块。完整科研审计仍在原候选events/archive/报告，保留原样 |

QA users最小列：id、username、password_hash（只在受保护进程内DB→DB，绝不落文件/打印）、role、status、ai_quota_daily、token_version、created_at、updated_at；不复制邮箱/头像/个人简介等。membership保留原id/org/user/role/status/时间，不改审批人或作者来过FK。
1046仅为331导入行created_by的历史引用：同原id建立不可登录的失活引用行，username明确标历史主体、role保持普通user、status=disabled、无原密码/邮箱/成员/私人项目，随机不可知密码hash；manifest保留源ID/org/原role等可核对元数据。不是冒充作者，不重写created_by。若进一步FK/JSON扫描发现白名单外主体或他人私有对象，只报告依赖并停该批，不自动扩复制范围。

机构资产/审批快照在上述own candidate.archive内逐字保留，复核人3033真实关联保留；不从其他author的candidate整行扩充。已冻结own evidence里既有引用只按原快照保留，不追溯读取他人项目/聊天。模型回执/研究文本仅DB→DB，不导出到Git或普通日志。

## 4. 复制和只读核验

- 源单连接REPEATABLE READ READ ONLY、5秒statement/有限批次；不加DDL、不禁触发器、不UPDATE源表。目标独立事务，先断言新库和白名单表无业务行，按FK依赖插入，失败只回滚新目标事务。
- 顺序：身份/org/membership→19工程→topics→parent拓扑branches→candidates/Agent jobs/F0→trials→sealed→导入/controls→grant/policy→root/parent拓扑queue→budget calls→需求/usage/缓存/审计。保留所有原PK/JSON指纹/report/run/版本/时间/授权依据；序列只在新库setval到已复制最大值。
- 不复制source schema_migrations；新库由规范43文件实执行建立记录。源旧41条仍原样，manifest记录旧36–41到新42–47的同内容映射。
- 源/目标逐表相同筛选的PK集合、数量、canonical有序行hash（auth密码只作内存相等检查、不得输出hash值）、业务状态/父子/FK/报告/审批引用、各课题真实K与剩余额度、原0cf K2、3复盘/0资产、sealed旧曝光、17调用121103及历史下限/46unknown均对照。公共参考仅yg_v1，缺指标不填0。
- 源冻结快照后再读最新PK/time/hash；若其他写入使其改变，停止切换、重做最小快照，不能宣称共享库有全局写冻结。QA操作由PM在维护窗口停下，本产品18799随后温和退出；其他服务不停。

## 5. 鉴权和公共能力的选择

现代码每次量化请求会本地读users/inst_members/org，不存在只改配置即可复用中央鉴权API的模式；且业务FK也需要本地主体。首版因此选上述最小QA副本，原角色/配额不扩，1046不获登录权；不是复制整个用户表或把同机构他人的权限/项目继承过来。
JWT_SECRET_KEY/LLM_*及现有provider选择继续在本机未跟踪backend/.env或原进程环境，已核backend/.env存在、非symlink、被Git忽略、未tracked。新目标URL和bundle引用另存runtime/.private/quant-zxd-db.env（0600/忽略），由私有launcher先加载覆盖数据库选择，再读取既有模型配置；不改共享全站/账号/模型，不将完整环境/密码放argv/日志/manifest。仍使用原模型/API、既有RE与已发布行情文件，不复制行情/原始文档。
本地QA副本在独立库内执行角色检查；它不自动反映共享库之后的成员撤销，不能称中央线上鉴权已接通。未来公共OrgScope/role/audit集成按公司契约另做，不为建库大搬代码。公开目录/固定发布元数据继续既有只读API/文件边界，cache仅白名单或重新只读拉取，不触发计算/采集。

## 6. 切换和回退（另等明确执行批准）

1. 实施前重新核master空号/目标库状态/源码和manifest/QA作用域；审查生成的DDL-only捕获、限制native连接只能写目标新库。共享svquant_dev此后只读；所有真实PG回归改为svquant_zxd_dev专用schema，脚本硬拒绝shared源库。
2. 完成空库43链与小范围复制/只读对账，不启动调度/新研究、不添加服务或端口。private启动器当前assert旧dbname必须最小修改为显式own目标，并指向规范bundle；不能仅改.env而Popen继续继承旧DATABASE_URL。
3. 切换前五类在途、已发模型/RE请求未知、owned队列/占槽/私有RE queued/running均0，PM停QA写操作。保持19536/18804不动，只温和停18799，原argv/cwd保持，明确覆写该新进程DATABASE_URL及必要bundle配置；原环境密钥不打印。
4. 新18799实际health ok/db/schema及真实current_database必须等于svquant_zxd_dev；正常量化登录/角色/原报告/研发K/复盘/费用/目录/需求做只读或新库专用验收，不发真实模型/行情。dispatcher复用原单槽，本次仅terminal jobs、空槽，不复活历史。
5. 首次新业务写入前若核验失败，可仅恢复原18799环境/原migration目录布局；源历史一直未动。新库保留待诊断，不自动删库。新库开始写入后禁止无声回旧库造成分叉：先停止本产品写操作，生成定向差异，另经批准处理；不反向自动写共享库。

## 7. 当前未验证/本轮交付

目标库还不存在，43链空库初始化、跨库COPY、QA凭证复制、target-only权限/序列/实际切换均尚未执行。现有目录服务保持原环境可访问，无真实研究。未声称公司schema/中央鉴权或好因子准入已完成。
证据：readonly-inventory.json、readonly-dependencies.json、readonly-copy-scope.json、readonly-closure.json（仅计数/角色/依赖/自身对象ID，不含其他用户正文/密钥）、migration-manifest-proposal.json、private-config-check.json。本次方案先交PM审查；不以具备superuser权限代替执行授权。
