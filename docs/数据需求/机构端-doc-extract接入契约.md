# 机构端 doc_extract 接入契约

日期：2026-11-10
状态：接入层已实现（`backend/services/institution/doc_layer.py`），待数据业务建表/产出
对接：数据业务 `doc_catalog` / `doc_page_text` / `doc_extract` → 机构端六维 FactPack

## 1. 目标

把年报、半年报、季报与关键公告的页级抽取结果，接入机构端价值分析的六维 FactPack，替换目前“前五大客户、量价拆分、成本结构、合同负债、渠道数据”只能标记缺失的状态。

原则：

- 机构端只读消费，不写 `doc_extract` 的抽取内容；`reviewed_by/reviewed_at` 由机构端复核后回写。
- 只有 `review_status in (approved, verified, reviewed)` 的结果进入正式结论；`pending` 只作线索。
- 每条结果必须能回到原文页：`doc_id + page_no + quote + pdf_sha256`。
- 严格 PIT：`available_time::date <= as_of`，不能用未来披露的数据回测过去。
- 表不存在、字段不齐或读取失败时，机构端自动降级为空覆盖，不阻断研究生成。

## 2. 表契约

### 2.1 `svquant.doc_extract`（机构端消费）

按数据业务确认的 18 列：

| 列 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `symbol` | text | 是 | 证券代码，如 `600519.SH` |
| `field_key` | text | 是 | 固定枚举，见第 3 节 |
| `field_label` | text | 否 | 中文名 |
| `value_text` | text | 二选一 | 文本值，如“前五名客户占比 12.3%” |
| `value_num` | numeric | 二选一 | 数值，配合 `unit` |
| `unit` | text | 否 | `%`、`元`、`万吨` 等 |
| `report_period` | text | 是 | `2025A` / `2025H1` / `2025Q3` |
| `page_no` | int | 是 | 原文页码（从 1 开始） |
| `quote` | text | 是 | 原文片段，不改写 |
| `doc_id` | text | 是 | 关联 `doc_catalog.doc_id` |
| `pdf_sha256` | text | 是 | 与 `doc_catalog.sha256` 一致 |
| `source_url` | text | 否 | 公告/报告原始 URL |
| `available_time` | timestamptz | 是 | 首次可获取时间（PIT 依据），见 2.2 的取值规则；不能用入库时间冒充 |
| `extractor_version` | text | 否 | 抽取器版本 |
| `confidence` | numeric | 否 | 0–1 |
| `review_status` | text | 是 | 默认 `pending` |
| `reviewed_by` | text | 否 | 复核人（机构端回写） |
| `reviewed_at` | timestamptz | 否 | 复核时间（机构端回写） |

建议索引：

```sql
CREATE INDEX IF NOT EXISTS idx_doc_extract_symbol_field_time
  ON svquant.doc_extract (symbol, field_key, available_time DESC);
CREATE INDEX IF NOT EXISTS idx_doc_extract_review
  ON svquant.doc_extract (review_status, symbol);
```

建表迁移：`backend/migrations/0036_inst_doc_extract.sql`（含 schema、表、索引与 `svquant_data_loader` 的 `INSERT, SELECT` 授权）；`0037_inst_doc_extract_privileges.sql` 撤销 schema 默认 ACL 带来的 `UPDATE/DELETE`，保持最小权限。生产 schema owner 为 `svquant`，数据业务角色无 CREATE 权限；2026-11-10 已由用户直接授权执行 0036/0037，生产 `pending=[]`。

### 2.2 目录与页文本（数据业务维护）

- `doc_catalog`：`doc_id, symbol, doc_type, report_period, title, announce_time, available_time, platform_available_time, pdf_url, local_path, sha256, page_count, text_status`。
  - `doc_type`：`annual_report` / `semi_annual_report` / `quarterly_report` / `announcement` / `prospectus` / `inquiry_reply`。
  - `available_time` 为 PIT 可用时间（回采文档 = `announce_time + 1 天`）；`announce_time` 只作展示；`platform_available_time` 保留实际入库时间。
