# GET /api/strategies

返回 `Strategy/libraries/index.yaml` 中登记的项目级策略及其当前版本。该接口仅读取索引，不导入或执行策略源码。

```json
{
  "strategies": [
    {
      "id": "weekly_rotation",
      "name": "周度轮动",
      "strategy_type": "momentum",
      "execution_mode": "vectorized",
      "current_version": "v2",
      "entrypoint": "WeeklyRotationStrategy",
      "tags": ["轮动"]
    }
  ]
}
```

策略目录由 `SVQUANT_STRATEGY_DIR` 覆盖，默认路径为仓库根目录的 `Strategy/libraries`。完整索引格式见 [`Strategy/libraries/README.md`](../../../../../Strategy/libraries/README.md)。
