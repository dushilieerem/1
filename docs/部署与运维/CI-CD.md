# CI/CD 设计与操作手册

本文回答三件事：提交后自动跑什么、打 tag 后自动部署什么、失败怎么回滚。
不覆盖需求与验收流程，那部分见[需求到交付工作流](../治理/需求到交付工作流.md)。

## 1. 结论

| 仓库 | 流水线 | 触发 | 做什么 |
|------|--------|------|--------|
| SVQuant | `svquant-ci` | 向 `master` 发 PR、合入 `master` | 后端 pytest、前端构建+单测；仅 master 额外验证镜像可构建 |
| SVQuant | `svquant-release` | 推送 `v*` tag | 备份库 → 构建带 tag 镜像 → compose 部署 → 冒烟 → 失败自动回滚 |
| ResearchEngine | `re-ci` / `re-release` | 同上 | 同构；模板见 [`deploy/re-template/`](../../deploy/re-template/README.md) |

原则：

1. **CI 只读**：不改服务器、不部署，任何有写权限的人提交都能跑。
2. **发布只认 tag**：部署的版本号等于一个 Git tag，可追溯、可回滚；分支合并只跑 CI。
3. **平台可替换**：流水线文件只做「调脚本」，真正的构建/测试/部署逻辑都在
   `scripts/ci/*.sh`，换成 Jenkins、GitLab CI 或本地一条命令都能跑（符合
   [ADR-006](../技术决策/ADR-006-为什么选择Gitee而不是GitHub.md) 不绑定平台私有能力）。
4. **重活只在服务器上跑**：本机（16GB 内存的开发机）只写代码、改文档、做 `bash -n`
   和 YAML 解析；`npm ci`、`vite build`、pytest、镜像构建一律在构建机执行。

## 2. 跑在哪：本机 vs 服务器

| 动作 | 本机 | 构建机/部署机 |
|------|------|---------------|
| 编辑代码、写文档 | ✅ | — |
| `bash -n`、YAML/Compose 语法解析 | ✅（秒级、几乎不占内存） | — |
| `npm ci` / `npm run build` / 前端单测 | ❌ | ✅ |
| 后端 pytest（pandas 全量） | ❌ | ✅ |
| `docker build` / compose 部署 | ❌ | ✅ |

原因：本机 16GB 内存、页面文件在机械盘，并发生过多次「虚拟内存耗尽 → 整机假死」，
详见 [ADR-034](../技术决策/ADR-034-CI-CD采用GiteeGo主机组与DockerCompose.md)。

## 3. 执行环境：自建构建机 + Gitee Go 主机组

选它而不是 Gitee Go 云构建的原因：

