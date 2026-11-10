# 模型输出配置核验
2026-11-10，PM只读核对。

- 实际请求证据：第一次规划显式max_tokens=4000，provider记录completion与reasoning均4000，finish_reason=length，无可用方案。见codex-factor-cr100-method-20261110/live-0cf7441a.json。
- 一手文档：[DeepSeek Thinking Mode](https://api-docs.deepseek.com/guides/thinking_mode/)、[Chat Completions](https://api-docs.deepseek.com/api/create-chat-completion/)。文档描述默认开启思考、默认high，输出限额同时涵盖思考与最终回答；可明确配置思考强度。文档能力不等于已验证本项目中间服务所有参数都透传。
- 本次工程选择：新配置明确三个职责各16000输出/150秒，保持原模型和现有思考方式。不是隐藏重试，也不据此断言研究质量提升。
- 若后续仍截断或超时，先读取实际回执再比较角色化配置；不得偷偷降档或自动增加额度，变更记录为新的运行方法revision，保留原失败与K。

## 后续用户授权覆盖
用户随后明确取消本产品累计Token上限，并允许用同时研究任务数控制负载。上面的16000/150秒为已加载R2的事实，不是长期产品要求；当前CR101要求核实服务单次容量、取消过低客户端限额并保留实际用量/技术接续，详见《因子工厂V5-持续研究与运行队列》。尚未实施，不更换模型或改共享全局配置。
