@echo off
REM SVQuant 因子面板补算 / 日更（可挂计划任务）
cd /d E:\quant-lab\SV\SVQuant\WebApp\backend
set PYTHONPATH=E:\quant-lab\SV\SVQuant\WebApp\backend
"F:\conda-envs\SVQuant\python.exe" -u scripts\backfill_panel_remaining.py %*
echo exit_code=%ERRORLEVEL%
