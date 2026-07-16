# SVQuant

#### 介绍
一站式AI量化投研平台

#### 软件架构

三大模块 + 数据层：

```
ResearchEngine（用户入口）  ->  QuantCore（底层引擎）  ->  Historical/Live Feed
              （阶段一/二 CLI/SDK，阶段三 Web SaaS）
```

- **QuantCore** - 底层量化引擎：DataEngine / FactorEngine / BacktestEngine / MetricEngine
- **ResearchEngine** - 投资研究层：ExperimentManager / Experiment / FactorLoader / ConfigManager / ResultManager
- **TradingEngine** - 交易层（待实现）

文档总入口见 `docs/README.md`。

#### 安装教程

1. 克隆仓库
2. 安装依赖（Python 3.9+）：

   ```bash
   pip install -e .
   # 开箱即用仅需 pandas / numpy / PyYAML；可选依赖按需安装：
   # pip install -e ".[akshare,clickhouse,numba,parquet]"
   ```

#### 使用说明

1. 运行端到端示例（读取根目录 `data/price.CSV` 宽表面板）：

   ```bash
   python ResearchEngine/examples/main.py   # 跑通 因子->指标 全流程 + BacktestEngine 演示
   ```

   > 数据为 Wind/Choice 风格宽表（3 行表头/GBK/OHLCV+市值）。无真实数据时可
   > `python ResearchEngine/examples/gen_data.py` 生成样本。

2. 研究员自定义因子：在 `Factor/libraries/` 下新建 `*.py`，定义 `BaseFactor` 子类并实现 `compute(data: Panel)`（面板模式，`data.close` 取宽表），修改 `examples/main.py` 调用即可。

3. 核心抽象（Experiment）：

   ```python
   from researchengine import Experiment
   experiment = Experiment(factor=MyFactor(), universe="CSI500",
                            start_date=None, end_date=None)  # None=用数据全部区间
   result = experiment.run()
   print(result.summary())
   ```

#### 参与贡献

1.  Fork 本仓库
2.  新建 Feat_xxx 分支
3.  提交代码
4.  新建 Pull Request


#### 特技

1.  使用 Readme\_XXX.md 来支持不同的语言，例如 Readme\_en.md, Readme\_zh.md
2.  Gitee 官方博客 [blog.gitee.com](https://blog.gitee.com)
3.  你可以 [https://gitee.com/explore](https://gitee.com/explore) 这个地址来了解 Gitee 上的优秀开源项目
4.  [GVP](https://gitee.com/gvp) 全称是 Gitee 最有价值开源项目，是综合评定出的优秀开源项目
5.  Gitee 官方提供的使用手册 [https://gitee.com/help](https://gitee.com/help)
6.  Gitee 封面人物是一档用来展示 Gitee 会员风采的栏目 [https://gitee.com/gitee-stars/](https://gitee.com/gitee-stars/)
