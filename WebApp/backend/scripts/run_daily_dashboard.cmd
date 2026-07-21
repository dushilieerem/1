@echo off
REM SVQuant 因子面板日更（可挂 Windows 计划任务）
REM 建议：每个交易日 18:00 后跑
cd /d E:\quant-lab\SVQuant\backend
call C:\Users\Administrator\anaconda3\Scripts\activate.bat NBquant
python -u scripts\daily_dashboard_refresh.py %*
echo exit_code=%ERRORLEVEL%
