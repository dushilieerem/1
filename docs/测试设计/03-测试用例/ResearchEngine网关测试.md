# ResearchEngine 网关测试用例（M5）

> 模块：RE 网关与 BFF 契约。代码：`backend/app/routers/re_gateway.py`、`services/core/re_config.py / re_http_gateway.py / lan_http.py`、`factor.py` BFF 部分。
> 关键代码事实：转发端点与超时——`POST /api/backtest/strategy` 1800s、`GET|DELETE /api/backtest/strategy/{run_id}` 60s、`GET /api/re/health` 15s、`POST /api/ai/factor-generations|strategy-generations|strategy-transcriptions|backtest-interpretations` 600s、market-data 三端点 60s；提交成功改写 `poll_url` 为本站路径并附 `Location`；RE 4xx/5xx 状态码与 body 透传、`Retry-After` 头透传；RE 不可达 → 502 `{"error":...}`；`YG_RE_BASE` 为唯一地址来源（导入期强校验）；网关仅白名单路径与方法。**RE 侧算法正确性不在测试范围**。
> 状态：全部 NOT RUN。Req 基线：PRD §6.10。测试载体：真实内网 RE + 本地 RE 桩（pytest fixture，可脚本化 4xx/5xx/慢响应/坏 JSON）。

## 覆盖概览

| 场景类别 | 用例数 | Case ID |
|---|---|---|
| 正常（契约 happy path） | 7 | 001–007 |
| 异常（错误映射） | 7 | 008–014 |
| 超时与网络 | 4 | 015–018 |
| Schema 校验（桩注入） | 4 | 019–022 |
| 网关约束 | 4 | 023–026 |

---

## 1. 健康与基础契约

### TC-RE-001 /api/re/health 代理
- **Req**: REQ-RE-002 ｜ **Pri**: P0 ｜ **Sev**: Major ｜ **Type**: Contract
- **Steps**: 1) 匿名 `GET /api/re/health`（RE 正常） 2) RE 停机
- **Expected**: 正常时透传 RE 健康对象（200）；停机 502；15s 超时生效
- **Auto**: AUTO ｜ **Env**: TEST ｜ **Status**: NOT RUN ｜ **Bug**: —

### TC-RE-002 策略回测提交契约
- **Req**: REQ-RE-001 ｜ **Pri**: P0 ｜ **Sev**: Critical ｜ **Type**: Contract
- **Steps**: `POST /api/backtest/strategy`（合法 strategy_id + 日期）→ 校验响应
- **Expected**: run_id 存在；`poll_url` 被改写为本站 `/api/backtest/strategy/{run_id}`；`Location` 头存在（异步形态）；请求体原样到达 RE 桩（字段逐项比对）
- **Auto**: AUTO ｜ **Env**: TEST ｜ **Status**: NOT RUN ｜ **Bug**: —

### TC-RE-003 策略回测轮询与取消契约
- **Req**: REQ-RE-001 ｜ **Pri**: P0 ｜ **Sev**: Critical ｜ **Type**: Contract
- **Steps**: 对桩依次返回 running / completed / failed 状态 → `GET .../{run_id}`；再 `DELETE`
- **Expected**: 状态与结果字段透传一致（含失败原因）；DELETE 转发成功
- **Auto**: AUTO ｜ **Env**: TEST ｜ **Status**: NOT RUN ｜ **Bug**: —

### TC-RE-004 AI 生成/转写代理四端点契约
- **Req**: REQ-RE-003 ｜ **Pri**: P1 ｜ **Sev**: Major ｜ **Type**: Contract
- **Steps**: `POST /api/ai/factor-generations`、`strategy-generations`、`strategy-transcriptions`、`backtest-interpretations`（合法 body，RE 桩）
- **Expected**: 200 透传生成结果；请求 schema 与 RE 契约一致；600s 超时配置生效（桩延迟验证）
- **Auto**: AUTO ｜ **Env**: TEST ｜ **Status**: NOT RUN ｜ **Bug**: —

### TC-RE-005 行情三端点契约
- **Req**: REQ-RE-003 ｜ **Pri**: P1 ｜ **Sev**: Major ｜ **Type**: Contract
- **Steps**: symbols / indices / constituents 对桩请求
- **Expected**: 方法与路径正确；响应字段与契约一致（Required 字段齐全、类型正确）
- **Auto**: AUTO ｜ **Env**: TEST ｜ **Status**: NOT RUN ｜ **Bug**: —

