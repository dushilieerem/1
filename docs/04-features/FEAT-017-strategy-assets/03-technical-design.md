# 策略资产目录与版本化持久化：技术设计

## 模块边界

`Strategy/` 是项目资产目录，源码和索引由 Git 管理；`ResearchEngine.strategy_catalog` 只读取、校验和解析资产；`researchengine.api` 负责枚举与将解析后的源码交给既有回测编排；`QuantCore` 不感知文件路径或资产元数据。

```text
Strategy/libraries/index.yaml + *.py
              ↓
       StrategyCatalog（不执行源码）
              ↓
 GET /api/strategies  或  POST /api/backtest/strategy
                                      ↓
                            既有向量化回测流程
```

## 目录和索引

```text
Strategy/libraries/
├── index.yaml
├── weekly_rotation_v1.py
└── weekly_rotation_v2.py
```

版本映射位于单一 `index.yaml`：策略 ID 映射到业务策略类型、执行模式、当前版本、标签和每个版本的文件/入口。读取时以源码实际字节计算 SHA-256，不相信索引中人工维护的哈希。

## 接口

- `GET /api/strategies`：只返回索引元数据，不执行源码。
- `POST /api/backtest/strategy`：保留 `strategy_code`；新增互斥的 `strategy_id` 和可选 `strategy_version`。资产策略运行成功后，在 `meta` 返回 ID、解析版本和 `code_hash`。

## 兼容与回滚

原有内联 `strategy_code` 仍受支持。发生目录问题时，设置 `SVQUANT_STRATEGY_DIR` 指向可用库；需要回滚时停止使用 `strategy_id` 请求即可，既有回测路径不受影响。

## 测试策略

单元测试覆盖索引解析、默认版本、缺失版本和路径限制；API 测试覆盖列表、资产策略回测、内联回测回归和事件策略拒绝。

## 风险

当前策略仍在可信开发环境内执行，不因“保存在文件中”而获得沙箱能力；生产执行隔离由 FEAT-006 的事件策略/安全设计另行解决。
