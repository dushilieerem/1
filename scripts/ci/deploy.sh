#!/usr/bin/env bash
# 发布：构建带标签镜像 → compose 起新版本 → 冒烟 → 失败自动回滚上一组镜像。
# 用法：bash scripts/ci/deploy.sh [tag]
# 前置：deploy/.env 已配置；宿主机已登录镜像仓库（仅 REGISTRY 模式需要）。
set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)"
COMPOSE_FILE="$ROOT_DIR/deploy/compose.yml"
ENV_FILE="$ROOT_DIR/deploy/.env"
LAST_GOOD="$ROOT_DIR/deploy/.last-good.env"
IMAGE_PREFIX="${IMAGE_PREFIX:-svquant}"
REGISTRY="${REGISTRY:-}"

log() { printf '[deploy] %s\n' "$*" >&2; }

[[ -f "$ENV_FILE" ]] || { log "缺少 deploy/.env"; exit 1; }

# 宿主机端口优先取 deploy/.env（生产与开发端口分离），再退回环境变量/默认值
env_val() { sed -n "s/^$1=//p" "$ENV_FILE" | head -n1; }
WEB_PORT_GUESS="${WEB_PORT:-$(env_val WEB_PORT)}"
WEB_PORT_GUESS="${WEB_PORT_GUESS:-9630}"
API_PORT="${API_PORT:-$(env_val BACKEND_PORT)}"
API_PORT="${API_PORT:-9766}"
WEB_BASE="http://127.0.0.1:${WEB_PORT_GUESS}"
API_BASE="http://127.0.0.1:${API_PORT}"

TAG="${1:-}"
if [[ -z "$TAG" ]]; then
  TAG="$(git -C "$ROOT_DIR" describe --tags --exact-match 2>/dev/null || git -C "$ROOT_DIR" rev-parse --short HEAD)"
fi

IMAGE_BASE="$IMAGE_PREFIX"
[[ -n "$REGISTRY" ]] && IMAGE_BASE="$REGISTRY/$IMAGE_PREFIX"
NEW_BACKEND="$IMAGE_BASE-backend:$TAG"
NEW_WEB="$IMAGE_BASE-web:$TAG"

compose() {
  BACKEND_IMAGE="$1" WEB_IMAGE="$2" \
    docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" "${@:3}"
}

# 读取上一组已验证镜像作为回滚目标（grep 取值，避免 source 覆盖上面的新 tag）
PREV_BACKEND=""
PREV_WEB=""
if [[ -f "$LAST_GOOD" ]]; then
  PREV_BACKEND="$(sed -n 's/^BACKEND_IMAGE=//p' "$LAST_GOOD" | head -n1)"
  PREV_WEB="$(sed -n 's/^WEB_IMAGE=//p' "$LAST_GOOD" | head -n1)"
fi

log "发布 $TAG（$NEW_BACKEND / $NEW_WEB）"
bash "$ROOT_DIR/scripts/ci/docker-build.sh" "$TAG"

# 没有迁移框架，破坏性变更只能靠备份兜底；备份失败就不发布
if [[ "${SKIP_DB_BACKUP:-0}" != "1" ]]; then
  bash "$ROOT_DIR/scripts/ci/backup-db.sh" "$TAG" || { log "数据库备份失败，终止发布"; exit 1; }
fi

log "启动新版本"
if ! compose "$NEW_BACKEND" "$NEW_WEB" up -d --wait --wait-timeout 300; then
  log "compose 启动失败"
  START_OK=0
else
  START_OK=1
fi

if [[ "$START_OK" == "1" ]] && bash "$ROOT_DIR/scripts/ci/smoke.sh" "$WEB_BASE" "$API_BASE"; then
  printf 'BACKEND_IMAGE=%s\nWEB_IMAGE=%s\n' "$NEW_BACKEND" "$NEW_WEB" > "$LAST_GOOD"
  log "发布成功，已记录回滚点 $LAST_GOOD"
  exit 0
fi

log "发布未通过，开始回滚"
if [[ -n "$PREV_BACKEND" && -n "$PREV_WEB" ]]; then
  log "回滚到 $PREV_BACKEND / $PREV_WEB"
  if compose "$PREV_BACKEND" "$PREV_WEB" up -d --wait --wait-timeout 300; then
    bash "$ROOT_DIR/scripts/ci/smoke.sh" "$WEB_BASE" "$API_BASE" || \
      log "警告：回滚后冒烟仍失败，需要人工介入"
  else
    log "回滚启动失败，需要人工介入"
  fi
else
  log "没有可用回滚点（首次发布？），请人工处理"
fi
exit 1
