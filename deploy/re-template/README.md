# RE 仓库 CI/CD 模板

ResearchEngine 是独立仓库（`gitee.com/yanggu-yuanqi-intelligence/research-engine`），
SVQuant 仓库里只有它的 `.pyc` 残留，没有源码，所以流水线文件必须落在那边的仓库里。
本目录是可直接复制过去的模板。

## 1. 复制哪些文件

```text
re-template/
├── Dockerfile              → RE 仓库根目录
├── compose.yml             → RE 仓库根目录
├── workflow/
│   ├── re-ci.yml           → RE 仓库 .workflow/re-ci.yml
│   └── re-release.yml      → RE 仓库 .workflow/re-release.yml
└── scripts/ci/re-check.sh  → RE 仓库 scripts/ci/
```

```bash
# 在 RE 仓库根目录执行（$TPL 指向本目录）
cp "$TPL/Dockerfile" "$TPL/compose.yml" .
mkdir -p .workflow scripts/ci
cp "$TPL/workflow/"*.yml .workflow/
cp "$TPL/scripts/ci/re-check.sh" scripts/ci/
chmod +x scripts/ci/re-check.sh
```

注意：模板放在 `workflow/` 而不是 `.workflow/`，避免 Gitee Go 把 SVQuant 仓库里的
RE 流水线也当成 SVQuant 自己的流水线加载；复制时才落到 RE 仓库的 `.workflow/`。

## 2. 必须先核对的四件事

模板按 SVQuant 侧观察到的形状写，**没有在 RE 源码上验证过**，落地前逐项确认：

| 项 | 模板假设 | 怎么确认 |
|----|----------|----------|
| ASGI 入口 | `app.api.app:app` | `grep -rn "FastAPI(" app/`，看 app 对象在哪个模块 |
| 端口 | `9527` | `grep -rn "uvicorn.run\|--port" .`，以 RE 实际启动命令为准 |
| 依赖清单 | 仓库根 `requirements.txt` | `ls requirements*.txt`，虚拟环境/conda 是否另装系统包 |
| 健康路径 | `/api/health` | `grep -rn "health" app/api/routes/` |
| 测试命令 | `python -m pytest tests -q` | 本地先跑一遍，记录失败基线；需要 marketdata 的用例要么给夹具要么标记跳过 |

## 3. 流水线设计

与 SVQuant 完全同构，理由是两仓需要联调、且都跑在同一台构建机上：

- `re-ci`：PR / master push → `scripts/ci/re-check.sh`（venv + 依赖 + pytest）
  → 镜像可构建。
- `re-release`：`v*` tag → 构建嵌套镜像 → `docker compose up -d --wait`
  → `curl` 健康检查 → 失败回滚上一 tag。

发布顺序：**RE 先发，SVQuant 后发**。RE 的 API 契约必须向后兼容；破坏性变更时
先让 SVQuant 网关（`backend/services/core/re_http_gateway.py`）适配并发布，再发 RE。

## 4. 与 SVQuant 的边界

- RE 不导入 SVQuant 的任何代码；SVQuant 不读 RE 的 SQLite 和行情目录。
- SVQuant 通过 `YG_RE_BASE` 访问 RE；RE 部署地址变更只改 SVQuant 的 `deploy/.env`。
- `marketdata` 以只读卷挂进 RE 容器，RE 的 `output` 用命名卷，均不进 Git。
- 两个仓库各自有 `.last-good.env` 回滚点，互不依赖。

## 5. 常见坑

- 构建机同时装 conda 与系统 Python 时，脚本里固定用 venv（`python3 -m venv`），
  不要 `conda activate`，否则 agent 的非交互 shell 里找不到 conda 钩子。
- RE 测试若依赖真实行情文件，CI 里要么挂只读样本目录，要么用 `pytest.mark.skipif`
  按 `RE_CI_HAS_MARKETDATA` 环境变量跳过，不要默认读取生产目录。
- 首次部署前确认宿主机上 `9527` 未被占用；RE 与 SVQuant 的 `db` 不是同一个实例。
