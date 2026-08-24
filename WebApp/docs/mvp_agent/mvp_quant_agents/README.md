# AI 量化投研 · MVP 多 Agent 系统（外部 Token 版）

> 大脑 Boss + 5 个主 Agent（数据 / 因子 / 策略 / 交易 / 风控），每个主 Agent 下挂分支 Agent；
> 通过消息总线跨部门通信，最终向 Boss 汇报「是否执行」，由 Boss 裁决 Gate 决定交易 Agent 是否下单。
> MVP 阶段先用外部 Token 跑通全链路，**L3（因子公式/仓位/PnL/权重/原始数据）一律不出网**。

## 目录结构
```
mvp_quant_agents/
├── config.yaml            # LLM 端点 / Key(建议环境变量) / mock 开关 / 合规开关 / 交易参数
├── core/
│   ├── llm_client.py      # OpenAI 兼容客户端；出站前过 L3 闸；mock 模式零成本
│   ├── message_bus.py     # 跨部门消息总线 + 留痕(trace_id)
│   ├── compliance.py      # 敏感度分类 + 脱敏 + 路由(L3 硬拦截)
│   └── base_agent.py      # Agent 基类(send/act/think/call_tool/handle)
├── agents/
│   ├── boss.py            # 大脑：编排 + 执行裁决(风控否决不可 override)
│   ├── data_agent.py      # 数据：采集/因子库/因子计算
│   ├── factor_agent.py    # 因子：评价/挖掘/组合
│   ├── strategy_agent.py  # 策略：生成/回测/评价/组合切换(含配对交易)
│   ├── risk_agent.py      # 风控：实盘分析(否决权)/实盘风控
│   └── trading_agent.py   # 交易：模拟/实盘下单
├── tools/mock_tools.py    # 数据/因子/回测/风控/交易 的 MVP 桩工具
├── main.py                # 跑一次完整研究循环
└── README.md
```

## 快速开始
```bash
cd mvp_quant_agents
pip install pyyaml openai        # openai 仅实跑需要
python main.py                   # 默认 mock=true，无需 Key 即可看全链路
```

## 切到真实外部 Token
1. `config.yaml` 把 `llm.mock` 改为 `false`，填 `base_url`（**仅国内合规零留存端点**）、`model`；
2. 设置环境变量 `export QUANT_LLM_API_KEY=sk-xxx`（勿明文落盘）；
3. 再跑 `python main.py`。所有出站内容会自动过 `compliance.route`，命中 L3 直接抛错拦截。

## 执行裁决流程
```
Boss 发起 → 数据 → 因子 → 策略(向因子 request 专用因子) → 风控(approve/reject)
        → Boss.decide()：风控 approve 且策略达标 → execute 下达交易；否则 block/revise
```
风控 Agent 对执行拥有**一票否决权**：`verdict=reject` 时 Boss 不得 override 直接执行。

## 西蒙斯式配对交易
由「策略 Agent · 策略生成」分支产出（`theme="pair_trading"`：协整对 + z-score 入场/出场），
经回测/评价进入「组合·风格切换」与其它策略做风险预算；风控对价差失效、单边暴露做实盘监控。

## 真实研究链路（数据接入层 + 四因子 + IC/IR 组合）
`research/` 是一条可独立运行、也可被 Agent 调用的真实研究链路：
**Tushare 接入 → 计算 动量/PE/PB/ROE 四因子 → 入库(SQLite) → 算 IC/IR → 按 IC/IR 加权合成 → 回测 → 绩效分析**。

```
mvp_quant_agents/
├── research/
│   ├── data_source.py   # Tushare 取数；无 token 时用带因子结构的合成数据兜底
│   ├── factors.py       # momentum / pe / pb / roe 计算
│   ├── db.py            # SQLite 落库(prices/fundamentals/factors/eval/strategy)
│   ├── evaluation.py    # 截面 rank IC / IR / t 值 / 胜率 / IC 衰减 / 取向 / 合成权重
│   ├── strategy.py      # IC/IR 加权合成 + 多空/多头组合向量化回测 + 绩效分析
│   ├── run_pipeline.py  # 端到端运行（python research/run_pipeline.py）
│   └── quant.db         # 运行后生成的数据库
└── tools/research_tools.py  # Agent 阶段函数(ingest_and_compute / evaluate / build_strategy)
```

因子定义：动量=momentum_window 日收益(默认20)；PE/PB=日频估值(取反取向)；ROE=质量因子(正向)。
评价：在每个月末调仓日算因子截面值 vs 未来 hold_days 收益率的 Spearman rank IC，多期得 IR；
按 `sign(IC)` 取向、按 `|IR|` 归一化得合成权重（Top3 模式取 |IR| 最大的 3 个）。
回测：月频调仓、持有 hold_days，取 composite 前后 top_quantile 做多/空，等权，扣单边 cost_bps 成本。

运行方式：
```bash
python research/run_pipeline.py                 # 端到端（默认按 config.yaml）
python research/run_pipeline.py --source synthetic --size 50
```
接入真实 Tushare：在 `config.yaml` 配 `tushare.token`（或环境变量 `TUSHARE_TOKEN`）与 `tushare.index`（如 000300.SH）；
留空则自动用合成数据演示。把 `research.enabled` 设为 `true`，`python main.py` 即让数据/因子/策略三个 Agent 走真实链路。

> 注意：合成数据用来验证工程链路与指标口径，IC/IR 量级已调到接近真实多因子选股的可信区间，
> 但**不代表真实 alpha**；接真实 Tushare 后请以实盘口径为准。

## 后续演进（与已购 GPU 衔接）
H100 集群就位后，按 Router 把高频/重复/含 alpha 的调用切到本地自训模型（Qwen/DeepSeek），
把"外部 Token"收敛为自有 GPU 上的本地推理；L3 全程内网闭环。详见架构设计文档。
