# FEAT-012：通用因子预处理工具

状态：已完成 MVP

本功能将横截面去极值、标准化、排名、归一化和中性化收敛至
`quantcore.factor.tool`。具体需求、设计和验证范围见同目录文档。

因子函数可直接使用：

```python
from app.quantcore.factor.tool import winsorize, zscore

def value_score(self):
    return zscore(winsorize(1 / self.pb))
```

行业/市值中性化需要显式传入对应的历史暴露面板：

```python
from app.quantcore.factor.tool import neutralize

def neutral_value(self):
    return neutralize(
        1 / self.pb,
        industry=self["industry"],
        market_cap=self.total_mv,
    )
```
