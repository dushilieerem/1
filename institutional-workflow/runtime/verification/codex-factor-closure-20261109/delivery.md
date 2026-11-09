# 因子 A/B/C 可审批次（2026-11-09）

基线 c2eb6b036e9231cf9c0ed5ab7c0a9b6d0f0dc6de。仅因子业务、必要接口、隔离测试。D 未执行；没有模型调用、真实回测或真实审批决定。

## 本批行为

- 启动/resume 共用 actor→topic 锁顺序；F0 queued 原子领取，恢复与手工重试共用候选计算租约；保留既有事件和总轮次。
- 原运行ID/已保存结果优先恢复，不盲目重复提交；提交响应未知保留预算和身份。取消优先，已知 failed/cancelled 保存明确终态、退出未知恢复/预留。数值已完成但台账未落的候选持续占预算并阻止批准；台账与批准协调锁。
- 历史固定 view 仅允许可核对原运行身份的结果查询恢复；不会换 current 数据补算。没有身份则保留记录并提示人工处理。
- CR-095 新动作 approve_research_and_register，与旧反馈分开；领取者/独立复核权限/机构隔离、当前K与实际数值/封存/正式查重证据重验。一次事务写审批、不可变 archive.research_asset 和事件。重复批准同一资产；已登记版本不可重开审批。
- qfa 为新发现资产，qfr 为既有因子复现验证记录；复现记录附原因子，不能冒充新发现。机构资产接口白名单提供冻结可执行定义和登记时授权报告摘要，复用保留来源ID/版本/指纹，不继承通过状态，不开放作者项目/聊天/全台账。
- 待审批沿主卡/证据入口/说明/底部决定，领取与已复核状态明确；原生dialog键盘/关闭回焦，批准需分类与确认。独立意见响应后重读候选。因子库标题与口径折叠作本次限定清理；完整库布局对齐属于后批。
- 策略审批段与基线逐字一致；没有数据业务/PM原型改动。

## 证据与命令

所有命令工作区为本仓库。后端解释器 /home/dev01/project/SVQuant/.ci/venv/bin/python；Node24.20.0。以下日志包含精确命令和退出码。

|证据|结果|边界|
|---|---|---|
|abc-backend-tests.log|178通过|12个因子模块 unittest；实际db._new_conn设拒绝卫兵，0连接尝试/0池占用；网络/模型/业务存储替身|
|abc-api-tests.log|28通过|pytest tests/test_quant_factor_routes.py -q -p no:cacheprovider；FastAPI TestClient/ASGI内存路由，require_quant_user、_quant_uid与业务数据服务替身；实际角色依赖、输入校验和错误映射；不是在线HTTP验证|
|pg-transaction-tests.log|6通过|QUANT_FACTOR_PG_INTEGRATION=1；显式svquant_dev、唯一schema/高位唯一actor与org、5秒statement/2秒lock超时、自有fixture清理。真实审批事务/回滚/并发幂等/锁、未落账审批阻塞和预算占位；worker内部计算替身|
|abc-frontend-regressions.log|48通过|node --import tsx --test --test-concurrency=1；实际页面组件/浏览器DOM替身、fetch替身，含新增5项审批/资产复用用例|
|abc-component-tests.log|5通过|新增审批/资产组件定向日志，包含在48项中，不重复相加|
|abc-build.log|通过|npm run build；tsc与Vite构建，普通大chunk提示保留；不能替代视觉验收|
|connection-warning-diagnostic.log|已定位并清理测试缺口|旧测试遗漏_context/control_status/封存读取替身，曾只读借用池连接并归还；退出空闲池产生ResourceWarning。补齐隔离替身后178项无真实连接尝试/无ResourceWarning，不改共享池|

## 加载状态及方案

19536 返回 Vite，前端源代码已即时热更。18799 仍是 PID1919483 / 原 start_quant_bff.py 进程，未重载本批后端；新资产/批准接口在旧BFF上尚不可用，不能称新页面完全未变化或在线链路已通过。18804/共享服务不改。

建议 PM 读提交及证据确认后：只读检查 quant_factor_f0_runs、quant_factor_candidates、quant_factor_sealed_validations、quant_factor_agent_jobs、quant_factor_iterations 的 queued/running 在途总数；有在途则不重启。仅使用现有18799启动器及原环境（保留隔离RE18804设置及凭证，不输出凭证）重启18799；19536不停。无需数据库迁移。加载后用普通研究员/独立复核身份检查新路由及页面，实际批准由PM执行。不擅停现有服务，不在本次提交后自行执行D。

## 尚未通过的验收/依赖

- 没有真实新建→模型迭代→正式全库查重→封存→独立批准→库复用的在线闭环验收；隔离fixture不是正式因子准入。
- 封存提交身份持久化/提交响应丢失恢复仍依赖 services/quant_factor/sealed.py→隔离RE封存接口的任务身份契约，本批未扩RE实现；不能称全部异常恢复闭环。
- 历史view新计算仍不支持；只有已知原run且数据/源码/规格身份可核对才安全恢复结果。身份缺失明确阻塞。
- D40证券诊断尚未执行，准确样本/参考/60有效交易日与预热、RSS硬限及停止线/调用时长上限仍待方案批准；诊断永不等同正式全库新颖性通过。
- 本批新审批/资产页面尚待配套BFF加载后的真实浏览器与身份验收；没有截图文件，不虚构截图路径。
- 库分类侧栏/分页与旧详情文案、创建表单密度等后批UI债务不包含于本次验收。

## 精确业务/测试文件

- `backend/app/routers/quant_factor_workflow.py`
- `backend/services/quant_factor/asset_context.py`
- `backend/services/quant_factor/decision_engine.py`
- `backend/services/quant_factor/f0.py`
- `backend/services/quant_factor/f5.py`
- `backend/services/quant_factor/ledger.py`
- `backend/services/quant_factor/novelty.py`
- `backend/services/quant_factor/policy.py`
- `backend/services/quant_factor/review.py`
- `backend/services/quant_factor/service.py`
- `backend/tests/test_quant_factor_f0.py`
- `backend/tests/test_quant_factor_f5.py`
- `backend/tests/test_quant_factor_jobs.py`
- `backend/tests/test_quant_factor_review.py`
- `backend/tests/test_quant_factor_routes.py`
- `frontend/package.json`
- `frontend/src/lib/detectStore.ts`
- `frontend/src/lib/researchClient.ts`
- `frontend/src/pages/institutional-workflow/FactorEvidencePanel.tsx`
- `frontend/src/pages/institutional-workflow/FactorReviewPage.tsx`
- `frontend/src/pages/institutional-workflow/FactorReviewRequest.tsx`
- `frontend/src/pages/institutional-workflow/QuantFactorLibraryPage.tsx`
- `frontend/src/pages/institutional-workflow/quantWorkspace.css`
- `backend/services/quant_factor/assets.py`
- `backend/services/quant_factor/provenance.py`
- `backend/tests/test_quant_factor_assets.py`
- `backend/tests/test_quant_factor_assets_pg.py`
- `backend/tests/test_quant_factor_recovery.py`
- `frontend/src/lib/factorResearchAssets.ts`
- `frontend/src/pages/institutional-workflow/FactorResearchAssetDetails.tsx`
- `frontend/tests/factorAdmissionFlow.test.tsx`
