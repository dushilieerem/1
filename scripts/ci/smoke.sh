#!/usr/bin/env bash
# 部署后冒烟：前端壳、后端健康、ResearchEngine 连通性。
# 用法：bash scripts/ci/smoke.sh [web_base] [api_base]
# 退出码 0 表示全部通过；任一失败即非 0，供 deploy.sh 触发回滚。
set -Eeuo pipefail

# 默认值是生产端口，与开发环境的 9530/8766 区分；deploy.sh 会显式传入
WEB_BASE="${1:-http://127.0.0.1:9630}"
API_BASE="${2:-http://127.0.0.1:9766}"
RETRIES="${SMOKE_RETRIES:-20}"

log() { printf '[smoke] %s\n' "$*" >&2; }

wait_http() {
  local url="$1" label="$2" code=""
  for _ in $(seq 1 "$RETRIES"); do
    code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "$url" || true)"
    if [[ "$code" == "200" ]]; then
      log "$label 正常（$url）"
      return 0
    fi
    sleep 3
  done
  log "$label 失败：$url 最后一次状态码 $code"
  return 1
}

wait_http "$WEB_BASE/healthz" "前端静态服务"
wait_http "$API_BASE/api/health" "后端 API"

# RE 可能是外部服务，失败不阻断发布，只告警
code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$API_BASE/api/re/health" || true)"
if [[ "$code" == "200" ]]; then
  log "ResearchEngine 网关正常"
else
  log "警告：ResearchEngine 网关返回 $code，请检查 YG_RE_BASE 与 RE 服务"
fi
