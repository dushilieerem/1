# GET /api/strategies

返回 `ResearchEngine/app/assets/strategies/index.yaml` 中登记的项目级策略及其当前版本。该接口仅读取索引，不导入或执行策略源码。

```json
{
  "strategies": [
    {
      "id": "dual_moving_average",
      "name": "双均线趋势",
      "strategy_type": "trend",
      "execution_mode": "vectorized",
      "current_version": "v1",
      "entrypoint": "DualMovingAverageStrategy",
      "tags": ["trend", "moving_average", "long_only"]
    }
  ]
}
```

策略目录由 `SVQUANT_STRATEGY_DIR` 覆盖，默认路径为
`ResearchEngine/app/assets/strategies/libraries`。完整索引格式见
[`ResearchEngine 策略库 README`](../../../../app/assets/strategies/libraries/README.md)。
