/**
 * 数据模块 · 字段说明与样例（产品展示用）
 * 口径来自现有字段表（2026-09-04）及日行情常用字段；
 * 「K 线面板当前」仅消费日线 OHLC。
 */

export type FieldAvailability = "kline" | "catalog" | "planned";

export type DataFieldDef = {
  key: string;
  nameZh: string;
  source: string;
  definition: string;
  formula?: string;
  format?: string;
  /** kline=K线面板已用；catalog=字段库已有/可取；planned=规划中 */
  availability: FieldAvailability;
  note?: string;
};

export type FieldGroup = {
  id: string;
  title: string;
  blurb: string;
  fields: DataFieldDef[];
};

export const FIELD_GROUPS: FieldGroup[] = [
  {
    id: "basic",
    title: "证券基础信息",
    blurb: "代码、名称、上市归属等，用于搜索、列表与个股页头。",
    fields: [
      {
        key: "symbol",
        nameZh: "同花顺代码 / 证券代码",
        source: "同花顺 / 交易所",
        definition:
          "「代码 + 市场」唯一标识，避免同码不同品种混淆。示例：000001.SZ 平安银行，000001.SH 上证指数，000001.OF 基金，000001.IB 国债。",
        format: "string",
        availability: "kline",
      },
      {
        key: "name",
        nameZh: "证券名称",
        source: "交易所",
        definition: "交易用证券简称（非公司全称），用于行情查询与下单展示。",
        format: "string",
        availability: "kline",
      },
      {
        key: "exchange",
        nameZh: "上市交易所",
        source: "交易所",
        definition: "首次发行并上市的交易所，如上交所、深交所、北交所。",
        format: "string",
        availability: "catalog",
      },
      {
        key: "board",
        nameZh: "上市板块",
        source: "交易所",
        definition: "主板、创业板、科创板等板块归属。",
        format: "string",
        availability: "catalog",
      },
      {
        key: "list_date",
        nameZh: "上市时间",
        source: "公司公告",
        definition: "股票首次挂牌交易日期，用于上市时长与历史回溯。",
        format: "date",
        availability: "catalog",
      },
      {
        key: "delist_date",
        nameZh: "摘牌日期",
        source: "上交所 / 深交所",
        definition: "终止上市或取消上市资格的日期；未摘牌可为空。",
        format: "date",
        availability: "catalog",
      },
    ],
  },
  {
    id: "daily",
    title: "股票日行情（A 股）",
    blurb: "日频行情主表。K 线面板当前绘制依赖开高低收；量额等字段在字段库中已有定义。",
    fields: [
      {
        key: "date",
        nameZh: "交易日期",
        source: "交易所",
        definition: "该条日行情对应的交易日。",
        format: "YYYY-MM-DD",
        availability: "kline",
      },
      {
        key: "open",
        nameZh: "开盘价 open",
        source: "交易所",
        definition:
          "指定交易日开盘价。A 股/基金/权证等人民币品种单位为人民币；上证 B 股为美元，深证 B 股为港元。",
        format: "float",
        availability: "kline",
      },
      {
        key: "high",
        nameZh: "最高价 high",
        source: "交易所",
        definition: "指定交易日最高价。币种规则同开盘价。",
        format: "float",
        availability: "kline",
      },
      {
        key: "low",
        nameZh: "最低价 low",
        source: "交易所",
        definition: "指定交易日最低价。币种规则同开盘价。",
        format: "float",
        availability: "kline",
      },
      {
        key: "close",
        nameZh: "收盘价 close",
        source: "交易所",
        definition: "指定交易日收盘价。币种规则同开盘价。K 线与多数估值常用此价。",
        format: "float",
        availability: "kline",
      },
      {
        key: "volume",
        nameZh: "成交量 volume",
        source: "交易所",
        definition: "指定交易日成交数量（股/手，以数据源口径为准）。",
        format: "float",
        availability: "catalog",
        note: "K 线面板当前未接；副图 VOL 需接口带出量字段。",
      },
      {
        key: "amount",
        nameZh: "成交额 amount / turnover",
        source: "交易所",
        definition: "指定交易日成交金额合计（元）。",
        format: "float",
        availability: "catalog",
      },
      {
        key: "turnover_rate",
        nameZh: "换手率 turnover",
        source: "同花顺计算",
        definition: "指定交易日证券转手买卖频率。",
        formula: "成交量 / 流通总股数 × 100%",
        format: "float (%)",
        availability: "catalog",
      },
      {
        key: "avg_price",
        nameZh: "均价 avg_price",
        source: "计算 / 行情",
        definition: "当日成交均价（元）。模拟盘日终撮合可约定用 VWAP/均价口径。",
        format: "float",
        availability: "catalog",
      },
      {
        key: "prev_close",
        nameZh: "前收盘价 prev_close",
        source: "交易所",
        definition: "上一交易日收盘价，用于涨跌幅等计算。",
        format: "float",
        availability: "catalog",
      },
      {
        key: "quote_rate",
        nameZh: "涨跌幅 quote_rate",
        source: "计算",
        definition: "相对前收的涨跌幅度（%）。",
        format: "float (%)",
        availability: "catalog",
      },
      {
        key: "factor",
        nameZh: "复权因子 factor",
        source: "计算",
        definition: "用于前后复权价格换算。",
        formula: "复权因子 = 后复权价格 / 不复权价格",
        format: "float",
        availability: "catalog",
      },
      {
        key: "is_paused",
        nameZh: "是否停牌 is_paused",
        source: "交易所 / 计算",
        definition: "0 未停牌，1 停牌。",
        format: "0 | 1",
        availability: "catalog",
      },
      {
        key: "high_limit",
        nameZh: "涨停价 high_limit",
        source: "计算",
        definition: "当日涨停价格（元）。",
        format: "float",
        availability: "catalog",
      },
      {
        key: "low_limit",
        nameZh: "跌停价 low_limit",
        source: "计算",
        definition: "当日跌停价格（元）。",
        format: "float",
        availability: "catalog",
      },
      {
        key: "index_weight",
        nameZh: "股指权重",
        source: "同花顺统计",
        definition: "个股在某指数中的权重，成分股权重之和为 100。",
        format: "float",
        availability: "catalog",
      },
    ],
  },
  {
    id: "valuation",
    title: "估值 · 财务 · 状态",
    blurb: "市值、PE/PB/ROE、行业与交易状态等，多用于筛选与个股画像（非 K 线主路径）。",
    fields: [
      {
        key: "float_mv",
        nameZh: "流通市值",
        source: "同花顺计算",
        definition:
          "可自由交易股份的市值规模，衡量流动性与体量；与总市值不同。",
        formula:
          "A股收盘价×流通A股 + B股收盘价×流通B股×人民币外汇牌价（口径以数据源为准）",
        format: "float (元)",
        availability: "catalog",
      },
      {
        key: "industry_sw_code",
        nameZh: "所属申万行业代码",
        source: "申银万国",
        definition: "申万行业分类代码，用于行业筛选与对比。",
        format: "string",
        availability: "catalog",
      },
      {
        key: "list_status",
        nameZh: "上市状态",
        source: "上交所 / 深交所",
        definition: "如正常、ST、*ST、停牌、退市等，用于可交易过滤与风险识别。",
        format: "string",
        availability: "catalog",
      },
      {
        key: "limit_status",
        nameZh: "涨跌停状态",
        source: "同花顺计算",
        definition: "当日是否触及涨停、跌停或未触及。",
        format: "string",
        availability: "catalog",
      },
      {
        key: "pe_ttm",
        nameZh: "PE(TTM) 滚动市盈率",
        source: "同花顺计算",
        definition: "用近 12 个月归母净利润滚动计算的市盈率，较静态 PE 更及时。",
        format: "float",
        availability: "catalog",
      },
      {
        key: "roe_ttm",
        nameZh: "ROE(TTM) 净资产收益率",
        source: "同花顺计算",
        definition: "近四个季度归母净利润相对净资产的收益率，减弱季节性。",
        formula: "归母净利润(TTM) / 归母股东权益(MRQ) × 100%",
        format: "float (%)",
        availability: "catalog",
      },
      {
        key: "pb_mrq",
        nameZh: "PB(MRQ) 市净率",
        source: "同花顺计算",
        definition: "总市值相对最新报告期归母净资产的倍数。",
        formula: "总市值 / (归属母公司股东权益 − 其他权益工具)",
        format: "float",
        availability: "catalog",
      },
      {
        key: "pcf_ttm",
        nameZh: "PCF(经营现金流 TTM) 市现率",
        source: "同花顺计算",
        definition: "市值相对经营现金流 TTM；常用于现金流视角的估值与风险观察。",
        format: "float",
        availability: "catalog",
      },
    ],
  },
];

