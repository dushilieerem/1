#!/usr/bin/env bash
# 在服务器上安装内网轮询（systemd timer），把 Gitee 的 master / tag 变化接到 CI/CD。
#
# 用法（需要 root）：
#   sudo bash scripts/ci/poll-install.sh --user svquant
#   sudo bash scripts/ci/poll-install.sh --user svquant --interval 120 --name svquant-poll
#
# 做的事：
#   1. 写 /etc/svquant/<name>.env（状态目录、分支、tag 前缀）
#   2. 安装 <name>.service + <name>.timer 并启动
#   3. 立刻跑一次建立基线（不触发历史版本）
#   4. 检查运行用户能否 fetch 远端
set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)"
SERVICE_TEMPLATE="$ROOT_DIR/deploy/poll/svquant-poll.service"
TIMER_TEMPLATE="$ROOT_DIR/deploy/poll/svquant-poll.timer"
ENV_DIR="/etc/svquant"
NAME="svquant-poll"
RUN_USER="${SUDO_USER:-$(id -un)}"
INTERVAL=60
BRANCH=master
TAG_PREFIX=v
STATE_DIR=/var/lib/svquant

while [[ $# -gt 0 ]]; do
  case "$1" in
    --user) RUN_USER="$2"; shift 2 ;;
    --interval) INTERVAL="$2"; shift 2 ;;
    --name) NAME="$2"; shift 2 ;;
    --branch) BRANCH="$2"; shift 2 ;;
    --tag-prefix) TAG_PREFIX="$2"; shift 2 ;;
    --state-dir) STATE_DIR="$2"; shift 2 ;;
    -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
    *) echo "未知参数：$1" >&2; exit 2 ;;
  esac
done

log() { printf '[poll-install] %s\n' "$*"; }
die() { printf '错误：%s\n' "$*" >&2; exit 1; }

[[ "$(id -u)" == "0" ]] || die "需要 root（sudo）"
[[ -f "$SERVICE_TEMPLATE" && -f "$TIMER_TEMPLATE" ]] || die "缺少模板文件"
id "$RUN_USER" >/dev/null 2>&1 || die "用户 $RUN_USER 不存在"
[[ "$INTERVAL" =~ ^[0-9]+$ ]] && (( INTERVAL >= 30 )) || die "间隔至少 30 秒"

ENV_FILE="$ENV_DIR/${NAME}.env"
SERVICE_FILE="/etc/systemd/system/${NAME}.service"
TIMER_FILE="/etc/systemd/system/${NAME}.timer"

mkdir -p "$ENV_DIR" "$STATE_DIR"
chmod 700 "$ENV_DIR"
chown "$RUN_USER:$RUN_USER" "$STATE_DIR"
chmod 750 "$STATE_DIR"

cat > "$ENV_FILE" <<EOF
# SVQuant 内网轮询配置（由 poll-install.sh 生成）
POLL_STATE_DIR=$STATE_DIR
POLL_BRANCH=$BRANCH
POLL_TAG_PREFIX=$TAG_PREFIX
EOF
chmod 644 "$ENV_FILE"

install_unit() {
  local template="$1" target="$2"
  sed -e "s|__REPO_DIR__|$ROOT_DIR|g" \
      -e "s|__RUN_USER__|$RUN_USER|g" \
      -e "s|__NAME__|$NAME|g" \
      -e "s|__INTERVAL__|$INTERVAL|g" \
      -e "s|__STATE_DIR__|$STATE_DIR|g" \
      "$template" > "$target"
  chmod 644 "$target"
}

install_unit "$SERVICE_TEMPLATE" "$SERVICE_FILE"
install_unit "$TIMER_TEMPLATE" "$TIMER_FILE"

# 运行用户必须能拉取仓库；这一步失败会让轮询永远"无变化"
log "检查 $RUN_USER 能否 fetch 远端"
if sudo -u "$RUN_USER" git -C "$ROOT_DIR" fetch --prune --tags origin >/tmp/svquant-poll-fetch.log 2>&1; then
  log "fetch 正常"
else
  sed -n '1,10p' /tmp/svquant-poll-fetch.log
  die "fetch 失败：给 $RUN_USER 配 deploy key 或 access token 后再装"
fi

systemctl daemon-reload
systemctl enable --now "$NAME.timer" >/dev/null

# 先建立基线，避免一装上就把历史 tag 重新部署
log "建立基线（首次运行不会触发任务）"
systemctl start "$NAME.service" || true
sleep 1

if systemctl is-active --quiet "$NAME.timer"; then
  log "定时器已启动：$(systemctl list-timers "$NAME.timer" --no-pager | sed -n '2p')"
else
  journalctl -u "$NAME.service" -n 30 --no-pager || true
  die "定时器未启动"
fi

cat <<EOF

下一步：
1) 看一眼本轮日志（应显示"首次运行，建立基线"）：
   journalctl -u $NAME.service -n 30 --no-pager

2) 手动试跑（不改状态）：
   sudo -u $RUN_USER POLL_DRY_RUN=1 POLL_STATE_DIR=$STATE_DIR bash $ROOT_DIR/scripts/ci/poll.sh

3) 真实验证：往 master 推一个小改动，等 ${INTERVAL} 秒后看：
   journalctl -u $NAME.service -f

4) 强制重跑最近一次 CI（状态里记过就不会自动重试）：
   改完代码后直接推新提交即可；或手动
   sudo -u $RUN_USER bash $ROOT_DIR/scripts/ci/webhook-job.sh ci master

5) 发布：git tag v0.1.0 && git push origin v0.1.0，轮询会在一个间隔内部署
EOF
