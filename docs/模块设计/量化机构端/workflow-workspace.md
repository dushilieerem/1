# Workflow research workspace

2026-11-03. Independent local development worktree on `codex/workflow-tools`, based on e20d0f6. Does not modify the original dev-zxd worktree or subjective-investment routes.

`backend/services/workflow_workspace/` implements local research tasks, immutable factor definitions and run snapshots, review/registration, SQLite records and a bounded DeepSeek tool caller. All calculation goes through loopback HTTP to the separate ResearchEngine process on 8798. No ResearchEngine Python imports or filesystem reads.

UI and launcher are in the outer workspace's `工作台/01_任务/平台AI功能开发/SVQuant机构版-流程原型/`. This is the initial local tool workbench, not yet the production React portal or production authentication.

Run tests from `backend`:

```sh
python -m unittest discover -s tests -p test_workflow_workspace.py -v
```

Tests use fake compute/model responses in temporary SQLite stores. Real data/model acceptance is recorded separately in the outer project's `docs/验收/2026-11-03-真实工具工作台/`.

HTTP routes: GET `/api/health`, `/api/state`, `/api/catalog`, `/api/runs/{id}`, `/api/runs/{id}/export`; POST `/api/factors`, `/api/validate`, `/api/preview`, `/api/runs`, `/api/cancel`, `/api/submit`, `/api/review`, `/api/connection`, `/api/assistant`, `/api/assistant/cancel`, `/api/method`.

Only the model connection route accepts a key, held in memory and never returned. Token totals and reservations persist; uncertain requests retain budget. The local API has loopback-host and same-origin guards, not enterprise identity. Asset registration is research-only. Agents cannot approve, change budgets, execute arbitrary code or trade.

Failed, cancelled and interrupted experiments remain visible. Cancellation prevents publishing late results but cannot undo compute/provider requests already dispatched. Restart marks in-flight jobs interrupted and conservatively transfers outstanding token reservations.

For production integration: formal authentication/authorization, provider credential vault, independent protected validation, asset retirement, data-revocation propagation, task scheduling and account execution are still outstanding. Do not market this local workbench as a completed investment system.
