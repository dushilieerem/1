# FEAT-002 因子分析可视化数据 API 验证记录

> 验证日期：2026-07-20  
> 状态：通过

## 验证范围

- 日频 IC、累计 IC、60 日滚动 IR 的计算与 JSON 序列化。
- 行业等权收益曲线与行业内因子分组曲线。
- 无行业映射时的兼容行为。
- 既有因子回测 API 的缓存、基准和请求字段校验。

## 自动化验证

```powershell
& 'D:\Devtools\anaconda3\envs\svquant\python.exe' -m pytest ResearchEngine/tests -q
```

结果：**55 passed，1 warning**。

其中 `ResearchEngine/tests/test_api.py` 验证：

1. 累计 IC 末值等于日频 IC 序列之和。
2. 90 个交易日样本能返回 60 日滚动 IR。
3. 有 `stock_info.parquet` 映射时返回两个行业及每行业 `G1..G3` 分组曲线。
4. 删除行业映射后，回测正常完成且行业曲线数组为空。

## 已知边界

- `stock_info.parquet` 的行业值直接作为 `industry_code` 和 `industry_name` 返回；行业编码、名称和版本的主数据治理不属于 ResearchEngine。
- 本次仅交付回测结果 API；前端负责 IC 直方图分桶和所有图表渲染。
