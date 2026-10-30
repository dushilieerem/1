# CI/CD 设计与操作手册

本文回答三件事：提交后自动跑什么、打 tag 后自动部署什么、失败怎么回滚。
不覆盖需求与验收流程，那部分见[需求到交付工作流](../治理/需求到交付工作流.md)。

## 1. 结论

CI/CD 用 **Gitee WebHook + 服务器脚本** 实现，不用 Gitee Go（主机组在账号里没有入口，见
[ADR-035](../技术决策/ADR-035-CI触发改为Gitee-WebHook.md)）：

| 触发 | 动作 | 执行内容 |
|------|------|----------|
| 推送到 `master` | CI | `scripts/ci/webhook-job.sh ci`：后端 pytest + 前端构建与单测 |
| 推送 `v*` tag | 发布 | `scripts/ci/webhook-job.sh deploy`：备份库 → 构建带 tag 镜像 → compose 部署 → 冒烟 → 失败回滚 |
| 手动 | 同上 | 直接跑 `scripts/ci/*.sh`，不经过 WebHook |

```text
git push / git tag v1.0.0
        │
        ▼
Gitee WebHook（Push / Tag Push，签名密钥）
        │ HTTPS
        ▼
宿主机 Nginx  /hooks/gitee → 127.0.0.1:8788
        ▼
deploy/webhook/server.py   验签 → 分类 → flock 串行
        ├── refs/heads/master → webhook-job.sh ci
        └── refs/tags/v*      → webhook-job.sh deploy
```

原则：

1. **CI 只读**：不部署，只跑测试与构建校验；部署只由 tag 触发。
2. **发布只认 tag**：部署的版本号等于一个 Git tag，可追溯、可回滚。
3. **逻辑不绑平台**：触发方式可换，但构建/测试/部署全部在 `scripts/ci/*.sh`，
   换成 Jenkins、GitLab CI 或人工执行都成立。
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

## 4. 安装 WebHook 接收器

```bash
sudo bash scripts/ci/webhook-install.sh --user <运行用户>
```

脚本会生成 `/etc/svquant/svquant-webhook.env`（随机签名密钥，600 权限）、安装并启动
`svquant-webhook.service`、做本地健康检查，最后打印要填进 Gitee 的地址与密钥。

然后在 Gitee：仓库 → 管理 → **WebHooks** → 添加：

| 项 | 值 |
|---|---|
| URL | `https://<域名>/hooks/gitee` |
| 密码/签名密钥 | 用「签名密钥」模式，粘贴脚本打印的密钥 |
| 事件 | **Push**、**Tag Push** |
| SSL 校验 | 证书有效时保持开启 |

Nginx 反代片段见 [`deploy/webhook/nginx.conf.example`](../../deploy/webhook/nginx.conf.example)，
细节与排障见 [`deploy/webhook/README.md`](../../deploy/webhook/README.md)。

自测：

```bash
curl -fsS http://127.0.0.1:8788/healthz
python3 deploy/webhook/selftest.py                              # 期望 ignored
python3 deploy/webhook/selftest.py --ref refs/heads/master      # 真跑一次 CI
```

## 5. CI 做什么

`bash scripts/ci/backend-check.sh`：

- 校验 Python ≥ 3.11，建 `.ci/venv`，装 `backend/requirements-test.txt`；
- 没有 `DATABASE_URL` 时用 `postgres:16-alpine` 起一次性实例（默认 `:55432`），
  **必须**有它：`RefreshLockTest` 两个用例走 PostgreSQL advisory lock；
- 注入测试用 `YG_RE_BASE` / `JWT_SECRET_KEY`（测试对 HTTP 全 mock）；
- `python -m pytest tests -q`，基线 **106 passed**（无库时 2 failed）。

`bash scripts/ci/frontend-check.sh`：

- 校验 Node ≥ 20；
- `vite.config.ts` 强制要求 `backend/.env` 的 `YG_RE_BASE`：缺失时临时生成、退出时还原；
- `npm ci`（Windows 自动退化为 `npm install`）→ `npm run build` → `npm test`，基线 **75 passed**。

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
失败：用上一组镜像重新 up，再冒烟，最后退出码 1
```

跳过备份：`SKIP_DB_BACKUP=1 bash scripts/ci/deploy.sh <tag>`（仅限确认无数据变更时）。

编排文件：[`deploy/compose.yml`](../../deploy/compose.yml)：

| 服务 | 镜像 | 端口 | 说明 |
|------|------|------|------|
| `db` | postgres:16-alpine | 仅内网 | 命名卷 `pgdata` |
| `backend` | `docker/backend.Dockerfile` | `127.0.0.1:8766` | 启动时 `bootstrap_schemas()` 自动建表 |
| `web` | `docker/frontend.Dockerfile` | `127.0.0.1:${WEB_PORT:-9530}` | Nginx 托管 dist + `/api` 反代 |

## 7. 版本与发布规矩

- tag 格式 `vMAJOR.MINOR.PATCH`（可加 `-rc1`），**只从 `master` 打**，且该 commit 的 CI 绿；
- 部署版本 = tag，`:latest` 不参与发布；
- 顺序：**RE 先发（契约向后兼容）→ SVQuant 后发**；
- 回滚点只认 `deploy/.last-good.env`。

发布检查清单：

1. 最近一次 master push 的 CI 通过（`deploy/webhook-logs/` 里对应日志 exit 0）；
2. RE 已发布且 `/api/re/health` 可达；
3. 有破坏性数据变更时，确认 `deploy/backups/` 里已有备份且能解压；
4. `git tag vX.Y.Z && git push origin vX.Y.Z`；
5. 看 WebHook 任务日志与冒烟结果。

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
RE 的 CI/CD 用同一套接收器：在 RE 仓库放 `scripts/ci/re-check.sh`，再装一个实例：

```bash
sudo bash scripts/ci/webhook-install.sh --name re-webhook --port 8789 --user svquant
```

Gitee 侧给 RE 仓库配一条 WebHook 指向 `https://<域名>/hooks/re`（或同路径不同端口反代）。
模板与入口核对清单见 [`deploy/re-template/`](../../deploy/re-template/README.md)。

RE 的回测结果用 SQLite（`output` 命名卷），发布前备份：

```bash
docker run --rm -v research-engine_re-output:/data -v "$PWD/deploy/backups":/backup alpine \
  tar czf /backup/re-output-$(date +%Y%m%d-%H%M%S).tgz -C /data .
```

## 9. 当前边界（未纳入）

- PR 事件未接入：PR 阶段不自动跑，合并进 `master` 才跑 CI。需要时给 WebHook 勾选
  Pull Request 事件并在 `server.py` 里加分支。
- Playwright E2E（`tests/e2e/`）需要前端+后端+RE 同时在跑，未接自动触发。
- 没有把结果回写 Gitee（commit status / PR 评论），失败只能看服务器日志。
- 镜像漏洞扫描、依赖升级机器人未接入。
- 容器当前以 root 运行，加固待排期。
- 单机接收器是单点：它挂掉时推送不会触发，但不会影响已部署服务。
