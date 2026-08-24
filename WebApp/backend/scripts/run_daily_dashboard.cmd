@echo off
REM SVQuant 因子面板日更（可挂 Windows 计划任务）
REM 建议：每个交易日 18:00 后跑
cd /d E:\quant-lab\SV\SVQuant\WebApp\backend
set PYTHONPATH=E:\quant-lab\SV\SVQuant\WebApp\backend
"F:\conda-envs\SVQuant\python.exe" -u scripts\daily_dashboard_refresh.py %*
echo exit_code=%ERRORLEVEL%
