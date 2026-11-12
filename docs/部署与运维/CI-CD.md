# CI/CD 设计与操作手册

本文回答三件事：提交后自动跑什么、打 tag 后自动部署什么、失败怎么回滚。
不覆盖需求与验收流程，那部分见[需求到交付工作流](../治理/需求到交付工作流.md)。

## 1. 结论

CI/CD 用 **内网轮询 + 服务器脚本** 实现：代码托管在 Gitee，执行环境在内网，内网能出网、
外网进不来，所以由服务器定时 `git fetch` 发现变化（见 [ADR-036](../技术决策/ADR-036-触发方式定为内网轮询.md)）。

| 触发 | 动作 | 执行内容 |
|------|------|----------|
| 轮询发现 `master` 新提交 | CI | `scripts/ci/webhook-job.sh ci`：后端 pytest + 前端构建与单测 |
| 轮询发现新的 `v*` tag | 发布 | `scripts/ci/webhook-job.sh deploy`：备份库 → 构建带 tag 镜像 → compose 部署 → 冒烟 → 失败回滚 |
| 手动 | 同上 | 直接跑 `scripts/ci/*.sh`，不经过轮询 |

```text
systemd timer（默认 60s）
        │
        ▼
scripts/ci/poll.sh   git fetch --prune --tags → 对比状态文件
        ├── 新 tag        → webhook-job.sh deploy refs/tags/<tag>   （同步，优先）
        └── master 变化   → 后台 webhook-job.sh ci master            （独立 worktree + ci.lock）
        ▼
scripts/ci/*.sh      测试 / 构建 / 部署 / 冒烟 / 回滚
```

CI 在 `../svquant-ci-wt` 独立 worktree 里检出并运行，用 `ci.lock` 单独互斥，
不再占用主检出的 `poll.lock`：CI 跑着的时候推 tag，部署照样立即开始。
CI 占锁时本轮不推进 master 基线，下一轮重试，提交不会漏跑。

原则：

1. **CI 只读**：不部署，只跑测试与构建校验；部署只由 tag 触发。
2. **发布只认 tag**：部署的版本号等于一个 Git tag，可追溯、可回滚。
3. **逻辑不绑平台**：触发方式可换（轮询 / WebHook / Jenkins），构建/测试/部署全在 `scripts/ci/*.sh`。
4. **重活只在服务器上跑**：本机（16GB 内存、页面文件在机械盘、多次因虚拟内存耗尽假死）
   只写代码、改文档、做 `bash -n` 与 YAML 解析。

## 2. 跑在哪：本机 vs 服务器

| 动作 | 本机 | 构建机/部署机 |
|------|------|---------------|
| 编辑代码、写文档 | ✅ | — |
| `bash -n`、YAML/Compose 语法解析 | ✅（秒级） | — |
| `npm ci` / `npm run build` / 前端单测 | ❌ | ✅ |
| 后端 pytest（pandas 全量） | ❌ | ✅ |
| `docker build` / compose 部署 | ❌ | ✅ |

## 3. 服务器要求与初始化

| 项 | 要求 |
|----|------|
| OS | Linux（Ubuntu 22.04 / Debian 12） |
| Docker | 24+，含 compose v2（`docker compose version`） |
| Python | 3.11+（接收器与后端都用系统 python3，不依赖 conda） |
| Node | 20.19+ / 22 LTS |
| 其他 | `flock`（util-linux）、`curl`、`git`、`openssl` |
| 内存 | ≥ 8GB（pytest 与镜像构建串行执行） |
| 磁盘 | 仓库分区 ≥ 20GB |
| 权限 | 运行用户需在 `docker` 组；能读仓库（deploy key 或 token） |

```bash
git clone https://gitee.com/yanggu-yuanqi-intelligence/SVQuant.git /opt/SVQuant
cd /opt/SVQuant
bash scripts/ci/host-setup.sh              # 体检：缺什么直接给补装命令
bash scripts/ci/host-setup.sh --write-env  # 生成 deploy/.env（再填 YG_RE_BASE）
```

## 4. 安装内网轮询（默认触发方式）

```bash
sudo bash scripts/ci/poll-install.sh --user <运行用户>
# 可选：--interval 120（默认 60 秒）、--name svquant-poll、--tag-prefix v
```