### TC-RE-006 BFF 目录与试算契约
- **Req**: REQ-RE-001 ｜ **Pri**: P1 ｜ **Sev**: Major ｜ **Type**: Contract
- **Steps**: `GET /api/factor/re-catalog?fresh=1`、`POST /api/factor/custom/trial` 对桩
- **Expected**: BFF 发往 RE 的请求 schema 正确；返回映射正确（目录→快照结构；试算 metrics/error 判定）
- **Auto**: AUTO ｜ **Env**: TEST ｜ **Status**: NOT RUN ｜ **Bug**: —

### TC-RE-007 /yg-api 直连代理路径行为记录
- **Req**: REQ-NFR-001（DCM-01）｜ **Pri**: P1 ｜ **Sev**: Major ｜ **Type**: Contract
- **Steps**: 经前端 dev server `GET/POST /yg-api/*`（detectStore 实际使用的路径）
- **Expected**: 记录当前行为（代理至 YG_RE_BASE）；与 PRD"前端不直连"冲突点留档，待架构确认（不判 FAIL）
- **Auto**: AUTO ｜ **Env**: DEV ｜ **Status**: NOT RUN ｜ **Bug**: —

## 2. 错误映射

### TC-RE-008 RE 4xx 透传
- **Req**: REQ-RE-004 ｜ **Pri**: P0 ｜ **Sev**: Major ｜ **Type**: Contract
- **Steps**: 桩返回 400/401/404（含错误 body）
- **Expected**: SVQuant 原样透传状态码与 body（业务语义保留）；不吞错误改 200
- **Auto**: AUTO ｜ **Env**: TEST ｜ **Status**: NOT RUN ｜ **Bug**: —

### TC-RE-009 RE 5xx 透传与 502
- **Req**: REQ-RE-004 ｜ **Pri**: P0 ｜ **Sev**: Major ｜ **Type**: Contract
- **Steps**: 桩返回 500/503；桩进程终止（连接拒绝）
- **Expected**: 5xx 透传；连接失败/拒绳 → 502 `{"error":...}` 文案明确
- **Auto**: AUTO ｜ **Env**: TEST ｜ **Status**: NOT RUN ｜ **Bug**: —

### TC-RE-010 Retry-After 头透传
- **Req**: REQ-RE-004 ｜ **Pri**: P2 ｜ **Sev**: Minor ｜ **Type**: Contract
- **Steps**: 桩返回 429 + `Retry-After: 30`
- **Expected**: 状态码与头透传至客户端
- **Auto**: AUTO ｜ **Env**: TEST ｜ **Status**: NOT RUN ｜ **Bug**: —

### TC-RE-011 不可达时全研究入口一致性
- **Req**: REQ-RE-005 ｜ **Pri**: P0 ｜ **Sev**: Critical ｜ **Type**: Integration
- **Steps**: RE 停机后逐一调用：回测提交/轮询、目录 fresh、试算、daily、AI 生成代理、market-data
- **Expected**: 全部明确失败（502/400），**无一返回伪造成功数据**（PRD §6.10 验收标准）
- **Auto**: AUTO ｜ **Env**: TEST ｜ **Status**: NOT RUN ｜ **Bug**: —

## 3. 超时与网络

### TC-RE-012 提交超时（1800s 配置存在性验证）
- **Req**: REQ-RE-004 ｜ **Pri**: P2 ｜ **Sev**: Minor ｜ **Type**: Integration
- **Steps**: 桩在 65s 后响应的轮询请求；核对代码/配置中 1800s/600s/60s/15s 超时表
- **Expected**: 轮询类 60s 超时 → 502；长任务不被 60s 误杀（1800s 仅提交）；超时映射表与实现一致
- **Auto**: MIXED ｜ **Env**: TEST ｜ **Status**: NOT RUN ｜ **Bug**: —

### TC-RE-013 RE 慢响应期间用户侧体验
- **Req**: REQ-RE-004 ｜ **Pri**: P1 ｜ **Sev**: Major ｜ **Type**: E2E
- **Steps**: 桩延迟 30s → 前端提交回测
- **Expected**: 前端不假死（异步轮询语义）；提示进行中；重复提交行为符合 TC-STRATEGY-022
- **Auto**: MANUAL ｜ **Env**: TEST ｜ **Status**: NOT RUN ｜ **Bug**: —

### TC-RE-014 网络中断恢复
- **Req**: REQ-RE-004 ｜ **Pri**: P2 ｜ **Sev**: Minor ｜ **Type**: Integration
- **Steps**: 轮询中途断桩 10s 再恢复
- **Expected**: 中断期间明确失败，恢复后可继续轮询至终态；不产生僵尸状态
- **Auto**: AUTO ｜ **Env**: TEST ｜ **Status**: NOT RUN ｜ **Bug**: —

## 4. Schema 校验（RE 桩注入异常响应）

