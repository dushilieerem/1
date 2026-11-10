# CR100 显式运行配置 r2

首个新版规划4000输出全部为reasoning而截断，实耗7114已结算。该调用、failed运行、H1、K0和项目原契约完全保留；本批没有真实模型/RE调用或自动重试。

新配置bounded-factor-rd-v2-output16000-schema-r2：规划/实现/诊断各16000输出、150秒，原模型/slot/温度/一次物理HTTP路径保留。budget的实际max_output、timeout和prompt必须匹配本次冻结snapshot；候选provenance取真实run/task snapshot，纯人工执行仍标manual。

项目固定数据、范围、规则和RE源码契约，不再用BFF目录内容集合摘要作为项目兼容门槛；旧bff_code_revision原值仍留存。原摘要并不是Git HEAD，不能将从未发生的文档commit锁定当成实测故障。每次运行单独固定相关方法文件的模块加载时指纹、配置revision、角色cap/timeout/prompt版本及hash。后续磁盘WIP/文档/非方法文件不改变已加载snapshot；实际方法不兼容时旧run不能静默恢复。

沿现有start接口明确创建新run：绑定前run、当前方法hash、控制代次、操作者与原因，保持同topic/分支/K/预算。单个“使用更新研究方法继续”按钮即明确授权，无新增原生confirm；方法参数在折叠详情。诊断状态跨轮询保留，重复原因去重。完整Pydantic JSON schema进入规划/诊断prompt，空串/空数组规则明确，null/未知字段仍严格拒绝，没有隐藏repair请求。

验证仅8项+3子测、2项真实PG临时schema、1项实际组件及一次正式build，详见commands.json。PG首次失败只是“新运行/新建运行”的测试正则，已修复后两例全部后续断言完成。组件含4秒真实轮询、单一按钮、无原生确认和新run绑定；没有重复旧109项集合。Node2048MiB堆、单并发、总时限/RSS停止线保留。正式build通过（34.925秒，RSS进程树峰值2393313280字节），仅既有chunk提示。

本批无迁移或新增grant。提交后重新核五类在途0，仅以原env/argv加载自有18799；18804/19536和共享服务不动，实际PID/health见load-evidence.json。原任务0cf7441a的真实继续由PM在页面点击，不由开发者代发。

待后续混合小修：若failed后人工接手并保存源码，交回时新run须同时带既有manual_handoff和必要method_change，避免更新方法入口丢失人工绑定。当前0cf7441a无人工实现，纯自动继续不依赖此项。本批不宣称新方法已产出合格因子或完成正式封存/入库。

实际加载2026-11-10 11:45:04+08：业务e9132254578189aaa17fde1bb756ba2942be03e0，18799 PID2990133→4120193；health HTTP200且ok=true/db=ok/schema_ok=true。五类在途0、18804前后queued/running0，19536持续200，18804未重启。新运行未由开发者创建，原0cf7441a仍failed/K0等待PM按钮操作。