脚本会：写 `/etc/svquant/svquant-poll.env`、安装并启动 `svquant-poll.timer`（每 60 秒触发
一次 oneshot 服务）、**立刻跑一次建立基线**（不会把历史 tag 重新部署），并检查运行用户能否
`git fetch` 远端。

状态文件 `/var/lib/svquant/poll-state.env` 记录上次见到的 `master` 与最新 tag（CI 结果见
`/var/lib/svquant/jobs.log`）；失败不自动重试，
避免每分钟重复跑一次失败的构建。

```bash
# 看每轮日志（普通用户读不到 systemd journal 时看下面这份）
journalctl -u svquant-poll.service -f

# CI/部署的完整输出：轮询状态目录下，按 8MB 截断
tail -f /var/lib/svquant/jobs.log

# 只报告差异、不改状态
sudo -u <运行用户> POLL_DRY_RUN=1 POLL_STATE_DIR=/var/lib/svquant bash scripts/ci/poll.sh

# 手动补跑一次
sudo -u <运行用户> bash scripts/ci/webhook-job.sh ci master
```

### 可选：内网 Git 用 WebHook

如果以后把仓库迁到内网（Gitea/裸 Git），回调地址是内网 IP，就不需要轮询了，直接启用已备好的
接收器即可，脚本层完全复用：

```bash
sudo bash scripts/ci/webhook-install.sh --user <运行用户>
```

反代片段见 [`deploy/webhook/nginx.conf.example`](../../deploy/webhook/nginx.conf.example)，
排障见 [`deploy/webhook/README.md`](../../deploy/webhook/README.md)。

## 5. CI 做什么

`bash scripts/ci/backend-check.sh`：

- 校验 Python ≥ 3.11，建 `.ci/venv`，装 `backend/requirements-test.txt`；
  两个 requirements 文件内容没变时跳过 pip（指纹存 `.ci/venv/.requirements.sha256`），
  CD 上省掉每轮 3~4 分钟的联网安装；
- 没有 `DATABASE_URL` 时用 `postgres:16-alpine` 起一次性实例（默认 `:55432`，库名 `svquant_ci`），
  **必须**有它：`RefreshLockTest` 两个用例走 PostgreSQL advisory lock；
- `services/core/db.py` 在 pytest 进程里拒绝非 `*_test/*_dev/*_ci/*_e2e/*_local` 库，
  防止本地 `backend/.env` 指向生产 `svquant` 时测试改生产 schema；本地测试用 `svquant_test`；
- 注入测试用 `YG_RE_BASE` / `JWT_SECRET_KEY`（测试对 HTTP 全 mock）；
- `python -m pytest tests -q`，基线 **863 passed / 3 skipped**（无库时 2 failed）。

`bash scripts/ci/frontend-check.sh`：

- 校验 Node ≥ 20；
- `vite.config.ts` 强制要求 `backend/.env` 的 `YG_RE_BASE`：缺失时临时生成、退出时还原；
- `npm ci`（Windows 自动退化为 `npm install`）→ `npm run build` → `npm test`，基线 **97 passed**（串行执行，约 40 秒）。

`bash scripts/ci/docker-build.sh <tag>`：直接 `docker build` 两个 Dockerfile，供发布与排查使用。

## 6. 发布链路

`bash scripts/ci/deploy.sh <tag>`：

```text
backup-db.sh <tag>              pg_dump → deploy/backups/*.sql.gz（失败即终止发布）
  ↓
docker-build.sh <tag>           镜像名带 tag，例如 svquant-backend:v1.3.0
  ↓
compose up -d --wait            等 db / backend / web 健康检查通过
  ↓
smoke.sh                        前端 /healthz、后端 /api/health，RE 网关只告警
  ↓
成功：写 deploy/.last-good.env（回滚点）
  ↓
serve-public.sh start           重启 invest-api 与手机 H5，创建或复用 cloudflared 临时通道
失败：用上一组镜像重新 up，再冒烟，最后退出码 1
```

跳过备份：`SKIP_DB_BACKUP=1 bash scripts/ci/deploy.sh <tag>`（仅限确认无数据变更时）。

