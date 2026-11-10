# 机构端排版阶梯自检（2026-11-10）

## 口径

- 字号仅允许：**12 / 14 / 18 / 24 / 32px**
  - 12 辅助信息
  - 14 列表主文与正文
  - 18 区块标题与口号（口号字重 400）
  - 24 页面标题
  - 32 KPI 数字（等宽数字）
- 字重仅允许：**400 / 500 / 600**
- 中文最小 12px；原先低于 12px 的一律改为 12px，并使用更浅的辅助色。

## 方法

Playwright 以 `inst_manager` 登录，1440×900 视口，逐个访问：

`/inst`、`/inst/pipeline`、`/inst/research`、`/inst/debate`、`/inst/approvals`、`/inst/execute`、`/inst/manage`、`/inst/playbook`

收集 `.inst-v3` 下所有“有直接文本节点且可见”的元素的 `getComputedStyle`，记录 `fontSize` / `fontWeight`，逐节点写入 `font-nodes.csv`。

## 结果

- 文本节点：**1167**
- 字号分布：`12px 595`、`14px 478`、`18px 53`、`24px 18`、`32px 23`
- 越界字号：**0**
- 越界字重：**0**

代表层级：

| 层级 | 选择器 | 计算值 |
|---|---|---|
| 页面标题 | `.v3-page-head h1` | 24px / 600 |
| 区块标题 | `.v3-card-head h2` | 18px / 600 |
| KPI 数字 | `.v3-kpi .v` | 32px / 600 |
| 口号 | `.v3-hero h2` | 18px / 400 |
| 列表主文 | `.v3-nav-item` | 14px（激活态 600） |
| 辅助 | `.v3-kpi .d` | 12px / 400 |

逐节点清单：`font-nodes.csv`（列：page / tag / class / text / font-size / font-weight）。