- 后端是 Python 3.13 + pandas 3.x，Gitee Go 云构建的 Python 插件最高 3.9；
- 前端 Vite 8 需要 Node ≥ 20.19，云构建 Node 插件最高 15；
- 账号级 500 分钟/月，两个仓库一个月跑不了几轮（[计费说明](https://help.gitee.com/gitee-go/price)）；
- 发布要落到内网 PostgreSQL / ResearchEngine，本来就只能在部署网段执行。

构建机要求：

| 项 | 要求 |
|----|------|
| OS | Linux（Ubuntu 22.04 / Debian 12） |
| Docker | 24+，含 compose v2 插件（`docker compose version`） |
| Python | 3.11+，装 `python3-venv`（脚本自建 venv，不依赖 conda） |
| Node | 20.19+ / 22 LTS（`npm ci` 用 lockfile） |
| 内存 | ≥ 8GB；`pytest` 与镜像构建**串行**执行，不并发 |
| 磁盘 | 仓库分区 ≥ 20GB（镜像、node_modules、venv 都在这） |
| 网络 | Gitee、npm registry、PyPI、Docker Hub（或配镜像源） |

一次性体检：`bash scripts/ci/host-setup.sh`，缺什么会直接给补装命令；
`bash scripts/ci/host-setup.sh --write-env` 会生成带随机密码的 `deploy/.env`。

Gitee 侧配置：

1. 仓库 → 服务 → **Gitee Go** → 主机组，安装 agent，确认在线；
2. 把 `.workflow/*.yml` 里的 `hostGroupID: gitee-go` 换成实际 ID；
3. 用 `.workflow/*.yml` 新建流水线（Gitee Go 从仓库 **根目录 `.workflow/`** 读取配置）。

## 4. CI 做什么

`bash scripts/ci/backend-check.sh`：

- 校验 Python ≥ 3.11，建 `.ci/venv`，装 `backend/requirements-test.txt`；
- 没有 `DATABASE_URL` 时用 `postgres:16-alpine` 起一次性实例（默认 `:55432`），
  **必须**有它：`RefreshLockTest` 两个用例走 PostgreSQL advisory lock，缺库会失败；
- 注入测试用 `YG_RE_BASE` / `JWT_SECRET_KEY`（测试对 HTTP 全 mock，不需要真实 RE）；
- `python -m pytest tests -q`，基线 **106 passed**（无库时 2 failed）。

`bash scripts/ci/frontend-check.sh`：

- 校验 Node ≥ 20；
- `vite.config.ts` 强制要求 `backend/.env` 的 `YG_RE_BASE`：缺失时临时生成、
  退出时还原，不覆盖真实配置；
- `npm ci`（Windows 上自动退化为 `npm install`）→ `npm run build` → `npm test`，基线 **75 passed**。

`bash scripts/ci/docker-build.sh <tag>`：直接 `docker build` 两个 Dockerfile，
不碰 `deploy/.env`；只在 master push 阶段执行，PR 阶段跳过以省主机内存。

## 5. CD 做什么

`bash scripts/ci/deploy.sh <tag>`：

```text
打 tag 推送
  ↓
backup-db.sh <tag>              pg_dump → deploy/backups/*.sql.gz（失败即终止发布）
  ↓
docker-build.sh <tag>           镜像名带 tag，例如 svquant-backend:v1.3.0
  ↓
compose up -d --wait            等 db / backend / web 健康检查通过
  ↓
smoke.sh                        前端 /healthz、后端 /api/health，RE 网关只告警
  ↓
成功：写 deploy/.last-good.env（回滚点）
失败：用上一组镜像重新 up，再冒烟，最后退出码 1
```

跳过备份：`SKIP_DB_BACKUP=1 bash scripts/ci/deploy.sh <tag>`（仅限确认无数据变更时）。

编排文件：[`deploy/compose.yml`](../../deploy/compose.yml)。三个容器：

| 服务 | 镜像 | 端口 | 说明 |
|------|------|------|------|
| `db` | postgres:16-alpine | 仅内网 | 命名卷 `pgdata` |
| `backend` | `docker/backend.Dockerfile` | `127.0.0.1:8766` | 启动时 `bootstrap_schemas()` 自动建表 |
| `web` | `docker/frontend.Dockerfile` | `127.0.0.1:${WEB_PORT:-9530}` | Nginx 托管 dist + `/api` 反代 |

只绑 `127.0.0.1`：对外 TLS 由宿主机 Nginx/网关终止，配置参考
[`deploy/invest.nginx.conf`](../../deploy/invest.nginx.conf) 的写法。

## 6. 版本与发布规矩

- tag 格式 `vMAJOR.MINOR.PATCH`（可加 `-rc1` 后缀），**只从 `master` 打**，
  且该 commit 的 CI 必须是绿的；
- 部署的版本 = tag，`:latest` 不参与发布；
- 发布顺序：**RE 先发（保持契约向后兼容）→ SVQuant 后发**；RE 有破坏性变更时，
  先让 SVQuant 网关（`backend/services/core/re_http_gateway.py`）适配并发布，再发 RE；
- 回滚点只认 `deploy/.last-good.env`，不手工猜镜像。

发布检查清单：

1. `master` 的 `svquant-ci` 最近一次通过；
2. RE 已发布且 `/api/re/health` 在新环境可达；
3. 本次是否有破坏性数据变更？有则确认备份文件已生成且能解压；
4. `git tag vX.Y.Z && git push origin vX.Y.Z`；
5. 看 `svquant-release` 冒烟结果；失败先确认它是否已自动回滚，再决定人工介入。

回滚：

```bash
# 流水线没兜住时人工回滚（镜像粒度）
source deploy/.last-good.env
docker compose -f deploy/compose.yml --env-file deploy/.env up -d --wait

# 数据库回滚（只在确认需要时执行，会覆盖当前数据）
gunzip -c deploy/backups/svquant-<tag>-<时间戳>.sql.gz | \
  docker compose -f deploy/compose.yml --env-file deploy/.env exec -T db \
  psql -U svquant -d svquant
```

数据库回滚**不自动**：`bootstrap_schemas()` 只做增量建表，没有迁移版本表，
破坏性 DDL 前必须人工确认备份可用。

## 7. 服务器上怎么执行

```bash
# 构建机首次
git clone <repo> && cd SVQuant
bash scripts/ci/host-setup.sh              # 体检
bash scripts/ci/host-setup.sh --write-env  # 生成 deploy/.env（再填 YG_RE_BASE）

# 日常：不用手动，流水线会调；排障时可单步
bash scripts/ci/backend-check.sh
bash scripts/ci/frontend-check.sh
bash scripts/ci/docker-build.sh v1.3.0
bash scripts/ci/smoke.sh http://127.0.0.1:9530 http://127.0.0.1:8766
bash scripts/ci/backup-db.sh manual
```

## 8. ResearchEngine

RE 是独立仓库（`gitee.com/yanggu-yuanqi-intelligence/research-engine`），
本仓库只有它的 `.pyc` 残留，**不含源码**，因此 RE 的流水线不能放在本仓。
模板在 [`deploy/re-template/`](../../deploy/re-template/README.md)：复制到 RE 仓库，
确认入口、端口、测试命令后启用。

RE 的回测结果用 SQLite（`output` 命名卷），发布前备份方式：

```bash
docker run --rm -v research-engine_re-output:/data -v "$PWD/deploy/backups":/backup alpine \
  tar czf /backup/re-output-$(date +%Y%m%d-%H%M%S).tgz -C /data .
```

## 9. 当前边界（未纳入）

- Playwright E2E（`tests/e2e/`）需要真实前端+后端+RE，未接流水线；在构建机上按需执行。
- 回测/因子重计算类性能测试未纳入 PR 门禁，避免吃满 500 分钟额度。
- 暂无镜像漏洞扫描与依赖升级机器人；需要时在 `stage-image` 后加 `trivy` 步骤。
- 容器当前以 root 运行，加固（非 root 用户 + 只读根文件系统）待排期。
- 单机构建机是单点：它宕机时 CI 与发布同时不可用。
