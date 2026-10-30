# RE 仓库 CI/CD 模板

ResearchEngine 是独立仓库（`gitee.com/yanggu-yuanqi-intelligence/research-engine`），
SVQuant 仓库里只有它的 `.pyc` 残留，没有源码，所以 CI/CD 文件必须落在那边的仓库里。
本目录是可直接复制过去的模板。

触发方式与 SVQuant 一致：**Gitee WebHook → 服务器接收器 → 脚本**（见
[ADR-035](../../docs/技术决策/ADR-035-CI触发改为Gitee-WebHook.md)），不使用 Gitee Go。

## 1. 复制哪些文件

```text
re-template/
├── Dockerfile              → RE 仓库根目录
├── compose.yml             → RE 仓库根目录
└── scripts/ci/re-check.sh  → RE 仓库 scripts/ci/
```

```bash
# 在 RE 仓库根目录执行（$TPL 指向本目录）
cp "$TPL/Dockerfile" "$TPL/compose.yml" .
mkdir -p scripts/ci
cp "$TPL/scripts/ci/re-check.sh" scripts/ci/
chmod +x scripts/ci/re-check.sh
```

触发与部署脚本从 SVQuant 仓库复制（同一套，避免两处维护）：

```bash
# 假设 SVQuant 检出在 /opt/SVQuant
cp /opt/SVQuant/scripts/ci/webhook-job.sh /opt/SVQuant/scripts/ci/webhook-install.sh RE仓库/scripts/ci/
cp -r /opt/SVQuant/deploy/webhook RE仓库/deploy/
```

`webhook-job.sh` 里的 `deploy` 分支默认调用 `scripts/ci/deploy.sh`；RE 没有
`deploy.sh`，复制过去后把该行改成调用 RE 自己的发布脚本（可参照 SVQuant 的写法，
用 `docker compose up -d --wait` + 健康检查 + 失败回滚上一 tag）。

## 2. 必须先核对的四件事

模板按 SVQuant 侧观察到的形状写，**没有在 RE 源码上验证过**，落地前逐项确认：

| 项 | 模板假设 | 怎么确认 |
|----|----------|----------|
| ASGI 入口 | `app.api.app:app` | `grep -rn "FastAPI(" app/`，看 app 对象在哪个模块 |
| 端口 | `9527` | `grep -rn "uvicorn.run\|--port" .`，以 RE 实际启动命令为准 |
| 依赖清单 | 仓库根 `requirements.txt` | `ls requirements*.txt`，虚拟环境/conda 是否另装系统包 |
| 健康路径 | `/api/health` | `grep -rn "health" app/api/routes/` |
| 测试命令 | `python -m pytest tests -q` | 先在服务器跑一遍，记录失败基线；依赖 marketdata 的用例标记 `skipif` |

## 3. 流水线设计

与 SVQuant 同构，两仓都跑在同一台服务器上：

- **CI**：推送到 `master` → `scripts/ci/re-check.sh`（venv + 依赖 + pytest）；
- **发布**：推 `v*` tag → 构建镜像 → `docker compose up -d --wait` → 健康检查 → 失败回滚上一 tag。

安装第二个接收器实例（与 SVQuant 的互不影响）：

```bash
cd /opt/research-engine
sudo bash scripts/ci/webhook-install.sh --name re-webhook --port 8789 --user svquant
# 然后在 Gitee 的 RE 仓库配 WebHook：
#   URL  https://<域名>/hooks/re      （Nginx 把 /hooks/re 反代到 127.0.0.1:8789）
```

发布顺序：**RE 先发，SVQuant 后发**。RE 的 API 契约必须向后兼容；破坏性变更时
先让 SVQuant 网关（`backend/services/core/re_http_gateway.py`）适配并发布，再发 RE。

## 4. 与 SVQuant 的边界

- RE 不导入 SVQuant 的任何代码；SVQuant 不读 RE 的 SQLite 和行情目录。
- SVQuant 通过 `YG_RE_BASE` 访问 RE；RE 部署地址变更只改 SVQuant 的 `deploy/.env`。
- `marketdata` 以只读卷挂进 RE 容器，RE 的 `output` 用命名卷，均不进 Git。
- 两个仓库各自有 `.last-good.env` 回滚点，互不依赖。
- 两个接收器实例各自一个 `flock` 文件，互不阻塞。

## 5. 常见坑

- 构建机同时装 conda 与系统 Python 时，脚本里固定用 venv（`python3 -m venv`），
  不要 `conda activate`，否则 systemd 服务的非交互 shell 里找不到 conda 钩子。
- RE 测试依赖真实行情文件时，用 `pytest.mark.skipif` 按 `RE_CI_HAS_MARKETDATA` 跳过，
  不要默认读取生产目录。
- 首次部署前确认宿主机 `9527` 未被占用；RE 与 SVQuant 的 `db` 不是同一个实例。
- 接收器和 SVQuant 的接收器同名会互相覆盖：务必用不同的 `--name` 与 `--port`。
