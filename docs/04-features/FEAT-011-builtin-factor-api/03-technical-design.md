# Technical Design：内置因子库回测 API

`FactorBacktestRequest` 将 `factor_code` 改为可选，并新增可接受字符串或字符串列表的 `library_name`。未传 `factor_code` 时仅允许一个库名；传了 `factor_code` 时允许多个库名。`Factor/libraries/index.yaml` 是内置库注册的唯一来源：API 每次根据索引中的库名和 `file` 声明校验并通过 `FactorLoader` 加载，不再在 `runner.py` 维护第二份手工白名单。自定义请求继续写入临时模块并包装函数代码，再将索引登记库中的公开因子方法注入临时库。注入方法调用原库的 `BaseFactor.compute()`，因此原库私有辅助方法仍在原库上下文执行。

因子目录接口拆分为两级：`GET /api/factor-libraries` 返回 `index.yaml` 登记的全部因子库（名称、说明、标签和因子数量）；`GET /api/factors/{library_name}` 返回指定因子库中的全部因子（名称和 docstring）。指定库接口仍通过 `FactorLoader` 实际加载并校验源码、索引中的因子清单和数量，库不存在返回 404，库登记但实现不可用返回 503。

该设计不新增运行时依赖、不改变缓存键构成方式（请求对象本身包含来源），也不执行任意前端指定模块。回滚时停止前端发送 `library_name`，旧的 `factor_code` 请求持续兼容。
