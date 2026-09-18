@echo off
REM SVQuant 因子面板补算 / 日更（可挂计划任务）
set "BACKEND_DIR=%~dp0.."
cd /d "%BACKEND_DIR%"
set "PYTHONPATH=%BACKEND_DIR%"
call conda activate svquant
python -u scripts\backfill_panel_remaining.py %*
echo exit_code=%ERRORLEVEL%
