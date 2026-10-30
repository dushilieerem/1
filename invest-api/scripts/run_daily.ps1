# Daily EOD refresh (Windows Task Scheduler). 18:30 on weekdays.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$env:PYTHONIOENCODING = "utf-8"
conda run -n svquant python scripts/fetch_live.py --db data/invest.db --codes all
conda run -n svquant python scripts/fetch_news.py --db data/invest.db --codes all
