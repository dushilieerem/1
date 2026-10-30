#!/usr/bin/env bash
# 在服务器上安装 Gitee WebHook 接收器（systemd 服务）。
#
# 用法（需要 root）：
#   sudo bash scripts/ci/webhook-install.sh
#   sudo bash scripts/ci/webhook-install.sh --user svquant --port 8788
#
# 做的事：
#   1. 生成签名密钥并写入 /etc/svquant/webhook.env（600 权限）
#   2. 按模板安装 /etc/systemd/system/svquant-webhook.service
#   3. 启动服务并做一次本地健康检查
# 不做：装 Nginx、改防火墙、在 Gitee 后台建 WebHook——这三件在输出里给出具体值。
set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)"
UNIT_TEMPLATE="$ROOT_DIR/deploy/webhook/svquant-webhook.service"
ENV_DIR="/etc/svquant"
ENV_DIR="/etc/svquant"
SERVICE_NAME="svquant-webhook"
RUN_USER="${SUDO_USER:-$(id -un)}"
PORT=8788

while [[ $# -gt 0 ]]; do
  case "$1" in
    --user) RUN_USER="$2"; shift 2 ;;
    --port) PORT="$2"; shift 2 ;;
    --name) SERVICE_NAME="$2"; shift 2 ;;
    -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
    *) echo "未知参数：$1" >&2; exit 2 ;;
  esac
done

# 同名服务共用一套环境文件，方便 SVQuant 与 ResearchEngine 各跑一个实例
ENV_FILE="$ENV_DIR/${SERVICE_NAME}.env"
UNIT_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

log() { printf '[webhook-install] %s\n' "$*"; }
die() { printf '错误：%s\n' "$*" >&2; exit 1; }

[[ "$(id -u)" == "0" ]] || die "需要 root（sudo）"
[[ -f "$UNIT_TEMPLATE" ]] || die "缺少模板 $UNIT_TEMPLATE"
id "$RUN_USER" >/dev/null 2>&1 || die "用户 $RUN_USER 不存在"
command -v flock >/dev/null 2>&1 || die "缺少 flock（apt install util-linux）"

PYTHON_BIN="$(command -v python3 || true)"
[[ -n "$PYTHON_BIN" ]] || die "缺少 python3"

if id -nG "$RUN_USER" | tr ' ' '\n' | grep -qx docker; then
  log "用户 $RUN_USER 已在 docker 组"
else
  log "警告：$RUN_USER 不在 docker 组，部署任务会失败；先执行 usermod -aG docker $RUN_USER"
fi

mkdir -p "$ENV_DIR"
chmod 700 "$ENV_DIR"

if [[ -f "$ENV_FILE" ]]; then
  log "已存在 $ENV_FILE，沿用旧配置（要轮换密钥请先删掉该文件）"
else
  SECRET="$(openssl rand -hex 32 2>/dev/null || head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n')"
  cat > "$ENV_FILE" <<EOF
# SVQuant Gitee WebHook 配置（600 权限，勿提交仓库）
WEBHOOK_HOST=127.0.0.1
WEBHOOK_PORT=$PORT
WEBHOOK_SECRET=$SECRET
WEBHOOK_BRANCH=master
WEBHOOK_TAG_PREFIX=v
WEBHOOK_REPO_DIR=$ROOT_DIR
WEBHOOK_LOG_DIR=$ROOT_DIR/deploy/webhook-logs
WEBHOOK_LOCK_FILE=/tmp/${SERVICE_NAME}.lock
EOF
  chmod 600 "$ENV_FILE"
  log "已生成 $ENV_FILE"
fi

sed -e "s|__REPO_DIR__|$ROOT_DIR|g" \
    -e "s|__RUN_USER__|$RUN_USER|g" \
    -e "s|__PYTHON__|$PYTHON_BIN|g" \
    "$UNIT_TEMPLATE" > "$UNIT_FILE"
chmod 644 "$UNIT_FILE"

systemctl daemon-reload
systemctl enable --now "$SERVICE_NAME" >/dev/null
sleep 1

if ! systemctl is-active --quiet "$SERVICE_NAME"; then
  journalctl -u "$SERVICE_NAME" -n 30 --no-pager || true
  die "服务未启动"
fi

if curl -fsS --max-time 5 "http://127.0.0.1:${PORT}/healthz" >/dev/null; then
  log "健康检查通过：http://127.0.0.1:${PORT}/healthz"
else
  journalctl -u "$SERVICE_NAME" -n 30 --no-pager || true
  die "健康检查失败"
fi

cat <<EOF

下一步：
1) 把下面地址配到 Gitee 仓库 → 管理 → WebHooks（勾选 Push、Tag Push 事件）：
   https://你的域名/hooks/gitee
   （Nginx 反代配置见 deploy/webhook/nginx.conf.example）

2) 密钥（Gitee 里选「签名密钥」模式，粘贴下面这串）：
$(sed -n 's/^WEBHOOK_SECRET=//p' "$ENV_FILE")

3) 本地自测（应返回 ignored，说明签名链路通了）：
   python3 $ROOT_DIR/deploy/webhook/selftest.py --env $ENV_FILE

   想验证 CI 真能触发（会真的跑一遍门禁）：
   python3 $ROOT_DIR/deploy/webhook/selftest.py --env $ENV_FILE --ref refs/heads/master

4) 看任务日志：
   journalctl -u "$SERVICE_NAME" -f
   ls -lt $ROOT_DIR/deploy/webhook-logs/ | head
EOF
