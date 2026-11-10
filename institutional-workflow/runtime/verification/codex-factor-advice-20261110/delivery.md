# 因子研究建议：明确拒绝与未知回执的最小修复

## 真实事实和限制

r4任务0cf / run1aea8ba2已结束，实际human_advice=[]；没有证据可将那次建议记为接收或采用。历史HTTP状态/原请求未记录，不能事后断言必为409。只读看到当前分支已从H1切到修订分支、epoch仍原值；旧H1目标按代码确会拒绝。实际证据见readonly-diagnosis.json。没有回写两次真实试验、K、源码或旧建议。

已确认UI读detail、全局错误handler却返回error，因此确定拒绝原因也被隐藏成“继续确认原提交”。原服务还在运行状态检查后、仅最新run查key，无法在结束/新run后确认实际已保存回执。

## 改动

- 现有POST端点不变，无新表/迁移/平台。新增可选run_id绑定，旧客户端兼容；先按当前user/org/topic所有run查原key、逐项核message/branch/epoch/candidate/run目标后返回原回执，再检查是否能新增。相同key不同输入/目标明确conflict，不拿旧回执冒充新建议。
- 明确拒绝返回结构化saved=false/code和用户文字（全局error协议）；真实旧回执包含原run_id与当前pending/adopted/not_adopted状态。
- 正式首页使用FactorResearchAdvice原位组件，仍先按钮、后编辑器；轮询不折叠/清空。首个物理POST前保存不可变正文/key/目标；草稿按org/user/topic放当前浏览器会话存储，不含token。未知时只允许按原内容确认，结束/换run后仍可核旧回执；未知后403只表示无权确认，不伪称从未保存。
- 确定过期/结束/权限拒绝显示真实说明并保留文字；仍可提交时先显示新的H/版本，由用户原位明确确认后再创建新提交身份。不会静默把旧建议转给新分支/新run；无原生confirm。
- 成功必须匹配真实完整回执；只说已保存/待处理，实际采用依据独立返回状态。任务/账号切换隔离本地草稿，迟到响应不写当前界面。

## 验证

- advice-api.log：2个实际FastAPI路由+全局错误handler检查；鉴权身份/业务服务替身，数据库/网络卫兵，不是在线HTTP验收。
- advice-pg.log/json：5项+7子测，唯一临时svquant_dev schema/高位fixture actor，真实提交后丢响应→结束/新run原回执、同key正文/分支/epoch/run冲突、跨user/org/topic拒绝、版本拒绝无写入/明确新目标两线程同key一条、旧无run_id兼容。原connect仅允许显式fixture文件，pooled DB/外网均禁；fixture清理自身schema，不写真实业务表/账号。
- advice-components.log/resources：6实际React组件场景，fetch/DOM替身；保存后丢响应重挂载、终态确认、409/403区别、错误200不伪报成功、显式重绑定、任务/账号/迟到/轮询保持。最终2.808s/317779968B。
- advice-home-integration.log/resources：正式Home父页实际组件1项，确认所有阶段只读不启动、建议含真实目标绑定/回执。3.209s/355762176B；原测试的缺字段简化回执改为真实完整形状，没有删断言。
- advice-build.log/resources：本批一次tsc+Vite exit0，34.513s/2412384256B进程树峰值，Node heap2048MiB/单并发；只保留既有chunk警告。

命令：backend解释器 scripts/run_quant_isolated_tests.py tests/test_quant_research_advice.py；scripts/run_quant_research_advice_pg_tests.py --allow-isolated-dev；本目录run-node-bounded.py运行精确组件/父页模式与npm run build，完整参数见resources JSON。没有新模型、RE、真实建议写入、真实市场计算或重载。

## 加载与未验

前端19536是HMR，已显示新组件；18799未重载本批后端。新run_id契约与typed拒绝应在PM复核后配套加载再做真实浏览器验证；本交付没有自行重载。18804/共享服务/current未动，METHOD_FILES未改，CR102仍后置；本批不创建/更新PR或合master。原研究已经用满两次的事实不变。

浏览器真实提交/版本切换/成功采用仍待PM明确验收；本批隔离证据不冒称旧失败建议已追回或Agent已采用。
