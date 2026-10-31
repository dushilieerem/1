#!/usr/bin/env bash
set -Eeuo pipefail

# 幂等创建开发库（默认 svquant_dev），与生产库（默认 svquant）隔离。
# 连接信息取自 backend/.env 的 DATABASE_URL；只借用其中的账号/密码/主机，
# 实际连到 postgres 管理库执行 CREATE DATABASE。

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
ROOT_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd -P)"
BACKEND_DIR="$ROOT_DIR/backend"
ENV_FILE="${SVQUANT_ENV_FILE:-$BACKEND_DIR/.env}"
DEV_DB_NAME="${SVQUANT_DEV_DB_NAME:-svquant_dev}"
CONDA_ENV_NAME="${SVQUANT_CONDA_ENV:-svquant}"

usage() {
  cat <<'EOF'
创建 SVQuant 开发库

用法：
  ./scripts/init-dev-db.sh

读取 backend/.env 的 DATABASE_URL 获取账号/密码/主机，在同一个 PostgreSQL
实例中创建 svquant_dev（已存在则跳过）。可用 SVQUANT_DEV_DB_NAME 指定库名，
用 SVQUANT_ENV_FILE 指定其他 .env 路径，用 SVQUANT_CONDA_ENV 指定 Conda 环境。
EOF
}

die() {
  printf '错误：%s\n' "$*" >&2
  exit 1
}

find_conda_hook() {
  local candidate="" conda_base=""

  if [[ -n "${CONDA_PREFIX:-}" && -f "$CONDA_PREFIX/etc/profile.d/conda.sh" ]]; then
    printf '%s\n' "$CONDA_PREFIX/etc/profile.d/conda.sh"
    return 0
  fi

  if [[ -n "${CONDA_EXE:-}" ]]; then
    conda_base="$(cd -- "$(dirname -- "$(dirname -- "$CONDA_EXE")")" && pwd -P 2>/dev/null || true)"
    candidate="$conda_base/etc/profile.d/conda.sh"
    if [[ -f "$candidate" ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  fi

  if command -v conda >/dev/null 2>&1; then
    conda_base="$(conda info --base 2>/dev/null || true)"
    candidate="$conda_base/etc/profile.d/conda.sh"
    if [[ -f "$candidate" ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  fi

  local base
  for base in \
    "${HOME:-}/miniconda3" \
    "${HOME:-}/anaconda3" \
    "${HOME:-}/mambaforge" \
    "${HOME:-}/miniforge3" \
    "/opt/conda" \
    "/home/dev01/program/anaconda3"; do
    candidate="$base/etc/profile.d/conda.sh"
    if [[ -f "$candidate" ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done

  return 1
}

activate_conda_env() {
  if [[ "${CONDA_DEFAULT_ENV:-}" == "$CONDA_ENV_NAME" ]]; then
    return 0
  fi
  local hook
  hook="$(find_conda_hook)" || return 1
  # shellcheck disable=SC1090
  source "$hook"
  conda activate "$CONDA_ENV_NAME"
}

case "${1:-}" in
  "" ) ;;
  -h|--help) usage; exit 0 ;;
  *) usage >&2; die "未知参数：$1" ;;
esac

[[ -f "$ENV_FILE" ]] || die "$ENV_FILE 不存在。先 cp backend/.env.example backend/.env 并填写 DATABASE_URL。"
activate_conda_env || die "无法激活 Conda 环境 '$CONDA_ENV_NAME'。可用 SVQUANT_CONDA_ENV 指定。"

exec python - "$ENV_FILE" "$DEV_DB_NAME" <<'PY'
import sys
from urllib.parse import unquote, urlsplit

import psycopg
from psycopg import sql

env_file, dev_db = sys.argv[1], sys.argv[2]

url = None
for raw in open(env_file, encoding="utf-8"):
    line = raw.strip()
    if line.startswith("DATABASE_URL="):
        url = line.split("=", 1)[1].strip().strip('"').strip("'")
        break
if not url:
    raise SystemExit(f"{env_file} 缺少 DATABASE_URL")

parsed = urlsplit(url)
user = unquote(parsed.username or "")
password = unquote(parsed.password or "")
host = parsed.hostname or None
port = parsed.port or 5432
current_db = (parsed.path or "/").lstrip("/").split("?")[0]
if not user:
    raise SystemExit("DATABASE_URL 里没有用户名，无法确定开发库 owner")

try:
    with psycopg.connect(
        host=host, port=port, user=user, password=password,
        dbname="postgres", autocommit=True, connect_timeout=5,
    ) as conn:
        exists = conn.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (dev_db,)
        ).fetchone()
        if exists:
            print(f"开发库 {dev_db} 已存在，跳过创建。")
        else:
            conn.execute(
                sql.SQL("CREATE DATABASE {} OWNER {} ENCODING 'UTF8' TEMPLATE template0").format(
                    sql.Identifier(dev_db), sql.Identifier(user)
                )
            )
            print(f"已创建开发库 {dev_db}（owner={user}）。")
except psycopg.Error as exc:
    raise SystemExit(f"连接或建库失败：{exc}")

if current_db == dev_db:
    print(f"backend/.env 的 DATABASE_URL 已指向 {dev_db}。")
else:
    print(
        f"注意：backend/.env 当前连的是 {current_db or '(未指定)'}，不是 {dev_db}。\n"
        f"      请把 DATABASE_URL 的库名改成 {dev_db}，开发环境才会使用开发库。",
        file=sys.stderr,
    )
    sys.exit(1)
PY
