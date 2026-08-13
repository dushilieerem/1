# SVQuant 因子持久化设计

> 文档版本：v1.1
> 最后更新：2026-07-17
> 适用范围：公共因子库（PublicAlphaLibrary）

> 因子名称、公式要点、参数、依赖字段和兼容范围见[《SVQuant 内置因子库总览》](../因子库总览.md)；该文档由研究员手工维护。

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
├── worldquant_alpha101.py # WorldQuant Alpha 101（alpha001-alpha101）
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

`index.yaml` 保存前端展示所需的元数据，也是 ResearchEngine API 的唯一内置库注册来源；API 不再维护第二份库名白名单：

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

- 因子实现的唯一事实来源是对应 `.py` 文件中的公开方法；不要手工维护逐因子清单。
- 新增、修改、删除或重命名因子后，只修改 `.py` 文件并运行下方的 `sync` 命令。
- `index.yaml` 中的库级标签、来源、验证状态等治理字段可以人工维护；逐因子名称、说明、默认参数、文件、类名和数量由同步器生成。

### 3.1 源码与索引同步（当前规则）

因子源码是可执行事实来源，`index.yaml` 是 API 与前端使用的登记清单；逐因子
名称、说明、默认参数、文件、类名和数量不再手工维护。修改
`Factor/libraries/*.py` 后，在仓库根目录执行：

```powershell
conda run -n svquant python -m researchengine.factor_catalog sync
```

该命令会从所有 `FactorLibrary` 的公开方法重新发现因子，并原子更新：

- `Factor/libraries/index.yaml`：因子名称、说明、默认参数、文件、类名和数量；

`Factor/因子库总览.md` 不由同步器写入或校验，研究员可以按研究需要手工补充和整理。

提交前执行只读校验：

```powershell
conda run -n svquant python -m researchengine.factor_catalog check
```

校验会重新扫描源码并比较 `index.yaml`；新增、删除、重命名因子或修改
docstring/默认参数后未执行 `sync`，校验会失败。`pytest` 也包含同一项仓库目录
一致性测试，因此 CI 或本地全量测试会拦截漏同步。

## 4. 与 ResearchEngine 的关系

```text
内置因子库目录：GET /api/factor-libraries 返回全部因子库
        ↓
指定因子库：GET /api/factors/{library_name} 返回该库全部因子
        ↓
内置因子回测：传 library_name + factor_name
        ↓
ResearchEngine 加载完整因子库并回测

用户自定义因子：前端传单个函数体 + factor_name
        ↓
ResearchEngine 生成临时 FactorLibrary 并回测
```

当前 API 的两种来源必须二选一：内置因子传 `library_name` 与 `factor_name`，由服务端按 `index.yaml` 登记加载完整库；用户自定义因子传 `factor_code` 与 `factor_name`，其中 `factor_code` 只接收**单个因子函数体**，服务端自动补全 `FactorLibrary` 类定义。

## 5. API 接口文档

因子回测 API 已独立维护在 [因子回测 API 文档](FACTOR-BACKTEST-API.md)。

系统级 ResearchEngine API 文档见
[FEAT-002 API 文档](../../docs/04-features/FEAT-002-research-engine/06-research-api.md)。