复用 Web 镜像：上个发布 tag 到新 tag 之间 `frontend/`、`docker/frontend.Dockerfile`、
`docker/nginx.conf`、`docs/用户指南` 都没变，且本机仍有上一版 `svquant-web:<上个 tag>`
时，`deploy.sh` 直接 `docker tag` 复用，不再跑 `npm ci` + `vite build`（包依赖缓存失效时这一步要 2~3 分钟）。
后端镜像有层缓存（约 2 秒），始终重建。需要强制重建时删掉上一版镜像或改前端任一文件。
跳过手机 H5 与通道：`SKIP_PUBLIC_SERVICES=1`。

`serve-public.sh` 启动的进程是长期进程，依赖两件事：

1. 轮询服务设置 `KillMode=process`（`deploy/poll/svquant-poll.service` 模板已包含），
   否则 oneshot 结束时 systemd 会把它们连带杀掉；
2. 子进程关闭继承的 fd 9（轮询的 flock），否则会永久占锁、让后续轮询全部跳过。

编排文件：[`deploy/compose.yml`](../../deploy/compose.yml)：

| 服务 | 镜像 | 端口 | 说明 |
|------|------|------|------|
| `db` | postgres:16-alpine | `${DB_PORT:-5432}`（所有网卡） | 命名卷 `pgdata` |
| `backend` | `docker/backend.Dockerfile` | `${BACKEND_PORT:-8766}`（容器内 8766） | 启动时 `bootstrap_schemas()` 自动建表 |
| `web` | `docker/frontend.Dockerfile` | `${WEB_PORT:-9530}`（所有网卡） | Nginx 托管 dist + `/api` 反代 |

生产沿用原开发端口（`9530` / `8766` / `5432`），且监听所有网卡；原 dev02 的 PostgreSQL
实例已停用。开发启动脚本改用 `9531` / `8768` / `8769` / `9541`，两套可同时运行。
`deploy.sh` 从 `deploy/.env` 读取端口做冒烟检查。

## 6.5 开发流程与测试分层

同一个测试只在**一个**时机跑，避免 Agent 本机、服务器 CI、发版前各跑一遍全量：

| 时机 | 命令 | 内容 | 目标耗时 |
|------|------|------|----------|
| 改代码时 | `bash scripts/ci/quick-check.sh` | 按改动选后端测试 + `tsc --noEmit` + `bash -n` + H5 build | < 30 秒 |
| 提 PR 前 | `backend-check.sh` + `frontend-check.sh` | 全量 pytest / 迁移门禁 / AI 评测 / 单测 / 构建 / 体积预算 | 3~4 分钟 |
| 合并前（可选） | `scripts/ci/pr-gate.sh <分支>` | 在 PR head 的独立 worktree 上跑 P0 E2E | ~1.5 分钟 |
| 合并后 | 轮询自动 CI | 同「提 PR 前」，兜底防止绕过 | ~4 分钟 |
| 打 tag 前 | `bash scripts/ci/e2e.sh p0` | 登录、H5 个股透视、机构端主链路，6 条 | ~1 分钟 |
| 每晚 / 大改动 | `bash scripts/ci/e2e.sh full` | 全部 14 个 spec、57 条 | ~8 分钟 |

- `quick-check.sh` 不是门禁，只是快速反馈；它匹配不到测试时会明确提示去跑全量。
- `e2e.sh` 自动挑空闲端口起后端 + 主前端 + H5，跑完清理；`DATABASE_URL` 必须是
  `*_test/_dev/_e2e/_ci` 库，指向 `svquant_test` 时写库用例（`INST_E2E_ALLOW_WRITE`）才会执行。
- P0 之外还有布局/溢出/空态类 E2E，属于回归保护，放全量或每晚跑，不拦每次发版。
- `pr-gate.sh <分支>` 在临时 worktree 里检出待合并分支并跑 P0，合并前用；同一时间只允许一个，
  结果打在 stdout（暂不自动写 Gitee 评论）：`bash scripts/ci/pr-gate.sh dev-zmy`。

### 测试库数据

`svquant_test` 默认只有测试夹具，E2E 只能覆盖空态。用生产数据抽样灌一次，让「有数据」路径也能验证：

