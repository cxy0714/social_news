# 每日 digest 计划任务 wrapper。
# 由 setup_task.ps1 注册的两个计划任务调用（每天 06:00 + 开机后 2 分钟）；
# 也可手动 `pwsh scripts/run_daily.ps1`。
# 负责：定位仓库根 → 选 python → 补缺模式跑 generate_digest.py（先补缺的日报，含今天）
#       → 再跑 generate_weekly.py 补缺的周综述 → 写日志。
#
# 补缺（--catch-up）：过去 -Lookback 天里缺的 digest 逐天补齐（关机几天后开机能追上）；
# 周综述同理补已完结但缺的周。两个计划任务都跑这个脚本，幂等——已存在的天/周会跳过。
#
# 用法（手动）:
#   powershell -ExecutionPolicy Bypass -File scripts\run_daily.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\run_daily.ps1 -Lookback 5 -NoCommit

param(
    [int]$Hours = 24,
    [int]$MaxItems = 120,
    [int]$Lookback = 3,
    [switch]$NoCommit
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot   # scripts/ 的上一级
Set-Location $RepoRoot

# 选 python：优先仓库内 .venv，其次 PATH 上的 python。
$Py = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $Py)) { $Py = "python" }

# 日志目录（gitignore）。
$LogDir = Join-Path $RepoRoot "logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$Stamp = Get-Date -Format "yyyy-MM-dd"
$Log = Join-Path $LogDir "digest-$Stamp.log"

# 每日：补缺模式——先补过去 $Lookback 天里缺的日报（含今天），一次提交。
$DArgs = @("scripts/generate_digest.py", "--catch-up", "--lookback", $Lookback,
           "--hours", $Hours, "--max-items", $MaxItems)
if (-not $NoCommit) { $DArgs += "--commit" }

"===== $(Get-Date -Format 'u') 开始补缺/生成每日 digest =====" | Tee-Object -FilePath $Log -Append
& $Py @DArgs 2>&1 | Tee-Object -FilePath $Log -Append
$code = $LASTEXITCODE
"===== 每日 digest 结束，退出码 $code =====" | Tee-Object -FilePath $Log -Append

# 每周：补缺模式——已完结但缺 weekly 的周补齐（周日缺、或关机错过周日都能追上）。
# 日报成功后才跑，确保当周日报已落地再综述。
if ($code -eq 0) {
    $WArgs = @("scripts/generate_weekly.py", "--catch-up")
    if (-not $NoCommit) { $WArgs += "--commit" }
    "===== $(Get-Date -Format 'u') 开始补缺/生成每周综述 =====" | Tee-Object -FilePath $Log -Append
    & $Py @WArgs 2>&1 | Tee-Object -FilePath $Log -Append
    $wcode = $LASTEXITCODE
    "===== 每周综述结束，退出码 $wcode =====" | Tee-Object -FilePath $Log -Append
    if ($code -eq 0) { $code = $wcode }  # 任一失败则整体非 0
} else {
    "⚠ 每日 digest 失败（退出码 $code），跳过每周综述。" | Tee-Object -FilePath $Log -Append
}
exit $code
