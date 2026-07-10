# 一次性注册 Windows 计划任务：每天定时跑 run_daily.ps1 生成并 push digest。
# 需要以「当前用户」身份运行（不必管理员，除非你想用 -RunAsSystem）。
#
# 用法：
#   powershell -ExecutionPolicy Bypass -File scripts\setup_task.ps1              # 默认每天 07:30
#   powershell -ExecutionPolicy Bypass -File scripts\setup_task.ps1 -Time 08:00
#   powershell -ExecutionPolicy Bypass -File scripts\setup_task.ps1 -Remove      # 删除任务

param(
    [string]$Time = "07:30",
    [string]$TaskName = "social-news-daily",
    [switch]$Remove
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot

if ($Remove) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "已删除计划任务：$TaskName"
    exit 0
}

$RunScript = Join-Path $RepoRoot "scripts\run_daily.ps1"
$Action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$RunScript`"" `
    -WorkingDirectory $RepoRoot
$Trigger = New-ScheduledTaskTrigger -Daily -At $Time
# 错过时间（关机）后开机补跑；任务最长跑 1 小时。
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1) -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger `
    -Settings $Settings -Description "每日生成新闻 digest 并 push（DeepSeek/Claude API）" `
    -Force | Out-Null

Write-Host "✅ 已注册计划任务 '$TaskName'，每天 $Time 运行。"
Write-Host "   先手动验证一次：  powershell -ExecutionPolicy Bypass -File scripts\run_daily.ps1 -NoCommit"
Write-Host "   查看状态：        Get-ScheduledTask -TaskName $TaskName"
Write-Host "   立即触发一次：    Start-ScheduledTask -TaskName $TaskName"
