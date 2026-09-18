@echo off
REM SVQuant 因子面板日更（可挂 Windows 计划任务）
REM 建议：每个交易日 18:00 后跑；调用前请准备 svquant 环境与 backend/.env
set "BACKEND_DIR=%~dp0.."
cd /d "%BACKEND_DIR%"
set "PYTHONPATH=%BACKEND_DIR%"
call conda activate svquant
python -u scripts\daily_dashboard_refresh.py %*
echo exit_code=%ERRORLEVEL%
