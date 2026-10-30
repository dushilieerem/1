#!/usr/bin/env bash
# Daily EOD refresh (Linux cron). 30 18 * * 1-5
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONIOENCODING=utf-8
python scripts/fetch_live.py --db data/invest.db --codes all
python scripts/fetch_news.py --db data/invest.db --codes all
