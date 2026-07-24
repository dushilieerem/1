@echo off
REM SVQuant 因子面板补算 / 日更（可挂计划任务）
cd /d E:\quant-lab\SV\SVQuant\WebApp\backend
call C:\Users\Administrator\anaconda3\Scripts\activate.bat SVQuant
python -u scripts\backfill_panel_remaining.py %*
echo exit_code=%ERRORLEVEL%
