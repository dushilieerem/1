# 机构端历史脏数据清理（2026-11-10）

## 范围

- 开发库 `svquant_dev` 直接执行；生产库 `svquant` 需 `--allow-production --confirm-production`，并先走 dry-run 与仓库外备份。
- 默认 dry-run；本次先 dry-run 再 `--apply`。
- 不删除任何业务记录：
  - 重复研究案归档为 `stage='closed'`、`stage_state='closed'`；
  - 在途议案作废（stale + rejected）；
  - 重复 qualified 授权撤销；
  - 已成交订单/成交/持仓不动，只输出人工复核清单。
- 每条变更写 `inst_audit_event`，action 前缀 `cleanup.`。

## 结果

| 项目 | 数量 |
|---|---|
| 重复研究案组 | 9 |
| 归档旧研究案 | 178（含 150 个测试/自检公司案；1 个与重复案重叠） |
| 重复授权组 | 0 |
| 待撤销 qualified 授权 | 0 |
| 已成交重复授权（人工复核） | 0 |
| 同案多份在途议案组 | 0 |
| 清理后仍开放的重复研究案组 | 0 |
| 清理后仍开放的测试/自检公司案 | 0 |
| cleanup 审计事件 | 178 |

## 生产库执行（svquant）

- 先 dry-run：5 组重复、32 个旧案、2 份同案多议案、0 重复授权、0 测试案。
- 备份：`/home/dev01/backups/inst-cleanup-20261110/`（inst_research_case / inst_proposal / inst_proposal_version / inst_authorization / inst_exit_case / inst_audit_event 的 CSV.gz，已做 gzip 完整性校验；仓库外保存）。
- 执行：`--allow-production --confirm-production --apply`。
- 结果：归档 32 个旧案、作废 2 份旧 draft 议案、撤销 0 份授权；生产库当前开放案 8 个。
- 复核：开放重复研究案组 0、同案多开放议案组 0、关闭案上仍有在途议案 0、cleanup 审计 34 条。
- 600519：保留较新的退出案，归档已完成买入的原研究案；原案仍可按 key 访问，历史不删除。

## 代码变更

- `scripts/ops/cleanup_inst_duplicates.py`：可重复执行的 dry-run/apply 清理脚本。
- `backend/services/institution/repo.py`：`repo.cases` 排除 `stage='closed'`，归档案不再进入流水线、仪表盘与左列表；按 key 仍可访问详情。
- `backend/tests/test_inst_v3_flow.py`：新增“关闭案不再出现在列表/流水线”的回归测试。

## 产物

原始 JSON（含生产案 ID 与 keep/archive 明细）不进入仓库，保存在仓库外：

`/home/dev01/backups/inst-cleanup-20261110/reports/`

包含开发库与生产库的 dry-run / apply 报告；仓库内仅保留本脱敏说明。
