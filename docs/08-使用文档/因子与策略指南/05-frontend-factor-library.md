# 前端因子库映射规范

> 适用对象：前端、后端和因子库管理功能开发者

## 1. 用户操作与文件映射

| 用户操作 | 后台结果 |
|----------|----------|
| 新建因子库 | 创建一个因子库 Python 文件 |
| 新建因子 | 向库类追加一个因子方法 |
| 编辑因子 | 修改对应方法体 |
| 删除因子 | 删除对应方法 |
| 删除/重命名因子库 | 删除/重命名对应 Python 文件 |

前端只暴露因子方法体；服务端负责生成完整文件：

```python
from app.services.factor.base import FactorLibrary

class MomentumLibrary(FactorLibrary):
    author = "当前用户"

    def momentum_5d(self):
        """5 日动量。"""
        return self.close.pct_change(5)
```

## 2. 模板规则

| 生成项 | 规则 |
|--------|------|
| 导入 | ResearchEngine 侧使用 `from app.services.factor.base import FactorLibrary` |
| 类名 | 因子库名转换为大驼峰并追加 `Library` |
| 作者 | 当前登录用户名 |
| 方法 | 用户编辑的函数体原样插入并做语法校验 |

## 3. 前端编辑器约束

- 因子名采用小写字母和下划线。
- 必须包含 docstring 与 `return` 表达式。
- 参数使用默认值，例如 `window=20`。
- 编辑器应提示可用字段和禁止未来函数的规则。
- 代码保存与回测执行是两件事：保存后仍须通过回测响应的 `error` 字段确认可运行。