- `doc_page_text`：`doc_id, symbol, page_no, text, char_count, source_sha256, available_time`。
- PIT 取值规则（2026-11-10 联调修正）：
  - `platform_available_time` 只在平台确实于该时间首次拿到文档时使用；
  - 回采历史文档时，`platform_available_time` 是入库时间（本次 7 只标的全为 2026-11-10），不得直接当 `available_time`，否则历史 as_of 全部看不到公告；
  - 回采文档统一用 `announce_time + 1 个自然日` 作为保守 PIT 代理（公告多在盘后发布，次日可用）；`announce_time` 只作展示与审计；
  - 写入 `doc_extract.available_time` 和 `doc_page_text.available_time` 时按上述规则生成；若平台有真实历史首次可得时间，优先用它。
  - `available_time` 为空的行不进入 FactPack（避免无法判断前视）；缺该列时整个接入层降级为空。
- 机构端当前只直接读 `doc_extract`；`doc_catalog/doc_page_text` 用于原文回溯与后续按页检索。

## 3. 固定 field_key

| field_key | 中文 | 主要维度 | 典型来源 |
|---|---|---|---|
| `top5_customers` | 前五大客户及占比 | 公司商业模式 | 年报“主要客户” |
| `volume_price_split` | 量价拆分 | 公司商业模式 | 年报/经营数据公告 |
| `cost_structure` | 成本结构 | 商业模式、财务质量 | 年报“营业成本构成” |
| `contract_liabilities` | 合同负债 | 商业模式、财务质量 | 资产负债表附注 |
| `channel_data` | 渠道与销售模式 | 公司商业模式 | 年报“销售模式/渠道” |

新增字段必须先改本契约和 `doc_layer.DOC_FIELDS`，不允许自由字符串。

## 4. 复核状态机

```
pending ──复核通过──> approved / verified
   │                     │
   ├──业务不适用──> not_applicable（不计入数据缺口）
   └──退回补充──> rejected（不进入正式证据）
```

- 机构端读取时把 `approved/verified/reviewed` 归一为“已复核”。
- 同一 `symbol + field_key + report_period` 存在多条时，按 `available_time DESC` 取最新三条；正式结论优先使用已复核结果。
- `pending` 在 FactPack 中保留为 `coverage=pending`，并写入 `data_gaps`（“抽取结果待复核”）。
- `not_applicable` 在 FactPack 中为 `coverage=na`：从 `missing` 移入 `have`，文案“不适用：字段（原因）”，不扣门禁、不写入数据缺口。

## 5. 机构端行为

实现位置：`backend/services/institution/doc_layer.py`，接入点 `research_service._build_research`。

1. 用 `to_regclass` 依次探测 `svquant.doc_extract`、`doc_extract`、`public.doc_extract`。
2. 缺表/缺关键列/查询异常 → `empty_doc_extracts()`，`document_extract_available=false`，六维照常生成。
3. 查询：`WHERE symbol=%s AND (available_time IS NULL OR available_time::date <= %s) ORDER BY available_time DESC`。
4. FactPack 新增：
   - `facts.document_extracts[field_key] = {label, status, items[]}`
   - `facts.document_coverage[field_key] = have|pending|na|missing`
   - `facts.document_extract_available`、`facts.document_extract_note`
5. `_data_completeness`：
   - 已复核字段从 `missing` 移入 `have`，文案带“年报/公告页级抽取（已复核）”；
   - `pending` 字段留在 `missing` 并标注“抽取结果待复核”；
   - `contract_liabilities` 已复核时，财务缺口改为“受限资金/租赁负债（B 组补）”，不再笼统写合同负债缺失。
6. Agent payload：
   - 商业模式维度注入全部五个字段，财务维度只注入 `cost_structure/contract_liabilities`；
   - 提示词明确要求引用时带 `doc_id`、`page_no`、`quote`、`available_time`，`pending` 不得作结论依据；
   - 其他维度不注入文档字段。

## 6. 验收样例

```sql
INSERT INTO svquant.doc_extract
  (symbol, field_key, field_label, value_text, report_period, page_no, quote,
   doc_id, pdf_sha256, source_url, available_time, extractor_version,
   confidence, review_status)
VALUES
  ('600519.SH', 'top5_customers', '前五大客户及占比',
   '前五名客户销售额占比 12.3%', '2025A', 38,
   '前五名客户销售额占年度销售总额 12.3%',
   'doc-2025-annual', '<sha256>', 'https://...', '2026-03-28', 'extract-v1',
   0.92, 'approved');
```

