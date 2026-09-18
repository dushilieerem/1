# SVQuant 因子适配（精简）

> 更新：2026-08-12  
> **官方内置因子**目录与源码由独立 **ResearchEngine** 管理，本目录不再存放官方 `.py`。

## 本机保留

```text
factor/
├── index.yaml              # 仅 custom_lib 元数据（rebuild 同步）
├── custom_lib.py           # 用户自定义方法体同步产物
├── factor-libraries.md     # RE：GET /api/factor-libraries
├── factor-library-factors.md
└── __init__.py
```

## SVQuant 读库

1. 官方：经 SVQuant 网关调用 `GET /api/factor-libraries` → `GET /api/factors/{lib}`
2. 自定义：本机 `GET /api/factor/index`（仅 `custom_lib`）
3. 回测官方单因子：只传 `library_name` + `factor_name`
4. 自定义 / 混合：传 `factor_code`（± `library_name`）

## 管理

- 新增自定义：走 SVQuant「自定义因子」页面 → PostgreSQL + `rebuild_custom_lib`
- 官方公式/源码：只在 ResearchEngine 侧维护，本站不展示或执行