```bash
bash scripts/ops/seed_test_db.sh --dry-run     # 先看各表会灌多少行
bash scripts/ops/seed_test_db.sh               # 默认 120 天行情 + 180 天公告/研报
```

- 只灌行情与内容表（K 线、估值、资金流、指数、公告/研报、新闻、分红、股本、公司概况），不动 `users` 和业务写入表；
- 目标库名必须含 `_test/_e2e/_ci`，先 TRUNCATE 再灌，重复执行结果一致；
- 灌完跑 `e2e.sh full` 验证：H5 42 条、机构端 18 条。

### 共享开发库的纪律

`svquant_dev` 是多个 Agent 共用的开发库，**只能承载 master 上的迁移**：

- 分支如果新增迁移，先在自己的库（如 `svquant_<agent>_dev`）里验证，不要连共享库启动后端；
- 共享库里出现 master 没有的迁移（`backend-check.sh` 的迁移门禁会报「存在无文件迁移」）时，由该分支负责人清掉自己写入的表和 `schema_migrations` 记录。

## 7. 版本与发布规矩

- tag 格式 `vMAJOR.MINOR.PATCH`（可加 `-rc1`），**只从 `master` 打**，且该 commit 的 CI 绿；
- 部署版本 = tag，`:latest` 不参与发布；
- 顺序：**RE 先发（契约向后兼容）→ SVQuant 后发**；
- 回滚点只认 `deploy/.last-good.env`。

发布检查清单：

1. 最近一次 master 变化对应的 CI 通过（`tail /var/lib/svquant/jobs.log` 里看到 "CI 通过"）；
2. RE 已发布且 `/api/re/health` 可达；
3. 有破坏性数据变更时，确认 `deploy/backups/` 里已有备份且能解压；
4. `git tag vX.Y.Z && git push origin vX.Y.Z`，等一个轮询间隔；
5. 看 `/var/lib/svquant/jobs.log` 与冒烟结果。

回滚：

```bash
# 镜像粒度（流水线没兜住时）
source deploy/.last-good.env
docker compose -f deploy/compose.yml --env-file deploy/.env up -d --wait

# 数据库回滚（会覆盖当前数据，确认后再执行）
gunzip -c deploy/backups/svquant-<tag>-<时间戳>.sql.gz | \
  docker compose -f deploy/compose.yml --env-file deploy/.env exec -T db \
  psql -U svquant -d svquant
```

数据库回滚**不自动**：`bootstrap_schemas()` 只做增量建表，没有迁移版本表。

## 8. ResearchEngine

RE 是独立仓库（`gitee.com/yanggu-yuanqi-intelligence/research-engine`），本仓库不含其源码。
RE 的 CI/CD 用同一套轮询与脚本，只是状态目录与服务名独立：

```bash
# 在 RE 的检出目录里
sudo bash scripts/ci/poll-install.sh --name re-poll --state-dir /var/lib/research-engine --user svquant
```

`webhook-job.sh` 的 `deploy` 分支需要 RE 自己的发布脚本（参照 SVQuant 的 `deploy.sh`）。
模板与入口核对清单见 [`deploy/re-template/`](../../deploy/re-template/README.md)。

RE 的回测结果用 SQLite（`output` 命名卷），发布前备份：

```bash
docker run --rm -v research-engine_re-output:/data -v "$PWD/deploy/backups":/backup alpine \
  tar czf /backup/re-output-$(date +%Y%m%d-%H%M%S).tgz -C /data .
```

## 9. 当前边界（未纳入）

- **不是推送即触发**：最坏延迟一个轮询间隔（默认 60 秒），秒级回滚请直接跑脚本。
- PR 阶段没有门禁：轮询只认 `master` 与 tag；需要 PR 检查时按 ADR-036 评估内网 Gitea。
- Playwright E2E（`tests/e2e/`）仍然手动触发：用 `scripts/ci/e2e.sh p0|full` 起服务后跑，
  未接轮询自动触发。
- 没有把结果回写 Gitee（commit status / PR 评论），失败只能看服务器日志。
- 镜像漏洞扫描、依赖升级机器人未接入。
- 容器当前以 root 运行，加固待排期。
- 轮询服务是单点：它挂掉时不会触发新任务，但不影响已部署服务；恢复后从状态文件继续。
