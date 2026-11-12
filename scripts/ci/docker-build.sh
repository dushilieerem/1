#!/usr/bin/env bash
# 构建 SVQuant 前后端镜像并打上发布标签（不需要 deploy/.env）。
# 用法：bash scripts/ci/docker-build.sh [tag]
#   tag 缺省取 git tag（精确匹配 HEAD），再退化为 commit 短 SHA。
# 可选：IMAGE_PREFIX（默认 svquant）、REGISTRY（填了才 push）。
set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)"
IMAGE_PREFIX="${IMAGE_PREFIX:-svquant}"
REGISTRY="${REGISTRY:-}"

log() { printf '[docker-build] %s\n' "$*" >&2; }

TAG="${1:-}"
if [[ -z "$TAG" ]]; then
  TAG="$(git -C "$ROOT_DIR" describe --tags --exact-match 2>/dev/null || git -C "$ROOT_DIR" rev-parse --short HEAD)"
fi

IMAGE_BASE="$IMAGE_PREFIX"
if [[ -n "$REGISTRY" ]]; then
  IMAGE_BASE="$REGISTRY/$IMAGE_PREFIX"
fi

BACKEND_IMAGE="$IMAGE_BASE-backend:$TAG"
WEB_IMAGE="$IMAGE_BASE-web:$TAG"

# 发布时按变更范围跳过不必要的镜像：前端镜像的 npm ci 是 CD 主耗时（包依赖缓存失效时 2~3 分钟）。
BUILD_BACKEND="${BUILD_BACKEND:-1}"
BUILD_WEB="${BUILD_WEB:-1}"

if [[ "$BUILD_BACKEND" == "1" ]]; then
  log "构建 $BACKEND_IMAGE"
  docker build -f "$ROOT_DIR/docker/backend.Dockerfile" -t "$BACKEND_IMAGE" "$ROOT_DIR"
else
  log "跳过后端镜像构建（BUILD_BACKEND=0）：$BACKEND_IMAGE"
fi

if [[ "$BUILD_WEB" == "1" ]]; then
  log "构建 $WEB_IMAGE"
  docker build -f "$ROOT_DIR/docker/frontend.Dockerfile" -t "$WEB_IMAGE" "$ROOT_DIR"
else
  log "跳过前端镜像构建（BUILD_WEB=0）：$WEB_IMAGE"
fi

if [[ -n "$REGISTRY" ]]; then
  log "推送镜像到 $REGISTRY"
  [[ "$BUILD_BACKEND" == "1" ]] && docker push "$BACKEND_IMAGE"
  [[ "$BUILD_WEB" == "1" ]] && docker push "$WEB_IMAGE"
fi

log "完成：$BACKEND_IMAGE / $WEB_IMAGE"
