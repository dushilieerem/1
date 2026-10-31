#!/usr/bin/env bash
# 前端产物体积门禁（P2-08）。在 frontend/ 目录或任意目录执行均可。
set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)"
DIST_DIR="${DIST_DIR:-$ROOT_DIR/frontend/dist}"
MAX_TOTAL_MB="${MAX_TOTAL_JS_MB:-8}"
MAX_CHUNK_MB="${MAX_CHUNK_MB:-1.5}"

[[ -d "$DIST_DIR/assets" ]] || {
  echo "[frontend-budget] 未找到 $DIST_DIR/assets，请先 vite build" >&2
  exit 1
}

total_bytes="$(find "$DIST_DIR/assets" -name '*.js' -printf '%s\n' | awk '{s+=$1} END{print s+0}')"
max_line="$(find "$DIST_DIR/assets" -name '*.js' -printf '%s %p\n' | awk '{if($1>m){m=$1;n=$2}} END{print (m?m:0) "|" n}')"
max_bytes="${max_line%%|*}"
max_name="${max_line#*|}"
total_mb="$(awk -v b="$total_bytes" 'BEGIN{printf "%.2f", b/1048576}')"
max_mb="$(awk -v b="$max_bytes" 'BEGIN{printf "%.2f", b/1048576}')"

echo "[frontend-budget] JS 总量 ${total_mb}MB（上限 ${MAX_TOTAL_MB}MB）"
echo "[frontend-budget] 最大单文件 ${max_mb}MB ${max_name}（上限 ${MAX_CHUNK_MB}MB）"

awk -v v="$total_mb" -v m="$MAX_TOTAL_MB" 'BEGIN{exit !(v>m)}' && {
  echo "[frontend-budget] 超出 JS 总量预算" >&2
  exit 1
}
awk -v v="$max_mb" -v m="$MAX_CHUNK_MB" 'BEGIN{exit !(v>m)}' && {
  echo "[frontend-budget] 超出单文件预算" >&2
  exit 1
}
echo "[frontend-budget] OK"
