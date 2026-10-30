# Gitee WebHook 接收器

Gitee Go 的主机组在你们的账号体系里没有入口，CI/CD 改用 **WebHook + 服务器脚本**：
Gitee 推送事件打到服务器上的一个小接收器，接收器校验签名后执行 `scripts/ci/*.sh`。
效果与流水线一致，但触发链完全在我们的服务器上，日志也在本机。

```text
git push / git tag v1.0.0
        │
        ▼
Gitee WebHook（Push / Tag Push 事件，带签名密钥）
        │  HTTPS
        ▼
宿主机 Nginx  /hooks/gitee → 127.0.0.1:8788
        │
        ▼
deploy/webhook/server.py   校验签名 → 判断事件 → flock 串行
        │
        ├── refs/heads/master   → scripts/ci/webhook-job.sh ci     （后端 + 前端门禁）
        └── refs/tags/v*        → scripts/ci/webhook-job.sh deploy （备份→构建→部署→冒烟→回滚）
```

## 文件

| 文件 | 作用 |
|---|---|
| `server.py` | 接收器：验签、分类事件、用 `flock` 串行拉起任务，只监听 127.0.0.1 |
| `selftest.py` | 本地模拟一条签名请求，验证链路 |
| `nginx.conf.example` | 宿主 Nginx 的 `location` 片段（TLS 终止 + 反代） |
| `svquant-webhook.service` | systemd 单元模板，由安装脚本替换占位符 |

## 安装（服务器，root）

```bash
git clone https://gitee.com/yanggu-yuanqi-intelligence/SVQuant.git /opt/SVQuant
cd /opt/SVQuant
sudo bash scripts/ci/webhook-install.sh --user svquant
```

脚本会：生成 `/etc/svquant/svquant-webhook.env`（随机签名密钥，600 权限）→ 安装并启动
`svquant-webhook.service` → 本地健康检查 → 打印要在 Gitee 填的地址与密钥。

RE 仓库要独立触发时，加 `--name re-webhook --port 8789`，用同一套模板装第二个实例。

## 在 Gitee 里加 WebHook

仓库 → **管理** → **WebHooks** → 添加：

| 项 | 值 |
|---|---|
| URL | `https://<你的域名>/hooks/gitee` |
| 密码 / 签名密钥 | 用安装脚本打印的密钥，选**签名密钥**模式 |
| 事件 | 勾选 **Push**、**Tag Push**（PR 事件不需要） |
| SSL 校验 | 证书有效时保持开启 |

## 验证

```bash
# 1. 服务活着
curl -fsS http://127.0.0.1:8788/healthz

# 2. 签名链路（返回 ignored 即通过，不会真跑任务）
python3 deploy/webhook/selftest.py

# 3. 真触发一次 CI（会跑后端 + 前端门禁，耗时数分钟）
python3 deploy/webhook/selftest.py --ref refs/heads/master

# 4. 看任务日志
journalctl -u svquant-webhook -f
ls -lt deploy/webhook-logs/ | head
```

## 安全要点

- 接收器**只监听 127.0.0.1**，公网入口只有 Nginx 那一条 `location`；
- 必须配置签名密钥（`WEBHOOK_SECRET`），否则所有请求 500 拒绝；
- 校验 `X-Gitee-Timestamp` 与本地时间差 ≤ 1 小时，防重放；
- 同一时刻只跑一个任务（`flock`），避免 `git checkout` 与 `compose build` 互相踩；
- 任务以运行用户身份执行，该用户需在 `docker` 组；不要用 root 跑服务；
- 工作区有未提交改动时 `webhook-job.sh` 直接拒绝更新，不静默覆盖。

## 常见问题

| 现象 | 原因 / 处理 |
|---|---|
| Gitee 显示 401 | 密钥不一致：Gitee 里选的是签名模式，却填了密码；重新复制安装脚本打印的密钥 |
| 返回 429 busy | 上一个任务还在跑；看 `webhook-job-logs` 或 `journalctl`，等它结束 |
| 任务日志里 `git fetch` 失败 | 运行用户没有仓库读权限：给它配 deploy key 或 token |
| 部署成功但页面没变 | 看 `deploy/.last-good.env` 与 `docker compose ps`；Nginx 静态缓存需 `no-cache` |
| 接收器起不来 | `journalctl -u svquant-webhook -n 50`，多半是 `webhook.env` 缺 `WEBHOOK_SECRET` |
