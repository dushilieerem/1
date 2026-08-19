# 安装 / 更新 Windows 计划任务：每天 02:05 同步 RE 因子目录到 PostgreSQL
# 用法（管理员 PowerShell 可选，当前用户任务一般即可）:
#   powershell -ExecutionPolicy Bypass -File E:\quant-lab\SV\SVQuant\WebApp\backend\scripts\install_re_catalog_sync_task.ps1
# 卸载:
#   powershell -ExecutionPolicy Bypass -File ...\install_re_catalog_sync_task.ps1 -Unregister

param(
  [switch]$Unregister
)

$TaskName = "SVQuant-RE-FactorCatalog-Sync"
$Backend = "E:\quant-lab\SV\SVQuant\WebApp\backend"
# 环境已迁到 F 盘；旧 C:\...\anaconda3\envs\SVQuant 不存在会导致 02:05 任务失败(0x80070002)
$Py = "F:\conda-envs\SVQuant\python.exe"
if (-not (Test-Path $Py)) {
  $Py = "C:\Users\Administrator\anaconda3\envs\SVQuant\python.exe"
}
$Script = Join-Path $Backend "scripts\sync_re_factor_catalog.py"
$LogDir = Join-Path $Backend "output"

if ($Unregister) {
  Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
  Write-Host "已卸载计划任务: $TaskName"
  exit 0
}

if (-not (Test-Path $Py)) { throw "找不到 Python: $Py" }
if (-not (Test-Path $Script)) { throw "找不到脚本: $Script" }
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

# --all：同步 RE 全部因子库（对齐同事侧 800+）；默认 primary 只有约 700+
$arg = "-u `"$Script`" --all"
$action = New-ScheduledTaskAction -Execute $Py -Argument $arg -WorkingDirectory $Backend
# 每天 02:05
$trigger = New-ScheduledTaskTrigger -Daily -At 2:05am
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null
Write-Host "已注册计划任务: $TaskName"
Write-Host "  时间: 每天 02:05"
Write-Host "  命令: $Py $Script --all"
Write-Host "  日志: $LogDir\re_factor_catalog_sync.log"
Write-Host "手动立即跑: Start-ScheduledTask -TaskName '$TaskName'"
