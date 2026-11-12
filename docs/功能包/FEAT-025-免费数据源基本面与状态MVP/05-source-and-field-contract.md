# 免费数据源与字段契约：FEAT-025

## 1. 来源清单

| 来源 | 用途 | 主要接口/字段 | 适用市场 | 备注 |
|---|---|---|---|---|
| BaoStock | 历史估值和交易状态 | `query_history_k_data_plus`：`peTTM`、`pbMRQ`、`psTTM`、`tradestatus`、`isST` | 主要为沪深 | 免费库；需验证当前服务稳定性和数据再分发边界 |
| AKShare/CNINFO | 股本事件和当前快照校验 | 股本变动、A 股实时快照、当前 ST 相关接口 | 沪深京，按接口而定 | 返回字段、单位和历史能力必须逐接口确认 |
| 本地 `unadjusted_price` | 市值计算 | `close` | 已有全 A 覆盖范围 | 不依赖在线源，作为发布输入 |

官方参考：

- [BaoStock PyPI](https://pypi.org/project/baostock/)
- [AKShare A 股数据接口](https://akshare.akfamily.xyz/data/stock/stock.html)
- [AKShare 项目说明](https://github.com/akfamily/akshare/blob/main/docs/introduction.md)

## 2. 字段契约

| 标准字段 | 源字段 | 转换 | 缺失/限制 |
|---|---|---|---|
| `pe_ttm` | BaoStock `peTTM` | 数值直写 | 不得映射为 `pe` |
| `pb` | BaoStock `pbMRQ` | 数值直写 | 与 iFinD 口径差异需报告 |
| `ps_ttm` | BaoStock `psTTM` | 数值直写 | 仅在源声明可用时写入 |
| `is_st` | BaoStock `isST` | 转 bool；原始异常值不转 False | 沪深优先 |
| `is_suspended` | BaoStock `tradestatus` | `0` → `True`，`1` → `False` | 与已有 iFinD 样本校验 |
| `total_shares` | CNINFO 总股本 | 万股 × 10,000 | 必须有可验证生效日 |
| `float_shares` | CNINFO 流通股本 | 万股 × 10,000 | 同上 |
| `total_mv` | 本地 `close` + `total_shares` | 乘法计算 | 任一输入缺失则缺失 |
| `float_mv` | 本地 `close` + `float_shares` | 乘法计算 | 任一输入缺失则缺失 |

## 3. 来源状态枚举

- `ready`：字段已通过覆盖率和口径检查，可供内部研究使用。
- `partial`：仅部分市场、日期或证券可用，调用方必须看到覆盖范围。
- `blocked`：来源口径或点时有效性未确认，不得进入标准面板。
- `legacy`：沿用上一 release，未由免费源更新。

MVP 初始状态建议：

```yaml
daily_basic:
  total_mv: ready
  float_mv: ready
  total_shares: partial
  float_shares: partial
  pe: blocked
  pe_ttm: partial
  pb: partial
  ps_ttm: partial
security_status:
  is_st: partial
  is_suspended: partial
  industry_sw: legacy
  industry_sw_code: legacy
  limit_status: legacy
```

## 4. 授权边界

“免费可访问”不等于“可商业缓存、展示或再分发”。MVP 默认只用于本地和内部研究；对外 API、SaaS、数据下载或商业回测前，必须对 BaoStock、AKShare/CNINFO 及其上游来源分别完成授权审查，并在数据目录中登记结论。