/** 日行情样例（示意；含 OHLC + 扩展列） */
export const DAILY_SAMPLE_ROWS = [
  {
    date: "2026-09-01",
    symbol: "000001.SZ",
    name: "平安银行",
    open: 11.52,
    high: 11.68,
    low: 11.41,
    close: 11.55,
    volume: 82_450_000,
    amount: 951_200_000,
    turnover_rate: 0.42,
    avg_price: 11.54,
    prev_close: 11.48,
    quote_rate: 0.61,
    is_paused: 0,
    high_limit: 12.63,
    low_limit: 10.33,
  },
  {
    date: "2026-09-02",
    symbol: "000001.SZ",
    name: "平安银行",
    open: 11.56,
    high: 11.72,
    low: 11.50,
    close: 11.66,
    volume: 76_120_000,
    amount: 885_600_000,
    turnover_rate: 0.39,
    avg_price: 11.63,
    prev_close: 11.55,
    quote_rate: 0.95,
    is_paused: 0,
    high_limit: 12.71,
    low_limit: 10.40,
  },
  {
    date: "2026-09-03",
    symbol: "000001.SZ",
    name: "平安银行",
    open: 11.66,
    high: 11.70,
    low: 11.38,
    close: 11.42,
    volume: 91_300_000,
    amount: 1_048_000_000,
    turnover_rate: 0.47,
    avg_price: 11.48,
    prev_close: 11.66,
    quote_rate: -2.06,
    is_paused: 0,
    high_limit: 12.83,
    low_limit: 10.49,
  },
] as const;

/** 基础信息 + 估值样例（单票截面） */
export const SNAPSHOT_SAMPLE = {
  symbol: "000001.SZ",
  name: "平安银行",
  exchange: "深圳证券交易所",
  board: "主板",
  list_date: "1991-04-03",
  delist_date: null as string | null,
  float_mv: 224_500_000_000,
  industry_sw_code: "801780",
  list_status: "正常",
  limit_status: "非涨跌停",
  pe_ttm: 5.12,
  roe_ttm: 9.85,
  pb_mrq: 0.58,
  pcf_ttm: 3.40,
} as const;

export function availabilityLabel(a: FieldAvailability): string {
  if (a === "kline") return "K 线已用";
  if (a === "catalog") return "字段库已有";
  return "规划中";
}