### TC-RE-015 RE 返回非法 JSON
- **Req**: REQ-RE-004 ｜ **Pri**: P1 ｜ **Sev**: Major ｜ **Type**: Contract
- **Steps**: 桩返回截断/非 JSON body（200 状态）
- **Expected**: SVQuant 报错（502/400 明确错误），不把坏数据当成功透传
- **Auto**: AUTO ｜ **Env**: TEST ｜ **Status**: NOT RUN ｜ **Bug**: —

### TC-RE-016 RE 缺少必需字段
- **Req**: REQ-RE-004 ｜ **Pri**: P1 ｜ **Sev**: Major ｜ **Type**: Contract
- **Steps**: 桩回测结果缺 `run_id`/状态字段
- **Expected**: 提交链路明确失败或标记任务异常；不得生成假 job/假结果
- **Auto**: AUTO ｜ **Env**: TEST ｜ **Status**: NOT RUN ｜ **Bug**: —

### TC-RE-017 RE 返回未知字段
- **Req**: REQ-RE-006 ｜ **Pri**: P2 ｜ **Sev**: Minor ｜ **Type**: Contract
- **Steps**: 桩在响应中附加新字段（模拟 RE 升级）
- **Expected**: 默认容忍透传（向前兼容）；不崩溃；记录行为作为锁步兼容基线
- **Auto**: AUTO ｜ **Env**: TEST ｜ **Status**: NOT RUN ｜ **Bug**: —

### TC-RE-018 契约版本兼容（锁步验证）
- **Req**: REQ-RE-006 ｜ **Pri**: P1 ｜ **Sev**: Major ｜ **Type**: Contract
- **Steps**: 用 RE 契约测试套件（RE 仓库）+ SVQuant 契约脚本对同一版本组合跑通；再对"新 RE + 旧 SVQuant"组合跑关键端点
- **Expected**: 配套版本全绿；不兼容组合在被测端点上**显式失败**（阻断发布），失败信息指向不兼容字段
- **Auto**: MIXED ｜ **Env**: TEST ｜ **Status**: NOT RUN ｜ **Bug**: —

## 5. 网关约束

### TC-RE-019 地址唯一来源
- **Req**: REQ-NFR-001 ｜ **Pri**: P0 ｜ **Sev**: Critical ｜ **Type**: Integration
- **Steps**: 1) 删除 `YG_RE_BASE` 启动后端 2) 设非法值（非 http URL、无主机名）启动
- **Expected**: 启动即失败（RuntimeError，导入期校验）；错误信息指向 backend/.env
- **Auto**: AUTO ｜ **Env**: TEST ｜ **Status**: NOT RUN ｜ **Bug**: —

### TC-RE-020 白名单路径与方法
- **Req**: REQ-RE-001 ｜ **Pri**: P0 ｜ **Sev**: Critical ｜ **Type**: Security
- **Steps**: 对网关未登记路径/方法发请求（如 `PUT /api/backtest/strategy`、`POST /api/re/health`、伪造深层路径）
- **Expected**: 404/405，**不存在任意 URL 代理能力**（不能借网关访问 RE 任意端点）
- **Auto**: AUTO ｜ **Env**: TEST ｜ **Status**: NOT RUN ｜ **Bug**: —

### TC-RE-021 RE 地址不泄漏给浏览器
- **Req**: REQ-NFR-001 ｜ **Pri**: P0 ｜ **Sev**: Critical ｜ **Type**: Security
- **Steps**: 扫描前端构建产物（`npm run build` 产物）与 API 响应中是否出现 `YG_RE_BASE` 值/内网 RE 主机名
- **Expected**: 业务 API 响应与前端产物无 RE 地址（`/yg-api` dev 代理除外，见 DCM-01 留档）
- **Auto**: AUTO ｜ **Env**: TEST ｜ **Status**: NOT RUN ｜ **Bug**: —

### TC-RE-022 契约冒烟脚本回归
- **Req**: REQ-RE-006 ｜ **Pri**: P1 ｜ **Sev**: Major ｜ **Type**: API
- **Steps**: `cd backend && python scripts/contract/run_all.py`（CONTRACT_BASE 指向 TEST）
- **Expected**: `ALL CONTRACTS OK`（注意：test_modules 允许 re-catalog 502，脚本通过≠RE 集成可用——报告需注明）
- **Auto**: AUTO ｜ **Env**: TEST ｜ **Status**: NOT RUN ｜ **Bug**: —

---

## 统计

TC-RE 共 **22** 条：P0×13、P1×7、P2×2；AUTO 19 / MIXED 2 / MANUAL 1。状态全部 NOT RUN。
