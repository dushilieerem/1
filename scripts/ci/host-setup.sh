#!/usr/bin/env bash
# 构建机/部署机一次性体检（默认只检查，不改系统）。
#
# 用法：
#   bash scripts/ci/host-setup.sh              # 只体检，列出缺口和补装命令
#   bash scripts/ci/host-setup.sh --write-env  # 缺 deploy/.env 时生成一份（随机密码，YG_RE_BASE 待填）
#
# 不在本机跑测试是硬规矩：本脚本也不装 node/python，只告诉你在服务器上要装什么。
set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)"
ENV_FILE="$ROOT_DIR/deploy/.env"
ENV_EXAMPLE="$ROOT_DIR/deploy/.env.example"
WRITE_ENV=0
[[ "${1:-}" == "--write-env" ]] && WRITE_ENV=1

FAILS=()
WARNS=()

ok()   { printf '  [OK]   %s\n' "$*"; }
bad()  { printf '  [缺失] %s\n' "$*"; FAILS+=("$*"); }
warn() { printf '  [注意] %s\n' "$*"; WARNS+=("$*"); }

need_cmd() {
  if command -v "$1" >/dev/null 2>&1; then ok "$1"; else bad "$1（$2）"; fi
}

printf '== 系统 ==\n'
printf '  %s\n' "$(uname -srm 2>/dev/null || echo unknown)"

printf '\n== 必需命令 ==\n'
need_cmd git "apt install git"
need_cmd docker "安装 docker 24+"
need_cmd openssl "apt install openssl"
need_cmd curl "apt install curl"
need_cmd gzip "apt install gzip"

printf '\n== Docker Compose v2 ==\n'
if docker compose version >/dev/null 2>&1; then
  ok "$(docker compose version --short 2>/dev/null || echo 'compose v2')"
else
  bad "docker compose 插件（安装 docker-compose-plugin）"
fi

printf '\n== Python ==\n'
if command -v python3 >/dev/null 2>&1; then
  PYVER="$(python3 -c 'import sys;print("%d.%d.%d"%sys.version_info[:3])')"
  if python3 -c 'import sys;sys.exit(0 if sys.version_info>=(3,11) else 1)'; then
    ok "python3 $PYVER"
  else
    bad "python3 $PYVER（需要 >= 3.11）"
  fi
  if python3 -c 'import venv' >/dev/null 2>&1; then ok "venv 模块"; else bad "python3-venv"; fi
else
  bad "python3（需要 >= 3.11）"
fi

printf '\n== Node ==\n'
if command -v node >/dev/null 2>&1; then
  NODE_MAJOR="$(node -p 'process.versions.node.split(".")[0]')"
  if (( NODE_MAJOR >= 20 )); then ok "node $(node -v)"; else bad "node $(node -v)（Vite 8 需要 >= 20.19）"; fi
  if command -v npm >/dev/null 2>&1; then ok "npm $(npm -v)"; else bad "npm"; fi
else
  bad "node >= 20（推荐 NodeSource 或 nvm 安装 LTS）"
fi

printf '\n== 资源 ==\n'
MEM_GB=$(awk '/MemTotal/ {printf "%.1f", $2/1048576}' /proc/meminfo 2>/dev/null || echo 0)
if awk "BEGIN{exit !($MEM_GB >= 8)}"; then
  ok "内存 ${MEM_GB}GB"
else
  warn "内存 ${MEM_GB}GB（同时跑 pytest 与镜像构建建议 >= 8GB）"
fi
AVAIL_GB=$(df -Pk "$ROOT_DIR" 2>/dev/null | awk 'NR==2 {printf "%.1f", $4/1048576}')
if awk "BEGIN{exit !($AVAIL_GB >= 20)}"; then
  ok "仓库所在分区剩余 ${AVAIL_GB}GB"
else
  warn "仓库所在分区只剩 ${AVAIL_GB}GB（镜像与 node_modules 建议 >= 20GB）"
fi

printf '\n== 部署配置 ==\n'
if [[ -f "$ENV_FILE" ]]; then
  ok "deploy/.env 已存在"
  for k in POSTGRES_PASSWORD JWT_SECRET_KEY YG_RE_BASE; do
    v="$(sed -n "s/^$k=//p" "$ENV_FILE" | head -n1)"
    if [[ -z "$v" ]]; then bad "deploy/.env 的 $k 为空"; else ok "$k 已填写"; fi
  done
elif [[ "$WRITE_ENV" == "1" ]]; then
  cp "$ENV_EXAMPLE" "$ENV_FILE"
  PG_PW="$(openssl rand -base64 24 | tr -d '\n=+/' | cut -c1-24)"
  JWT="$(openssl rand -base64 48 | tr -d '\n')"
  sed -i "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=${PG_PW}|" "$ENV_FILE"
  sed -i "s|^JWT_SECRET_KEY=.*|JWT_SECRET_KEY=${JWT}|" "$ENV_FILE"
  chmod 600 "$ENV_FILE"
  ok "已生成 deploy/.env（YG_RE_BASE 仍需手工填写）"
  warn "POSTGRES_PASSWORD / JWT_SECRET_KEY 已随机生成；YG_RE_BASE 必须手工填 RE 地址"
else
  bad "deploy/.env 不存在（重跑加 --write-env，或手工 cp deploy/.env.example deploy/.env）"
fi

printf '\n== 结论 ==\n'
if (( ${#FAILS[@]} == 0 )); then
  printf '  可以跑流水线。记得在 Gitee「服务 → Gitee Go → 主机组」里确认 agent 在线。\n'
else
  printf '  还有 %d 项缺失，按上面的命令补齐后重跑本脚本。\n' "${#FAILS[@]}"
fi
if (( ${#WARNS[@]} > 0 )); then
  printf '  另有 %d 条提醒，不阻塞。\n' "${#WARNS[@]}"
fi

(( ${#FAILS[@]} == 0 )) || exit 1