研究生成后应看到：

- `document_coverage.top5_customers = have`
- `business_model.data_completeness.have` 含“前五大客户占比（已复核）”
- `business_model.data_completeness.missing` 不再含“前五大客户占比”
- `_agent_payload(facts, "business_model").document_extracts.fields.top5_customers.items[0]` 带页码与 quote

## 7. 数据业务当前覆盖与排期（2026-11-10 确认）

- 已有：CSI300 2025 年报 291 份，页级文本可先交付；`doc_extract` 目前只有审计意见，五个新字段抽取器未建。
- 待扩采：2019–2025 全 A 年报、半年报/季报、公告类、招股书/问询回复。
- 建议批次：
  - 批 1：近 5 年目录 + 2025 年报全文（约 5,500 份）；
  - 批 2：2019–2024 全文 + 公告类。
- 在研 20–50 只优先预取，股票列表由机构端提供。

## 8. 责任边界

| 事项 | 数据业务 | 机构端 |
|---|---|---|
| 采 PDF、建 catalog/page_text | 是 | 否 |
| 五个字段抽取器 | 待定（机构端可自抽回写） | 若自抽，按本契约写 `doc_extract` |
| 复核与 `review_status` | 提供流程与默认 pending | 复核后回写 reviewed_by/at |
| PIT 过滤、FactPack 注入、Agent 提示 | 否 | 是 |
| 原文页码/quote 回溯 | 保证字段可用 | 展示与引用 |

## 9. 2025 年报首版抽取（2026-11-10）

脚本：`scripts/ops/extract_inst_doc_fields.py`
输入：数据业务 `inst_pilot/catalog.parquet`、`pagetext.parquet`（2023–2025，7 只 A 股）
输出（本地，未入库）：

- `backend/output/inst_doc_extract_2025/doc_extract_2025.csv`
- `backend/output/inst_doc_extract_2025/doc_extract_2025.sql`
- `backend/output/inst_doc_extract_2025/doc_extract_2025_report.json`

结果：7 份 2025 年报，24 条字段，11 个明确缺口；24 条全部 `review_status=pending`。

| 标的 | 客户 | 量价 | 成本 | 合同负债 | 渠道 |
|---|---|---|---|---|---|
| 600519.SH | 10.10% | 销量 85,104.14 吨 | 缺（仅分行业/分产品表） | 80.07 亿元 | 直销 + 批发代理 |
| 001219.SZ | 23.74% | 销量 55,866 | 直接材料 69.10% 等 | 0.386 亿元 | 经销为主、直营为辅 |
| 000625.SZ | 10.28% | 销量 291.30 万辆 | 营业成本构成表 | 69.09 亿元 | 经销商 90.18% / 直营 4.78% |
| 000006.SZ | 3.51% | 缺 | 营业成本构成表 | 24.90 亿元 | 缺 |
| 001233.SZ | 58.41% | 销量 18,847 条 | 产品成本表 | 0.052 亿元 | 缺 |
| 000002.SZ | 缺（无表述） | 销售面积 1,025 万㎡ | 缺 | 930.57 亿元 | 缺 |
| 000001.SZ | 不适用（银行） | 不适用 | 不适用 | 24.24 百亿元 | 不适用 |

复核建议：

- 客户、量价、合同负债：数值已与年报原文页交叉核对，可优先抽检后置 `verified`；
- 成本结构：当前 `value_text` 保留年报成本构成表原文，需人工确认口径后置 `verified`；
- 渠道：600519/001219 为原文描述，000625 为分销售模式表；000006/001233/000002/000001 明确缺失或不适用；
- 复核回写时填 `reviewed_by`、`reviewed_at`，不要改 `quote/page_no/doc_id`。
- 2026-11-10 数据业务已将 24 行写入生产。机构端抽检后已回写：客户 5 条、量价 5 条、合同负债 7 条、渠道 3 条共 **20 条 `verified`**（`reviewed_by=inst-doc-review-20261110`）；4 条成本结构保持 `pending`，需人工确认口径后再置 `verified`。回读 `load_doc_extracts` 已验证：600519/001219 的客户、量价、合同负债、渠道为 `have`，成本为 missing/pending。

