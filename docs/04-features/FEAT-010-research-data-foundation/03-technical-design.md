# Technical Design：投研因子数据底座

## 模块边界

```text
授权数据供应商 / 用户导入
        ↓ 原始披露记录（不可覆盖）
Data Ingestion + 字段字典 + 质量校验
        ↓ 公告日点时转换
MarketData/（字段 Parquet + 数据清单）
        ↓
FieldParquetProvider / DataEngine → Panel → FactorEngine / ResearchEngine
```

沿用 `FieldParquetProvider` 的“一个字段一个 Parquet”模式。历史数据由 `MarketData/DataIngestion/` 批量采集后发布；`QuantCore` 只读取标准字段并向因子层提供面板；`ResearchEngine` 不管理数据源凭据或数据资产。实时或临时高频查询可使用 `WindProvider`，但不得替代历史回测的可复现数据发布。

## 存储与字段契约

原始财务记录保存为长表，最小列为：`symbol`、`report_period`、`announcement_date`、`field`、`value`、`unit`、`source`、`source_version`、`revision_at`。转换后每个标准字段输出 `日期 × 标的` 宽表，例如：

```text
MarketData/
  DataIngestion/                      # Wind 历史数据采集工具（入库）
  current/                            # API 当前只读数据版本（不入库）
    panels/                           # 字段 Parquet：日期 × 标的
      net_profit_ttm.parquet
      total_assets.parquet
      adj_factor.parquet
      is_suspended.parquet
      listing_status.parquet
      market_return_all_a.parquet
    benchmark/                         # 指数与成分数据
    metadata/                          # stock_info、字段说明等非面板数据
  releases/                           # 后续不可变历史发布版本（不入库）
```

字段字典和数据资产清单的评审基线分别见 `05-field-dictionary.md`、`06-data-catalog.md`。实现时将其机读副本随每个发布版本输出；价格字段必须标注复权口径，财务字段必须标注单季/累计/TTM 与点时规则。

## 已交付的数据访问层

- `DataEngine` 以 `IDataProvider` 作为唯一数据读取入口；因子、研究编排和回测只访问标准字段面板，不直接依赖 Wind、AkShare、iFind 或文件路径。
- `FieldParquetProvider` 支持 `MarketData/current/panels` 的字段宽表、`current/benchmark` 的指数和成分、`current/metadata` 的非面板数据；传入旧版扁平目录时保持兼容。
- Provider 对字段按需懒加载并在实例内缓存；API 服务应按每个进程、每个数据版本复用其实例，而非每次回测重新读取全部文件。多数据源分层和适配要求见 `../../06-decisions/ADR-010-为什么采用统一数据引擎和多数据源适配.md`。
- 历史 Pandas Parquet 的日期索引可能保存于文件元数据；读取器已兼容显式 `datetime` 列与历史隐式索引两种格式，统一输出索引名为 `datetime`。

## 点时转换

对于每只证券、每个交易日，选择公告日不晚于该日的最新有效原始记录。TTM 由当时可见的四个季度构成，缺季度即空值；禁止使用报告期结束日直接对齐。转换任务输出数据版本、源版本、覆盖率和校验报告。

## 接口、兼容与回滚

- 新字段通过现有 `Panel["field"]` 按需加载，不改变已有字段或因子名称。
- 数据清单记录每个文件的哈希、覆盖区间、证券覆盖、来源版本和生成版本；因子/回测缓存键需纳入数据版本。
- 出现源数据问题时，将 `SVQUANT_DATA_DIR` 指向上一个完整版本；原始记录和旧版本 Parquet 保留至验证完成后按数据保留策略清理。

当前 `current/` 是运行时活动版本目录；后续发布流程先在 `releases/<data_version>/` 完成校验，再以原子方式切换 `current/`，避免 API 读到部分更新的数据。

### iFinD `history_data` 日线协议（已由超级命令确认）

全 A 股日线 OHLC 使用 `POST https://quantapi.51ifind.com/api/v1/history_data`，请求体外层为 `{"reqBody": ...}`。`reqBody` 至少包含显式证券代码列表 `codes`、`startdate`、`enddate` 与 `indicators: "open,high,low,close"`。该 endpoint 的复权参数以超级命令实际协议为唯一准则：省略 `functionpara.CPS` 为不复权，`CPS: "1"` 为后复权，`CPS: "2"` 为前复权。

此映射不得套用其他 iFinD 历史行情 endpoint 或旧版 SDK 文档的 `CPS` 含义。采集器须分别记录 endpoint、完整 `functionpara`、超级命令协议确认日期和供应商版本；三种口径分别落入原始数据目录，未经发布规则确认不得覆盖同一标准字段面板。

