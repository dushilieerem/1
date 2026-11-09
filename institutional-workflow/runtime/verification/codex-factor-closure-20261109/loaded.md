# 本批开发环境加载与在线只读验收

- 2026-11-09 17:28:28（Asia/Shanghai）仅重载18799：PID1919483 → 3521847；BFF加载业务提交 b7172bd4b261c9a3b056c608d8f4655c705fc51f，启动argv/cwd与原完整环境保持，隔离查重RE18804保留，凭证未输出或保存到证据。旧process记录PID已过期，因此以实际监听进程及cwd/argv核对为准，再更新本产品process记录。
- 重载前五类在途再次确认全0：F0、候选检验、封存、Agent jobs、自动迭代。无真实研究/模型/回测/审批执行；19536和其他服务未重启。
- BFF `/api/health`、前端19536 `/`、隔离RE18804已有 `/api/health` 实际HTTP均200。初探`/health`404只说明路径不存在，未当健康通过。未验证计算执行能力。
- `load-evidence.json` 记录PID/HEAD/时间/计数及端口；`online-readonly-http.json` 是对已加载BFF的真实HTTP，无鉴权或数据依赖替身。前一批 `abc-api-tests.log` 则是ASGI内存TestClient，二者不能混称。
- 使用已登记测试身份；登录是唯一POST，之后均GET：研究员权限write、复核员权限review；资产列表200且当前0条；研究员本人复核详情200，作者只读、不能领取/决定、无events；复核员队列6条和详情200，未领取未签署。匿名401、篡改机构声明401、不存在资产/审批404。
- 当前没有既有异机构审批或登记资产样本，未创建假准入资产；因此有效异机构对象隔离、真实批准后机构资产展示/复用仍未在线验收。篡改token401不能替代有效异机构对象验证。
- 注册凭据说明在runtime/coordination/dev-test-accounts.md，受保护凭据文件仅由进程读取，不纳入Git、不输出。证据脚本 `online_readonly_check.py` 不含任何凭据值。
- PM指出的两处旧关闭口径仅修正文案：QuantWorkspacePages.tsx研究员复核说明、FactorWorkflowPage.tsx人工F6产品说明。独立复核页说明已是“研究用途决定”。`copy-http-evidence.json`核对19536实际模块返回新文字/旧文字消失；前端即时HMR，无BFF代码增量、无需再次重启。仅文案变更未重做全量构建或测试，沿用b7172bd此前通过的构建/隔离验证；浏览器由PM独立验收。
- D、数据业务和真实新发现审批闭环继续未执行。封存提交响应丢失与历史版本新计算依赖仍按delivery.md列明。
