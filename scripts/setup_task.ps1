# 一次性注册 Windows 计划任务：每天定时跑 run_daily.ps1 生成并 push digest。
# 需要以「当前用户」身份运行（不必管理员，除非你想用 -RunAsSystem）。
#
# 用法：
#   powershell -ExecutionPolicy Bypass -File scripts\setup_task.ps1              # 默认每天 07:30
#   powershell -ExecutionPolicy Bypass -File scripts\setup_task.ps1 -Time 08:00
#   powershell -ExecutionPolicy Bypass -File scripts\setup_task.ps1 -Remove      # 删除任务

param(
    [string]$Time = "06:00",
    [int]$BootDelayMin = 2,
    [string]$TaskName = "social-news-daily",
    [string]$BootTaskName = "social-news-boot",
    [switch]$Remove
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot

if ($Remove) {
    foreach ($t in @($TaskName, $BootTaskName)) {
        Unregister-ScheduledTask -TaskName $t -Confirm:$false -ErrorAction SilentlyContinue
        Write-Host "已删除计划任务：$t"
    }
    exit 0
}

$RunScript = Join-Path $RepoRoot "scripts\run_daily.ps1"
$Action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$RunScript`"" `
    -WorkingDirectory $RepoRoot
# 错过时间（关机）后开机补跑；补缺+周综述可能两段，任务最长跑 2 小时。
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2) -MultipleInstances IgnoreNew

# 任务一：每天定点跑（补缺过去几天缺的日报 + 缺的周综述）。
$DailyTrigger = New-ScheduledTaskTrigger -Daily -At $Time
Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $DailyTrigger `
    -Settings $Settings -Description "每天 $Time 补缺/生成新闻 digest 并 push；缺的周综述一并补（DeepSeek/Claude API）" `
    -Force | Out-Null

# 任务二：登录后（≈开机）延迟 $BootDelayMin 分钟跑一次，补最近缺的新闻。
# 用 AtLogOn 而非 AtStartup：登录时才在当前用户会话里、带 git 凭据与网络就绪。
$BootTrigger = New-ScheduledTaskTrigger -AtLogOn
$BootTrigger.Delay = "PT${BootDelayMin}M"   # ISO8601 时长
Register-ScheduledTask -TaskName $BootTaskName -Action $Action -Trigger $BootTrigger `
    -Settings $Settings -Description "登录后 $BootDelayMin 分钟补最近缺的新闻 digest（关机几天后开机追上）" `
    -Force | Out-Null

Write-Host "✅ 已注册两个计划任务："
Write-Host "   · $TaskName —— 每天 $Time 运行（补缺+周综述）"
Write-Host "   · $BootTaskName —— 登录后 $BootDelayMin 分钟运行（开机补最近缺的）"
Write-Host "   先手动验证一次：  powershell -ExecutionPolicy Bypass -File scripts\run_daily.ps1 -NoCommit"
Write-Host "   查看状态：        Get-ScheduledTask -TaskName $TaskName, $BootTaskName"
Write-Host "   立即触发一次：    Start-ScheduledTask -TaskName $TaskName"
