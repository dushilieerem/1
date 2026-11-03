#!/usr/bin/env bash
# 安装 SVQuant 数据自动同步 timer（需要 root）。
# 用法：
#   sudo REPO_DIR=/home/dev01/svquant-deploy PYTHON=/home/dev01/program/anaconda3/bin/python \
#        RUN_USER=dev01 ./deploy/systemd/install-data-sync.sh
set -euo pipefail

REPO_DIR="${REPO_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}"
PYTHON="${PYTHON:-/home/dev01/program/anaconda3/bin/python}"
RUN_USER="${RUN_USER:-dev01}"
NAME="svquant-data-sync"
UNIT_DIR="/etc/systemd/system"
ENV_FILE="/etc/svquant/${NAME}.env"

if [[ "${EUID}" -ne 0 ]]; then
  echo "请用 root 运行（sudo）" >&2
  exit 1
fi

install -d -m 755 "$UNIT_DIR"
install -d -m 750 /etc/svquant
touch "$ENV_FILE"
chmod 600 "$ENV_FILE"

for unit in "${NAME}.service" "${NAME}.timer"; do
  sed \
    -e "s#__REPO_DIR__#${REPO_DIR}#g" \
    -e "s#__PYTHON__#${PYTHON}#g" \
    -e "s#__RUN_USER__#${RUN_USER}#g" \
    "${REPO_DIR}/deploy/systemd/${unit}" > "${UNIT_DIR}/${unit}"
done

systemctl daemon-reload
systemctl enable --now "${NAME}.timer"
systemctl --no-pager --full status "${NAME}.timer" || true
echo "已安装 ${NAME}.timer；日志：journalctl -u ${NAME}.service -f"
echo "环境文件：${ENV_FILE}（可放 DATABASE_URL / SVQUANT_DATA_ROOT）"
