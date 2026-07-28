# SVQuant 因子持久化设计

> 文档版本：v1.1
> 最后更新：2026-07-17
> 适用范围：公共因子库（PublicAlphaLibrary）

> 因子名称、公式要点、参数、依赖字段和兼容范围见[《SVQuant 内置因子库总览》](../因子库总览.md)。

## 1. 设计原则

因子是**可执行代码**，不是数据：代码保存在 `.py` 文件，名称、描述和参数等元数据由
`index.yaml` 管理；前端负责因子库展示与管理。ResearchEngine 对内置因子加载完整库，对用户自定义因子接收单个函数体并执行回测。

## 2. 存储结构

```text
Factor/libraries/
├── index.yaml                 # 因子索引与元数据
├── momentum_lib.py            # 因子库
├── value_lib.py
├── technical_lib.py
├── volatility_lib.py
├── trading_lib.py
├── alpha_library.py
├── technical_indicators.py # 技术指标（第一批）
├── risk_indicators.py      # 风险指标（第一批）
└── emotion_indicators.py   # 情绪指标
```

每个 `.py` 文件包含一个 `FactorLibrary` 子类，每个公开方法为一个因子：

```python
from quantcore import FactorLibrary

class MomentumLib(FactorLibrary):
    author = "SVQuant"

    def momentum_5d(self):
        """5 日动量因子。"""
        return self.close.pct_change(5)
```

`index.yaml` 保存前端展示所需的元数据：

```yaml
libraries:
  momentum_lib:
    file: momentum_lib.py
    class: MomentumLib
    factors:
      - name: momentum_5d
        description: "5日动量"
        params: { window: 5 }
```

## 3. 因子管理

- 新增：在对应 `.py` 文件新增方法，并在 `index.yaml` 增加元数据。
- 修改：直接修改方法体；仅当名称、描述或参数变化时同步修改 `index.yaml`。
- 删除：同时删除方法和对应的 `index.yaml` 条目。
- 重命名：同步修改方法名和 `index.yaml` 中的 `name`。

## 4. 与 ResearchEngine 的关系

```text
内置因子：前端读取 index.yaml，传 library_name + factor_name
        ↓
ResearchEngine 加载完整因子库并回测

用户自定义因子：前端传单个函数体 + factor_name
        ↓
ResearchEngine 生成临时 FactorLibrary 并回测
```

当前 API 的两种来源必须二选一：内置因子传 `library_name` 与 `factor_name`，由服务端加载完整库；用户自定义因子传 `factor_code` 与 `factor_name`，其中 `factor_code` 只接收**单个因子函数体**，服务端自动补全 `FactorLibrary` 类定义。

## 5. API 接口文档

因子回测 API 已独立维护在 [因子回测 API 文档](FACTOR-BACKTEST-API.md)。

系统级 ResearchEngine API 文档见
[FEAT-002 API 文档](../../docs/04-features/FEAT-002-research-engine/06-research-api.md)。
