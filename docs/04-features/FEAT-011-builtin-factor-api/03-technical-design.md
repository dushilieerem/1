# Technical Design：内置因子库回测 API

`FactorBacktestRequest` 将 `factor_code` 改为可选，并新增可接受字符串或字符串列表的 `library_name`。未传 `factor_code` 时仅允许一个库名；传了 `factor_code` 时允许多个库名。`runner.py` 维护内置库白名单：内置请求通过 `FactorLoader.load(library_name)` 加载完整库；自定义请求继续写入临时模块并包装函数代码，再将声明库中的公开因子方法注入临时库。注入方法调用原库的 `BaseFactor.compute()`，因此原库私有辅助方法仍在原库上下文执行。

该设计不新增运行时依赖、不改变缓存键构成方式（请求对象本身包含来源），也不执行任意前端指定模块。回滚时停止前端发送 `library_name`，旧的 `factor_code` 请求持续兼容。