全 A 股下载任务使用 `POST /api/v1/get_trade_dates` 获取交易日历，固定 `functionpara: {"mode": "1", "dateType": "0", "period": "D", "dateFormat": "0"}`。交易所与 iFinD `marketcode` 映射为：`SH → 212001`、`SZ → 212100`、`BJ → 212300`。三份日历独立保存并进行差异检查；按证券所属交易所选择下载窗口，不假定三地日历恒等。

### iFinD `p03291` 全 A 证券主表协议

全 A 证券主表使用 `POST /api/v1/data_pool`，每日对同一个目标日请求三次：在市板块 `001005010`、已摘牌板块 `001005334011`、退市整理板块 `001005334025`。三次请求均固定 `reportname: p03291`、`functionpara.iv_type: allcontract`、`outputpara: p03291_f002,p03291_f003`；`p03291_f002` 为证券代码，`p03291_f003` 为证券名称。

原始响应按状态分区保存；同日三张快照通过 `thscode` 互斥校验后直接联合为原有扁平证券主表：

```text
sources/ifind/universe/raw/LISTED/<date>.json
sources/ifind/universe/raw/DELISTED/<date>.json
sources/ifind/universe/raw/DELISTING/<date>.json
sources/ifind/universe/a_share.csv
```

`a_share.csv` 的列固定为 `thscode` 和 `name`，分别对应 `p03291_f002` 与 `p03291_f003`；交易所从证券代码后缀派生。交易所名称、上市日期、板块和上市状态等字段不在该请求中返回，不写入证券池 CSV，后续由独立数据资产提供。

同一日期的三张 raw 各只下载一次，重复运行直接重放缓存。在市与已摘牌快照必须非空；退市整理快照允许为空，供应商返回的 `-4001 / no data` 原始响应按空快照缓存，但其他错误不得降级。构建 CSV 时取最新的同日快照，先校验三张快照的 `thscode` 集合两两互斥；只要存在任意交集就报错并拒绝落盘，不能用状态优先级覆盖异常。通过校验后直接联合三张列表。该 CSV 是历史证券集合，不是日期 × 证券成员矩阵；需要某日成员资格时，应结合可用的上市/退市生效日期或状态面板派生。

### iFinD CSV 优先落盘规则

所有 iFinD 下载结果先写入 `MarketData/sources/ifind/` 下按数据域、交易所和时间窗口分区的 UTF-8 CSV；不得由 HTTP 响应直接写入 `current/` 或 `releases/` 的 Parquet。CSV 经字段名、证券代码、日期、重复记录、OHLC 关系、缺失率和请求覆盖区间检查后，才转换为候选发布版本中的标准字段 Parquet。每个 CSV 分区对应的请求参数、`dataVol`、来源版本、生成时间和内容哈希由 checkpoint / manifest 记录；CSV 用于人工查看和问题追溯，Parquet 用于研究运行时读取。

指数权重使用 `POST /api/v1/data_pool` 的 `p03563`，`functionpara` 只含 `date`、`index_name`，`outputpara` 固定为 `p03563_f002,p03563_f004`。两字段分别映射证券代码与权重。每个指数的 CSV 与 Parquet 都采用日期索引、股票代码列的宽表结构；权重保持 iFinD 百分比原值，非成分股为空值。

### iFinD 全量与日增量任务

每类 iFinD 数据均提供两个独立命令入口，并复用同一下载、标准化、CSV 落盘和质量检查实现：

- **全量回填命令**：显式接收证券池版本、起止日期和字段组；按预算切分为可断点续传的历史批次，生成或补齐指定历史区间。
- **收盘后日增量命令**：由定时任务每天收盘并确认数据完整后运行；根据三地交易日历确定最近一个已完成交易日，只下载该日期尚未完成的分区。非交易日、已完成分区或行情未最终落定时安全退出，不重复计量或覆盖已验证数据。

日增量任务不得按本机日历日盲目请求“今天”。它必须记录运行时间、目标交易日、各交易所状态、实际 `dataVol` 和 CSV 分区哈希，并通过相同质量门禁后才允许进入后续 Parquet 发布。调度器是外部运行方式，不得把账号凭据、调度配置或 token 写入代码仓库。

## 测试策略

- 单元测试：字段映射、公告日边界、TTM/同比、修订版本、复权转换与缺字段异常。
- 集成测试：FieldParquetProvider 懒加载、因子计算与 API 回测。
- 数据质量：单位校验、覆盖率、日期连续性、证券代码一致性、异常值和源版本检查。

已完成验证：`FieldParquetProvider` 的 `current/` 目录解析、旧版 Pandas 日期索引读取，以及因子回测 API 从实际 `MarketData` 读取 2023 年 CSI500 数据并返回策略与基准净值曲线。

## 技术风险

最大风险是数据许可和公告日质量；第二风险是不同供应商的科目定义、单位和修订规则不同。MVP 必须先固定一个授权来源和字段字典，不能混用多个来源后再猜测映射。
